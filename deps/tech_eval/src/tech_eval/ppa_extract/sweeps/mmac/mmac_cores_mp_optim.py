import json
import os
from dataclasses import dataclass
from itertools import product
from typing import ClassVar, Dict, List, Optional

from spirehdl.spirehdl import reset_shared_cache

from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    PPAOption,
    PPGOption,
    MultiplierOption,
    TwoInputAritEncodings,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import (
    Encoding,
)
from spirehdl.cores.matmul_accumulate.matmul_accumulate_core import (
    AdderConfig as MMAcAdderConfig,
    MMAcCfg,
    MMAcDims,
    MMAcWidths,
    MultiplierConfig as MMAcMultiplierConfig,
    MatmulAccumulateComponent as MatmulAccumulateComponentBase,
    max_y_width_unsigned,
)
from spirehdl.cores.matmul_accumulate.matmul_accumulate_core_fused import (
    MMAcFusedCfg,
    MultiplierConfig as MMAcFusedMultiplierConfig,
    MatmulAccumulateComponent as MatmulAccumulateComponentFused,
)
from spirehdl.cores.matmul_accumulate.matmul_accumulate_core_sign_magnitude import (
    AdderConfig as MMAcEncodedAdderConfig,
    MMAcEncodedCfg,
    MultiplierConfig as MMAcEncodedMultiplierConfig,
    SignMagnitudeEncoderConfig,
    MatmulAccumulateComponent as MatmulAccumulateComponentEncoded,
)

from tech_eval.ppa_extract.sweeps.plotting2 import plot_delay_vs_area, plot_power_vs_area, plot_power_vs_delay, plot_switch_count_vs_area, plot_switch_count_vs_delay, plot_transistor_count_vs_area
from tech_eval.ppa_extract.core.ppa_configs import InstanceConfig, JsonExportConfig
from tech_eval.ppa_extract.core.ppa_extraction import PPA_REPORT_TIME_UNIT, get_target_delay
from tech_eval.ppa_extract.tests.mmac_core_test import _build_vectors_encoding
from tech_eval.ppa_extract.core.ppa_extraction_specific import run_configs

from tech_eval.ppa_extract.core.template import (lib_time_unit, technology)



@dataclass(frozen=True)
class MMAcCoreConfig(JsonExportConfig):
    json_export_fields: ClassVar[Dict[str, str]] = {
        "cfg.mult_cfg.multiplier_opt": "multiplier_opt_name",
        "cfg.mult_cfg.ppg_opt": "ppg_cls_name",
        "cfg.mult_cfg.ppa_opt": "ppa_cls_name",
        "cfg.mult_cfg.fsa_opt": "mult_fsa_cls_name",
        "cfg.add_cfg.fsa_opt": "fsa_cls_name",
        "cfg.mult_cfg.optim_type": "mult_optim_type",
        "cfg.add_cfg.optim_type": "add_optim_type",
    }

    cfg: object


@dataclass(frozen=True)
class MMAcFusedCoreConfig(JsonExportConfig):
    json_export_fields: ClassVar[Dict[str, str]] = {
        "cfg.mult_cfg.ppg_opt": "ppg_cls_name",
        "cfg.mult_cfg.ppa_opt": "ppa_cls_name",
        "cfg.mult_cfg.fsa_opt": "fsa_cls_name",
        "cfg.mult_cfg.optim_type": "mult_optim_type",
    }

    cfg: MMAcFusedCfg


from tech_eval.ppa_extract.sweeps.sweep_utils import (
    prepare_out_dir,
    serialize_case_results,
    case_key as _case_key,
    report_sweep_counts,
)

# ---------------------------------------------------
# -- Matmul-Accumulate Core
# ---------------------------------------------------

def run_ppa_mmac_core():
    dim_m = 4
    dim_n = 4
    dim_k = 4
    a_width = 4
    b_width = 4
    c_width = max_y_width_unsigned(a_width, b_width, dim_k, include_carry_from_add=False)

    sigma = 3.0 * 2**a_width / 2**4
       
    single_point = False  # for quicker testing
    
    target_delays = [700, 900, 1100, 1400] if a_width <= 4 else [1050, 1400, 2000, 3200] #get_target_delay(c_width) # for faster testing
    if single_point:
        target_delays = [700] # for quicker testing
    
    num_vectors = 100
    
    n_processes = 80
    keep_files = False
    
    #base_encodings = [Encoding.unsigned, Encoding.twos_complement]
    base_encodings = [Encoding.twos_complement] # for quicker testing
    #fused_encodings = [Encoding.unsigned, Encoding.twos_complement]
    fused_encodings = [Encoding.twos_complement]  # for quicker testing
    #sign_encodings = [Encoding.twos_complement, Encoding.twos_complement_symmetric]
    sign_encodings = [Encoding.twos_complement_symmetric]  # for quicker testing
    sign_encodings2 = [Encoding.twos_complement]
    sign_encodings_list = [sign_encodings] #+ [sign_encodings2]

    ppa_opts = [PPAOption.CARRY_SAVE_TREE, PPAOption.ACCUMULATOR_TREE, PPAOption.DADDA_TREE, PPAOption.WALLACE_TREE]
    fsa_opts = [FSAOption.PREFIX_SKLANSKY, FSAOption.PREFIX_KOGGE_STONE, FSAOption.RIPPLE_CARRY, FSAOption.PREFIX_KOGGE_STONE]
    if single_point:
        ppa_opts = [PPAOption.WALLACE_TREE] # for quicker testing
        fsa_opts = [FSAOption.RIPPLE_CARRY]  # for quicker testing
        
    ppa_opts_none = [PPAOption.NONE]
    fsa_opts_none = [FSAOption.NONE]
        
    #same fss for add an mul
    
    optim_types = ["area", "speed"]
    if single_point:
        optim_types = ["area"]  # for quicker testing

    def base_ppg_opts(encoding: Encoding):
        if encoding == Encoding.twos_complement:
            #return [PPGOption.BAUGH_WOOLEY, PPGOption.BOOTH_OPTIMISED]
            return [PPGOption.BAUGH_WOOLEY]  # for quicker testing
        #return [PPGOption.AND, PPGOption.BOOTH_OPTIMISED]
        return [PPGOption.AND]  # for quicker testing

    def fused_ppg_opts(encoding: Encoding):
        if encoding == Encoding.twos_complement:
            return [PPGOption.BAUGH_WOOLEY]
        return [PPGOption.AND]

    def get_core_cfg(
        encoding: Encoding,
        ppg_opt_mult: PPGOption,
        ppa_opt_mult: PPAOption,
        fsa_opt_mult: FSAOption,
        fsa_opt_add: FSAOption,
        optim_type: str,
    ) -> MMAcCfg:

        mult_cfg = MMAcMultiplierConfig(
            use_operator=False,
            multiplier_opt=MultiplierOption.OPTIMIZED_MULTIPLIER,
            encodings=TwoInputAritEncodings.with_enc(encoding),
            ppg_opt=ppg_opt_mult,
            ppa_opt=ppa_opt_mult,
            fsa_opt=fsa_opt_mult,
            optim_type=optim_type,
        )
        add_cfg = MMAcAdderConfig(
            use_operator=False,
            encoding=encoding,
            optim_type=optim_type,
            fsa_opt=fsa_opt_add,
            full_output_bit=True,
        )

        core_cfg = MMAcCfg(
            dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
            widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
            mult_cfg=mult_cfg,
            add_cfg=add_cfg,
        )
        return core_cfg

    def get_fused_core_cfg(
        encoding: Encoding,
        ppg_opt_mult: PPGOption,
        ppa_opt_mult: PPAOption,
        fsa_opt_mult: FSAOption,
        optim_type: str,
    ) -> MMAcFusedCfg:
        mult_cfg = MMAcFusedMultiplierConfig(
            ppg_opt=ppg_opt_mult,
            ppa_opt=ppa_opt_mult,
            fsa_opt=fsa_opt_mult,
            optim_type=optim_type,
        )
        fused_fields = getattr(MMAcFusedCfg, "__dataclass_fields__", None)
        if fused_fields and "encoding" in fused_fields:
            return MMAcFusedCfg(
                dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
                widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
                mult_cfg=mult_cfg,
                encoding=encoding,
            )
        return MMAcFusedCfg(
            dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
            widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
            mult_cfg=mult_cfg,
        )

    def get_sign_mag_core_cfg(
        encoding: Encoding,
        ppg_opt_mult: PPGOption,
        ppa_opt_mult: PPAOption,
        fsa_opt_mult: FSAOption,
        fsa_opt_add: FSAOption,
        optim_type: str,
    ) -> MMAcEncodedCfg:
        sign_encodings = TwoInputAritEncodings.with_enc(
            Encoding.sign_magnitude if encoding == Encoding.twos_complement_symmetric else Encoding.sign_magnitude_ext
        )
        
        if encoding == Encoding.twos_complement:
            raise(ValueError("no optimized sign-magnitude extended available"))
        
        mult_cfg = MMAcEncodedMultiplierConfig(
            use_operator=False,
            multiplier_opt=(
                MultiplierOption.OPTIMIZED_SIGN_MAGNITUDE_MULTIPLIER if encoding == Encoding.twos_complement_symmetric
                else MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_MULTIPLIER
            ),
            encodings=sign_encodings,
            ppg_opt=ppg_opt_mult,
            ppa_opt=ppa_opt_mult,
            fsa_opt=fsa_opt_mult,
            optim_type=optim_type,
        )
        add_cfg = MMAcEncodedAdderConfig(
            use_operator=False,
            encoding=encoding,
            optim_type=optim_type,
            fsa_opt=fsa_opt_add,
            full_output_bit=True,
        )
        encoding_cfg = SignMagnitudeEncoderConfig(
            encoder_clip_most_negative=False,
            decoder_clip_most_negative=False,
        )
        return MMAcEncodedCfg(
            dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
            widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
            mult_cfg=mult_cfg,
            add_cfg=add_cfg,
            encoding_cfg=encoding_cfg,
        )
        
    def get_sign_encoding(encoding: Encoding) -> TwoInputAritEncodings:
        return Encoding.sign_magnitude if encoding == Encoding.twos_complement_symmetric else Encoding.sign_magnitude_ext
        
    def get_sign_mag_core_no_enc_cfg(
        encoding: Encoding,
        ppg_opt_mult: PPGOption,
        ppa_opt_mult: PPAOption,
        fsa_opt_mult: FSAOption,
        fsa_opt_add: FSAOption,
        optim_type: str,
    ) -> MMAcEncodedCfg:
        
        if encoding == Encoding.twos_complement:
            raise(ValueError("no optimized sign-magnitude extended available"))
        
        sign_encodings = TwoInputAritEncodings.with_enc(get_sign_encoding(encoding))
        mult_cfg = MMAcEncodedMultiplierConfig(
            use_operator=False,
            multiplier_opt=(
                MultiplierOption.OPTIMIZED_SIGN_MAGNITUDE_MULTIPLIER if encoding == Encoding.twos_complement_symmetric
                else MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_MULTIPLIER
            ),
            encodings=sign_encodings,
            ppg_opt=ppg_opt_mult,
            ppa_opt=ppa_opt_mult,
            fsa_opt=fsa_opt_mult,
            optim_type=optim_type,
        )
        add_cfg = MMAcEncodedAdderConfig(
            use_operator=False,
            encoding=encoding,
            optim_type=optim_type,
            fsa_opt=fsa_opt_add,
            full_output_bit=True,
        )
        encoding_cfg = SignMagnitudeEncoderConfig(
            encoder_clip_most_negative=False,
            decoder_clip_most_negative=False,
            encoder_cls=None,
        )
        return MMAcEncodedCfg(
            dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
            widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
            mult_cfg=mult_cfg,
            add_cfg=add_cfg,
            encoding_cfg=encoding_cfg,
        )

    out_dir = prepare_out_dir()

    def run_case(case_key: str, configs: List[InstanceConfig], encoding: Encoding, worker_base_path: str, encoding_inputs: Optional[Encoding] = None) -> List[dict]:
        if not configs:
            print(f"No {case_key} MMAC core configs generated.")
            return []
        core_for_vectors = configs[0].gen_instance()
        vectors = _build_vectors_encoding(core_for_vectors, encoding=encoding, num_vectors=num_vectors, sigma=sigma, encoding_ab_inputs=encoding_inputs)
        reset_shared_cache()
        results = run_configs(
            configs=configs,
            target_delays=target_delays,
            worker_base_path=worker_base_path,
            keep_files=keep_files,
            processes=n_processes,
            vectors=vectors,
        )
        if not results:
            print(f"No {case_key} MMAC core results generated.")
        return results

    case_results = {}
    all_results = []
    total_configs = 0
    
    # ---------------------------------------------------
    # -- Run base case
    # ---------------------------------------------------
    case_base_key = "core"
    reset_shared_cache()
    for encoding in base_encodings:
        base_configs = [
            InstanceConfig(
                impl_cls=MatmulAccumulateComponentBase,
                config=MMAcCoreConfig(
                    cfg=get_core_cfg(encoding, ppg_opt_mult, ppa_opt_mult, fsa_opt, fsa_opt, optim_type),
                ),
            )
            for ppg_opt_mult, ppa_opt_mult, fsa_opt, optim_type in product(
                base_ppg_opts(encoding),
                ppa_opts_none,
                fsa_opts,
                optim_types,
            )
        ]
        total_configs += len(base_configs)
        case_key = _case_key(case_base_key, encoding)
        results = run_case(
            case_key,
            base_configs,
            encoding,
            f"worker_mmac_{case_base_key}_{encoding.value}",
        )
        case_results[case_key] = results
        all_results.extend(results)

    # ---------------------------------------------------
    # -- Run baseline case (Verilog * and + operators)
    # ---------------------------------------------------
    case_base_key = "baseline"
    reset_shared_cache()
    for encoding in base_encodings:
        baseline_configs = [
            InstanceConfig(
                impl_cls=MatmulAccumulateComponentBase,
                config=MMAcCoreConfig(
                    cfg=MMAcCfg(
                        dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
                        widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
                        mult_cfg=MMAcMultiplierConfig(use_operator=True, optim_type=optim_type),
                        add_cfg=MMAcAdderConfig(use_operator=True, encoding=encoding, optim_type=optim_type),
                    ),
                ),
            )
            for optim_type in optim_types
        ]
        total_configs += len(baseline_configs)
        case_key = _case_key(case_base_key, encoding)
        results = run_case(
            case_key,
            baseline_configs,
            encoding,
            f"worker_mmac_{case_base_key}_{encoding.value}",
        )
        case_results[case_key] = results
        all_results.extend(results)

    # ---------------------------------------------------
    # -- Run fused cases
    # ---------------------------------------------------
    case_base_key = "fused"
    reset_shared_cache()
    for encoding in fused_encodings:
        fused_configs = [
            InstanceConfig(
                impl_cls=MatmulAccumulateComponentFused,
                config=MMAcFusedCoreConfig(
                    cfg=get_fused_core_cfg(encoding, ppg_opt_mult, ppa_opt_mult, fsa_opt, optim_type),
                ),
            )
            for ppg_opt_mult, ppa_opt_mult, fsa_opt, optim_type in product(
                fused_ppg_opts(encoding),
                ppa_opts,
                fsa_opts,
                optim_types,
            )
        ]
        total_configs += len(fused_configs)
        case_key = _case_key(case_base_key, encoding)
        results = run_case(
            case_key,
            fused_configs,
            encoding,
            f"worker_mmac_core_{case_base_key}_{encoding.value}",
        )
        case_results[case_key] = results
        all_results.extend(results)

    # ---------------------------------------------------
    # -- Run sign-magnitude cases
    # ---------------------------------------------------
    for (no_encoding, case_base_key), sign_encodings_picked in product([(False, "encoded"), (True, "encoded_wo_enc")], sign_encodings_list):
        reset_shared_cache()
        sign_ppg_opts = [PPGOption.AND]
        ppg_opts_none = [PPGOption.NONE]
        for encoding in sign_encodings_picked:
            sign_configs = [
                InstanceConfig(
                    impl_cls=MatmulAccumulateComponentEncoded,
                    config=MMAcCoreConfig(
                        cfg=get_sign_mag_core_cfg(encoding, ppg_opt_mult, ppa_opt_mult, fsa_opts_none[0], fsa_opt, optim_type) if not no_encoding \
                                else get_sign_mag_core_no_enc_cfg(encoding, ppg_opt_mult, ppa_opt_mult, fsa_opts_none[0], fsa_opt, optim_type),
                    ),
                )
                for ppg_opt_mult, ppa_opt_mult, fsa_opt, optim_type in product(
                    ppg_opts_none,
                    ppa_opts_none,
                    fsa_opts,
                    optim_types,
                )
            ]
            total_configs += len(sign_configs)
            case_key = _case_key(case_base_key, encoding)
            results = run_case(
                case_key,
                sign_configs,
                encoding,
                f"worker_mmac_core_{case_base_key}_{encoding.value}",
                encoding_inputs=get_sign_encoding(encoding) if no_encoding else None,
            )
            case_results[case_key] = results
            all_results.extend(results)
        
    # ---------------------------------------------------
    # -- Save and plot results
    # ---------------------------------------------------

    if not all_results:
        print("No MMAC core results generated.")
        return

    results_path = os.path.join(out_dir, f"MMAC_m{dim_m}_a{a_width}_results.json")
    results_payload = {
        "meta": {
            "dim_m": dim_m,
            "dim_n": dim_n,
            "dim_k": dim_k,
            "a_width": a_width,
            "b_width": b_width,
            "c_width": c_width,
            "design_prefix": "MMAC",
            "title_label": "MMAC Core",
            "case_key_format": "case_label_encoding",
            "suffix": "by_case",
            "target_delays": list(target_delays),
            "sigma": sigma,
            "vector_count": num_vectors,
            "lib_time_unit": lib_time_unit,
            "ppa_report_time_unit": PPA_REPORT_TIME_UNIT,
            "technology": technology,
        },
        "case_results": serialize_case_results(case_results),
    }
    with open(results_path, "w") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Saved MMAC core results to {results_path}")
   
    plot_kwargs = dict(
        results_payload=results_payload,
        groups=case_results,
        out_dir=out_dir,
        suffix="by_case",
        design_prefix="MMAC",
        title_label="MMAC Core",
        add_legend=True,
    )
    for plotter in (
        plot_delay_vs_area,
        plot_power_vs_area,
        plot_switch_count_vs_area,
        plot_transistor_count_vs_area,
        plot_power_vs_delay,
        plot_switch_count_vs_delay,
    ):
        plotter(**plot_kwargs)

    report_sweep_counts(all_results, target_delays, total_configs)

if __name__ == "__main__":
    run_ppa_mmac_core()

"""
Standalone adder and multiplier PPA sweep.

Runs a comprehensive sweep over adder and multiplier configurations,
collecting PPA (Power, Performance, Area) metrics across multiple
target delays, modelled after mmac_cores_mp.py in the restored/
directory. Results are saved to JSON and plotted using the existing
plotting2 module from the mmac sweeps.
"""
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
    PrefixAdderFinalStage,
    TwoInputAritEncodings,
    encoding_for_multiplier,
    get_list_from_enum,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import (
    AdderTestVectors,
    Encoding,
    MultiplierTestVectors,
)
from spirehdl.arithmetic.prefix_adders.adders import StageBasedPrefixAdder

from tech_eval.ppa_extract.core.ppa_extraction import PPA_REPORT_TIME_UNIT
from tech_eval.ppa_extract.sweeps.plotting2 import plot_delay_vs_area, plot_power_vs_area, plot_power_vs_delay, plot_switch_count_vs_area, plot_switch_count_vs_delay, plot_transistor_count_vs_area, regroup_by_fsa, regroup_by_ppa, regroup_by_target_delay
from tech_eval.ppa_extract.core.ppa_configs import InstanceConfig, JsonExportConfig
from tech_eval.ppa_extract.core.ppa_extraction_specific import run_configs
from tech_eval.ppa_extract.core.template import get_tech_config

SAVE_VCD_FOR_POWER = False # to make it faster



# ---------------------------------------------------------------------------
# -- Config dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MultiplierCfg(JsonExportConfig):
    """Flat config for a standalone multiplier; fields match constructor kwargs."""
    json_export_fields: ClassVar[Dict[str, str]] = {
        "ppg_cls": "ppg_cls_name",
        "ppa_cls": "ppa_cls_name",
        "fsa_cls": "fsa_cls_name",
        "optim_type": "optim_type",
    }

    a_w: int
    b_w: int
    a_encoding: object
    b_encoding: object
    optim_type: str
    ppg_cls: Optional[type] = None
    ppa_cls: Optional[type] = None
    fsa_cls: Optional[type] = None


@dataclass(frozen=True)
class AdderCfg(JsonExportConfig):
    """Flat config for a standalone adder; fields match StageBasedPrefixAdder kwargs."""
    json_export_fields: ClassVar[Dict[str, str]] = {
        "fsa_cls": "fsa_cls_name",
        "optim_type": "optim_type",
    }

    a_w: int
    b_w: int
    signed_a: bool
    signed_b: bool
    optim_type: str
    fsa_cls: type
    full_output_bit: bool


from tech_eval.ppa_extract.sweeps.sweep_utils import (
    prepare_out_dir,
    serialize_case_results,
)


def _run_and_collect(
    case_key: str,
    configs: List[InstanceConfig],
    vectors: List,
    worker_base_path: str,
    target_delays: List[int],
    n_processes: int,
    keep_files: bool,
    technology: str = "asap7",
) -> List[dict]:
    if not configs:
        print(f"No {case_key} configs generated.")
        return []
    reset_shared_cache()
    results = run_configs(
        configs=configs,
        target_delays=target_delays,
        worker_base_path=worker_base_path,
        keep_files=keep_files,
        processes=n_processes,
        vectors=vectors,
        save_vcd=SAVE_VCD_FOR_POWER,  # set to True to use VCD for power estimation, False to skip VCD generation and use a placeholder value
        technology=technology,
    )
    if not results:
        print(f"No {case_key} results generated.")
    return results


_PLOTTERS = (
    plot_delay_vs_area,
    plot_power_vs_area,
    plot_switch_count_vs_area,
    plot_transistor_count_vs_area,
    plot_power_vs_delay,
    plot_switch_count_vs_delay,
)


def _run_all_plotters(results_payload, case_results, out_dir, design_prefix, title_label):
    base_kwargs = dict(
        results_payload=results_payload,
        out_dir=out_dir,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=True,
    )

    # Primary grouping: by case (e.g. multiplier type / encoding)
    for plotter in _PLOTTERS:
        plotter(**base_kwargs, groups=case_results, suffix="by_case")

    # Additional groupings: by target delay, PPA tree, FSA adder
    extra_groups = [
        ("by_td",  regroup_by_target_delay(case_results)),
        ("by_ppa", regroup_by_ppa(case_results)),
        ("by_fsa", regroup_by_fsa(case_results)),
    ]
    for group_suffix, grouped in extra_groups:
        if not grouped:
            continue
        for plotter in _PLOTTERS:
            plotter(**base_kwargs, groups=grouped, suffix=group_suffix)


# ---------------------------------------------------------------------------
# -- Multiplier sweep
# ---------------------------------------------------------------------------

def run_ppa_multiplier_sweep():
    technology = "asap7"
    lib_time_unit = get_tech_config(technology).lib_time_unit

    n_bits = 8
    sigma = 3.0 * 2**n_bits / 2**4  # = 3.0 for 4-bit

    single_point = False  # set True for quick smoke-test

    if n_bits == 16:
        target_delays = [700, 900, 1100, 1400]
    elif n_bits == 8:
        target_delays = [200, 400, 600, 800]
    elif n_bits == 4:
        target_delays = [100, 250, 400, 600]
    if single_point:
        target_delays = [700]

    num_vectors = 100
    n_processes = 80
    keep_files = False

    ppa_opts = [
        PPAOption.CARRY_SAVE_TREE,
        PPAOption.ACCUMULATOR_TREE,
        PPAOption.DADDA_TREE,
        PPAOption.WALLACE_TREE,
        #PPAOption.EAGER_WALLACE_TREE,
        PPAOption.BDT_WALLACE_TREE,
        PPAOption.FOUR_TWO_COMPRESSOR,
        #PPAOption.FOUR_TWO_COMPRESSOR_PARALLEL
    ]
    fsa_opts = [
        FSAOption.PREFIX_SKLANSKY,
        FSAOption.PREFIX_KOGGE_STONE,
        FSAOption.RIPPLE_CARRY,
        FSAOption.PREFIX_BRENT_KUNG,
        FSAOption.PREFIX_SPARSE_KOGGE_STONE_2,
        FSAOption.PREFIX_SPARSE_KOGGE_STONE_4,
        FSAOption.NAIVE_RIPPLE_CARRY,
    ]
    if single_point:
        ppa_opts = [PPAOption.WALLACE_TREE]
        fsa_opts = [FSAOption.RIPPLE_CARRY]

    optim_types = ["area", "speed"]
    if single_point:
        optim_types = ["area"]

    out_dir = prepare_out_dir()
    case_results = {}
    all_results = []
    total_configs = 0

    # ---------------------------------------------------
    # -- Standard (stage-based) multiplier: twos complement
    # ---------------------------------------------------
    reset_shared_cache()
    for encoding in [Encoding.twos_complement, Encoding.unsigned]:
        encodings_obj = TwoInputAritEncodings.with_enc(encoding)
        ppg_opts = [PPGOption.BAUGH_WOOLEY, PPGOption.BOOTH_OPTIMISED] if encoding == Encoding.twos_complement else [PPGOption.AND, PPGOption.BOOTH_OPTIMISED, PPGOption.BOOTH_UNOPTIMISED]
        configs = [
            InstanceConfig(
                impl_cls=MultiplierOption.STAGE_BASED_MULTIPLIER.value,
                config=MultiplierCfg(
                    a_w=n_bits,
                    b_w=n_bits,
                    a_encoding=encodings_obj.a,
                    b_encoding=encodings_obj.b,
                    optim_type=optim_type,
                    ppg_cls=ppg_opt.value,
                    ppa_cls=ppa_opt.value,
                    fsa_cls=fsa_opt.value,
                ),
            )
            for ppg_opt, ppa_opt, fsa_opt, optim_type in product(
                ppg_opts, ppa_opts, fsa_opts, optim_types
            )
        ]
        # Baseline: Verilog * operator (no structural decomposition)
        for optim_type in optim_types:
            configs.append(InstanceConfig(
                impl_cls=MultiplierOption.STAR_MULTIPLIER.value,
                config=MultiplierCfg(
                    a_w=n_bits,
                    b_w=n_bits,
                    a_encoding=encodings_obj.a,
                    b_encoding=encodings_obj.b,
                    optim_type=optim_type,
                ),
            ))
        total_configs += len(configs)
        case_key = f"mul_tc_{encoding.value}"
        first_inst = configs[0].gen_instance()
        vectors = MultiplierTestVectors(
            a_w=n_bits,
            b_w=n_bits,
            y_w=first_inst.io.y.typ.width,
            num_vectors=num_vectors,
            tb_sigma=sigma,
            a_encoding=encodings_obj.a,
            b_encoding=encodings_obj.b,
            y_encoding=encodings_obj.y,
        ).generate()
        results = _run_and_collect(
            case_key, configs, vectors,
            f"worker_mul_tc_{encoding.value}",
            target_delays, n_processes, keep_files,
            technology=technology,
        )
        case_results[case_key] = results
        all_results.extend(results)

    # # ---------------------------------------------------
    # # -- Sign-magnitude multiplier variants
    # # ---------------------------------------------------
    # sign_mag_opts = [
    #     MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_MULTIPLIER,
    #     MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_MULTIPLIER,
    #     MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_TO_TWOS_COMPLEMENT_MULTIPLIER,
    #     MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_TO_TWOS_COMPLEMENT_MULTIPLIER,
    # ]
    # for mul_opt in sign_mag_opts:
    #     reset_shared_cache()
    #     encodings_list = encoding_for_multiplier(mul_opt.value)
    #     encodings_obj = encodings_list[-1]  # use last (preferred) encoding
    #     ppg_opts = [PPGOption.AND]
    #     configs = [
    #         InstanceConfig(
    #             impl_cls=mul_opt.value,
    #             config=MultiplierCfg(
    #                 a_w=n_bits,
    #                 b_w=n_bits,
    #                 a_encoding=encodings_obj.a,
    #                 b_encoding=encodings_obj.b,
    #                 optim_type=optim_type,
    #                 ppg_cls=ppg_opt.value,
    #                 ppa_cls=ppa_opt.value,
    #                 fsa_cls=fsa_opt.value,
    #             ),
    #         )
    #         for ppg_opt, ppa_opt, fsa_opt, optim_type in product(
    #             ppg_opts, ppa_opts, fsa_opts, optim_types
    #         )
    #     ]
    #     total_configs += len(configs)
    #     case_key = f"mul_{mul_opt.name.lower()}"
    #     first_inst = configs[0].gen_instance()
    #     vectors = MultiplierTestVectors(
    #         a_w=n_bits,
    #         b_w=n_bits,
    #         y_w=first_inst.io.y.typ.width,
    #         num_vectors=num_vectors,
    #         tb_sigma=sigma,
    #         a_encoding=encodings_obj.a,
    #         b_encoding=encodings_obj.b,
    #         y_encoding=encodings_obj.y,
    #     ).generate()
    #     results = _run_and_collect(
    #         case_key, configs, vectors,
    #         f"worker_{case_key}",
    #         target_delays, n_processes, keep_files,
    #     )
    #     case_results[case_key] = results
    #     all_results.extend(results)

    # ---------------------------------------------------
    # -- Save and plot
    # ---------------------------------------------------
    if not all_results:
        print("No multiplier results generated.")
        return

    results_payload = {
        "meta": {
            "dim_m": 1,
            "dim_n": 1,
            "dim_k": 1,
            "a_width": n_bits,
            "b_width": n_bits,
            "c_width": 2 * n_bits,
            "design_prefix": "Mul",
            "title_label": "Multiplier",
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

    results_path = os.path.join(out_dir, f"Mul_a{n_bits}_results.json")
    with open(results_path, "w") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Saved multiplier results to {results_path}")

    _run_all_plotters(results_payload, case_results, out_dir, "Mul", "Multiplier")

    print(
        f"Multiplier sweep: {total_configs} configs x {len(target_delays)} delays = "
        f"{total_configs * len(target_delays)} runs, got {len(all_results)} results"
    )


# ---------------------------------------------------------------------------
# -- Adder sweep
# ---------------------------------------------------------------------------

def run_ppa_adder_sweep():
    technology = "asap7"
    lib_time_unit = get_tech_config(technology).lib_time_unit

    n_bits = 16
    sigma = 3.0 * 2**n_bits / 2**4  # = 3.0 for 4-bit

    single_point = False  # set True for quick smoke-test

    target_delays = [200, 400, 600, 800]
    if single_point:
        target_delays = [200]
    #target_delays = [500]


    num_vectors = 100
    n_processes = 80
    keep_files = False

    # fsa_opts = [
    #     FSAOption.PREFIX_SKLANSKY,
    #     FSAOption.PREFIX_KOGGE_STONE,
    #     FSAOption.RIPPLE_CARRY,
    # ]
    
    fsa_opts = [
         FSAOption.PREFIX_SKLANSKY,
         FSAOption.PREFIX_KOGGE_STONE,
         FSAOption.RIPPLE_CARRY,
         FSAOption.PREFIX_BRENT_KUNG,
         FSAOption.PREFIX_RCA,
         FSAOption.PREFIX_LADNER_FISCHER,
         FSAOption.PREFIX_SPARSE_KOGGE_STONE_2,
         FSAOption.PREFIX_SPARSE_KOGGE_STONE_4,
         FSAOption.NAIVE_RIPPLE_CARRY,
    ]
    
    if single_point:
        fsa_opts = [FSAOption.RIPPLE_CARRY]

    optim_types = ["area", "speed"]
    if single_point:
        optim_types = ["area"]

    out_dir = prepare_out_dir()
    case_results = {}
    all_results = []
    total_configs = 0

    # (case_key, signed_a, signed_b, enc_in, enc_out)
    adder_cases = [
        ("add_signed", True, True, Encoding.twos_complement, Encoding.twos_complement),
        ("add_unsigned", False, False, Encoding.unsigned, Encoding.unsigned),
    ]

    for case_key, signed_a, signed_b, enc_in, enc_out in adder_cases:
        reset_shared_cache()
        configs = [
            InstanceConfig(
                impl_cls=StageBasedPrefixAdder,
                config=AdderCfg(
                    a_w=n_bits,
                    b_w=n_bits,
                    signed_a=signed_a,
                    signed_b=signed_b,
                    optim_type=optim_type,
                    fsa_cls=fsa_opt.value,
                    full_output_bit=True,
                ),
            )
            for fsa_opt, optim_type in product(fsa_opts, optim_types)
        ]
        # Baseline: Verilog + operator (no structural decomposition)
        for optim_type in optim_types:
            configs.append(InstanceConfig(
                impl_cls=StageBasedPrefixAdder,
                config=AdderCfg(
                    a_w=n_bits,
                    b_w=n_bits,
                    signed_a=signed_a,
                    signed_b=signed_b,
                    optim_type=optim_type,
                    fsa_cls=FSAOption.PLUS_OPERATOR.value,
                    full_output_bit=True,
                ),
            ))
        total_configs += len(configs)
        first_inst = configs[0].gen_instance()
        vectors = AdderTestVectors(
            a_w=n_bits,
            b_w=n_bits,
            y_w=first_inst.io.y.typ.width,
            num_vectors=num_vectors,
            tb_sigma=sigma,
            a_encoding=enc_in,
            b_encoding=enc_in,
            y_encoding=enc_out,
        ).generate()
        results = _run_and_collect(
            case_key, configs, vectors,
            f"worker_{case_key}",
            target_delays, n_processes, keep_files,
            technology=technology,
        )
        case_results[case_key] = results
        all_results.extend(results)

    # ---------------------------------------------------
    # -- Save and plot
    # ---------------------------------------------------
    if not all_results:
        print("No adder results generated.")
        return

    results_payload = {
        "meta": {
            "dim_m": 1,
            "dim_n": 1,
            "dim_k": 1,
            "a_width": n_bits,
            "b_width": n_bits,
            "c_width": n_bits + 1,
            "design_prefix": "Add",
            "title_label": "Adder",
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

    results_path = os.path.join(out_dir, f"Add_a{n_bits}_results.json")
    with open(results_path, "w") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Saved adder results to {results_path}")

    _run_all_plotters(results_payload, case_results, out_dir, "Add", "Adder")

    print(
        f"Adder sweep: {total_configs} configs x {len(target_delays)} delays = "
        f"{total_configs * len(target_delays)} runs, got {len(all_results)} results"
    )


if __name__ == "__main__":
    run_ppa_multiplier_sweep()
    #run_ppa_adder_sweep()

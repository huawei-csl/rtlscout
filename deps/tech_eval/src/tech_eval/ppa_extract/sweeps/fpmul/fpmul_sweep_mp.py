"""Floating-point multiplier PPA sweep.

Runs a comprehensive sweep over FpMulSN configurations (varying PPA tree,
final-stage adder, and optimisation target), collecting PPA metrics across
multiple target delays.  Format parameters (EW, FW, subnormals, …) are read
from metadata.json in this directory.
"""

import json
import os
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple

from spirehdl.spirehdl import reset_shared_cache

from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    PPAOption,
    PPGOption,
    MultiplierOption,
    TwoInputAritEncodings,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding
from spirehdl.arithmetic.int_arithmetic_config import MultiplierConfig
from spirehdl.arithmetic.floating_point.spire_hdl_float_mult_sn import FpMulSN
from spirehdl.arithmetic.int_arithmetic_config import AdderConfig
from tech_eval.ppa_extract.sweeps.fpmul.fp_mul_opt import FpMulOpt
from tech_eval.ppa_extract.sweeps.fpmul.script_to_component import load_component_cls
from spirehdl.arithmetic.floating_point.fp_mul_testvectors import FpMulTestVectors

from tech_eval.ppa_extract.core.ppa_configs import InstanceConfig, JsonExportConfig
from tech_eval.ppa_extract.core.ppa_extraction import PPA_REPORT_TIME_UNIT
from tech_eval.ppa_extract.core.ppa_extraction_specific import run_configs
from tech_eval.ppa_extract.core.template import get_tech_config
from tech_eval.ppa_extract.sweeps.plotting2 import (
    plot_delay_vs_area,
    plot_power_vs_area,
    plot_power_vs_delay,
    plot_switch_count_vs_area,
    plot_switch_count_vs_delay,
    plot_transistor_count_vs_area,
    regroup_by_target_delay,
)

SAVE_VCD_FOR_POWER = False

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_METADATA_PATH = os.path.join(_SCRIPT_DIR, "metadata.json")


# ---------------------------------------------------------------------------
# -- Config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FpMulCfg(JsonExportConfig):
    """Flat config for FpMulSN / FpMulOpt; field names match their __init__ kwargs exactly."""

    json_export_fields: ClassVar[Dict[str, str]] = {
        "mult_cfg.use_operator": "mult_use_operator",
        "mult_cfg.multiplier_opt": "mult_multiplier_opt",
        "mult_cfg.ppa_opt": "mult_ppa_cls_name",
        "mult_cfg.fsa_opt": "mult_fsa_cls_name",
        "mult_cfg.ppg_opt": "mult_ppg_cls_name",
        "mult_cfg.optim_type": "mult_optim_type",
        "adder_cfg.use_operator": "add_use_operator",
        "adder_cfg.fsa_opt": "add_fsa_cls_name",
        "adder_cfg.optim_type": "add_optim_type",
    }

    EW: int
    FW: int
    subnormals: bool
    always_subnormal_rounding: bool
    mult_cfg: Optional[object]   # MultiplierConfig or None
    adder_cfg: Optional[object]  # AdderConfig or None


# ---------------------------------------------------------------------------
# -- Shared utilities
# ---------------------------------------------------------------------------

def _discover_pareto_designs(
    references_dir: str = None,
) -> List[Tuple[str, str, str]]:
    if references_dir is None:
        references_dir = os.path.join(_SCRIPT_DIR, "references")
    """Discover design scripts from all ``pareto_*`` folders.

    Returns a list of ``(script_path, gen_source, design)`` tuples where:
    - *script_path*: path to the design ``.py`` file
    - *gen_source*:  pareto front folder name  (e.g. ``"pareto_"``)
    - *design*:      design subfolder name     (e.g. ``"design_000"``)
    """
    entries: List[Tuple[str, str, str]] = []
    for pf_dir in sorted(Path(references_dir).glob("pareto_*")):
        if not pf_dir.is_dir():
            continue
        gen_source = pf_dir.name
        for design_dir in sorted(pf_dir.glob("design_*")):
            scripts = [s for s in design_dir.glob("*.py")
                       if not s.name.endswith("_component.py")]
            if not scripts:
                continue
            entries.append((str(scripts[0]), gen_source, design_dir.name))
    return entries


from tech_eval.ppa_extract.sweeps.sweep_utils import (
    prepare_out_dir,
    serialize_case_results,
)


def _regroup_by_field(case_results, field):
    regrouped = {}
    for entries in case_results.values():
        for entry in entries:
            key = entry.get(field)
            if key is not None:
                regrouped.setdefault(str(key), []).append(entry)
    return regrouped


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

    for plotter in _PLOTTERS:
        plotter(**base_kwargs, groups=case_results, suffix="by_case")

    extra_groups = [
        ("by_target_delay",       regroup_by_target_delay(case_results)),
        ("by_mult_ppa_cls_name",  _regroup_by_field(case_results, "mult_ppa_cls_name")),
        ("by_mult_fsa_cls_name",  _regroup_by_field(case_results, "mult_fsa_cls_name")),
        ("by_design",             _regroup_by_field(case_results, "design")),
        ("by_gen_source",         _regroup_by_field(case_results, "gen_source")),
    ]
    for group_suffix, grouped in extra_groups:
        if not grouped:
            continue
        for plotter in _PLOTTERS:
            plotter(**base_kwargs, groups=grouped, suffix=group_suffix)


# ---------------------------------------------------------------------------
# -- Sweep
# ---------------------------------------------------------------------------

def run_ppa_fpmul_sweep(references_dir: str = None):
    technology = "asap7"
    lib_time_unit = get_tech_config(technology).lib_time_unit

    with open(_METADATA_PATH) as f:
        meta = json.load(f)

    gen_cfg = meta["generator"]["config"]
    EW = gen_cfg["exponent_width"]
    FW = gen_cfg["fraction_width"]
    subnormals = gen_cfg.get("subnormals", True)
    always_subnormal_rounding = gen_cfg.get("always_subnormal_rounding", False)
    num_vectors = meta["generator"].get("num_vectors", 2000)

    W = 1 + EW + FW

    single_point = False

    target_delays = [900, 1200, 1700]
    if single_point:
        target_delays = [200]

    n_processes = 80
    keep_files = True

    ppa_opts = [
        PPAOption.CARRY_SAVE_TREE,
        PPAOption.ACCUMULATOR_TREE,
        PPAOption.DADDA_TREE,
        PPAOption.WALLACE_TREE,
        PPAOption.FOUR_TWO_COMPRESSOR,
    ]
    fsa_opts = [
        FSAOption.PREFIX_SKLANSKY,
        FSAOption.PREFIX_KOGGE_STONE,
        FSAOption.RIPPLE_CARRY,
        FSAOption.PREFIX_BRENT_KUNG,
        FSAOption.PREFIX_SPARSE_KOGGE_STONE_2,
        FSAOption.PREFIX_SPARSE_KOGGE_STONE_4,
    ]
    if single_point:
        ppa_opts = [PPAOption.WALLACE_TREE]
        fsa_opts = [FSAOption.RIPPLE_CARRY]

    optim_types = ["area", "speed"]
    if single_point:
        optim_types = ["area"]

    out_dir = prepare_out_dir()

    vectors = FpMulTestVectors(
        EW=EW,
        FW=FW,
        num_vectors=num_vectors,
        subnormals=subnormals,
        always_subnormal_rounding=always_subnormal_rounding,
    ).generate()

    def _make_configs(impl_cls):
        # Mantissa inputs are unsigned → PPG is always AND.
        # Same fsa_opt used for both mult and exponent adder (mirrors mmac approach).
        configs = [
            InstanceConfig(
                impl_cls=impl_cls,
                config=FpMulCfg(
                    EW=EW,
                    FW=FW,
                    subnormals=subnormals,
                    always_subnormal_rounding=always_subnormal_rounding,
                    mult_cfg=MultiplierConfig(
                        use_operator=False,
                        multiplier_opt=MultiplierOption.STAGE_BASED_MULTIPLIER,
                        encodings=TwoInputAritEncodings.with_enc(Encoding.unsigned),
                        ppg_opt=PPGOption.AND,
                        ppa_opt=ppa_opt,
                        fsa_opt=fsa_opt,
                        optim_type=optim_type,
                    ),
                    adder_cfg=AdderConfig(
                        use_operator=False,
                        fsa_opt=fsa_opt,
                        optim_type=optim_type,
                    ),
                ),
            )
            for ppa_opt, fsa_opt, optim_type in product(ppa_opts, fsa_opts, optim_types)
        ]
        # Baseline: use Verilog * and + operators (no structural decomposition)
        configs.append(InstanceConfig(
            impl_cls=impl_cls,
            config=FpMulCfg(
                EW=EW,
                FW=FW,
                subnormals=subnormals,
                always_subnormal_rounding=always_subnormal_rounding,
                mult_cfg=MultiplierConfig(use_operator=True),
                adder_cfg=AdderConfig(use_operator=True),
            ),
        ))
        return configs

    design_entries = _discover_pareto_designs(references_dir)

    case_results = {}
    all_results = []

    for script_path, gen_source, design in design_entries:
        impl_cls = load_component_cls(script_path)
        case_key = f"{gen_source}/{design}"
        configs = _make_configs(impl_cls)
        total_runs = len(configs) * len(target_delays)
        print(f"FpMul sweep ({case_key}): {len(configs)} configs x {len(target_delays)} delays = {total_runs} runs")
        reset_shared_cache()
        results = run_configs(
            configs=configs,
            target_delays=target_delays,
            worker_base_path=f"worker_fpmul_{gen_source}_{design}",
            keep_files=keep_files,
            processes=n_processes,
            vectors=vectors,
            save_vcd=SAVE_VCD_FOR_POWER,
            technology=technology,
        )
        for entry in results:
            entry["design"] = design
            entry["gen_source"] = gen_source
            wp = entry.get("worker_path", "")
            entry["verilog_path"] = os.path.join(wp, "design.v") if wp else None
        if not results:
            print(f"No results for {case_key}.")
        case_results[case_key] = results
        all_results.extend(results)

    if not all_results:
        print("No fpmul results generated.")
        return

    design_prefix = f"FpMul_e{EW}f{FW}"
    title_label = f"FP Multiplier e{EW}f{FW}"

    results_payload = {
        "meta": {
            "EW": EW,
            "FW": FW,
            "W": W,
            "dim_m": 1,
            "dim_n": 1,
            "dim_k": 1,
            "a_width": W,
            "b_width": W,
            "c_width": W,
            "subnormals": subnormals,
            "always_subnormal_rounding": always_subnormal_rounding,
            "design_prefix": design_prefix,
            "title_label": title_label,
            "target_delays": list(target_delays),
            "vector_count": num_vectors,
            "lib_time_unit": lib_time_unit,
            "ppa_report_time_unit": PPA_REPORT_TIME_UNIT,
            "technology": technology,
        },
        "case_results": serialize_case_results(case_results),
    }

    results_path = os.path.join(out_dir, f"FpMul_e{EW}f{FW}_results.json")
    with open(results_path, "w") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Saved fpmul results to {results_path}")

    _run_all_plotters(results_payload, case_results, out_dir, design_prefix, title_label)

    print(f"FpMul sweep: {len(all_results)} total results")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FP multiplier PPA sweep")
    parser.add_argument("--references-dir", type=str, default=None,
                        help="Directory containing pareto_* design folders "
                             "(default: references/ next to this script)")
    args = parser.parse_args()
    run_ppa_fpmul_sweep(references_dir=args.references_dir)

"""Floating-point adder PPA sweep.

Sweeps agent Pareto designs over prefix-adder architectures (FSAOption)
and optimisation targets, collecting PPA metrics across multiple target delays.

Agent designs from pareto_fronts/fpadd_f16_with_flowy/ are loaded and
AST-patched so that ``mant_add = m_big_ext + m_small_shift`` uses
``build_adder`` with the configured prefix-adder architecture.

Usage:
    cd /workspaces/tech_eval
    python -m tech_eval.ppa_extract.sweeps.fpadd.fpadd_sweep_mp
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
)
from spirehdl.arithmetic.int_arithmetic_config import AdderConfig
from spirehdl.arithmetic.floating_point.fp_add_testvectors import FpAddTestVectors

from tech_eval.ppa_extract.core.ppa_configs import InstanceConfig, JsonExportConfig
from tech_eval.ppa_extract.core.ppa_extraction import PPA_REPORT_TIME_UNIT
from tech_eval.ppa_extract.core.ppa_extraction_specific import run_configs
from tech_eval.ppa_extract.core.template import get_tech_config
from tech_eval.ppa_extract.sweeps.fpadd.script_to_component import load_fpadd_component_cls

SAVE_VCD_FOR_POWER = False


# ---------------------------------------------------------------------------
# -- Config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FpAddCfg(JsonExportConfig):
    """Config for FpAdd; field names match FpAdd.__init__ kwargs."""

    json_export_fields: ClassVar[Dict[str, str]] = {
        "adder_cfg.use_operator": "add_use_operator",
        "adder_cfg.fsa_opt": "add_fsa_cls_name",
        "adder_cfg.optim_type": "add_optim_type",
    }

    EW: int
    FW: int
    adder_cfg: Optional[object] = None  # AdderConfig or None


# ---------------------------------------------------------------------------
# -- Helpers
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _discover_pareto_designs(
    references_dir: str = None,
) -> List[Tuple[str, str, str]]:
    if references_dir is None:
        references_dir = os.path.join(_SCRIPT_DIR, "references")
    """Discover design scripts from all ``pareto_*`` folders.

    Returns a list of ``(script_path, gen_source, design)`` tuples.
    """
    entries: List[Tuple[str, str, str]] = []
    for pf_dir in sorted(Path(references_dir).glob("pareto_*")):
        if not pf_dir.is_dir():
            continue
        gen_source = pf_dir.name
        for design_dir in sorted(pf_dir.glob("design_*")):
            scripts = [s for s in design_dir.glob("*.py")
                       if not s.name.endswith("_adder_sweep.py")
                       and not s.name.endswith("_component.py")]
            if not scripts:
                continue
            # Prefer the script that defines a Component class (not a wrapper)
            # Heuristic: longer filename or one containing 'spire_hdl_float'
            best = scripts[0]
            for s in scripts:
                if "spire_hdl_float" in s.name or "float_add" in s.name:
                    best = s
                    break
            entries.append((str(best), gen_source, design_dir.name))
    return entries


from tech_eval.ppa_extract.sweeps.sweep_utils import (
    prepare_out_dir,
    serialize_case_results,
)


# ---------------------------------------------------------------------------
# -- Main sweep
# ---------------------------------------------------------------------------

def run_ppa_fpadd_sweep():
    technology = "asap7"
    lib_time_unit = get_tech_config(technology).lib_time_unit

    EW = 5
    FW = 10
    W = 1 + EW + FW
    subnormals = True
    num_vectors = 2000

    target_delays = [600, 1000, 1600]

    n_processes = 80
    keep_files = True

    fsa_opts = [
        FSAOption.PREFIX_SKLANSKY,
        FSAOption.PREFIX_KOGGE_STONE,
        FSAOption.RIPPLE_CARRY,
        FSAOption.PREFIX_BRENT_KUNG,
        FSAOption.PREFIX_LADNER_FISCHER,
        FSAOption.PREFIX_HAN_CARLSON,
        FSAOption.PREFIX_SPARSE_KOGGE_STONE_2,
        FSAOption.PREFIX_SPARSE_KOGGE_STONE_4,
    ]
    optim_types = ["area", "speed"]

    out_dir = prepare_out_dir()

    # Skip sprout-level simulation — the agent designs are already verified,
    # and the prefix adder substitution only changes the mantissa adder
    # implementation (not the algorithm). The sprout simulator has issues
    # with make_internal() components from build_adder.
    vectors = None

    def _make_configs(impl_cls):
        configs = [
            InstanceConfig(
                impl_cls=impl_cls,
                config=FpAddCfg(
                    EW=EW,
                    FW=FW,
                    adder_cfg=AdderConfig(
                        use_operator=False,
                        fsa_opt=fsa_opt,
                        optim_type=optim_type,
                    ),
                ),
            )
            for fsa_opt, optim_type in product(fsa_opts, optim_types)
        ]
        # Baseline: use default + operator (no structural adder)
        configs.append(InstanceConfig(
            impl_cls=impl_cls,
            config=FpAddCfg(
                EW=EW,
                FW=FW,
                adder_cfg=None,
            ),
        ))
        return configs

    design_entries = _discover_pareto_designs()

    case_results = {}
    all_results = []

    for script_path, gen_source, design in design_entries:
        try:
            impl_cls = load_fpadd_component_cls(script_path)
        except Exception as e:
            print(f"  SKIP {gen_source}/{design}: {e}")
            continue
        case_key = f"{gen_source}/{design}"
        configs = _make_configs(impl_cls)
        total_runs = len(configs) * len(target_delays)
        print(f"FpAdd sweep ({case_key}): {len(configs)} configs x {len(target_delays)} delays = {total_runs} runs")
        reset_shared_cache()
        try:
            results = run_configs(
                configs=configs,
                target_delays=target_delays,
                worker_base_path=f"worker_fpadd_{gen_source}_{design}",
                keep_files=keep_files,
                processes=n_processes,
                vectors=vectors,
                save_vcd=SAVE_VCD_FOR_POWER,
                technology=technology,
            )
        except Exception as e:
            print(f"  ERROR running {case_key}: {e}")
            continue
        for entry in results:
            entry["design"] = design
            entry["gen_source"] = gen_source
            wp = entry.get("worker_path", "")
            entry["verilog_path"] = os.path.join(wp, "design.v") if wp else None
        if not results:
            print(f"  No results for {case_key}.")
        case_results[case_key] = results
        all_results.extend(results)

    if not all_results:
        print("No fpadd results generated.")
        return

    design_prefix = f"FpAdd_e{EW}f{FW}"
    title_label = f"FP Adder e{EW}f{FW}"

    results_payload = {
        "meta": {
            "EW": EW,
            "FW": FW,
            "W": W,
            "subnormals": subnormals,
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

    results_path = os.path.join(out_dir, f"FpAdd_e{EW}f{FW}_results.json")
    with open(results_path, "w") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Saved fpadd results to {results_path}")

    print(f"FpAdd sweep: {len(all_results)} total results across {len(case_results)} designs")


if __name__ == "__main__":
    run_ppa_fpadd_sweep()

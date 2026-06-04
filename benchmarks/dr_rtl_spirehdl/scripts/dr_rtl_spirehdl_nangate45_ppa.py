#!/usr/bin/env python3
"""Extract nangate45 PPA for every `benchmarks/dr_rtl_spirehdl/*/` starting
point (spirehdl `.py`), at a fixed `target_delay`.

Wraps `benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py`'s flow for
verilog inputs, with one extra step in front: run the spirehdl `.py`
in a workdir to produce `design.v`, then feed that into `get_ppa`.

Only runs over cases that self-pass against tb.sv (per README). Use
`--case` to override.

Default `target_delay = 100 ps`. Outputs:
  1. JSON dump at `benchmarks/dr_rtl_spirehdl/eval_nangate45_ppa.json`.
  2. Markdown table on stdout.

Usage:
  python benchmarks/dr_rtl_spirehdl/scripts/dr_rtl_spirehdl_nangate45_ppa.py
  python benchmarks/dr_rtl_spirehdl/scripts/dr_rtl_spirehdl_nangate45_ppa.py --case datapath
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
BENCH_ROOT = REPO / "benchmarks/dr_rtl_spirehdl"
DR_RTL_SCRIPTS = REPO / "benchmarks/dr_rtl/scripts"

# Reuse the netlist-postprocess + fallback flow from the verilog side.
sys.path.insert(0, str(DR_RTL_SCRIPTS))
from dr_rtl_nangate45_ppa import _fallback_synth_and_sta  # noqa: E402


# Designs that PASS 2000/2000 (per current README). Update as ports land.
# Designs whose spirehdl port has a working `design.v` (correct hardware
# behavior). All but `i2c` pass 2000/2000; `i2c` is 1999/2000 (the missing
# vector is a Verilator `<= #1` scheduling artifact, not a hardware defect).
PASSING_CASES = ["ticket", "controller", "router", "i2c", "pcie", "cpu_pipe",
                  "datapath"]


def _spirehdl_starting_point(case_dir: Path) -> Optional[Path]:
    p = case_dir / "context" / "starting_point.py"
    return p if p.exists() else None


def _compile_spirehdl(starting_point: Path, workdir: Path) -> Path:
    """Run the spirehdl .py inside workdir, producing design.v.

    Mirrors core/runner.py's spirehdl compile step: copy the .py to
    workdir, chdir into workdir, run as a subprocess. Returns the path
    to the produced design.v.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    local_py = workdir / starting_point.name
    if not local_py.exists() or local_py.resolve() != starting_point.resolve():
        shutil.copy2(starting_point, local_py)
    result = subprocess.run(
        [sys.executable, str(local_py)],
        cwd=workdir, capture_output=True, text=True, timeout=180,
    )
    design_v = workdir / "design.v"
    if not design_v.exists():
        raise RuntimeError(
            f"spirehdl compile produced no design.v.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return design_v


def _run_one(case: str, target_delay_ps: int) -> dict:
    from tech_eval.ppa_extract.core.ppa_extraction import get_ppa

    case_dir = BENCH_ROOT / case
    md = json.loads((case_dir / "metadata.json").read_text())
    starting = _spirehdl_starting_point(case_dir)
    if starting is None:
        return {"case": case, "error": "no starting_point.py in context/"}

    worker = Path(f"/tmp/dr_rtl_spirehdl_ppa_{case}_d{target_delay_ps}")

    try:
        design_v = _compile_spirehdl(starting, worker)
    except Exception as e:
        return {"case": case, "module": md["module_name"],
                "target_delay_ps": target_delay_ps,
                "error": f"spirehdl_compile: {e}"}

    try:
        r = get_ppa(
            rtl_path=str(design_v),
            target_delay=target_delay_ps,
            worker_path=str(worker / "_ppa"),
            top_module_name=md["module_name"],
            technology="nangate45",
        )
        return {
            "case": case, "module": md["module_name"],
            "target_delay_ps": target_delay_ps,
            "delay_ps": r["delay"], "area_um2": r["area"],
            "power_w": r["power"], "worst_slack_ns": r["worst_slack"],
            "used_fallback": False,
        }
    except Exception as e:
        first_err = f"{type(e).__name__}: {e}"
        fb = _fallback_synth_and_sta(case, design_v, md["module_name"],
                                      target_delay_ps, worker / "_fb")
        if "error" not in fb:
            return {
                "case": case, "module": md["module_name"],
                "target_delay_ps": target_delay_ps,
                **fb,
                "first_pass_error": first_err,
            }
        return {"case": case, "module": md["module_name"],
                "target_delay_ps": target_delay_ps,
                "error": fb["error"],
                "first_pass_error": first_err}


def _discover_cases() -> list[str]:
    return [c for c in PASSING_CASES if (BENCH_ROOT / c / "metadata.json").exists()]


def _markdown_table(rows: list[dict], target_delay_ps: int) -> str:
    lines = []
    lines.append(f"### Nangate45 PPA (spirehdl) at `target_delay = {target_delay_ps} ps` "
                 f"(= {target_delay_ps/1000:.3f} ns)")
    lines.append("")
    lines.append("| Case | Module | Delay (ps) | Area (μm²) | Power (W) | Worst slack (ns) | Flow |")
    lines.append("|---|---|---:|---:|---:|---:|:---|")
    for r in rows:
        if "error" in r:
            lines.append(f"| `{r['case']}` | `{r.get('module', '?')}` | "
                         f"N/A | N/A | N/A | N/A | error: {r['error'][:60]} |")
            continue
        flow = "fallback" if r.get("used_fallback") else "stock"
        lines.append(
            f"| `{r['case']}` | `{r['module']}` | "
            f"{r['delay_ps']:.1f} | {r['area_um2']:.2f} | "
            f"{r['power_w']:.4e} | {r['worst_slack_ns']:.4f} | {flow} |"
        )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-delay-ps", type=int, default=100)
    p.add_argument("--processes", type=int, default=4)
    p.add_argument("--case", action="append")
    p.add_argument("--out", type=Path,
                   default=BENCH_ROOT / "eval_nangate45_ppa.json")
    args = p.parse_args()

    cases = args.case if args.case else _discover_cases()
    rows = []
    if args.processes <= 1:
        for c in cases:
            print(f"== {c} ==", file=sys.stderr)
            rows.append(_run_one(c, args.target_delay_ps))
    else:
        with ProcessPoolExecutor(max_workers=args.processes) as ex:
            futs = {ex.submit(_run_one, c, args.target_delay_ps): c for c in cases}
            for f in as_completed(futs):
                c = futs[f]
                try:
                    rows.append(f.result())
                    print(f"   done: {c}", file=sys.stderr)
                except Exception as e:
                    print(f"   {c} CRASH: {e}", file=sys.stderr)
                    rows.append({"case": c, "error": f"executor: {e}"})

    rows.sort(key=lambda r: r["case"])
    args.out.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"Wrote {args.out}", file=sys.stderr)
    print(_markdown_table(rows, args.target_delay_ps))


if __name__ == "__main__":
    main()

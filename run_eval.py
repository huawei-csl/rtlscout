#!/usr/bin/env python3
"""Debug tool: run evaluation on an existing workspace or design file.

Given a path to a design file (e.g. a .py or .sv file inside a workspace),
this script runs the full evaluation pipeline (SpireHDL compile if needed,
Verilator correctness, Yosys cost) and prints the result.

The workspace directory is inferred from the file's location — it must
contain tb.sv and (for data-driven testbenches) the .dat file.

Usage:
  python run_eval.py runs/fpmul_f16/.../workspace/starting_point.py
  python run_eval.py runs/fpmul_f16/.../workspace/starting_point.py --language spirehdl
  python run_eval.py runs/fpmul_f16/.../workspace/design.sv --language verilog
  python run_eval.py runs/fpmul_f16/.../workspace/design.py --cost-metric delay --target-delay 500
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from core.cost import COST_METRICS, make_cost_metric
from core.evaluation import COMPILE_TIMEOUT, evaluate


def _infer_top_module(workdir: Path) -> str | None:
    """Try to infer the design top module from design.v in the workspace."""
    design_v = workdir / "design.v"
    if not design_v.exists():
        return None
    text = design_v.read_text()
    # Find the last `module X(` declaration (skip testbench modules)
    matches = re.findall(r"^\s*module\s+(\w+)\s*[\(;#]", text, re.MULTILINE)
    if matches:
        # Filter out 'tb' and return the first real module
        for name in matches:
            if name != "tb":
                return name
    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="Run evaluation on a design file (for debugging)",
    )
    parser.add_argument("file", help="Path to the design file (.py or .sv/.v)")
    parser.add_argument("--language", default=None, choices=["verilog", "spirehdl", "amaranth"],
                        help="Source language (default: auto-detect from extension)")
    parser.add_argument("--cost-metric", default="transistors", choices=sorted(COST_METRICS),
                        help="Cost metric (default: transistors)")
    parser.add_argument("--target-delay", type=float, default=500.0,
                        help="Target delay in ps for PPA metrics (default: 500)")
    parser.add_argument("--technology", default="asap7",
                        help="Process technology for PPA metrics: asap7, nangate45, freepdk45 (default: asap7)")
    parser.add_argument("--top-module", default=None,
                        help="Design top module name (default: auto-detect from description)")
    parser.add_argument("--workdir", default=None,
                        help="Workspace directory (default: parent of the design file)")
    parser.add_argument("--benchmark", default=None,
                        help="Benchmark directory to use tb.sv/vectors.dat from (e.g. benchmarks/fpmul_f16)")
    parser.add_argument("--skip-cec", action="store_true",
                        help="Skip the combinational equivalence check (yosys-abc cec). "
                             "CEC runs by default when --benchmark has a golden_reference "
                             "in metadata.json, and gates pass/fail on it")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--save-to", default=None, type=Path,
                        help="Save result.json + workspace/ to this directory "
                             "(compatible with extract_pareto.py)")
    args = parser.parse_args()

    design_path = Path(args.file).resolve()
    if not design_path.exists():
        print(f"File not found: {design_path}")
        sys.exit(1)

    workdir = Path(args.workdir).resolve() if args.workdir else design_path.parent
    design_filename = design_path.name

    # Auto-detect language from extension
    if args.language is None:
        if design_filename.endswith(".py"):
            language = "spirehdl"
        else:
            language = "verilog"
    else:
        language = args.language

    # Copy testbench files from benchmark directory if specified
    if args.benchmark:
        bench_dir = Path(args.benchmark).resolve()
        if not bench_dir.is_dir():
            print(f"Benchmark directory not found: {bench_dir}")
            sys.exit(1)
        for name in ["tb.sv", "vectors.dat"]:
            src = bench_dir / name
            if src.exists():
                shutil.copy2(src, workdir / name)

    # Check workspace has tb.sv
    if not (workdir / "tb.sv").exists():
        print(f"No tb.sv found in {workdir}")
        sys.exit(1)

    cost_metric = make_cost_metric(args.cost_metric, target_delay=args.target_delay,
                                   technology=args.technology)

    # Auto-detect top module if not specified
    top_module = args.top_module
    if top_module is None:
        # For spirehdl, run the .py first to generate design.v, then infer
        # For verilog, infer directly from the .v/.sv file
        if language in ("spirehdl", "amaranth"):
            # We need design.v to exist — run the script first if needed
            design_v = workdir / "design.v"
            if not design_v.exists():
                import subprocess
                subprocess.run(
                    [sys.executable, design_filename],
                    cwd=str(workdir), capture_output=True,
                    timeout=COMPILE_TIMEOUT,
                )
            top_module = _infer_top_module(workdir)
        else:
            # For verilog, scan the design file itself
            dpath = workdir / design_filename
            if dpath.exists():
                matches = re.findall(
                    r"^\s*module\s+(\w+)\s*[\(;#]",
                    dpath.read_text(), re.MULTILINE,
                )
                top_module = next((n for n in matches if n != "tb"), None)

    print(f"Workdir:  {workdir}")
    print(f"Design:   {design_filename}")
    print(f"Language: {language}")
    print(f"Metric:   {args.cost_metric}")
    if top_module:
        print(f"Top:      {top_module}")
    print()

    # Resolve golden reference for the equivalence check (on by default).
    # CEC needs a benchmark with a golden_reference; otherwise it is skipped.
    cec_reference = None
    if not args.skip_cec and args.benchmark:
        from core.benchmarks import load_benchmark
        from core.equivalence import resolve_golden_reference
        bench = load_benchmark(Path(args.benchmark).resolve())
        cec_reference = resolve_golden_reference(bench, workdir / "_golden")

    import time
    t0 = time.monotonic()
    result = evaluate(
        workdir=workdir,
        design_top_module=top_module,
        cost_metric=cost_metric,
        language=language,
        design_file=design_filename,
        run_cec=cec_reference is not None,
        cec_reference=cec_reference,
    )
    duration = time.monotonic() - t0

    if args.save_to:
        save_dir = args.save_to.resolve()
        ws_dir = save_dir / "workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)
        # Copy design file
        shutil.copy2(design_path, ws_dir / design_filename)
        # Copy local .py dependencies if SpireHDL
        if design_path.suffix == ".py":
            try:
                from extract_pareto import _find_local_deps
                for dep in _find_local_deps(design_path, design_path.parent):
                    if not (ws_dir / dep.name).exists():
                        shutil.copy2(dep, ws_dir / dep.name)
            except ImportError:
                pass
        # Write result.json
        d = result.to_dict()
        d["duration_s"] = round(duration, 1)
        d["design_file"] = design_filename
        (save_dir / "result.json").write_text(json.dumps(d, indent=2))
        print(f"Saved: {save_dir / 'result.json'}")

    if args.json:
        d = result.to_dict()
        d["duration_s"] = round(duration, 1)
        print(json.dumps(d, indent=2))
    else:
        print(result.summary_str())
        print(f"\nDuration: {duration:.1f}s")


if __name__ == "__main__":
    main()

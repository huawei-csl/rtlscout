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
  python run_eval.py design.aig --benchmark benchmarks/mac_2x8s_sat16 --cost-metric area
      (AIG input: with symbols -> sim+cost; symbol-less -> RTL sim skipped automatically)
  python run_eval.py design.sv --benchmark ... --cost-metric area --skip-rtl-sim
      (--skip-rtl-sim: skip the RTL sim only; cost + CEC-vs-golden still run; any language)
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


def _aig_to_verilog(aig_path: Path, out_v: Path, top_module: str) -> bool:
    """Convert an AIGER (.aig/.aag) file to Verilog at *out_v*.

    Returns True if the AIG carried an I/O symbol table and named wide ports were
    reconstructed (so functional sim/CEC are valid); False for a symbol-less AIG, which
    is written as a bare positional module (cost-only — its I/O mapping can't be
    recovered). Generic: ports come from whatever symbols exist, no benchmark assumptions.
    """
    import subprocess
    core_v = out_v.parent / "_aig_core.v"
    subprocess.run(["yosys", "-q", "-p",
                    f"read_aiger -module_name aig_core {aig_path}; write_verilog {core_v}"],
                   capture_output=True, text=True)
    if not core_v.exists():
        raise RuntimeError(f"yosys read_aiger failed for {aig_path}")
    text = core_v.read_text()
    widths: dict = {}
    for d, nm, idx in re.findall(r"^\s*(input|output)\s+\\(\w+)\[(\d+)\]\s*;", text, re.M):
        widths[(d, nm)] = max(widths.get((d, nm), 0), int(idx))
    # scalar named ports, excluding yosys auto-names (_<digits>_) used for symbol-less AIGs
    scalars = {(d, nm) for d, nm in re.findall(r"^\s*(input|output)\s+\\?(\w+)\s*;", text, re.M)
               if (d, nm) not in widths and not re.fullmatch(r"_\d+_", nm)}
    if not widths and not scalars:                       # symbol-less -> bare positional module
        core_v.unlink()
        subprocess.run(["yosys", "-q", "-p",
                        f"read_aiger -module_name {top_module} {aig_path}; write_verilog {out_v}"],
                       capture_output=True, text=True)
        return False
    ports, conns = [], []                                # named symbols -> wide-port wrapper
    for (d, nm), hi in sorted(widths.items()):
        ports.append(f"{d} [{hi}:0] {nm}")
        conns += [f".\\{nm}[{k}] ({nm}[{k}])" for k in range(hi + 1)]
    for (d, nm) in sorted(scalars):
        ports.append(f"{d} {nm}")
        conns.append(f".{nm} ({nm})")
    wrapper = (f"module {top_module}(" + ", ".join(ports) + ");\n  aig_core u (\n    "
               + ",\n    ".join(conns) + "\n  );\nendmodule\n")
    out_v.write_text(text + "\n" + wrapper)
    core_v.unlink()
    # flatten wrapper+core into ONE module so every cost metric (incl. non-flattening ones
    # like `transistors`) sees a single flat design with the named wide ports.
    subprocess.run(["yosys", "-q", "-p",
                    f"read_verilog {out_v}; hierarchy -top {top_module}; flatten; "
                    f"write_verilog {out_v}"], capture_output=True, text=True)
    return True


def _prepare_aig_input(args, design_path: Path, workdir: Path) -> tuple:
    """Reconstruct an AIG (.aig/.aag) into ``design.v`` in *workdir* and configure *args*
    for the verilog pipeline. The caller invokes this only for AIG inputs.

    Top module name: ``--top-module``, else ``--benchmark``'s module_name, else the AIG's
    file stem (sanitized to a valid identifier). The stem default is fine for a cost-only
    run, where the name is just a label — but for sim/CEC it must match the testbench DUT.

    Returns ``(design_filename, force_cost_only)``: the filename becomes ``"design.v"``
    and ``force_cost_only`` is True for a symbol-less AIG (its I/O mapping can't be
    recovered, so the RTL sim must be skipped).
    """
    aig_top = args.top_module
    if aig_top is None and args.benchmark:
        from core.benchmarks import load_benchmark
        aig_top = load_benchmark(Path(args.benchmark).resolve()).module_name
    if not aig_top:                          # fall back to the AIG file stem
        aig_top = re.sub(r"\W", "_", design_path.stem) or "top"
        print(f"(no --top-module/--benchmark; using AIG file stem as top module: {aig_top})")

    symboled = _aig_to_verilog(design_path, workdir / "design.v", aig_top)
    args.language = "verilog"
    args.top_module = aig_top
    return "design.v", not symboled   # symbol-less -> force cost-only (no recoverable I/O)


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
    parser.add_argument("--energy-exp", type=float, default=1.0,
                        help="For --cost-metric edap: exponent k in edap = energy**k * runtime * area. "
                             "k=1 balanced EDAP, k>1 weights data-movement/reuse harder, k=0 == adp (default: 1.0)")
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
    parser.add_argument("--skip-netlist-sim", action="store_true",
                        help="For PPA metrics (area/delay/power/runtime/adp/area_delay_product), "
                             "skip re-simulating the synthesized gate-level netlist against tb.sv. "
                             "This is the slow step for large designs; skipping it makes synthesis+STA "
                             "run in seconds. Only safe when RTL correctness already covers the design.")
    parser.add_argument("--skip-rtl-sim", action="store_true",
                        help="Skip the RTL correctness simulation only. Cost still runs, and CEC "
                             "still runs against a golden reference (orthogonal to the sim). Works "
                             "for any language (verilog/spirehdl/amaranth/AIG); the spire/amaranth "
                             "compile still runs. Implied for symbol-less AIG inputs (no recoverable "
                             "I/O, so those can't run CEC either).")
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
    # AIG input (.aig/.aag): reconstruct to design.v; force_cost_only=True for symbol-less AIGs.
    force_cost_only = False
    if design_filename.endswith((".aig", ".aag")):
        design_filename, force_cost_only = _prepare_aig_input(args, design_path, workdir)
    # Skip the RTL correctness sim (+CEC) on request, or for un-simulatable symbol-less AIGs.
    skip_sim = args.skip_rtl_sim or force_cost_only
    if skip_sim:
        args.skip_netlist_sim = True   # no tb re-sim either; the cost metric runs alone

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

    # Check workspace has tb.sv (not required when the RTL sim is skipped)
    if not skip_sim and not (workdir / "tb.sv").exists():
        print(f"No tb.sv found in {workdir}")
        sys.exit(1)

    cost_metric = make_cost_metric(args.cost_metric, target_delay=args.target_delay,
                                   technology=args.technology,
                                   run_netlist_sim=not args.skip_netlist_sim,
                                   energy_exp=args.energy_exp)

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

    # Resolve golden reference for the equivalence check (on by default). CEC needs a
    # benchmark with a golden_reference. --skip-rtl-sim still allows CEC (formal check
    # without sim), but a symbol-less AIG (force_cost_only) can't: its I/O mapping is
    # unrecoverable, so CEC vs the golden would be meaningless — skip it there.
    cec_reference = None
    if not args.skip_cec and not force_cost_only and args.benchmark:
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
        run_rtl_sim=not skip_sim,
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

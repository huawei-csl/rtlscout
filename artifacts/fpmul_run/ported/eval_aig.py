#!/usr/bin/env python3
"""Convert an AIGER file to Verilog and run PPA evaluation (area + delay).

The AIGER file is binary (no port names), so we use yosys-abc to dump a flat verilog netlist with auto-generated
PI/PO names (pi00..piNN, po00..poMM), then emit a small wrapper module that maps those PIs/POs to the benchmark's
named ports (e.g. fp_mul_e5f10(a[15:0], b[15:0], y[15:0])).

By default simulation is skipped (since the AIG PI/PO bit-ordering may not match the original verilog). Pass
--with-sim to copy tb.sv + vectors.dat from the benchmark directory and run verilator on the wrapped design.

Usage:
  python eval_aig.py pareto_fronts/deepsyn_opt/fp_mul_e5f10-opt.aig --top fp_mul_e5f10 --inputs a:16,b:16 --outputs y:16
  # short-hand for the fpmul_f16 benchmark:
  python eval_aig.py pareto_fronts/deepsyn_opt/fp_mul_e5f10-opt.aig --benchmark fpmul_f16
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from core.cost import PPADelayCost
from core.correctness import evaluate_correctness


def parse_port_spec(spec: str) -> list[tuple[str, int]]:
    """Parse 'a:16,b:16' -> [('a',16),('b',16)]."""
    out = []
    for part in spec.split(","):
        name, _, width = part.partition(":")
        out.append((name.strip(), int(width)))
    return out


def aig_to_flat_verilog(aig_path: Path, out_v: Path) -> Path:
    """Use yosys-abc to dump a flat verilog netlist from an AIGER file."""
    cmd = ["yosys-abc", "-c",
           f"read_aiger {aig_path}; write_verilog {out_v}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_v.exists():
        raise RuntimeError(
            f"yosys-abc failed:\n{res.stdout}\n{res.stderr}"
        )
    return out_v


def rename_flat_module(flat_v: Path, new_name: str) -> str:
    """Read flat verilog, rename its (single, ABC-emitted) module to *new_name*.

    ABC writes a module named after the input file path, escaped with a leading
    backslash, e.g. `module \\/abs/path/file.aig (...);`. We rewrite that line
    to `module <new_name>_flat (...);` and return the new module name.
    """
    text = flat_v.read_text()
    flat_name = new_name + "_flat"
    # Replace the first 'module <anything> (' line.
    import re
    text2, n = re.subn(
        r"^module\s+\S+\s*\(",
        f"module {flat_name} (",
        text, count=1, flags=re.MULTILINE,
    )
    if n != 1:
        raise RuntimeError("Could not find module declaration in flat verilog")
    flat_v.write_text(text2)
    return flat_name


def pin_pad(flat_text: str) -> tuple[int, int]:
    """Digit width abc used for pi/po names — it pads to the port count, so it
    varies with design size and must be read off the netlist, not assumed."""
    import re
    pi = {len(d) for d in re.findall(r"\bpi(\d+)\b", flat_text)}
    po = {len(d) for d in re.findall(r"\bpo(\d+)\b", flat_text)}
    if len(pi) > 1 or len(po) > 1:
        raise RuntimeError(f"inconsistent abc pin-name widths: pi={pi} po={po}")
    return (pi.pop() if pi else 2), (po.pop() if po else 2)


def flat_clock_port(flat_text: str) -> str | None:
    """Name of the flat module's clock port, or None if the AIG is combinational.
    abc emits `module run (clock, pi000, ...)` when the AIG carries latches."""
    import re
    m = re.search(r"^module\s+\S+\s*\((.*?)\)\s*;", flat_text, re.S | re.M)
    if not m:
        return None
    ports = [p.strip() for p in m.group(1).split(",")]
    return next((p for p in ports if p in ("clock", "clk")), None)


def emit_wrapper_from_map(
    flat_module: str,
    top_module: str,
    map_text: str,
    inputs: list[tuple[str, int]],
    outputs: list[tuple[str, int]],
    pi_pad: int = 2,
    po_pad: int = 2,
    clock_port: str | None = None,
) -> str:
    """Like emit_wrapper, but PI/PO order comes from yosys `write_aiger -map`
    output (lines `input <idx> <bit> <port>` / `output <idx> <bit> <port>`),
    which is authoritative — spec order and alphabetical order are both wrong
    in general (PI order follows the design's internal wire creation order).

    Sequential AIGs: the clock is BOTH a primary input (unused by the logic) and
    the latch clock abc exposes as a separate port, so it is wired to both."""
    pis, pos, clk_pi = {}, {}, None
    for line in map_text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in ("input", "output"):
            idx, bit, name = int(parts[1]), int(parts[2]), parts[3]
            if parts[0] == "input":
                if name == "clk":
                    clk_pi = idx          # clock PI, not one of the data ports
                else:
                    pis[idx] = (name, bit)
            else:
                pos[idx] = (name, bit)
    total_in = sum(w for _, w in inputs)
    total_out = sum(w for _, w in outputs)
    if len(pis) != total_in or len(pos) != total_out:
        raise RuntimeError(
            f"map file has {len(pis)} PIs / {len(pos)} POs, "
            f"spec says {total_in} / {total_out}")
    seq = clock_port is not None or clk_pi is not None
    port_decl = ", ".join((["clk"] if seq else [])
                          + [n for n, _ in inputs] + [n for n, _ in outputs])
    lines = [
        f"// Auto-generated wrapper for {top_module} (port order from aiger map)",
        f"module {top_module}({port_decl});",
    ]
    if seq:
        lines.append("  input clk;")
    for name, w in inputs:
        lines.append(f"  input  [{w-1}:0] {name};")
    for name, w in outputs:
        lines.append(f"  output [{w-1}:0] {name};")
    lines.append("")
    pi_args = ([f".{clock_port}(clk)"] if clock_port else [])
    if clk_pi is not None:
        # Not a second clock: aiger latches clock implicitly, so the clk PI is
        # dead — driven only to keep it from floating. `.clock` is the real one.
        pi_args.append(f".pi{clk_pi:0{pi_pad}d}(clk)")
    pi_args += [f".pi{i:0{pi_pad}d}({pis[i][0]}[{pis[i][1]}])" for i in sorted(pis)]
    po_args = [f".po{i:0{po_pad}d}({pos[i][0]}[{pos[i][1]}])" for i in sorted(pos)]
    lines.append(f"  {flat_module} u_aig (")
    lines.append("    " + ",\n    ".join(pi_args + po_args))
    lines.append("  );")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def emit_wrapper(
    flat_module: str,
    top_module: str,
    inputs: list[tuple[str, int]],
    outputs: list[tuple[str, int]],
    msb_first: bool,
    pi_pad: int = 2,
    po_pad: int = 2,
) -> str:
    """Build a wrapper module that maps named buses to pi00..pi<N>/po00..po<M>.

    Bit-ordering: by default LSB-first within a bus (bit 0 -> first PI for that
    bus), matching yosys' default flattening order. Pass msb_first=True to flip.
    """
    total_in = sum(w for _, w in inputs)
    total_out = sum(w for _, w in outputs)

    port_decl = ", ".join([n for n, _ in inputs] + [n for n, _ in outputs])
    lines = [
        f"// Auto-generated wrapper for {top_module}",
        f"module {top_module}({port_decl});",
    ]
    for name, w in inputs:
        lines.append(f"  input  [{w-1}:0] {name};")
    for name, w in outputs:
        lines.append(f"  output [{w-1}:0] {name};")
    lines.append("")
    # Build the connection list in pi00..pi<N-1>, po00..po<M-1> order.
    pi_args = []
    idx = 0
    for name, w in inputs:
        bits = range(w - 1, -1, -1) if msb_first else range(w)
        for b in bits:
            pi_args.append(f".pi{idx:0{pi_pad}d}({name}[{b}])")
            idx += 1
    po_args = []
    idx = 0
    for name, w in outputs:
        bits = range(w - 1, -1, -1) if msb_first else range(w)
        for b in bits:
            po_args.append(f".po{idx:0{po_pad}d}({name}[{b}])")
            idx += 1
    lines.append(f"  {flat_module} u_aig (")
    lines.append("    " + ",\n    ".join(pi_args + po_args))
    lines.append("  );")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


# Map known benchmarks to (top_module, inputs, outputs).
BENCHMARK_PORTS: dict[str, dict] = {
    "fpmul_f16": {
        "top": "fp_mul_e5f10",
        "inputs": [("a", 16), ("b", 16)],
        "outputs": [("y", 16)],
    },
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("aig", type=Path, help="Path to .aig file")
    p.add_argument("--top", default=None,
                   help="Top module name to wrap to (overrides --benchmark)")
    p.add_argument("--inputs", default=None,
                   help="Input port spec, e.g. 'a:16,b:16'")
    p.add_argument("--outputs", default=None,
                   help="Output port spec, e.g. 'y:16'")
    p.add_argument("--benchmark", default=None,
                   help="Benchmark name from benchmarks/ to derive ports/tb")
    p.add_argument("--msb-first", action="store_true",
                   help="Use MSB-first bit ordering inside buses (default LSB-first)")
    p.add_argument("--workdir", type=Path, default=None,
                   help="Working directory (default: a fresh tempdir, removed on exit)")
    p.add_argument("--target-delay", type=float, default=500.0,
                   help="Target delay in ps for PPA (default: 500)")
    p.add_argument("--technology", default="asap7",
                   help="Process tech: asap7, nangate45, freepdk45 (default: asap7)")
    p.add_argument("--ppa-timeout", type=int, default=600,
                   help="PPA timeout in seconds (default: 600)")
    p.add_argument("--with-sim", action="store_true",
                   help="Also copy tb.sv + .dat from the benchmark and run verilator")
    p.add_argument("--keep-workdir", action="store_true",
                   help="Keep the workdir after eval (only meaningful with --workdir)")
    p.add_argument("--json", type=Path, default=None, metavar="PATH",
                   help="Write JSON result to PATH")
    args = p.parse_args()

    aig = args.aig.resolve()
    if not aig.exists():
        sys.exit(f"AIG not found: {aig}")

    # Resolve top + ports
    bench_dir = None
    if args.benchmark:
        bench_dir = (Path(__file__).resolve().parent / "benchmarks" / args.benchmark).resolve()
        if not bench_dir.is_dir():
            sys.exit(f"Benchmark dir not found: {bench_dir}")
        if args.benchmark not in BENCHMARK_PORTS:
            sys.exit(f"Benchmark '{args.benchmark}' not in BENCHMARK_PORTS table; "
                     f"pass --top/--inputs/--outputs explicitly")
        cfg = BENCHMARK_PORTS[args.benchmark]
        top = args.top or cfg["top"]
        inputs = parse_port_spec(args.inputs) if args.inputs else cfg["inputs"]
        outputs = parse_port_spec(args.outputs) if args.outputs else cfg["outputs"]
    else:
        if not (args.top and args.inputs and args.outputs):
            sys.exit("Pass --benchmark or all of --top, --inputs, --outputs")
        top = args.top
        inputs = parse_port_spec(args.inputs)
        outputs = parse_port_spec(args.outputs)

    # Workdir setup: explicit --workdir is kept; otherwise use a tempdir
    # that we clean up on exit.
    tmp_workdir: tempfile.TemporaryDirectory | None = None
    if args.workdir:
        workdir = args.workdir.resolve()
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        tmp_workdir = tempfile.TemporaryDirectory(prefix=f"aig_eval_{aig.stem}_")
        workdir = Path(tmp_workdir.name).resolve()

    print(f"Workdir: {workdir}")
    print(f"AIG:     {aig}")
    print(f"Top:     {top}")
    print(f"Inputs:  {inputs}  (total {sum(w for _,w in inputs)} bits)")
    print(f"Outputs: {outputs}  (total {sum(w for _,w in outputs)} bits)")
    print(f"Bit order: {'MSB-first' if args.msb_first else 'LSB-first'}")

    # Step 1: AIG -> flat verilog via yosys-abc
    flat_v = workdir / "design_flat.v"
    aig_to_flat_verilog(aig, flat_v)
    flat_module = rename_flat_module(flat_v, top)
    print(f"Flat module: {flat_module}")

    # Step 2: wrapper verilog
    pi_pad, po_pad = pin_pad(flat_v.read_text())
    wrapper_text = emit_wrapper(flat_module, top, inputs, outputs,
                                args.msb_first, pi_pad, po_pad)
    wrapper_v = workdir / "design.v"
    # Combine wrapper + flat so a single file contains both modules.
    wrapper_v.write_text(wrapper_text + "\n" + flat_v.read_text())
    flat_v.unlink()
    print(f"Wrote:   {wrapper_v}")

    # Step 3: optionally copy tb.sv + vectors.dat
    if args.with_sim:
        if bench_dir is None:
            sys.exit("--with-sim requires --benchmark")
        for name in ("tb.sv", "vectors.dat"):
            src = bench_dir / name
            if src.exists():
                shutil.copy2(src, workdir / name)
                print(f"Copied:  {src.name}")

    # Step 4: run PPA. Use PPADelayCost; the result.stats dict contains
    # both area and delay regardless of which subclass we instantiate.
    print("\nRunning PPA (yosys + OpenROAD STA)...")
    metric = PPADelayCost(target_delay=args.target_delay,
                          ppa_timeout=args.ppa_timeout,
                          technology=args.technology)
    t0 = time.monotonic()
    cost = metric.evaluate(workdir, top_module=top, design_file=wrapper_v)
    dur = time.monotonic() - t0

    # Step 5: optionally run RTL simulation separately
    correctness = None
    if args.with_sim and (workdir / "tb.sv").exists():
        print("\nRunning verilator simulation...")
        correctness = evaluate_correctness(workdir, design_file=wrapper_v)

    # Report
    print("\n=== PPA Result ===")
    if cost.ok:
        area = cost.stats.get("area")
        delay = cost.stats.get("delay")
        power = cost.stats.get("power")
        worst_slack = cost.stats.get("worst_slack")
        print(f"  area:        {area}")
        print(f"  delay (ps):  {delay}")
        print(f"  power:       {power}")
        print(f"  worst_slack: {worst_slack}")
        print(f"  target_delay: {cost.stats.get('target_delay')}")
        print(f"  duration:    {dur:.1f}s")
    else:
        print(f"  FAILED: {cost.error}")

    if correctness is not None:
        print("\n=== Simulation ===")
        print(f"  lint_ok: {correctness.lint_ok}")
        print(f"  sim_ok:  {correctness.sim_ok}")
        print(f"  checks:  {correctness.passed_checks}/{correctness.total_checks}")
        if not correctness.sim_ok:
            print(f"  sim_stderr: {correctness.sim_stderr[:300]}")

    if args.json is not None:
        out = {
            "aig": str(aig),
            "top": top,
            "ok": cost.ok,
            "area": cost.stats.get("area"),
            "delay": cost.stats.get("delay"),
            "power": cost.stats.get("power"),
            "worst_slack": cost.stats.get("worst_slack"),
            "target_delay": cost.stats.get("target_delay"),
            "error": cost.error or None,
            "duration_s": round(dur, 1),
        }
        if correctness is not None:
            out["sim"] = {
                "lint_ok": correctness.lint_ok,
                "sim_ok": correctness.sim_ok,
                "passed_checks": correctness.passed_checks,
                "total_checks": correctness.total_checks,
            }
        json_path = args.json.resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(out, indent=2))
        print(f"\nWrote JSON: {json_path}")

    rc = 0 if cost.ok else 1
    if tmp_workdir is not None and not args.keep_workdir:
        tmp_workdir.cleanup()
    sys.exit(rc)


if __name__ == "__main__":
    main()

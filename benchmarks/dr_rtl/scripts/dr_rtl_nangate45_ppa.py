#!/usr/bin/env python3
"""Extract nangate45 PPA (area + delay) for every `benchmarks/dr_rtl/*/` starting
point, at a fixed `target_delay`.

Default `target_delay = 100 ps` (= 0.1 ns). Units:
  - `target_delay` is passed to abc as ps (template.py:116).
  - The .lib file declares `time_unit "1 ns"` — STA reports in ns, then
    `lib_time_to_ps` converts back to ps before returning.
  - `delay` field in the returned dict is therefore always **picoseconds**.

Two-pass flow:
  1. Primary: `tech_eval.get_ppa(..., technology="nangate45")` — works for most
     designs. Uses yosys `synth` (no flatten) + `dfflibmap` + `abc` + OpenROAD STA.
  2. Fallback (only if primary STA returns a syntax error): re-run yosys with
     `synth -flatten` + `clean -purge` + `write_verilog -noattr -simple-lhs`,
     then post-process the netlist to (a) drop wire/reg duplicates of port
     declarations, (b) convert remaining top-level `reg X;` to `wire X;`
     (the netlist is purely structural after abc; the `reg` keyword is
     a yosys-emission quirk OpenROAD's parser rejects).

Designs that still fail after the fallback are reported as N/A with the
underlying error. Common causes:
  - **Inferred latches on register-mapped read paths** (uart's `read_data`,
    spi2's `read_data` — `always @* if (re) Y = X;` with no else clause).
    Yosys keeps these as `$_DLATCH_*` cells; Nangate45 has no transparent
    latch cell to map them to; the netlist retains the `always` block which
    OpenROAD's `read_verilog` (structural-only) rejects.
  - **Memory-array-driven async resets** (fifo's `dataOut <= mem.FIFO[0][0]`
    on `negedge rst`). Yosys can't decompose a reset value that comes from
    memory contents into Nangate cells (DFFR/DFFS only reset to 0/1); the
    flop emits as an `always @(posedge clk, negedge rst)` block.

Outputs:
  1. JSON dump at `benchmarks/dr_rtl/eval_nangate45_ppa.json`.
  2. Markdown table on stdout.

Usage:
  python benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py
  python benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py --target-delay-ps 100 --processes 4
  python benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py --case ticket --case controller
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

BENCH_ROOT = Path(__file__).resolve().parent.parent  # benchmarks/dr_rtl/
LIB = ("/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/"
       "NangateOpenCellLibrary_typical.lib")


def _starting_point(case_dir: Path) -> Optional[Path]:
    for ext in ("v", "sv"):
        p = case_dir / "context" / f"starting_point.{ext}"
        if p.exists():
            return p
    return None


def _fix_netlist(path: Path) -> int:
    """Post-process a yosys netlist for OpenROAD `read_verilog` compatibility.

    Drops `wire`/`reg` duplicates of port declarations and converts
    remaining top-level `reg X;` to `wire X;` (after abc the netlist is
    purely structural, so reg is just a yosys-emission quirk).
    """
    IDENT = r'(?:\w+|\\\S+\s)'
    text = path.read_text()
    out, cur_ports, fixed = [], set(), 0
    for line in text.splitlines(keepends=True):
        if re.match(r'^\s*module\s+\w+\s*\(', line):
            cur_ports = set()
        if re.match(r'^\s*endmodule', line):
            cur_ports = set()
        m_port = re.match(rf'^\s*(?:input|output)\s+(?:\[\d+:\d+\]\s+)?({IDENT});', line)
        if m_port:
            cur_ports.add(m_port.group(1).rstrip())
            out.append(line); continue
        m_dup = re.match(rf'^(\s*)(?:wire|reg)\s+(?:\[\d+:\d+\]\s+)?({IDENT});', line)
        if m_dup and m_dup.group(2).rstrip() in cur_ports:
            fixed += 1; continue
        m_reg = re.match(rf'^(\s*)reg\s+(\[\d+:\d+\]\s+)?({IDENT});', line)
        if m_reg:
            fixed += 1
            out.append(f"{m_reg.group(1)}wire {m_reg.group(2) or ''}{m_reg.group(3)};\n")
            continue
        out.append(line)
    path.write_text("".join(out))
    return fixed


def _fallback_synth_and_sta(case: str, src: Path, top: str,
                             target_delay_ps: int, worker: Path) -> dict:
    """Re-run yosys with `synth -flatten` + post-process netlist + STA."""
    ys = worker / "yosys_flat.ys"
    ys.write_text(f"""read_verilog -sv {src}
synth -top {top} -flatten
dfflibmap -liberty {LIB}
abc -D {target_delay_ps} -constr {worker}/constr.sdc -liberty {LIB}
clean -purge
write_verilog -noattr -simple-lhs {worker}/netlist.v
""")
    r = subprocess.run(["yosys", str(ys)], capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": f"yosys fallback: {r.stderr[-200:]}"}

    n_fixed = _fix_netlist(worker / "netlist.v")
    sta = subprocess.run(["openroad", "-exit", str(worker / "sta.tcl")],
                          capture_output=True, text=True)
    (worker / "sta_out.log").write_text(sta.stdout)
    if "STA-0171" in sta.stdout or "Error:" in sta.stdout:
        err = next((l for l in sta.stdout.splitlines() if "ERROR" in l or "Error" in l),
                   "unknown STA error")
        return {"error": f"STA after fallback ({n_fixed} netlist fixes): {err.strip()}"}

    delay = area = power = ws = None
    for line in sta.stdout.splitlines():
        w = line.split()
        if not w: continue
        if w[0] == "wns": delay = float(w[1])
        if w[0] == "worst" and len(w) > 1 and w[1] == "slack": ws = float(w[-1])
        if w[0] == "design_area_precise": area = float(w[1])
        if w[0] == "Total": power = float(w[-2])
    if delay is None or area is None:
        return {"error": f"could not parse PPA after fallback (delay={delay}, area={area})"}

    return {
        "delay_ps": delay * 1000.0,   # ns → ps
        "area_um2": area,
        "power_w": power,
        "worst_slack_ns": ws,
        "used_fallback": True,
    }


def _run_one(case: str, target_delay_ps: int) -> dict:
    from tech_eval.ppa_extract.core.ppa_extraction import get_ppa

    case_dir = BENCH_ROOT / case
    md = json.loads((case_dir / "metadata.json").read_text())
    src = _starting_point(case_dir)
    if src is None:
        return {"case": case, "error": "no starting_point.v/.sv in context/"}

    worker = Path(f"/tmp/dr_rtl_ppa_{case}_d{target_delay_ps}")

    try:
        r = get_ppa(
            rtl_path=str(src),
            target_delay=target_delay_ps,
            worker_path=str(worker),
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
        # First-pass failed (typically STA-0171 syntax error on yosys netlist).
        # Try the fallback flow: synth -flatten + post-process.
        first_err = f"{type(e).__name__}: {e}"
        fb = _fallback_synth_and_sta(case, src, md["module_name"],
                                      target_delay_ps, worker)
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
    return sorted(
        d.name for d in BENCH_ROOT.iterdir()
        if d.is_dir() and (d / "metadata.json").exists()
    )


def _markdown_table(rows: list[dict], target_delay_ps: int) -> str:
    lines = []
    lines.append(f"### Nangate45 PPA at `target_delay = {target_delay_ps} ps` "
                 f"(= {target_delay_ps/1000:.3f} ns)")
    lines.append("")
    lines.append("| Case | Module | Delay (ps) | Area (μm²) | Power (W) | Worst slack (ns) | Flow |")
    lines.append("|---|---|---:|---:|---:|---:|:---|")
    for r in rows:
        flow = "fallback" if r.get("used_fallback") else "stock"
        if "error" in r:
            lines.append(f"| `{r['case']}` | `{r.get('module', '?')}` | "
                         f"— | — | — | — | N/A — {r['error'][:60]}… |")
            continue
        ws = r.get("worst_slack_ns")
        ws_str = f"{ws:+.2f}" if ws is not None else "—"
        lines.append(
            f"| `{r['case']}` | `{r['module']}` | "
            f"{r['delay_ps']:.1f} | {r['area_um2']:.1f} | "
            f"{r['power_w']:.2e} | {ws_str} | {flow} |"
        )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-delay-ps", type=int, default=100,
                   help="abc target delay in picoseconds (default: 100 = 0.1 ns)")
    p.add_argument("--case", action="append", default=None,
                   help="Run only this case (repeatable).")
    p.add_argument("--processes", type=int, default=4)
    p.add_argument("--out-json", default=str(BENCH_ROOT / "eval_nangate45_ppa.json"))
    args = p.parse_args()

    cases = args.case if args.case else _discover_cases()
    print(f"Running nangate45 PPA on {len(cases)} cases at "
          f"target_delay={args.target_delay_ps} ps "
          f"(= {args.target_delay_ps/1000:.3f} ns):", file=sys.stderr)

    if args.processes <= 1 or len(cases) <= 1:
        results = [_run_one(c, args.target_delay_ps) for c in cases]
    else:
        results = []
        with ProcessPoolExecutor(max_workers=args.processes) as pool:
            futs = {pool.submit(_run_one, c, args.target_delay_ps): c for c in cases}
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                if "error" in r:
                    print(f"[FAIL] {r['case']}: {r['error'][:80]}", file=sys.stderr)
                else:
                    tag = "(fb)" if r.get("used_fallback") else "    "
                    print(f"[done {tag}] {r['case']}: delay={r['delay_ps']:.1f}ps "
                          f"area={r['area_um2']:.1f}um²", file=sys.stderr)

    results.sort(key=lambda r: r["case"])
    Path(args.out_json).write_text(json.dumps(
        {"target_delay_ps": args.target_delay_ps, "technology": "nangate45",
         "lib": LIB, "results": results}, indent=2) + "\n")
    print(f"\nWrote: {args.out_json}", file=sys.stderr)
    print()
    print(_markdown_table(results, args.target_delay_ps))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate the unified comparison markdown table in benchmarks/dr_rtl/README.md.

Joins three sources:
  - `benchmarks/dr_rtl/eval_nangate45_ppa.json` — our nangate45 PPA sweep
    (produced by `benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py`).
  - `benchmarks/dr_rtl/<case>/metadata.json:reference` — paper Table 2 values
    (injected by `benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py`).
  - Constant `PAPER_TARGET_DELAY_NS = 0.1` — the synthesis constraint used by
    both the paper and our sweep.

Derived columns:
    delay_ns  = PAPER_TARGET_DELAY_NS − WNS_ns       # for paper rows and ours
    ADP       = delay_ns × area_um2                  # μm²·ns
    ΔWNS      = (|ours_wns|  − |base_wns|)  / |base_wns|  × 100   # paper sign convention
    ΔArea     = ( ours_area  −  base_area)  /  base_area  × 100
    ΔADP      = ( ours_adp   −  base_adp )  /  base_adp   × 100

Note on delay derivation: we use the same `target_delay − WNS` formula for
*all three* columns (ours / paper-base / paper-Dr.RTL) so the ~30 ps setup-time
under-estimate is a constant offset across the row and cancels in the ratio.
This differs slightly from our `eval_nangate45_ppa.json:delay_ps`, which is
the actual STA-reported arrival time (and so includes the cell-specific setup
contribution).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent  # benchmarks/dr_rtl/
PAPER_TARGET_DELAY_NS = 0.1

# Same ordering as eval_verify.json's tier groupings.
ORDER = [
    # Tier 1
    "ticket", "controller", "lstm", "cpu_fsm", "dsp", "datapath",
    # Tier 2
    "vending", "uart", "spi1", "spi2", "communicate", "router", "pcie", "fifo",
    # Tier 3
    "aes", "i2c",
    # Tier 4
    "cpu_pipe", "tv80", "arm_cpu1", "arm_cpu2",
]


def delay_ns(wns_ns):
    return None if wns_ns is None else PAPER_TARGET_DELAY_NS - wns_ns


def adp_um2_ns(wns_ns, area_um2):
    d = delay_ns(wns_ns)
    if d is None or area_um2 is None:
        return None
    return d * area_um2


def pct(ours, ref):
    if ours is None or ref is None or ref == 0:
        return None
    return (ours - ref) / ref * 100


def pct_wns(ours, ref):
    """% delta on absolute WNS values — paper's own sign convention
    (negative = improvement, positive = regression)."""
    if ours is None or ref is None or ref == 0:
        return None
    return (abs(ours) - abs(ref)) / abs(ref) * 100


def f_wns(v):
    return f"{v:+.2f}" if v is not None else "N/A"


def f_area(v):
    if v is None:
        return "N/A"
    return f"{v:.1f}" if isinstance(v, float) else str(v)


def f_adp(v):
    if v is None:
        return "N/A"
    return f"{v:,.1f}" if v < 1000 else f"{v:,.0f}"


def f_pct(v):
    return f"{v:+.1f}%" if v is not None else "N/A"


def main():
    ours_path = BENCH_ROOT / "eval_nangate45_ppa.json"
    ours = {r["case"]: r for r in json.loads(ours_path.read_text())["results"]}

    rows = []
    for case in ORDER:
        md = json.loads((BENCH_ROOT / case / "metadata.json").read_text())
        ref = md["reference"]
        o = ours.get(case, {})

        ours_wns,  ours_area  = o.get("worst_slack_ns"),    o.get("area_um2")
        base_wns,  base_area  = ref["paper_baseline_wns_ns"], ref["paper_baseline_area_um2"]
        drrtl_wns, drrtl_area = ref["paper_drrtl_wns_ns"],    ref["paper_drrtl_area_um2"]

        a_ours  = adp_um2_ns(ours_wns,  ours_area)
        a_base  = adp_um2_ns(base_wns,  base_area)
        a_drrtl = adp_um2_ns(drrtl_wns, drrtl_area)

        rows.append({
            "case": case, "module": md["module_name"],
            "ours_wns": ours_wns,   "base_wns": base_wns,   "drrtl_wns": drrtl_wns,
            "ours_area": ours_area, "base_area": base_area, "drrtl_area": drrtl_area,
            "ours_adp": a_ours,     "base_adp": a_base,     "drrtl_adp": a_drrtl,
            "d_wns":  pct_wns(ours_wns,  base_wns),
            "d_area": pct(ours_area, base_area),
            "d_adp":  pct(a_ours,    a_base),
        })

    print("| Case | Module | "
          "WNS ours (ns) | WNS base (ns) | WNS Dr.RTL (ns) | ΔWNS | "
          "Area ours (μm²) | Area base | Area Dr.RTL | ΔArea | "
          "ADP ours (μm²·ns) | ADP base | ADP Dr.RTL | ΔADP |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(f"| `{r['case']}` | `{r['module']}` | "
              f"{f_wns(r['ours_wns'])} | {f_wns(r['base_wns'])} | {f_wns(r['drrtl_wns'])} | "
              f"{f_pct(r['d_wns'])} | "
              f"{f_area(r['ours_area'])} | {f_area(r['base_area'])} | {f_area(r['drrtl_area'])} | "
              f"{f_pct(r['d_area'])} | "
              f"{f_adp(r['ours_adp'])} | {f_adp(r['base_adp'])} | {f_adp(r['drrtl_adp'])} | "
              f"{f_pct(r['d_adp'])} |")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Inject Dr. RTL paper (arXiv:2604.14989) Table 2 values as a `reference` block
into each `benchmarks/dr_rtl/<case>/metadata.json`.

Values are recorded **verbatim as the paper reports them** — WNS/TNS in
nanoseconds, area in μm² — with no derived/converted fields. The paper's
synthesis constraint (`paper_target_delay_ns = 0.1`, the "tight clock period"
in §setup) is recorded in the same dict so any reader can do the slack→delay
conversion themselves if needed:

    delay_ps = (paper_target_delay_ns − WNS_ns) × 1000          # if you want

We keep our framework's `target_delay_ps = 100` in
`benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py` and `eval_nangate45_ppa.json` aligned with
this paper value, so cross-comparison is apples-to-apples on the constraint.

Each metadata.json gets a `reference` block under the existing keys
(`name`, `module_name`, `cost_metric`, `tb_module`, `source`, …). Pre-existing
`reference` blocks are OVERWRITTEN.
"""
from __future__ import annotations

import json
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent  # benchmarks/dr_rtl/
# Paper's synthesis constraint, from arXiv:2604.14989 §setup:
#   "we use a tight clock period of 0.1 ns to force aggressive synthesis
#    optimization across all paths."
PAPER_TARGET_DELAY_NS = 0.1


# Table 2 from the paper, transcribed verbatim from the layout-preserving
# pdftotext extraction. Field order:
#   (case, paper_design_name, LoC, NoM, n_gate, n_reg,
#    baseline_wns_ns, baseline_tns_ns, baseline_area_um2,
#    drrtl_wns_ns, drrtl_wns_pct,
#    drrtl_tns_ns, drrtl_tns_pct,
#    drrtl_area_um2, drrtl_area_pct,
#    sec_pass_pct)
#
# `case` is our short directory name (benchmarks/dr_rtl/<case>/);
# `paper_design_name` is the literal label the paper uses in its Table 2
# (different from our short name in 1 case: "datapth" → datapath, a typo).
TABLE2 = [
    ("vending",     "vending",      128, 1, 20272,   4, -0.27,   -1.02,  20488,
        -0.09, -66.7,   -0.50, -51.0,  20533,   0.2,  77),
    ("ticket",      "ticket",       134, 1,    56,   6, -0.23,   -1.24,     78,
        -0.09, -60.9,   -0.47, -62.1,     45, -41.8,  65),
    ("lstm",        "lstm",         135, 4,  8379,   0, -6.51, -166.76,  14828,
        -4.86, -25.3, -116.16, -30.3,   4753, -67.9,  83),
    ("dsp",         "dsp",          165, 5,  3345, 196, -2.61, -154.64,   4755,
        -2.59,  -0.8, -147.42,  -4.7,   4751,  -0.1,  83),
    ("communicate", "communicate",  225, 3,  1023, 232, -0.40,  -73.08,   2092,
        -0.26, -35.0,  -58.84, -19.5,   2446,  17.0,  95),
    ("spi1",        "spi1",         332, 2,   647, 131, -0.32,  -33.42,   1208,
        -0.29,  -9.4,  -33.53,   0.3,   1276,   5.7,  63),
    ("cpu_fsm",     "cpu_fsm",      354, 1, 13232, 4163, -0.82, -429.73, 32268,
        -0.61, -25.6, -427.28,  -0.6,  32157,  -0.3,  96),
    ("aes",         "aes",          374, 2, 24294, 1419, -0.70, -913.49, 33755,
        -0.67,  -4.3, -876.71,  -4.0,  33975,   0.7,  81),
    ("fifo",        "fifo",         390, 7, 13740, 4208, -0.54, -2002.10, 36061,
        -0.43, -20.4, -1681.97, -16.0, 36310,   0.7,  96),
    ("spi2",        "spi2",         441, 3,   856, 292, -0.26,  -28.19,   1748,
        -0.25,  -3.8,  -27.75,  -1.6,   1826,   4.5, 100),
    ("uart",        "uart",         447, 4,   851, 135, -0.38,  -23.17,   1272,
        -0.34, -10.5,  -23.08,  -0.4,   1107, -13.0,  87),
    ("controller",  "controller",   528, 1,   213,   8, -0.38,   -2.85,    235,
        -0.33, -13.2,   -2.57,  -9.8,    277,  18.0,  94),
    ("router",      "router",       571, 5,  3036, 609, -0.53, -289.91,   5479,
        -0.46, -13.2, -246.66, -14.9,   5575,   1.8,  92),
    ("cpu_pipe",    "cpu_pipe",     850, 5,  2845, 364, -0.38,  -23.24,   2622,
        -0.11, -71.1,   -2.69, -88.4,   2313, -11.8,  90),
    ("pcie",        "pcie",         923, 7,  1773,  97, -0.79,  -23.83,   2156,
        -0.44, -44.3,  -19.75, -17.1,   1426, -33.9, 100),
    ("datapath",    "datapth",     1065, 7,  6985, 881, -0.88, -513.42,  12137,
        -0.87,  -1.1, -504.00,  -1.8,  12137,   0.0,  92),
    ("i2c",         "i2c",         1036, 3,   723, 128, -0.36,  -26.67,   1290,
        -0.35,  -2.8,  -25.96,  -2.7,   1275,  -1.1,  98),
    ("tv80",        "tv80",        4615, 5,  4431, 359, -1.31, -381.20,   6044,
        -1.22,  -6.9, -362.09,  -5.0,   6200,   2.6,  92),
    ("arm_cpu1",    "arm_cpu1",    2070, 1, 11772, 1222, -5.24, -3148.68, 22172,
        -5.19,  -1.0, -3117.41, -1.0,  22257,   0.4,  56),
    ("arm_cpu2",    "arm_cpu2",    1450, 1,  6132, 736, -1.01, -662.70,  10688,
        -0.92,  -8.9, -619.13,  -6.6,  10995,   2.9,  87),
]


def build_reference(row: tuple) -> dict:
    (_case, paper_name, loc, nom, n_gate, n_reg,
     b_wns, b_tns, b_area,
     d_wns, d_wns_pct, d_tns, d_tns_pct, d_area, d_area_pct,
     sec_pass) = row
    return {
        "paper_source": "arXiv:2604.14989 (Dr. RTL), Table 2",
        "paper_design_name": paper_name,
        # Synthesis-constraint envelope — the paper calls this a "clock
        # period"; we call the same thing target_delay in our scripts.
        # Same number, just two terminologies.
        "paper_target_delay_ns": PAPER_TARGET_DELAY_NS,
        "paper_synthesis_tool": "Synopsys Design Compiler + Nangate 45 nm",
        # Paper-reported design statistics (independent of optimization)
        "paper_loc": loc,
        "paper_num_modules": nom,
        "paper_num_gates_baseline": n_gate,
        "paper_num_registers_baseline": n_reg,
        # Commercial-synthesis baseline column — verbatim from Table 2
        "paper_baseline_wns_ns": b_wns,
        "paper_baseline_tns_ns": b_tns,
        "paper_baseline_area_um2": b_area,
        # w/ Dr. RTL Optimization column — verbatim, including the paper's
        # reported %improvement vs baseline (negative = improvement).
        "paper_drrtl_wns_ns": d_wns,
        "paper_drrtl_wns_improvement_pct": d_wns_pct,
        "paper_drrtl_tns_ns": d_tns,
        "paper_drrtl_tns_improvement_pct": d_tns_pct,
        "paper_drrtl_area_um2": d_area,
        "paper_drrtl_area_improvement_pct": d_area_pct,
        "paper_drrtl_sec_pass_pct": sec_pass,
    }


def main():
    n_updated = 0
    n_missing = 0
    for row in TABLE2:
        case = row[0]
        md_path = BENCH_ROOT / case / "metadata.json"
        if not md_path.exists():
            print(f"[SKIP] {case}: metadata.json not found")
            n_missing += 1
            continue
        md = json.loads(md_path.read_text())
        md["reference"] = build_reference(row)
        md_path.write_text(json.dumps(md, indent=2) + "\n")
        ref = md["reference"]
        print(f"[ok] {case:14s}  "
              f"baseline: WNS={ref['paper_baseline_wns_ns']:+.2f}ns "
              f"TNS={ref['paper_baseline_tns_ns']:+.2f}ns "
              f"area={ref['paper_baseline_area_um2']}um²  |  "
              f"drrtl: WNS={ref['paper_drrtl_wns_ns']:+.2f}ns "
              f"area={ref['paper_drrtl_area_um2']}um²")
        n_updated += 1
    print(f"\nUpdated {n_updated}/{len(TABLE2)} metadata.json files "
          f"({n_missing} missing).")


if __name__ == "__main__":
    main()

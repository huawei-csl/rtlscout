#!/usr/bin/env python3
"""Render a side-by-side markdown table from run_rtl_rewriter.py's summary.json.

Input:  the summary JSON written by `experiments/run_rtl_rewriter.py`.
Output: markdown to stdout (or --out <path>).

Two tables are rendered per summary, one per metric. The one matching the
summary's `cost_metric` (i.e. what the agent was told to optimise) comes
first; the other follows. Both metrics are always measured by the runner
and carried in the summary, so the second table is free.

Columns per table (either ``w`` for wires or ``c`` for cells):
    Case | Module
    Vstart | Vopt  | Δ V
    Sstart | Sopt  | Δ S
    Δ S/V-ref     ← spirehdl opt vs. verilog reference baseline
    V | S         ← correctness flags (✓ / ✗ / err)

Run directories follow in a separate mini-table so you can jump straight
into `chat_log.txt` / `best_design/` for any case.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_rtlr_targets(benchmark_path: Optional[str]) -> Dict[str, Optional[int]]:
    """Read RTLRewriter-paper (and our reproduction of) the optimized target.

    Prefer reproduced numbers (same Yosys flow as our measurements). Fall back
    to the paper's claim, then to None. Returns ``{"wires": ..., "cells": ...}``.
    """
    if not benchmark_path:
        return {"wires": None, "cells": None}
    meta = REPO_ROOT / benchmark_path / "metadata.json"
    if not meta.exists():
        return {"wires": None, "cells": None}
    try:
        ref = (json.loads(meta.read_text()) or {}).get("reference", {}) or {}
    except Exception:
        return {"wires": None, "cells": None}
    return {
        "wires": ref.get("reproduced_rtlr_wires") or ref.get("paper_rtlr_wires"),
        "cells": ref.get("reproduced_rtlr_cells") or ref.get("paper_rtlr_cells"),
    }


def _fmt_int(x: Optional[int]) -> str:
    return "—" if x is None else str(x)


def _fmt_pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def _ok_flag(rec: Dict[str, Any]) -> str:
    if rec is None:
        return "—"
    if rec.get("passed"):
        return "✓"
    if rec.get("status") == "error":
        return "err"
    return "✗"


def _case_sort_key(case_id: str) -> int:
    return int(case_id.replace("case", ""))


# Metric key lookup --------------------------------------------------------
# Maps a short metric name to the corresponding fields on each per-lang rec.
METRIC_FIELDS = {
    "wires": {
        "suffix":    "w",
        "full":      "wires",
        "baseline":  "baseline_wires",
        "best":      "best_wires",
        "delta":     "delta_wires_pct",
        "cost_name": "yosys_wires",
    },
    "cells": {
        "suffix":    "c",
        "full":      "cells",
        "baseline":  "baseline_cells",
        "best":      "best_cells",
        "delta":     "delta_cells_pct",
        "cost_name": "yosys_cells",
    },
}


def _primary_metric_from_summary(summary: Dict[str, Any]) -> str:
    """The agent's optimised metric — determines which table comes first."""
    cost = summary.get("cost_metric", "yosys_cells")
    if cost == "yosys_wires":
        return "wires"
    return "cells"  # default to cells for any other cost metric


def _render_metric_table(summary: Dict[str, Any], metric: str) -> str:
    """Render one comparison table (wires or cells)."""
    fields = METRIC_FIELDS[metric]
    suf = fields["suffix"]
    results = summary.get("results", {})

    out: List[str] = []
    out.append(f"### {metric.capitalize()} ({fields['cost_name']})")
    out.append("")

    headers = ["Case", "Module",
               f"Vstart {suf}", f"RTLR {suf}",
               f"Vopt {suf}", f"Δ V {suf}", f"Δ V/RTLR {suf}",
               f"Sstart {suf}", f"Sopt {suf}", f"Δ S {suf}", f"Δ S/RTLR {suf}",
               f"Δ S/V-ref {suf}",
               "V", "S"]
    align = [":---", ":---",
             "---:", "---:",
             "---:", "---:", "---:",
             "---:", "---:", "---:", "---:",
             "---:",
             ":---:", ":---:"]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(align) + "|")

    totals = {"v_start": 0, "v_opt": 0, "s_start": 0, "s_opt": 0,
              # RTLR has per-language populations (the cases where the
              # corresponding opt accumulated), to keep the sum-row delta honest.
              "rtlr_v": 0, "rtlr_s": 0}
    # Per-case percentages, for an arithmetic-mean row alongside the sum.
    # Mean-of-percentages is usually the more honest cross-case summary than
    # the sum-based delta, because it isn't dominated by the single largest
    # case (e.g. case2 at ~11k cells would swamp any small-case contribution).
    pct_lists = {"v_d": [], "v_rtlr": [], "s_d": [], "s_rtlr": [], "s_vref": []}
    has_any = False

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        v = per_lang.get("verilog",   {})
        s = per_lang.get("spirehdl", {})
        module = v.get("module_name") or s.get("module_name") or (
            v.get("benchmark_name") or "")

        v_start = v.get(fields["baseline"])
        v_opt   = v.get(fields["best"])
        v_d     = v.get(fields["delta"])
        s_start = s.get(fields["baseline"])
        s_opt   = s.get(fields["best"])
        s_d     = s.get(fields["delta"])
        s_vref  = ((s_opt - v_start) / v_start * 100.0
                   if v_start not in (None, 0) and s_opt is not None else None)
        rtlr = _load_rtlr_targets(v.get("benchmark_path"))[metric]
        v_rtlr = ((v_opt - rtlr) / rtlr * 100.0
                  if rtlr not in (None, 0) and v_opt is not None else None)
        s_rtlr = ((s_opt - rtlr) / rtlr * 100.0
                  if rtlr not in (None, 0) and s_opt is not None else None)

        row = [case_id, f"`{module}`",
               _fmt_int(v_start), _fmt_int(rtlr),
               _fmt_int(v_opt), _fmt_pct(v_d), _fmt_pct(v_rtlr),
               _fmt_int(s_start), _fmt_int(s_opt), _fmt_pct(s_d), _fmt_pct(s_rtlr),
               _fmt_pct(s_vref),
               _ok_flag(v), _ok_flag(s)]
        out.append("| " + " | ".join(row) + " |")

        if v.get("passed") and None not in (v_start, v_opt):
            totals["v_start"] += v_start; totals["v_opt"] += v_opt
            if rtlr is not None:
                totals["rtlr_v"] += rtlr
            has_any = True
        if s.get("passed") and None not in (s_start, s_opt):
            totals["s_start"] += s_start; totals["s_opt"] += s_opt
            if rtlr is not None:
                totals["rtlr_s"] += rtlr
            has_any = True

        for key, val in (("v_d", v_d), ("v_rtlr", v_rtlr),
                         ("s_d", s_d), ("s_rtlr", s_rtlr),
                         ("s_vref", s_vref)):
            if val is not None:
                pct_lists[key].append(val)

    if has_any:
        def _pct(start, opt):
            return None if not start else (opt - start) / start * 100.0

        def _mean(xs):
            return None if not xs else sum(xs) / len(xs)

        v_d      = _pct(totals["v_start"], totals["v_opt"])
        s_d      = _pct(totals["s_start"], totals["s_opt"])
        v_rtlr_s = _pct(totals["rtlr_v"],  totals["v_opt"])
        s_rtlr_s = _pct(totals["rtlr_s"],  totals["s_opt"])
        # Cross-language sum: spirehdl opt vs verilog-ref start. Only
        # meaningful when every accumulated case passed on BOTH sides.
        vref_d = _pct(totals["v_start"], totals["s_opt"])
        rtlr_sum_display = totals["rtlr_v"] or totals["rtlr_s"]  # 0 → "0" which is fine

        # Sum row: absolute totals + deltas computed from those totals. The
        # per-case-weighted delta; dominated by the largest case.
        row = ["**sum**", "",
               f"**{totals['v_start']}**", f"**{rtlr_sum_display}**",
               f"**{totals['v_opt']}**", f"**{_fmt_pct(v_d)}**", f"**{_fmt_pct(v_rtlr_s)}**",
               f"**{totals['s_start']}**", f"**{totals['s_opt']}**", f"**{_fmt_pct(s_d)}**", f"**{_fmt_pct(s_rtlr_s)}**",
               f"**{_fmt_pct(vref_d)}**",
               "", ""]
        out.append("| " + " | ".join(row) + " |")

        # Mean row: arithmetic mean of per-case Δ percentages — equal weight
        # per case, independent of case size. Usually more informative than
        # the sum-row delta when the case sizes span orders of magnitude.
        row = ["**mean Δ**", "",
               "", "",      # Vstart, RTLR — no mean of absolute counts
               "", f"**{_fmt_pct(_mean(pct_lists['v_d']))}**",
               f"**{_fmt_pct(_mean(pct_lists['v_rtlr']))}**",
               "", "",      # Sstart, Sopt
               f"**{_fmt_pct(_mean(pct_lists['s_d']))}**",
               f"**{_fmt_pct(_mean(pct_lists['s_rtlr']))}**",
               f"**{_fmt_pct(_mean(pct_lists['s_vref']))}**",
               "", ""]
        out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


def render_table(summary: Dict[str, Any]) -> str:
    results = summary.get("results", {})
    cost_metric = summary.get("cost_metric", "?")
    model = summary.get("model", "?")

    out: List[str] = []
    out.append(f"**Model:** `{model}` · **Cost metric:** `{cost_metric}` · "
               f"**Max steps:** {summary.get('max_steps')} · "
               f"**Duration:** {summary.get('total_duration_s', 0)/60:.1f} min")
    out.append("")
    out.append("`Δ S/V-ref` = spirehdl opt vs. verilog reference baseline "
               "— the honest cross-language comparison (`Δ S` is vs "
               "spirehdl's own, often weaker, start).")
    out.append("")

    primary = _primary_metric_from_summary(summary)
    secondary = "wires" if primary == "cells" else "cells"

    out.append(_render_metric_table(summary, primary))
    out.append("")
    out.append(_render_metric_table(summary, secondary))
    out.append("")

    # Run-directory pointers (once, shared by both tables).
    out.append("## Run directories")
    out.append("")
    out.append("| Case | Verilog | SpireHDL |")
    out.append("|:---|:---|:---|")
    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        v_wd = per_lang.get("verilog",   {}).get("workdir") or "—"
        s_wd = per_lang.get("spirehdl", {}).get("workdir") or "—"
        out.append(f"| {case_id} | `{v_wd}` | `{s_wd}` |")

    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Render a markdown comparison table from a run_rtl_rewriter.py summary.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("summary_json", type=Path,
                        help="Path to the summary.json produced by run_rtl_rewriter.py")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write the table to this file instead of stdout")
    args = parser.parse_args()

    summary = json.loads(args.summary_json.read_text())
    table = render_table(summary)
    if args.out:
        args.out.write_text(table)
        print(f"Wrote table: {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(table)


if __name__ == "__main__":
    main()

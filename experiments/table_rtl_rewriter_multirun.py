#!/usr/bin/env python3
"""Render markdown tables from a rtl_rewriter_multirun summary.json.

Two tables per metric (cells and wires), primary metric first:

1. **Best per case × phase** — one row per case, columns for the *best*
   (= min) value each of (phase 1, phase 2) × (verilog, spirehdl)
   produced, plus per-language Δ phase1→phase2 and the cross-language
   `Δ S/V-ref` (spirehdl phase 2 best vs. verilog reference baseline).

2. **Stats (min / max / mean) per case × phase** — the distribution
   across the N runs inside each phase. Makes it visible when one phase
   has a low variance / high variance or a long tail.

Both metrics (cells and wires) are always measured, so both tables are
always rendered; the summary's ``cost_metric`` determines which is primary.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_rtlr_targets(benchmark_path: Optional[str]) -> Dict[str, Optional[int]]:
    """RTLRewriter-paper target for this case (the number to beat).

    Prefers our reproduction (same Yosys flow) over the paper's raw claim;
    falls back to None if neither is recorded. `transistors` is always None
    (the paper reports cells/wires, not transistor estimates).
    """
    if not benchmark_path:
        return {"wires": None, "cells": None, "transistors": None}
    meta = REPO_ROOT / benchmark_path / "metadata.json"
    if not meta.exists():
        return {"wires": None, "cells": None, "transistors": None}
    try:
        ref = (json.loads(meta.read_text()) or {}).get("reference", {}) or {}
    except Exception:
        return {"wires": None, "cells": None, "transistors": None}
    return {
        "wires": ref.get("reproduced_rtlr_wires") or ref.get("paper_rtlr_wires"),
        "cells": ref.get("reproduced_rtlr_cells") or ref.get("paper_rtlr_cells"),
        "transistors": None,
    }


def _fmt_int(x: Optional[int]) -> str:
    return "—" if x is None else str(x)


def _fmt_float(x: Optional[float]) -> str:
    if x is None:
        return "—"
    if isinstance(x, int) or float(x).is_integer():
        return str(int(x))
    return f"{x:.1f}"


def _fmt_pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def _case_sort_key(case_id: str) -> int:
    return int(case_id.replace("case", ""))


def _upstream_name(benchmark_path: Optional[str]) -> Optional[str]:
    """RTLRewriter-paper upstream directory name from metadata.json (e.g. `add3`).

    Read from ``metadata.source.upstream_name``; much more descriptive than the
    bland Verilog top-module name (`example` for most cases). Returns None if
    metadata.json is missing or doesn't carry the field.
    """
    if not benchmark_path:
        return None
    meta = REPO_ROOT / benchmark_path / "metadata.json"
    if not meta.exists():
        return None
    try:
        src = (json.loads(meta.read_text()) or {}).get("source", {}) or {}
    except Exception:
        return None
    return src.get("upstream_name")


def _case_label(per_lang: Dict[str, Any]) -> str:
    """Per-case display name for the Module column. Prefer the RTLRewriter
    upstream directory name (`add3`, `adder_bit_width`, …) over the bland
    Verilog top-module name (`example`) when the metadata is available.
    """
    v = per_lang.get("verilog", {})
    s = per_lang.get("spirehdl", {})
    upstream = (_upstream_name(v.get("benchmark_path"))
                or _upstream_name(s.get("benchmark_path")))
    if upstream:
        return upstream
    return v.get("module_name") or s.get("module_name") or ""


METRIC_FIELDS = {
    "wires": {"baseline": "baseline_wires", "cost": "yosys_wires"},
    "cells": {"baseline": "baseline_cells", "cost": "yosys_cells"},
    # transistor count is a side-stat captured during the same yosys synth run
    # used for wires/cells (core/cost.py `_YosysStatCost`); the paper has no
    # transistor target, so Δ V/RTLR and Δ S/RTLR show em-dash.
    "transistors": {"baseline": "baseline_transistors", "cost": "transistors_estimate"},
}


def _primary_metric(summary: Dict[str, Any]) -> str:
    cm = summary.get("cost_metric", "yosys_cells")
    if cm == "yosys_wires":
        return "wires"
    if cm in ("yosys_transistors", "transistors"):
        return "transistors"
    return "cells"


def _phase_best(rec: Dict[str, Any], phase: str, metric: str) -> Optional[int]:
    """Best (min) value of ``best_<metric>`` across passed runs in a phase."""
    if not rec:
        return None
    return (rec.get(phase) or {}).get("stats", {}).get(metric, {}).get("min")


def _phase_stats(rec: Dict[str, Any], phase: str, metric: str) -> Dict[str, Any]:
    if not rec:
        return {"min": None, "max": None, "mean": None, "count": 0}
    return ((rec.get(phase) or {}).get("stats", {}) or {}).get(
        metric, {"min": None, "max": None, "mean": None, "count": 0})


def _delta(new: Optional[float], ref: Optional[float]) -> Optional[float]:
    if new is None or ref in (None, 0):
        return None
    return (new - ref) / ref * 100.0


def _mean(xs: List[float]) -> Optional[float]:
    return None if not xs else sum(xs) / len(xs)


# ---------------------------------------------------------------------------
# Table 1: best per case × phase
# ---------------------------------------------------------------------------
def _render_best_table(summary: Dict[str, Any], metric: str) -> str:
    fields = METRIC_FIELDS[metric]
    results = summary.get("results", {})
    has_phase2 = summary.get("phases", 2) >= 2
    # No RTLRewriter target for transistors -> the Δ-vs-reference column
    # compares against each language's own Base (Δ vs B) instead of RTLR.
    vs_base = metric == "transistors"

    out: List[str] = []
    out.append(f"### Best per phase — {metric.capitalize()} ({fields['cost']})")
    out.append("")

    # Columns: Case | Module | Vbase | RTLR | P1 V best | P2 V best | Δ 1→2 V | Δ V/ref |
    #          Sbase | P1 S best | P2 S best | Δ 1→2 S | Δ S/ref | Δ S/V-ref (final best)
    # RTLR is the RTLRewriter paper's claim (the number the agent tries to
    # beat), loaded per-case from benchmarks/rtl_rewriter/case<N>/metadata.json.
    # Δ V/ref and Δ S/ref compare the language's *final* best (phase-2 if
    # present, else phase-1) against RTLR — or against Base when there is no
    # RTLR target (transistors). Negative = beats the reference.
    headers = ["Case", "Module",
               "Vbase", "RTLR",
               "P1 V best"]
    align   = [":---", ":---", "---:", "---:", "---:"]
    if has_phase2:
        headers += ["P2 V best", "Δ 1→2 V"]
        align   += ["---:", "---:"]
    headers += ["Δ V/Base" if vs_base else "Δ V/RTLR",
                "Sbase", "P1 S best"]
    align   += ["---:", "---:", "---:"]
    if has_phase2:
        headers += ["P2 S best", "Δ 1→2 S"]
        align   += ["---:", "---:"]
    headers += ["Δ S/Base" if vs_base else "Δ S/RTLR", "Δ S/V-ref"]
    align   += ["---:", "---:"]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(align) + "|")

    # Absolute-totals accumulator for the sum row; separate rtlr populations
    # per language (only accumulate rtlr when the corresponding opt accumulated).
    totals = {
        "v_base": 0, "v_final": 0, "p1v": 0, "p2v": 0,
        "s_base": 0, "s_final": 0, "p1s": 0, "p2s": 0,
        "rtlr_v": 0, "rtlr_s": 0,
    }
    # Per-case percentages for the mean row (equal weight per case).
    pct_lists = {
        "dv12": [], "ds12": [], "v_rtlr": [], "s_rtlr": [], "svref": [],
    }
    has_any = False

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        v = per_lang.get("verilog",   {})
        s = per_lang.get("spirehdl", {})
        module = _case_label(per_lang)
        v_base = v.get(fields["baseline"])
        s_base = s.get(fields["baseline"])
        p1v = _phase_best(v, "phase1", metric)
        p2v = _phase_best(v, "phase2", metric) if has_phase2 else None
        p1s = _phase_best(s, "phase1", metric)
        p2s = _phase_best(s, "phase2", metric) if has_phase2 else None
        dv12 = _delta(p2v, p1v) if has_phase2 else None
        ds12 = _delta(p2s, p1s) if has_phase2 else None
        # Cross-language delta: SpireHDL P2 best vs Verilog P2 best. Both went
        # through the same Phase 1 + Phase 2 pipeline, so this isolates the
        # language/framework contribution from the agent's contribution. When
        # no phase2 is run, falls back to phase1 on both sides.
        s_final = p2s if has_phase2 and p2s is not None else p1s
        v_final = p2v if has_phase2 and p2v is not None else p1v
        svref = _delta(s_final, v_final)

        rtlr = _load_rtlr_targets(
            v.get("benchmark_path") or s.get("benchmark_path"))[metric]
        # vs.\ RTLR normally; vs.\ the language's own Base when there is no
        # RTLR target (transistors).
        v_rtlr  = _delta(v_final, v_base if vs_base else rtlr)
        s_rtlr  = _delta(s_final, s_base if vs_base else rtlr)

        row = [case_id, f"`{module}`",
               _fmt_int(v_base), _fmt_int(rtlr),
               _fmt_int(p1v)]
        if has_phase2:
            row += [_fmt_int(p2v), _fmt_pct(dv12)]
        row += [_fmt_pct(v_rtlr),
                _fmt_int(s_base), _fmt_int(p1s)]
        if has_phase2:
            row += [_fmt_int(p2s), _fmt_pct(ds12)]
        row += [_fmt_pct(s_rtlr), _fmt_pct(svref)]
        out.append("| " + " | ".join(row) + " |")

        # Accumulators --------------------------------------------------
        if v_base is not None and v_final is not None:
            totals["v_base"]  += v_base
            totals["v_final"] += v_final
            if p1v is not None: totals["p1v"] += p1v
            if has_phase2 and p2v is not None: totals["p2v"] += p2v
            if rtlr is not None: totals["rtlr_v"] += rtlr
            has_any = True
        if s_base is not None and s_final is not None:
            totals["s_base"]  += s_base
            totals["s_final"] += s_final
            if p1s is not None: totals["p1s"] += p1s
            if has_phase2 and p2s is not None: totals["p2s"] += p2s
            if rtlr is not None: totals["rtlr_s"] += rtlr
            has_any = True

        for key, val in (("dv12", dv12), ("ds12", ds12),
                         ("v_rtlr", v_rtlr), ("s_rtlr", s_rtlr),
                         ("svref", svref)):
            if val is not None:
                pct_lists[key].append(val)

    if has_any:
        # `or None` → em-dash when no RTLR target exists (transistors).
        rtlr_sum_display = _fmt_int(totals["rtlr_v"] or totals["rtlr_s"] or None)
        # Δ-vs-reference sum: denominator is the summed Base (Δ vs B) when there
        # is no RTLR target, else the summed RTLR target (Δ vs R).
        v_rtlr_sum = _delta(totals["v_final"],
                            (totals["v_base"] if vs_base else totals["rtlr_v"]) or None)
        s_rtlr_sum = _delta(totals["s_final"],
                            (totals["s_base"] if vs_base else totals["rtlr_s"]) or None)
        dv12_sum = _delta(totals["p2v"] or None, totals["p1v"] or None) if has_phase2 else None
        ds12_sum = _delta(totals["p2s"] or None, totals["p1s"] or None) if has_phase2 else None
        svref_sum = _delta(totals["s_final"], totals["v_final"] or None)

        # Sum row: absolute totals + sum-derived deltas (weighted by case size).
        row = ["**sum**", "",
               f"**{totals['v_base']}**", f"**{rtlr_sum_display}**",
               f"**{totals['p1v']}**"]
        if has_phase2:
            row += [f"**{totals['p2v']}**", f"**{_fmt_pct(dv12_sum)}**"]
        row += [f"**{_fmt_pct(v_rtlr_sum)}**",
                f"**{totals['s_base']}**", f"**{totals['p1s']}**"]
        if has_phase2:
            row += [f"**{totals['p2s']}**", f"**{_fmt_pct(ds12_sum)}**"]
        row += [f"**{_fmt_pct(s_rtlr_sum)}**", f"**{_fmt_pct(svref_sum)}**"]
        out.append("| " + " | ".join(row) + " |")

        # Mean row: arithmetic mean of per-case Δ percentages (equal weight).
        row = ["**mean Δ**", "",
               "", "",       # Vbase, RTLR — no mean of absolute counts
               ""]           # P1 V best
        if has_phase2:
            row += ["",                                   # P2 V best
                    f"**{_fmt_pct(_mean(pct_lists['dv12']))}**"]
        row += [f"**{_fmt_pct(_mean(pct_lists['v_rtlr']))}**",
                "", ""]      # Sbase, P1 S best
        if has_phase2:
            row += ["",                                   # P2 S best
                    f"**{_fmt_pct(_mean(pct_lists['ds12']))}**"]
        row += [f"**{_fmt_pct(_mean(pct_lists['s_rtlr']))}**",
                f"**{_fmt_pct(_mean(pct_lists['svref']))}**"]
        out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Table 2: stats per case × phase × language
# ---------------------------------------------------------------------------
def _render_stats_table(summary: Dict[str, Any], metric: str) -> str:
    fields = METRIC_FIELDS[metric]
    results = summary.get("results", {})
    has_phase2 = summary.get("phases", 2) >= 2

    out: List[str] = []
    out.append(f"### Distribution across runs — "
               f"{metric.capitalize()} ({fields['cost']})")
    out.append("")
    out.append("`min` = best (= the number the best-per-phase table shows); "
               "`mean` rounded to 1 decimal; `n` is the number of PASSED "
               "runs contributing to the row (phases with fewer runs than "
               "`total_runs_per_phase` had correctness failures).")
    out.append("")

    # Columns. For each (phase, language): min / max / mean / n.
    phases: List[Tuple[str, str]] = [("phase1", "V"), ("phase1", "S")]
    if has_phase2:
        phases += [("phase2", "V"), ("phase2", "S")]
    phase_labels = {"phase1": "P1", "phase2": "P2"}

    headers = ["Case", "Module"]
    align   = [":---", ":---"]
    for phase, lang_tag in phases:
        p = phase_labels[phase]
        headers += [f"{p} {lang_tag} min",
                    f"{p} {lang_tag} max",
                    f"{p} {lang_tag} mean",
                    f"{p} {lang_tag} n"]
        align   += ["---:", "---:", "---:", "---:"]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(align) + "|")

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        module = _case_label(per_lang)
        row = [case_id, f"`{module}`"]
        for phase, lang_tag in phases:
            rec = per_lang.get("verilog" if lang_tag == "V" else "spirehdl", {})
            st = _phase_stats(rec, phase, metric)
            row += [_fmt_int(st.get("min")),
                    _fmt_int(st.get("max")),
                    _fmt_float(st.get("mean")),
                    str(st.get("count", 0))]
        out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# LaTeX renderer (parallel to the markdown one above)
# ---------------------------------------------------------------------------

def _latex_escape(s: str) -> str:
    """Escape LaTeX special characters in plain text (case names, module names)."""
    if not isinstance(s, str):
        return str(s)
    # Order matters: backslash must come first so we don't double-escape.
    s = s.replace("\\", r"\textbackslash{}")
    s = s.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")
    s = s.replace("$", r"\$").replace("_", r"\_")
    s = s.replace("{", r"\{").replace("}", r"\}")
    s = s.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")
    return s


def _ltx_int(x: Optional[int]) -> str:
    return "--" if x is None else str(x)


def _ltx_float(x: Optional[float]) -> str:
    if x is None:
        return "--"
    if isinstance(x, int) or float(x).is_integer():
        return str(int(x))
    return f"{x:.1f}"


def _ltx_pct(x: Optional[float]) -> str:
    return "--" if x is None else f"{x:+.1f}\\%"


def _ltx_mod(name: str) -> str:
    """Render a module / upstream name in LaTeX monospace, with underscores escaped."""
    return r"\texttt{" + _latex_escape(name) + r"}"


def _render_best_table_latex(summary: Dict[str, Any], metric: str) -> str:
    fields = METRIC_FIELDS[metric]
    results = summary.get("results", {})
    has_phase2 = summary.get("phases", 2) >= 2
    # The RTLRewriter paper has no transistor target, so the Δ-vs-reference
    # column compares the final best against that language's own Base
    # (Δ vs B) instead of against RTLR (Δ vs R), which would be all em-dash.
    vs_base = metric == "transistors"

    # Column order (group-aware):
    #   1. Case, 2. Module, 3. RTLR (shared paper target),
    #   4–8.  Verilog group: Base, P1, P2, Δ_{1→2}, Δ_{vs R/B}
    #   9–13. SpireHDL group: Base, P1, P2, Δ_{1→2}, Δ_{vs R/B}
    #  14.    Cross: Δ_{S/V} (SpireHDL final best vs Verilog reference baseline)
    # Phase-2 columns (P2 and Δ_{1→2}) collapse to absent when phases=1.
    per_lang_cols = 5 if has_phase2 else 3   # Base, P1, [P2, Δ12,] ΔR
    n_cols = 3 + 2 * per_lang_cols + 1       # +1 for cross-language Δ_S/V
    aligns = ["l", "l"] + ["r"] * (n_cols - 2)

    # Headers: two rows — a top "group" row and a bottom "field" row.
    # \cmidrule(lr){from-to} draws a horizontal line under each spanned group.
    blank = ""
    verilog_span_from = 4
    verilog_span_to = verilog_span_from + per_lang_cols - 1
    spirehdl_span_from = verilog_span_to + 1
    spirehdl_span_to = spirehdl_span_from + per_lang_cols - 1

    group_row = ([blank, blank, blank,
                  r"\multicolumn{" + str(per_lang_cols) + r"}{c}{\textbf{Verilog}}",
                  r"\multicolumn{" + str(per_lang_cols) + r"}{c}{\textbf{SpireHDL}}",
                  blank])
    # Compact group row uses one cell per multicol, so flatten:
    # (we emit per_lang_cols cells but only the first carries content; LaTeX's
    # \multicolumn consumes the right number of cells in the row separator.)
    # The row written below has 3 leading blanks + 1 multicol + 1 multicol + 1 trailing blank
    # = 3 + 1 + 1 + 1 = 6 LaTeX-cell positions, spanning 14 real columns.
    group_cells = ["", "", "",
                   r"\multicolumn{" + str(per_lang_cols) + r"}{c}{\textbf{Ours (Verilog)}}",
                   r"\multicolumn{" + str(per_lang_cols) + r"}{c}{\textbf{Ours (SpireHDL)}}",
                   ""]
    cmidrule = (r"\cmidrule(lr){" + f"{verilog_span_from}-{verilog_span_to}" + "} "
                r"\cmidrule(lr){" + f"{spirehdl_span_from}-{spirehdl_span_to}" + "}")

    # Per-language field labels reused on both sides.
    field_labels_lang = ["Base", "P1"]
    if has_phase2:
        field_labels_lang += ["P2", r"$\Delta_{1\!\to\!2}$"]
    field_labels_lang += [r"$\Delta_\text{vs B}$" if vs_base
                          else r"$\Delta_\text{vs R}$"]

    header_row2 = (["Case", "Module", "RTLR"]
                   + field_labels_lang + field_labels_lang
                   + [r"$\Delta_\text{S/V}$"])

    out: List[str] = []
    # `table*` (not `table`) so the wide table spans both columns of the
    # two-column host document — single-column wouldn't fit the 14 columns.
    out.append(r"\begin{table*}[t]")
    out.append(r"\centering")
    if metric == "transistors":
        # Two run modes produce this table: (a) cells-objective run with
        # transistors as a side-stat from the same yosys synth pass, or
        # (b) transistors-objective run (cost_metric=yosys_transistors). The
        # caption notes both; either way the RTLR column is em-dash since the
        # RTLRewriter paper reports no transistor target.
        objective_is_transistors = (
            summary.get("cost_metric") in ("yosys_transistors", "transistors"))
        if objective_is_transistors:
            obj_note = (
                r"Transistor count \emph{is} the optimization objective here "
                r"(\texttt{--cost-metric yosys\_transistors}); wires/cells in the "
                r"companion tables are side stats from the same Yosys \texttt{synth} pass."
            )
        else:
            obj_note = (
                r"From the \emph{same run} as the cell-count table "
                r"(Table~\ref{tab:best-cells}): cell count is the optimization "
                r"objective, transistor count a side metric recorded during the "
                r"same Yosys \texttt{synth} run."
            )
        cap = (
            r"Best per-phase Yosys transistor count on the 14 RTLRewriter cases. "
            + obj_note + " "
            + r"\textbf{Base}: shipped baseline; \textbf{P1} uses "
            r"\texttt{@arithmetic\_optimized}, \textbf{P2} adds "
            r"\texttt{@abc\_optimized}/\texttt{@mockturtle\_optimized} and seeds from P1. "
            r"$\Delta_{1\!\to\!2}$ within-language P1$\to$P2; "
            r"$\Delta_\text{vs B}$ final best vs.\ that language's own \textbf{Base}; "
            r"$\Delta_\text{S/V}$ SpireHDL P2 vs.\ Verilog P2 (cross-language, same pipeline). "
            r"The RTLRewriter paper reports no transistor target, so the "
            r"\textbf{RTLR} column is em-dash and $\Delta_\text{vs B}$ takes the "
            r"place of the cell table's $\Delta_\text{vs R}$. "
            r"Negative $=$ reduction; \textbf{bold} $=$ strict row minimum, "
            r"\underline{underline} $=$ tied for minimum."
        )
    else:
        cap = (
            r"Best per-phase Yosys " + metric + r" count on the 14 RTLRewriter cases. "
            r"\textbf{Base}: shipped baseline; \textbf{RTLR}: paper target; "
            r"\textbf{P1} uses \texttt{@arithmetic\_optimized}, \textbf{P2} adds "
            r"\texttt{@abc\_optimized}/\texttt{@mockturtle\_optimized} and seeds from P1. "
            r"$\Delta_{1\!\to\!2}$ within-language P1$\to$P2; $\Delta_\text{vs R}$ vs.\ RTLR; "
            r"$\Delta_\text{S/V}$ SpireHDL P2 vs.\ Verilog P2 (cross-language, same pipeline). "
            r"Negative $=$ reduction; \textbf{bold} $=$ strict row minimum, "
            r"\underline{underline} $=$ tied for minimum."
        )
    out.append(r"\caption{" + cap + r"}")
    out.append(r"\label{tab:best-" + metric + "}")
    out.append(r"\resizebox{\textwidth}{!}{%")
    out.append(r"\begin{tabular}{" + "".join(aligns) + "}")
    out.append(r"\toprule")
    out.append(" & ".join(group_cells) + r" \\")
    out.append(cmidrule)
    out.append(" & ".join(header_row2) + r" \\")
    out.append(r"\midrule")

    totals = {
        "v_base": 0, "v_final": 0, "p1v": 0, "p2v": 0,
        "s_base": 0, "s_final": 0, "p1s": 0, "p2s": 0,
        "rtlr_v": 0, "rtlr_s": 0,
    }
    pct_lists = {"dv12": [], "ds12": [], "v_rtlr": [], "s_rtlr": [], "svref": []}
    has_any = False

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        v = per_lang.get("verilog",   {})
        s = per_lang.get("spirehdl", {})
        module = _case_label(per_lang)
        v_base = v.get(fields["baseline"])
        s_base = s.get(fields["baseline"])
        p1v = _phase_best(v, "phase1", metric)
        p2v = _phase_best(v, "phase2", metric) if has_phase2 else None
        p1s = _phase_best(s, "phase1", metric)
        p2s = _phase_best(s, "phase2", metric) if has_phase2 else None
        dv12 = _delta(p2v, p1v) if has_phase2 else None
        ds12 = _delta(p2s, p1s) if has_phase2 else None
        # Cross-language delta: SpireHDL P2 vs Verilog P2 (same pipeline both
        # sides) — isolates the language contribution from the agent's.
        s_final = p2s if has_phase2 and p2s is not None else p1s
        v_final = p2v if has_phase2 and p2v is not None else p1v
        svref = _delta(s_final, v_final)

        rtlr = _load_rtlr_targets(
            v.get("benchmark_path") or s.get("benchmark_path"))[metric]
        # Δ-vs-reference column: vs.\ RTLR normally, vs.\ the language's own
        # Base when there is no RTLR target (transistors) — see `vs_base`.
        v_rtlr = _delta(v_final, v_base if vs_base else rtlr)
        s_rtlr = _delta(s_final, s_base if vs_base else rtlr)

        # Per-row winner highlight on the absolute-count columns
        # (RTLR + the four agent results + the two baselines). Strict minimum
        # → \textbf{}; tied for minimum → \underline{}. This makes it visible
        # at a glance which cell ``won'' each benchmark and whether the win
        # is shared across phases or languages.
        counts = {"rtlr": rtlr, "v_base": v_base, "p1v": p1v, "p2v": p2v,
                  "s_base": s_base, "p1s": p1s, "p2s": p2s}
        non_null = [x for x in counts.values() if x is not None]
        row_min = min(non_null) if non_null else None
        n_at_min = sum(1 for x in non_null if x == row_min) if non_null else 0
        def _mark(key, formatted, _counts=counts, _row_min=row_min, _n=n_at_min):
            x = _counts[key]
            if _row_min is None or x is None or x != _row_min:
                return formatted
            return (r"\textbf{" + formatted + r"}") if _n == 1 \
                else (r"\underline{" + formatted + r"}")

        row = [_latex_escape(case_id), _ltx_mod(module),
               _mark("rtlr", _ltx_int(rtlr)),
               _mark("v_base", _ltx_int(v_base)),
               _mark("p1v", _ltx_int(p1v))]
        if has_phase2:
            row += [_mark("p2v", _ltx_int(p2v)), _ltx_pct(dv12)]
        row += [_ltx_pct(v_rtlr),
                _mark("s_base", _ltx_int(s_base)),
                _mark("p1s", _ltx_int(p1s))]
        if has_phase2:
            row += [_mark("p2s", _ltx_int(p2s)), _ltx_pct(ds12)]
        row += [_ltx_pct(s_rtlr), _ltx_pct(svref)]
        out.append(" & ".join(row) + r" \\")

        for key, val in (("v_base", v_base), ("p1v", p1v), ("p2v", p2v),
                         ("s_base", s_base), ("p1s", p1s), ("p2s", p2s)):
            if val is not None:
                totals[key] += val
        if v_final is not None:
            totals["v_final"] += v_final
        if s_final is not None:
            totals["s_final"] += s_final
        if rtlr is not None and v_final is not None:
            totals["rtlr_v"] += rtlr
        if rtlr is not None and s_final is not None:
            totals["rtlr_s"] += rtlr
        for key, val in (("dv12", dv12), ("ds12", ds12),
                          ("v_rtlr", v_rtlr), ("s_rtlr", s_rtlr),
                          ("svref", svref)):
            if val is not None:
                pct_lists[key].append(val)
        has_any = True

    if has_any:
        out.append(r"\midrule")
        # Sum-row Δ-vs-reference: denominator is the summed Base (Δ vs B) when
        # there is no RTLR target, else the summed RTLR target (Δ vs R).
        v_ref_sum = totals["v_base"] if vs_base else totals["rtlr_v"]
        s_ref_sum = totals["s_base"] if vs_base else totals["rtlr_s"]
        sum_v_rtlr_pct = (_delta(totals["v_final"], v_ref_sum)
                          if v_ref_sum else None)
        sum_s_rtlr_pct = (_delta(totals["s_final"], s_ref_sum)
                          if s_ref_sum else None)
        sum_svref_pct = (_delta(totals["s_final"], totals["v_final"])
                         if totals["v_final"] else None)
        sum_dv12_pct = (_delta(totals["p2v"], totals["p1v"])
                        if has_phase2 and totals["p1v"] else None)
        sum_ds12_pct = (_delta(totals["p2s"], totals["p1s"])
                        if has_phase2 and totals["p1s"] else None)

        # Sum row uses the SAME winner-highlight convention as the data rows:
        # \textbf{} the strict row minimum over the absolute-count columns,
        # \underline{} a tie, everything else (and every Δ% column) plain.
        # Previously every cell in the sum/mean rows was bold, which buried the
        # actual winner and was inconsistent with the per-case rows.
        sum_counts = {
            "rtlr": totals["rtlr_v"] or None,
            "v_base": totals["v_base"], "p1v": totals["p1v"],
            "p2v": totals["p2v"] if has_phase2 else None,
            "s_base": totals["s_base"], "p1s": totals["p1s"],
            "p2s": totals["p2s"] if has_phase2 else None,
        }
        s_non_null = [x for x in sum_counts.values() if x is not None]
        s_row_min = min(s_non_null) if s_non_null else None
        s_n_at_min = sum(1 for x in s_non_null if x == s_row_min)
        def _smark(key, formatted, _c=sum_counts, _m=s_row_min, _n=s_n_at_min):
            x = _c[key]
            if _m is None or x is None or x != _m:
                return formatted
            return (r"\textbf{" + formatted + r"}") if _n == 1 \
                else (r"\underline{" + formatted + r"}")

        sum_row = [r"\textbf{sum}", "",
                   # `or None` → em-dash when no RTLR target exists (transistors),
                   # rather than a misleading 0.
                   _smark("rtlr", _ltx_int(totals["rtlr_v"] or None)),
                   _smark("v_base", _ltx_int(totals["v_base"])),
                   _smark("p1v", _ltx_int(totals["p1v"]))]
        if has_phase2:
            sum_row += [_smark("p2v", _ltx_int(totals["p2v"])), _ltx_pct(sum_dv12_pct)]
        sum_row += [_ltx_pct(sum_v_rtlr_pct),
                    _smark("s_base", _ltx_int(totals["s_base"])),
                    _smark("p1s", _ltx_int(totals["p1s"]))]
        if has_phase2:
            sum_row += [_smark("p2s", _ltx_int(totals["p2s"])), _ltx_pct(sum_ds12_pct)]
        sum_row += [_ltx_pct(sum_s_rtlr_pct), _ltx_pct(sum_svref_pct)]
        out.append(" & ".join(sum_row) + r" \\")

        # mean Δ row: only the percentage columns carry a value; numeric columns
        # blank. Δ% columns are never highlighted (same as the data rows), so
        # nothing in this row is bold. Layout matches the data row exactly:
        #   Case, Module, RTLR, V/Base, V/P1, [V/P2, V/Δ12,] V/ΔR, S/Base, S/P1, [S/P2, S/Δ12,] S/ΔR, Δ_S/V
        mean_row = [r"\textbf{mean $\Delta$}", "", "", "", ""]
        if has_phase2:
            mean_row += ["", _ltx_pct(_mean(pct_lists["dv12"]))]
        mean_row += [_ltx_pct(_mean(pct_lists["v_rtlr"])),
                     "", ""]
        if has_phase2:
            mean_row += ["", _ltx_pct(_mean(pct_lists["ds12"]))]
        mean_row += [_ltx_pct(_mean(pct_lists["s_rtlr"])),
                     _ltx_pct(_mean(pct_lists["svref"]))]
        out.append(" & ".join(mean_row) + r" \\")

    out.append(r"\bottomrule")
    out.append(r"\end{tabular}%")
    out.append(r"}")
    out.append(r"\end{table*}")
    return "\n".join(out)


_LATEX_HEADER_COMMENT = (
    "% Best-per-phase table, for \\input{} into a larger document.\n"
    "% Required packages in the host preamble:\n"
    "%   \\usepackage{booktabs}     % \\toprule / \\midrule / \\bottomrule\n"
    "%   \\usepackage{graphicx}     % \\resizebox\n"
    "%   \\usepackage{amsmath,amssymb}  % \\Delta, \\to\n"
)


def render_latex_table(summary: Dict[str, Any],
                       metric: Optional[str] = None) -> str:
    """Render a best-per-phase table as a standalone LaTeX fragment (no
    \\documentclass / \\begin{document}). Intended for \\input{} into a host
    document that supplies its own preamble — see header comment.

    ``metric`` defaults to the summary's primary metric (cells or wires); pass
    ``"transistors"`` for the transistor-count companion table.
    """
    if metric is None:
        metric = _primary_metric(summary)
    return _LATEX_HEADER_COMMENT + "\n" + _render_best_table_latex(summary, metric) + "\n"


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------
def render_table(summary: Dict[str, Any]) -> str:
    cost_metric = summary.get("cost_metric", "?")
    model = summary.get("model", "?")
    phases = summary.get("phases", 2)
    results = summary.get("results", {})

    out: List[str] = []
    out.append(f"**Model:** `{model}` · **Cost metric:** `{cost_metric}` · "
               f"**Phases:** {phases} · "
               f"**Runs/phase:** {summary.get('total_runs_per_phase')} · "
               f"**Max steps:** {summary.get('max_steps')} · "
               f"**Duration:** {summary.get('total_duration_s', 0)/60:.1f} min")
    out.append("")
    # Phase-flag recap
    pf = summary.get("phase_flags", {})
    if pf:
        out.append("**Phase flags (spirehdl only; verilog runs carry none):**")
        for phase in ("phase1", "phase2") if phases >= 2 else ("phase1",):
            flags = (pf.get(phase, {}) or {}).get("spirehdl", {}) or {}
            flagstr = (" ".join(f"`--{k.replace('_','-')}`" for k in flags)
                       if flags else "(none)")
            out.append(f"- `{phase}`: {flagstr}")
        out.append("")

    out.append("`Δ S/V-ref` = spirehdl's final-phase *best* vs. the "
               "verilog reference baseline — the honest cross-language "
               "comparison (phase-1/phase-2 `Δ` rows compare in-language).")
    out.append("")

    primary = _primary_metric(summary)
    # Render all three metrics, primary first. (wires, cells, transistors are
    # all measured every run regardless of which is the optimization target.)
    metric_order = [primary] + [m for m in ("cells", "wires", "transistors")
                                if m != primary]

    for m in metric_order:
        out.append(_render_best_table(summary, m))
        out.append("")
    for m in metric_order:
        out.append(_render_stats_table(summary, m))
        out.append("")

    # Run-root pointers (per phase, not per individual run — there are many)
    out.append("## Run roots")
    out.append("")
    out.append("| Case | Phase | Verilog runs_root | SpireHDL runs_root |")
    out.append("|:---|:---|:---|:---|")
    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        for phase in ("phase1", "phase2") if phases >= 2 else ("phase1",):
            v = (per_lang.get("verilog", {}) or {}).get(phase, {}) or {}
            s = (per_lang.get("spirehdl", {}) or {}).get(phase, {}) or {}
            v_rr = v.get("runs_root") or "—"
            s_rr = s.get("runs_root") or "—"
            out.append(f"| {case_id} | {phase} | `{v_rr}` | `{s_rr}` |")

    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Render markdown tables from a rtl_rewriter_multirun summary.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("--out", type=Path, default=None,
                        help="Write to this path (default: <summary_dir>/table.md)")
    parser.add_argument("--stdout", action="store_true",
                        help="Print to stdout instead of writing a file")
    args = parser.parse_args()

    summary = json.loads(args.summary_json.read_text())
    table = render_table(summary)
    if args.stdout:
        sys.stdout.write(table)
        return
    out_path = args.out or (args.summary_json.parent / "table.md")
    out_path.write_text(table)
    print(f"Wrote table: {out_path}", file=sys.stderr)

    # Also emit a standalone LaTeX version next to the markdown one. Compile with
    # `pdflatex table.tex` (requires booktabs + graphicx; preamble is included).
    latex_path = out_path.with_suffix(".tex")
    latex_path.write_text(render_latex_table(summary))
    print(f"Wrote LaTeX: {latex_path}", file=sys.stderr)

    # Transistor-count companion table — same run, same objective (cells); the
    # transistor count is a side stat of the synth run, so this confirms the
    # cell wins are not a techmap artifact. The RTLRewriter paper has no
    # transistor target, so its RTLR / Δ-vs-R columns render as em-dash.
    transistors_path = latex_path.with_name(latex_path.stem + "_transistors.tex")
    transistors_path.write_text(render_latex_table(summary, metric="transistors"))
    print(f"Wrote LaTeX (transistors): {transistors_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

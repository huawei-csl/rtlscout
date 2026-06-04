#!/usr/bin/env python3
"""Render markdown + LaTeX tables from a dr_rtl_multirun summary.json.

Near-copy of ``experiments/table_rtl_rewriter_multirun.py`` adapted for
DR-RTL. Differences:

- Case IDs are string names (``ticket``, ``router``, …), not ``caseN``.
  Cases are sorted in the canonical ``AVAILABLE_CASES`` order from
  ``experiments/dr_rtl_multirun.py``.
- No ``RTLR`` column. The DR-RTL paper reports Nangate45 ASIC PPA, which
  is not commensurable with our yosys-transistors / cells / wires
  numbers — comparing them would be misleading. Every metric therefore
  uses ``Δ vs Base`` for the cross-reference column (was ``Δ vs RTLR``
  for cells/wires in the RTLR table; here it's always ``vs B``).
- ``module_name`` (from ``metadata.json``) is used as the display label
  in the Module column.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical case order — keep aligned with experiments/dr_rtl_multirun.py
CASE_ORDER = ["ticket", "controller", "router", "pcie", "cpu_pipe", "datapath"]


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


def _case_sort_key(case_id: str) -> Tuple[int, str]:
    # Known cases first in CASE_ORDER, unknown cases trailing alphabetically.
    try:
        return (CASE_ORDER.index(case_id), case_id)
    except ValueError:
        return (len(CASE_ORDER), case_id)


def _module_label(per_lang: Dict[str, Any]) -> str:
    """Display name for the Module column. DR-RTL cases have descriptive
    top-module names (``ticket_machine``, ``router_top``) so we just use those.
    """
    v = per_lang.get("verilog", {})
    s = per_lang.get("spirehdl", {})
    return v.get("module_name") or s.get("module_name") or ""


METRIC_FIELDS = {
    "wires": {"baseline": "baseline_wires", "cost": "yosys_wires"},
    "cells": {"baseline": "baseline_cells", "cost": "yosys_cells"},
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
# Table 1: best per case × phase (markdown)
# ---------------------------------------------------------------------------
def _render_best_table(summary: Dict[str, Any], metric: str) -> str:
    fields = METRIC_FIELDS[metric]
    results = summary.get("results", {})
    has_phase2 = summary.get("phases", 2) >= 2

    out: List[str] = []
    out.append(f"### Best per phase — {metric.capitalize()} ({fields['cost']})")
    out.append("")

    headers = ["Case", "Module", "Vbase", "P1 V best"]
    align   = [":---", ":---", "---:", "---:"]
    if has_phase2:
        headers += ["P2 V best", "Δ 1→2 V"]
        align   += ["---:", "---:"]
    headers += ["Δ V/Base", "Sbase", "P1 S best"]
    align   += ["---:", "---:", "---:"]
    if has_phase2:
        headers += ["P2 S best", "Δ 1→2 S"]
        align   += ["---:", "---:"]
    headers += ["Δ S/Base", "Δ S/V-ref"]
    align   += ["---:", "---:"]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(align) + "|")

    totals = {
        "v_base": 0, "v_final": 0, "p1v": 0, "p2v": 0,
        "s_base": 0, "s_final": 0, "p1s": 0, "p2s": 0,
    }
    pct_lists = {"dv12": [], "ds12": [], "v_base": [], "s_base": [], "svref": []}
    has_any = False

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        v = per_lang.get("verilog",   {})
        s = per_lang.get("spirehdl", {})
        module = _module_label(per_lang)
        v_base = v.get(fields["baseline"])
        s_base = s.get(fields["baseline"])
        p1v = _phase_best(v, "phase1", metric)
        p2v = _phase_best(v, "phase2", metric) if has_phase2 else None
        p1s = _phase_best(s, "phase1", metric)
        p2s = _phase_best(s, "phase2", metric) if has_phase2 else None
        dv12 = _delta(p2v, p1v) if has_phase2 else None
        ds12 = _delta(p2s, p1s) if has_phase2 else None
        s_final = p2s if has_phase2 and p2s is not None else p1s
        v_final = p2v if has_phase2 and p2v is not None else p1v
        svref = _delta(s_final, v_final)

        v_vs_base = _delta(v_final, v_base)
        s_vs_base = _delta(s_final, s_base)

        row = [case_id, f"`{module}`",
               _fmt_int(v_base), _fmt_int(p1v)]
        if has_phase2:
            row += [_fmt_int(p2v), _fmt_pct(dv12)]
        row += [_fmt_pct(v_vs_base),
                _fmt_int(s_base), _fmt_int(p1s)]
        if has_phase2:
            row += [_fmt_int(p2s), _fmt_pct(ds12)]
        row += [_fmt_pct(s_vs_base), _fmt_pct(svref)]
        out.append("| " + " | ".join(row) + " |")

        if v_base is not None and v_final is not None:
            totals["v_base"]  += v_base
            totals["v_final"] += v_final
            if p1v is not None: totals["p1v"] += p1v
            if has_phase2 and p2v is not None: totals["p2v"] += p2v
            has_any = True
        if s_base is not None and s_final is not None:
            totals["s_base"]  += s_base
            totals["s_final"] += s_final
            if p1s is not None: totals["p1s"] += p1s
            if has_phase2 and p2s is not None: totals["p2s"] += p2s
            has_any = True

        for key, val in (("dv12", dv12), ("ds12", ds12),
                         ("v_base", v_vs_base), ("s_base", s_vs_base),
                         ("svref", svref)):
            if val is not None:
                pct_lists[key].append(val)

    if has_any:
        v_base_sum = _delta(totals["v_final"], totals["v_base"] or None)
        s_base_sum = _delta(totals["s_final"], totals["s_base"] or None)
        dv12_sum = _delta(totals["p2v"] or None, totals["p1v"] or None) if has_phase2 else None
        ds12_sum = _delta(totals["p2s"] or None, totals["p1s"] or None) if has_phase2 else None
        svref_sum = _delta(totals["s_final"], totals["v_final"] or None)

        row = ["**sum**", "",
               f"**{totals['v_base']}**", f"**{totals['p1v']}**"]
        if has_phase2:
            row += [f"**{totals['p2v']}**", f"**{_fmt_pct(dv12_sum)}**"]
        row += [f"**{_fmt_pct(v_base_sum)}**",
                f"**{totals['s_base']}**", f"**{totals['p1s']}**"]
        if has_phase2:
            row += [f"**{totals['p2s']}**", f"**{_fmt_pct(ds12_sum)}**"]
        row += [f"**{_fmt_pct(s_base_sum)}**", f"**{_fmt_pct(svref_sum)}**"]
        out.append("| " + " | ".join(row) + " |")

        row = ["**mean Δ**", "", "", ""]   # Vbase, P1V blank
        if has_phase2:
            row += ["", f"**{_fmt_pct(_mean(pct_lists['dv12']))}**"]
        row += [f"**{_fmt_pct(_mean(pct_lists['v_base']))}**", "", ""]
        if has_phase2:
            row += ["", f"**{_fmt_pct(_mean(pct_lists['ds12']))}**"]
        row += [f"**{_fmt_pct(_mean(pct_lists['s_base']))}**",
                f"**{_fmt_pct(_mean(pct_lists['svref']))}**"]
        out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Table 2: stats per case × phase × language (markdown)
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
               "runs contributing to the row.")
    out.append("")

    phases: List[Tuple[str, str]] = [("phase1", "V"), ("phase1", "S")]
    if has_phase2:
        phases += [("phase2", "V"), ("phase2", "S")]
    phase_labels = {"phase1": "P1", "phase2": "P2"}

    headers = ["Case", "Module"]
    align   = [":---", ":---"]
    for phase, lang_tag in phases:
        p = phase_labels[phase]
        headers += [f"{p} {lang_tag} min", f"{p} {lang_tag} max",
                    f"{p} {lang_tag} mean", f"{p} {lang_tag} n"]
        align   += ["---:", "---:", "---:", "---:"]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(align) + "|")

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        module = _module_label(per_lang)
        row = [case_id, f"`{module}`"]
        for phase, lang_tag in phases:
            rec = per_lang.get("verilog" if lang_tag == "V" else "spirehdl", {})
            st = _phase_stats(rec, phase, metric)
            row += [_fmt_int(st.get("min")), _fmt_int(st.get("max")),
                    _fmt_float(st.get("mean")), str(st.get("count", 0))]
        out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# LaTeX renderer
# ---------------------------------------------------------------------------
def _latex_escape(s: str) -> str:
    if not isinstance(s, str):
        return str(s)
    s = s.replace("\\", r"\textbackslash{}")
    s = s.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")
    s = s.replace("$", r"\$").replace("_", r"\_")
    s = s.replace("{", r"\{").replace("}", r"\}")
    s = s.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")
    return s


def _ltx_int(x: Optional[int]) -> str:
    return "--" if x is None else str(x)


def _ltx_pct(x: Optional[float]) -> str:
    return "--" if x is None else f"{x:+.1f}\\%"


def _ltx_mod(name: str) -> str:
    return r"\texttt{" + _latex_escape(name) + r"}"


def _bold(s: str) -> str:
    return r"\textbf{" + s + "}"


def _render_best_table_latex(summary: Dict[str, Any], metric: str) -> str:
    fields = METRIC_FIELDS[metric]
    results = summary.get("results", {})
    has_phase2 = summary.get("phases", 2) >= 2

    # Column layout:
    #   Case, Module, [Verilog group: Base, P1, P2, Δ12, ΔvsB],
    #                 [SpireHDL group: Base, P1, P2, Δ12, ΔvsB], Δ_S/V
    per_lang_cols = 5 if has_phase2 else 3   # Base, P1, [P2, Δ12,] ΔB
    n_cols = 2 + 2 * per_lang_cols + 1
    aligns = ["l", "l"] + ["r"] * (n_cols - 2)

    verilog_span_from = 3
    verilog_span_to = verilog_span_from + per_lang_cols - 1
    spirehdl_span_from = verilog_span_to + 1
    spirehdl_span_to = spirehdl_span_from + per_lang_cols - 1

    group_cells = ["", "",
                   r"\multicolumn{" + str(per_lang_cols) + r"}{c}{\textbf{Ours (Verilog)}}",
                   r"\multicolumn{" + str(per_lang_cols) + r"}{c}{\textbf{Ours (SpireHDL)}}",
                   ""]
    cmidrule = (r"\cmidrule(lr){" + f"{verilog_span_from}-{verilog_span_to}" + "} "
                r"\cmidrule(lr){" + f"{spirehdl_span_from}-{spirehdl_span_to}" + "}")

    field_labels_lang = ["Base", "P1"]
    if has_phase2:
        field_labels_lang += ["P2", r"$\Delta_{1\!\to\!2}$"]
    field_labels_lang += [r"$\Delta_\text{vs B}$"]

    header_row2 = (["Case", "Module"]
                   + field_labels_lang + field_labels_lang
                   + [r"$\Delta_\text{S/V}$"])

    out: List[str] = []
    out.append(r"\begin{table*}[t]")
    out.append(r"\centering")
    n_cases = len(results)
    if metric == "transistors":
        objective_is_transistors = (
            summary.get("cost_metric") in ("yosys_transistors", "transistors"))
        if objective_is_transistors:
            obj_note = (
                r"Transistor count \emph{is} the optimization objective here "
                r"(\texttt{--cost-metric yosys\_transistors})."
            )
        else:
            obj_note = (
                r"Transistor count is a side metric recorded during the "
                r"same Yosys \texttt{synth} run as the cells/wires objective."
            )
        cap = (
            r"Best per-phase Yosys transistor count on the " + str(n_cases)
            + r" DR-RTL cases with a working SpireHDL port, optimised directly "
            r"for transistors with the \emph{structural-exploration recipe}: "
            r"Phase~1 advertises no optimization-decorator APIs (forcing "
            r"gate-level structural rewrites); Phase~2 layers "
            r"\texttt{@arithmetic\_optimized}+\texttt{@abc\_optimized}+"
            r"\texttt{@mockturtle\_optimized} on top of P1's elite pool. "
            r"60~steps per phase, opus-4-6, \texttt{--fsm-optimize} on for "
            r"both phases (DR-RTL is controller-heavy). " + obj_note + " "
            r"\textbf{Base}: shipped baseline. $\Delta_{1\!\to\!2}$ "
            r"within-language P1$\to$P2; $\Delta_\text{vs B}$ final best vs.\ "
            r"that language's own \textbf{Base}; $\Delta_\text{S/V}$ SpireHDL "
            r"final vs.\ Verilog final (cross-language, same pipeline). "
            r"The DR-RTL paper reports Nangate45 ASIC PPA, not Yosys "
            r"transistor counts, so we omit a paper-target column. "
            r"Negative $=$ reduction; \textbf{bold} $=$ strict row minimum, "
            r"\underline{underline} $=$ tied for minimum."
        )
    else:
        cap = (
            r"Best per-phase Yosys " + metric + r" count on the " + str(n_cases)
            + r" DR-RTL cases with a working SpireHDL port. "
            r"\textbf{Base}: shipped baseline; \textbf{P1} structural-exploration "
            r"(no decorators), \textbf{P2} layers "
            r"\texttt{@arithmetic\_optimized}+\texttt{@abc\_optimized}+"
            r"\texttt{@mockturtle\_optimized} and seeds from P1. "
            r"$\Delta_{1\!\to\!2}$ within-language P1$\to$P2; "
            r"$\Delta_\text{vs B}$ final best vs.\ that language's own "
            r"\textbf{Base}; $\Delta_\text{S/V}$ SpireHDL final vs.\ Verilog "
            r"final (cross-language, same pipeline). Negative $=$ reduction; "
            r"\textbf{bold} $=$ strict row minimum, \underline{underline} $=$ "
            r"tied for minimum."
        )
    out.append(r"\caption{" + cap + r"}")
    out.append(r"\label{tab:drrtl-best-" + metric + "}")
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
    }
    pct_lists = {"dv12": [], "ds12": [], "v_base": [], "s_base": [], "svref": []}
    has_any = False

    for case_id in sorted(results, key=_case_sort_key):
        per_lang = results[case_id]
        v = per_lang.get("verilog",   {})
        s = per_lang.get("spirehdl", {})
        module = _module_label(per_lang)
        v_base = v.get(fields["baseline"])
        s_base = s.get(fields["baseline"])
        p1v = _phase_best(v, "phase1", metric)
        p2v = _phase_best(v, "phase2", metric) if has_phase2 else None
        p1s = _phase_best(s, "phase1", metric)
        p2s = _phase_best(s, "phase2", metric) if has_phase2 else None
        dv12 = _delta(p2v, p1v) if has_phase2 else None
        ds12 = _delta(p2s, p1s) if has_phase2 else None
        s_final = p2s if has_phase2 and p2s is not None else p1s
        v_final = p2v if has_phase2 and p2v is not None else p1v
        svref = _delta(s_final, v_final)

        v_vs_base = _delta(v_final, v_base)
        s_vs_base = _delta(s_final, s_base)

        # Per-row winner highlight on absolute-count columns.
        counts = {"v_base": v_base, "p1v": p1v, "p2v": p2v,
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
               _mark("v_base", _ltx_int(v_base)),
               _mark("p1v", _ltx_int(p1v))]
        if has_phase2:
            row += [_mark("p2v", _ltx_int(p2v)), _ltx_pct(dv12)]
        row += [_ltx_pct(v_vs_base),
                _mark("s_base", _ltx_int(s_base)),
                _mark("p1s", _ltx_int(p1s))]
        if has_phase2:
            row += [_mark("p2s", _ltx_int(p2s)), _ltx_pct(ds12)]
        row += [_ltx_pct(s_vs_base), _ltx_pct(svref)]
        out.append(" & ".join(row) + r" \\")

        for key, val in (("v_base", v_base), ("p1v", p1v), ("p2v", p2v),
                         ("s_base", s_base), ("p1s", p1s), ("p2s", p2s)):
            if val is not None:
                totals[key] += val
        if v_final is not None:
            totals["v_final"] += v_final
        if s_final is not None:
            totals["s_final"] += s_final
        for key, val in (("dv12", dv12), ("ds12", ds12),
                          ("v_base", v_vs_base), ("s_base", s_vs_base),
                          ("svref", svref)):
            if val is not None:
                pct_lists[key].append(val)
        has_any = True

    if has_any:
        out.append(r"\midrule")
        sum_v_base_pct = _delta(totals["v_final"], totals["v_base"] or None)
        sum_s_base_pct = _delta(totals["s_final"], totals["s_base"] or None)
        sum_svref_pct = _delta(totals["s_final"], totals["v_final"] or None)
        sum_dv12_pct = (_delta(totals["p2v"], totals["p1v"])
                        if has_phase2 and totals["p1v"] else None)
        sum_ds12_pct = (_delta(totals["p2s"], totals["p1s"])
                        if has_phase2 and totals["p1s"] else None)

        sum_row = [r"\textbf{sum}", "",
                   _bold(_ltx_int(totals["v_base"])),
                   _bold(_ltx_int(totals["p1v"]))]
        if has_phase2:
            sum_row += [_bold(_ltx_int(totals["p2v"])),
                        _bold(_ltx_pct(sum_dv12_pct))]
        sum_row += [_bold(_ltx_pct(sum_v_base_pct)),
                    _bold(_ltx_int(totals["s_base"])),
                    _bold(_ltx_int(totals["p1s"]))]
        if has_phase2:
            sum_row += [_bold(_ltx_int(totals["p2s"])),
                        _bold(_ltx_pct(sum_ds12_pct))]
        sum_row += [_bold(_ltx_pct(sum_s_base_pct)),
                    _bold(_ltx_pct(sum_svref_pct))]
        out.append(" & ".join(sum_row) + r" \\")

        mean_row = [r"\textbf{mean $\Delta$}", "", "", ""]
        if has_phase2:
            mean_row += ["", _bold(_ltx_pct(_mean(pct_lists["dv12"])))]
        mean_row += [_bold(_ltx_pct(_mean(pct_lists["v_base"]))), "", ""]
        if has_phase2:
            mean_row += ["", _bold(_ltx_pct(_mean(pct_lists["ds12"])))]
        mean_row += [_bold(_ltx_pct(_mean(pct_lists["s_base"]))),
                     _bold(_ltx_pct(_mean(pct_lists["svref"])))]
        out.append(" & ".join(mean_row) + r" \\")

    out.append(r"\bottomrule")
    out.append(r"\end{tabular}%")
    out.append(r"}")
    out.append(r"\end{table*}")
    return "\n".join(out)


_LATEX_HEADER_COMMENT = (
    "% DR-RTL best-per-phase table, for \\input{} into a larger document.\n"
    "% Required packages in the host preamble:\n"
    "%   \\usepackage{booktabs}     % \\toprule / \\midrule / \\bottomrule\n"
    "%   \\usepackage{graphicx}     % \\resizebox\n"
    "%   \\usepackage{amsmath,amssymb}  % \\Delta, \\to\n"
)


def render_latex_table(summary: Dict[str, Any],
                       metric: Optional[str] = None) -> str:
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
               "verilog final-phase best — the honest cross-language comparison.")
    out.append("")

    primary = _primary_metric(summary)
    metric_order = [primary] + [m for m in ("cells", "wires", "transistors")
                                if m != primary]

    for m in metric_order:
        out.append(_render_best_table(summary, m))
        out.append("")
    for m in metric_order:
        out.append(_render_stats_table(summary, m))
        out.append("")

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
        description="Render markdown + LaTeX tables from a dr_rtl_multirun summary.",
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

    latex_path = out_path.with_suffix(".tex")
    latex_path.write_text(render_latex_table(summary))
    print(f"Wrote LaTeX: {latex_path}", file=sys.stderr)

    transistors_path = latex_path.with_name(latex_path.stem + "_transistors.tex")
    transistors_path.write_text(render_latex_table(summary, metric="transistors"))
    print(f"Wrote LaTeX (transistors): {transistors_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render markdown + LaTeX tables for ADP runs of `dr_rtl_multirun.py`.

Distinct from `experiments/table_dr_rtl_multirun.py` because the metric
set is different. ADP runs evaluate every design with
``PPAAreaDelayProductCost`` (Yosys synth + OpenROAD STA via
``tech_eval``), which reports ``{area, delay, area_delay_product, power}``
in ``μm²``, ``ps``, ``area·ps`` rather than the cells / wires /
transistors set the yosys renderer expects.

What this renderer does that the yosys renderer doesn't:

1. **ADP baselines on the fly**: measures each case's starting point
   with ``area_delay_product`` under the run's ``(technology,
   target_delay)`` pair, cached at
   ``benchmarks/dr_rtl{,_spirehdl}/baselines_adp_<tech>_<target>ps.json``.
2. **Reads each phase's agent-tracked best** straight from the per-run
   ``best_metrics`` dict in ``multistage_summary.json`` (same shape as
   ``experiments/table_rtl_rewriter_multirun.py``). The agent may have
   searched at a non-nominal ``target_delay`` (the eval tool exposes a
   per-call override), so re-measuring at the nominal target would
   give a different number than the agent saw — we report what the
   agent actually optimised against.
3. **Reports three metrics**: ``area_delay_product`` (primary),
   ``area`` and ``delay`` (companions). Cells / wires / transistors
   from the multirun's yosys-side enrichment are ignored.

Same column layout as the yosys renderer (Case | Module | V_group
{Base, P1, [P2, Δ12], ΔvsB} | S_group {…} | Δ_S/V) so the table reads
like the rtl_rewriter / yosys-transistors tables.
"""

import argparse
import json
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.benchmarks import load_benchmark  # noqa: E402
from core.cost import make_cost_metric  # noqa: E402

# Keep aligned with experiments/dr_rtl_multirun.py::AVAILABLE_CASES.
CASE_ORDER = ["ticket", "controller", "router", "pcie", "cpu_pipe", "datapath"]

# Metric set surfaced by PPAAreaDelayProductCost. Order matters for the
# table render: ADP is primary, area + delay are the decomposition.
METRIC_NAMES = ["area_delay_product", "area", "delay"]

METRIC_LABELS = {
    "area_delay_product": "ADP",
    "area": "Area",
    "delay": "Delay",
}

METRIC_UNITS = {
    "area_delay_product": r"\mathrm{\mu m^2{\cdot}ps}",
    "area": r"\mathrm{\mu m^2}",
    "delay": r"\mathrm{ps}",
}


# ---------------------------------------------------------------------------
# Baseline + best-design measurement
# ---------------------------------------------------------------------------
def _baselines_cache_path(technology: str, target_delay: float, language: str) -> Path:
    root = "dr_rtl_spirehdl" if language == "spirehdl" else "dr_rtl"
    return (REPO_ROOT / "benchmarks" / root
            / f"baselines_adp_{technology}_{int(target_delay)}ps.json")


def _measure_with_adp(design_file: Path, top_module: str,
                      technology: str, target_delay: float) -> Dict[str, Optional[float]]:
    """Run PPAAreaDelayProductCost on a verilog file; return {area, delay, area_delay_product}."""
    m = make_cost_metric("area_delay_product",
                         target_delay=target_delay, technology=technology)
    r = m.evaluate(design_file.parent, top_module=top_module, design_file=design_file)
    if not r.ok:
        return {"area": None, "delay": None, "area_delay_product": None,
                "error": r.error}
    s = r.stats
    return {
        "area": s.get("area"),
        "delay": s.get("delay"),
        "area_delay_product": s.get("area_delay_product") or r.value,
        "error": "",
    }


def _emit_spire_to_v(starting_point: Path) -> Path:
    """Emit a SpireHDL design.py to a Verilog file in a tempdir, returning the
    tempdir-relative ``design.v``. Raises on emit failure. Caller is responsible
    for cleaning the tempdir up. ``pcie`` / ``datapath`` need a raised
    recursion limit, mirroring the multirun's baseline measurement."""
    td = Path(tempfile.mkdtemp(prefix="drrtl_adp_base_"))
    for aux in starting_point.parent.glob("*.py"):
        shutil.copy2(aux, td / aux.name)
    proc = subprocess.run(
        ["python", "-c",
         f"import sys; sys.setrecursionlimit(50000); "
         f"exec(open({starting_point.name!r}).read())"],
        cwd=td, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        shutil.rmtree(td, ignore_errors=True)
        raise RuntimeError(f"spire emit failed for {starting_point}: {proc.stderr[:400]}")
    out = td / "design.v"
    if not out.exists():
        shutil.rmtree(td, ignore_errors=True)
        raise RuntimeError(f"spire emit produced no design.v for {starting_point}")
    return out


def load_adp_baselines(technology: str, target_delay: float
                       ) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Measure or read cached per-case ADP/area/delay baselines for every
    language. The cache file is keyed by (technology, target_delay) so a
    re-run at a different PDK / constraint doesn't trample the existing
    measurements."""
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for language in ("verilog", "spirehdl"):
        cache = _baselines_cache_path(technology, target_delay, language)
        cached: Dict[str, Dict[str, Any]] = {}
        if cache.exists():
            try:
                cached = json.loads(cache.read_text())
            except Exception:
                cached = {}
        per_case: Dict[str, Dict[str, Any]] = {}
        updated = False
        for case in CASE_ORDER:
            if case in cached and cached[case].get("area") is not None:
                per_case[case] = cached[case]
                continue
            bench_root = ("dr_rtl_spirehdl" if language == "spirehdl"
                          else "dr_rtl")
            bench = REPO_ROOT / "benchmarks" / bench_root / case
            try:
                top = load_benchmark(bench).module_name
            except Exception:
                per_case[case] = {"area": None, "delay": None,
                                  "area_delay_product": None,
                                  "error": "load_benchmark failed"}
                continue
            sp = bench / "context" / (
                "starting_point.py" if language == "spirehdl"
                else "starting_point.v")
            if language == "spirehdl":
                try:
                    v_file = _emit_spire_to_v(sp)
                except Exception as e:
                    per_case[case] = {"area": None, "delay": None,
                                      "area_delay_product": None, "error": str(e)}
                    continue
                try:
                    per_case[case] = _measure_with_adp(v_file, top,
                                                       technology, target_delay)
                finally:
                    shutil.rmtree(v_file.parent, ignore_errors=True)
            else:
                per_case[case] = _measure_with_adp(sp, top,
                                                    technology, target_delay)
            updated = True
        if updated:
            cache.write_text(json.dumps(per_case, indent=2) + "\n")
        out[language] = per_case
    return out


# ---------------------------------------------------------------------------
# Per-phase aggregation — read agent's tracked best_metrics straight from JSON,
# same shape as experiments/table_rtl_rewriter_multirun.py.  No re-measurement.
# The agent may have searched at a non-nominal target_delay (the eval tool
# exposes a target_delay override); the agent-tracked numbers reflect what the
# agent actually optimized, which is the honest report.
# ---------------------------------------------------------------------------
def _phase_runs(rec: Dict[str, Any], phase: str) -> List[Dict[str, Any]]:
    return ((rec.get(phase) or {}).get("runs") or [])


def _phase_best_adp(rec: Dict[str, Any], phase: str
                    ) -> Dict[str, Optional[float]]:
    """ADP/area/delay for the phase's best passing run, read directly from the
    multistage_summary.json's per-run ``best_metrics`` dict (the agent's own
    eval values)."""
    runs = [r for r in _phase_runs(rec, phase)
            if r.get("passed") and r.get("best_cost") is not None]
    if not runs:
        return {"area": None, "delay": None, "area_delay_product": None}
    best = min(runs, key=lambda r: r["best_cost"])
    bm = best.get("best_metrics") or {}
    return {
        "area":               bm.get("area"),
        "delay":              bm.get("delay"),
        "area_delay_product": bm.get("area_delay_product") or best.get("best_cost"),
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
def _fmt_num(x: Optional[float], decimals: int = 1) -> str:
    if x is None:
        return "—"
    if abs(x) >= 1000 or (isinstance(x, int) or float(x).is_integer()):
        return str(int(round(x)))
    return f"{x:.{decimals}f}"


def _fmt_pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def _ltx_num(x: Optional[float], decimals: int = 1) -> str:
    return "--" if x is None else _fmt_num(x, decimals)


def _ltx_pct(x: Optional[float]) -> str:
    return "--" if x is None else f"{x:+.1f}\\%"


def _delta(new: Optional[float], ref: Optional[float]) -> Optional[float]:
    if new is None or ref in (None, 0):
        return None
    return (new - ref) / ref * 100.0


def _mean(xs: List[float]) -> Optional[float]:
    return None if not xs else sum(xs) / len(xs)


def _case_sort_key(case_id: str) -> Tuple[int, str]:
    try:
        return (CASE_ORDER.index(case_id), case_id)
    except ValueError:
        return (len(CASE_ORDER), case_id)


def _module_label(per_lang: Dict[str, Any]) -> str:
    v = per_lang.get("verilog", {})
    s = per_lang.get("spirehdl", {})
    return v.get("module_name") or s.get("module_name") or ""


# ---------------------------------------------------------------------------
# Build the per-case × per-phase ADP table data
# ---------------------------------------------------------------------------
def build_adp_grid(summary: Dict[str, Any]
                   ) -> Dict[str, Any]:
    """Return a per-case dict of measured ADP/area/delay for baseline and
    each phase's best, for both languages. Heavy lifting: re-measures every
    best_design with PPAAreaDelayProductCost. Cached implicitly by the
    on-disk baseline measurements; per-run measurements are uncached.
    """
    technology = summary.get("technology", "nangate45")
    target_delay = summary.get("target_delay", 100.0)
    phases = summary.get("phases", 2)
    results = summary.get("results", {})

    baselines = load_adp_baselines(technology, target_delay)
    grid: Dict[str, Dict[str, Any]] = {}

    for case in sorted(results, key=_case_sort_key):
        per_lang = results[case]
        case_grid: Dict[str, Any] = {"module": _module_label(per_lang)}
        for lang in ("verilog", "spirehdl"):
            lang_rec = per_lang.get(lang, {})
            base = baselines.get(lang, {}).get(case, {})
            entry = {
                "base": {k: base.get(k) for k in METRIC_NAMES},
                "p1":   _phase_best_adp(lang_rec, "phase1"),
            }
            if phases >= 2:
                entry["p2"] = _phase_best_adp(lang_rec, "phase2")
            case_grid[lang] = entry
        grid[case] = case_grid

    grid["_meta"] = {
        "technology": technology,
        "target_delay": target_delay,
        "phases": phases,
        "cost_metric": summary.get("cost_metric"),
        "model": summary.get("model"),
    }
    return grid


# ---------------------------------------------------------------------------
# Markdown table — one per metric (ADP / Area / Delay)
# ---------------------------------------------------------------------------
def _render_md_table(grid: Dict[str, Any], metric: str) -> str:
    meta = grid["_meta"]
    has_p2 = meta["phases"] >= 2
    label = METRIC_LABELS[metric]

    out: List[str] = []
    out.append(f"### Best per phase — {label} "
               f"({meta['technology']})")
    out.append("")
    headers = ["Case", "Module", f"V {label} base", f"P1 V {label}"]
    align = [":---", ":---", "---:", "---:"]
    if has_p2:
        headers += [f"P2 V {label}", "Δ 1→2 V"]
        align   += ["---:", "---:"]
    headers += ["Δ V/Base", f"S {label} base", f"P1 S {label}"]
    align   += ["---:", "---:", "---:"]
    if has_p2:
        headers += [f"P2 S {label}", "Δ 1→2 S"]
        align   += ["---:", "---:"]
    headers += ["Δ S/Base", "Δ S/V-ref"]
    align   += ["---:", "---:"]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(align) + "|")

    totals = {"v_base": 0.0, "v_final": 0.0, "p1v": 0.0, "p2v": 0.0,
              "s_base": 0.0, "s_final": 0.0, "p1s": 0.0, "p2s": 0.0}
    pct_lists: Dict[str, List[float]] = {
        "dv12": [], "ds12": [], "v_base": [], "s_base": [], "svref": []}
    has_any = False

    for case in CASE_ORDER:
        if case not in grid:
            continue
        gc = grid[case]
        v = gc.get("verilog", {})
        s = gc.get("spirehdl", {})
        v_base = (v.get("base", {}) or {}).get(metric)
        s_base = (s.get("base", {}) or {}).get(metric)
        p1v = (v.get("p1", {}) or {}).get(metric)
        p2v = (v.get("p2", {}) or {}).get(metric) if has_p2 else None
        p1s = (s.get("p1", {}) or {}).get(metric)
        p2s = (s.get("p2", {}) or {}).get(metric) if has_p2 else None
        dv12 = _delta(p2v, p1v) if has_p2 else None
        ds12 = _delta(p2s, p1s) if has_p2 else None
        v_final = p2v if (has_p2 and p2v is not None) else p1v
        s_final = p2s if (has_p2 and p2s is not None) else p1s
        v_vs_b = _delta(v_final, v_base)
        s_vs_b = _delta(s_final, s_base)
        svref = _delta(s_final, v_final)

        row = [case, f"`{gc['module']}`",
               _fmt_num(v_base), _fmt_num(p1v)]
        if has_p2:
            row += [_fmt_num(p2v), _fmt_pct(dv12)]
        row += [_fmt_pct(v_vs_b), _fmt_num(s_base), _fmt_num(p1s)]
        if has_p2:
            row += [_fmt_num(p2s), _fmt_pct(ds12)]
        row += [_fmt_pct(s_vs_b), _fmt_pct(svref)]
        out.append("| " + " | ".join(row) + " |")

        if v_base is not None and v_final is not None:
            totals["v_base"] += v_base; totals["v_final"] += v_final
            if p1v is not None: totals["p1v"] += p1v
            if has_p2 and p2v is not None: totals["p2v"] += p2v
            has_any = True
        if s_base is not None and s_final is not None:
            totals["s_base"] += s_base; totals["s_final"] += s_final
            if p1s is not None: totals["p1s"] += p1s
            if has_p2 and p2s is not None: totals["p2s"] += p2s
            has_any = True
        for k, x in (("dv12", dv12), ("ds12", ds12),
                     ("v_base", v_vs_b), ("s_base", s_vs_b),
                     ("svref", svref)):
            if x is not None:
                pct_lists[k].append(x)

    if has_any:
        v_sum = _delta(totals["v_final"], totals["v_base"] or None)
        s_sum = _delta(totals["s_final"], totals["s_base"] or None)
        sv_sum = _delta(totals["s_final"], totals["v_final"] or None)
        dv12_sum = _delta(totals["p2v"] or None,
                          totals["p1v"] or None) if has_p2 else None
        ds12_sum = _delta(totals["p2s"] or None,
                          totals["p1s"] or None) if has_p2 else None
        row = ["**sum**", "",
               f"**{_fmt_num(totals['v_base'])}**",
               f"**{_fmt_num(totals['p1v'])}**"]
        if has_p2:
            row += [f"**{_fmt_num(totals['p2v'])}**",
                    f"**{_fmt_pct(dv12_sum)}**"]
        row += [f"**{_fmt_pct(v_sum)}**",
                f"**{_fmt_num(totals['s_base'])}**",
                f"**{_fmt_num(totals['p1s'])}**"]
        if has_p2:
            row += [f"**{_fmt_num(totals['p2s'])}**",
                    f"**{_fmt_pct(ds12_sum)}**"]
        row += [f"**{_fmt_pct(s_sum)}**", f"**{_fmt_pct(sv_sum)}**"]
        out.append("| " + " | ".join(row) + " |")

        row = ["**mean Δ**", "", "", ""]
        if has_p2:
            row += ["", f"**{_fmt_pct(_mean(pct_lists['dv12']))}**"]
        row += [f"**{_fmt_pct(_mean(pct_lists['v_base']))}**", "", ""]
        if has_p2:
            row += ["", f"**{_fmt_pct(_mean(pct_lists['ds12']))}**"]
        row += [f"**{_fmt_pct(_mean(pct_lists['s_base']))}**",
                f"**{_fmt_pct(_mean(pct_lists['svref']))}**"]
        out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# LaTeX table (ADP-primary)
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


def _ltx_mod(name: str) -> str:
    return r"\texttt{" + _latex_escape(name) + r"}"


def _bold(s: str) -> str:
    return r"\textbf{" + s + "}"


def _render_latex_table(grid: Dict[str, Any], metric: str) -> str:
    meta = grid["_meta"]
    has_p2 = meta["phases"] >= 2
    label = METRIC_LABELS[metric]
    unit = METRIC_UNITS[metric]
    technology = meta["technology"]
    target_delay = int(meta["target_delay"])

    per_lang_cols = 5 if has_p2 else 3   # Base, P1, [P2, Δ12,] ΔB
    n_cols = 2 + 2 * per_lang_cols + 1
    aligns = ["l", "l"] + ["r"] * (n_cols - 2)

    verilog_from = 3
    verilog_to = verilog_from + per_lang_cols - 1
    spire_from = verilog_to + 1
    spire_to = spire_from + per_lang_cols - 1

    group_cells = ["", "",
                   r"\multicolumn{" + str(per_lang_cols)
                   + r"}{c}{\textbf{Ours (Verilog)}}",
                   r"\multicolumn{" + str(per_lang_cols)
                   + r"}{c}{\textbf{Ours (SpireHDL)}}",
                   ""]
    cmidrule = (r"\cmidrule(lr){" + f"{verilog_from}-{verilog_to}" + "} "
                r"\cmidrule(lr){" + f"{spire_from}-{spire_to}" + "}")

    field_labels = ["Base", "P1"]
    if has_p2:
        field_labels += ["P2", r"$\Delta_{1\!\to\!2}$"]
    field_labels += [r"$\Delta_\text{vs B}$"]
    header_row = (["Case", "Module"]
                  + field_labels + field_labels
                  + [r"$\Delta_\text{S/V}$"])

    n_cases = sum(1 for c in CASE_ORDER if c in grid)
    out: List[str] = []
    out.append(r"\begin{table*}[t]")
    out.append(r"\centering")
    if metric == "area_delay_product":
        cap = (
            r"Best per-phase " + label + r" (area $\times$ delay, $"
            + unit + r"$) on the " + str(n_cases) + r" DR-RTL cases with a "
            r"working SpireHDL port, optimised directly for ADP "
            r"(\texttt{--cost-metric area\_delay\_product}) under "
            + technology + r" via Yosys synth "
            r"+ OpenROAD STA. Recipe: same as Appendix~B "
            r"(Phase~1 no decorators $\to$ Phase~2 layers "
            r"\texttt{@arithmetic\_optimized}+\texttt{@abc\_optimized}+"
            r"\texttt{@mockturtle\_optimized} on top of P1's elite pool), "
            r"60~steps per phase, opus-4-6, \texttt{--fsm-optimize} on for "
            r"both phases. \textbf{Base}: shipped baseline. $\Delta_{1\!\to\!2}$ "
            r"within-language P1$\to$P2; $\Delta_\text{vs B}$ final best vs.\ "
            r"that language's own \textbf{Base}; $\Delta_\text{S/V}$ "
            r"SpireHDL final vs.\ Verilog final (cross-language, same "
            r"pipeline). Companion tables (Tables~\ref{tab:drrtl-best-area} "
            r"and~\ref{tab:drrtl-best-delay}) decompose into area and delay. "
            r"Negative $=$ reduction; \textbf{bold} $=$ strict row minimum, "
            r"\underline{underline} $=$ tied for minimum."
        )
    else:
        cap = (
            r"Best per-phase " + label + r" ($" + unit + r"$) on the "
            + str(n_cases) + r" DR-RTL cases with a working SpireHDL port. "
            r"This is the " + label.lower() + r" decomposition of the "
            r"$ADP = \text{area} \cdot \text{delay}$ headline number in "
            r"Table~\ref{tab:drrtl-best-area_delay_product}; the agent's "
            r"objective is the product, not " + label.lower() + r" in "
            r"isolation. " + technology
            + r". \textbf{Base}: shipped baseline; $\Delta_\text{vs B}$ "
            r"final best vs.\ baseline; $\Delta_\text{S/V}$ SpireHDL vs.\ "
            r"Verilog final. Negative $=$ reduction (for delay, faster; "
            r"for area, smaller); \textbf{bold} $=$ strict row minimum."
        )
    out.append(r"\caption{" + cap + r"}")
    out.append(r"\label{tab:drrtl-best-" + metric + "}")
    out.append(r"\resizebox{\textwidth}{!}{%")
    out.append(r"\begin{tabular}{" + "".join(aligns) + "}")
    out.append(r"\toprule")
    out.append(" & ".join(group_cells) + r" \\")
    out.append(cmidrule)
    out.append(" & ".join(header_row) + r" \\")
    out.append(r"\midrule")

    totals = {"v_base": 0.0, "v_final": 0.0, "p1v": 0.0, "p2v": 0.0,
              "s_base": 0.0, "s_final": 0.0, "p1s": 0.0, "p2s": 0.0}
    pct_lists: Dict[str, List[float]] = {
        "dv12": [], "ds12": [], "v_base": [], "s_base": [], "svref": []}
    has_any = False

    for case in CASE_ORDER:
        if case not in grid:
            continue
        gc = grid[case]
        v = gc.get("verilog", {})
        s = gc.get("spirehdl", {})
        v_base = (v.get("base", {}) or {}).get(metric)
        s_base = (s.get("base", {}) or {}).get(metric)
        p1v = (v.get("p1", {}) or {}).get(metric)
        p2v = (v.get("p2", {}) or {}).get(metric) if has_p2 else None
        p1s = (s.get("p1", {}) or {}).get(metric)
        p2s = (s.get("p2", {}) or {}).get(metric) if has_p2 else None
        dv12 = _delta(p2v, p1v) if has_p2 else None
        ds12 = _delta(p2s, p1s) if has_p2 else None
        v_final = p2v if (has_p2 and p2v is not None) else p1v
        s_final = p2s if (has_p2 and p2s is not None) else p1s
        v_vs_b = _delta(v_final, v_base)
        s_vs_b = _delta(s_final, s_base)
        svref = _delta(s_final, v_final)

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

        row = [_latex_escape(case), _ltx_mod(gc["module"]),
               _mark("v_base", _ltx_num(v_base)),
               _mark("p1v", _ltx_num(p1v))]
        if has_p2:
            row += [_mark("p2v", _ltx_num(p2v)), _ltx_pct(dv12)]
        row += [_ltx_pct(v_vs_b),
                _mark("s_base", _ltx_num(s_base)),
                _mark("p1s", _ltx_num(p1s))]
        if has_p2:
            row += [_mark("p2s", _ltx_num(p2s)), _ltx_pct(ds12)]
        row += [_ltx_pct(s_vs_b), _ltx_pct(svref)]
        out.append(" & ".join(row) + r" \\")

        for k, val in (("v_base", v_base), ("p1v", p1v), ("p2v", p2v),
                       ("s_base", s_base), ("p1s", p1s), ("p2s", p2s)):
            if val is not None:
                totals[k] += val
        if v_final is not None: totals["v_final"] += v_final
        if s_final is not None: totals["s_final"] += s_final
        for k, val in (("dv12", dv12), ("ds12", ds12),
                       ("v_base", v_vs_b), ("s_base", s_vs_b),
                       ("svref", svref)):
            if val is not None:
                pct_lists[k].append(val)
        has_any = True

    if has_any:
        out.append(r"\midrule")
        v_sum = _delta(totals["v_final"], totals["v_base"] or None)
        s_sum = _delta(totals["s_final"], totals["s_base"] or None)
        sv_sum = _delta(totals["s_final"], totals["v_final"] or None)
        dv12_sum = (_delta(totals["p2v"], totals["p1v"])
                    if has_p2 and totals["p1v"] else None)
        ds12_sum = (_delta(totals["p2s"], totals["p1s"])
                    if has_p2 and totals["p1s"] else None)

        sum_row = [r"\textbf{sum}", "",
                   _bold(_ltx_num(totals["v_base"])),
                   _bold(_ltx_num(totals["p1v"]))]
        if has_p2:
            sum_row += [_bold(_ltx_num(totals["p2v"])),
                        _bold(_ltx_pct(dv12_sum))]
        sum_row += [_bold(_ltx_pct(v_sum)),
                    _bold(_ltx_num(totals["s_base"])),
                    _bold(_ltx_num(totals["p1s"]))]
        if has_p2:
            sum_row += [_bold(_ltx_num(totals["p2s"])),
                        _bold(_ltx_pct(ds12_sum))]
        sum_row += [_bold(_ltx_pct(s_sum)), _bold(_ltx_pct(sv_sum))]
        out.append(" & ".join(sum_row) + r" \\")

        mean_row = [r"\textbf{mean $\Delta$}", "", "", ""]
        if has_p2:
            mean_row += ["", _bold(_ltx_pct(_mean(pct_lists["dv12"])))]
        mean_row += [_bold(_ltx_pct(_mean(pct_lists["v_base"]))), "", ""]
        if has_p2:
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
    "% DR-RTL ADP best-per-phase table, for \\input{} into a larger document.\n"
    "% Required packages in the host preamble:\n"
    "%   \\usepackage{booktabs}     % \\toprule / \\midrule / \\bottomrule\n"
    "%   \\usepackage{graphicx}     % \\resizebox\n"
    "%   \\usepackage{amsmath,amssymb}  % \\Delta, \\to, \\cdot\n"
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def render_md(grid: Dict[str, Any]) -> str:
    meta = grid["_meta"]
    out: List[str] = []
    out.append(f"**Model:** `{meta['model']}` · "
               f"**Cost metric:** `{meta['cost_metric']}` · "
               f"**PDK:** `{meta['technology']}` · "
               f"**Phases:** {meta['phases']}")
    out.append("")
    out.append("`Δ S/V-ref` = spirehdl's final-phase *best* vs. the "
               "verilog final-phase best — the honest cross-language comparison.")
    out.append("")
    for m in METRIC_NAMES:
        out.append(_render_md_table(grid, m))
        out.append("")
    return "\n".join(out) + "\n"


def render_latex(grid: Dict[str, Any], metric: Optional[str] = None) -> str:
    if metric is None:
        metric = "area_delay_product"
    return _LATEX_HEADER_COMMENT + "\n" + _render_latex_table(grid, metric) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Render ADP tables from a dr_rtl_multirun summary.json.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("--out", type=Path, default=None,
                        help="Write to this path (default: <summary_dir>/table_adp.md)")
    parser.add_argument("--stdout", action="store_true",
                        help="Print to stdout instead of writing files")
    args = parser.parse_args()

    summary = json.loads(args.summary_json.read_text())
    grid = build_adp_grid(summary)

    md = render_md(grid)
    if args.stdout:
        sys.stdout.write(md)
        return

    out_path = args.out or (args.summary_json.parent / "table_adp.md")
    out_path.write_text(md)
    print(f"Wrote markdown: {out_path}", file=sys.stderr)

    # Emit one LaTeX file per metric (ADP / area / delay). The ADP table is the
    # headline; area + delay tables are companion decompositions for the appendix.
    for metric in METRIC_NAMES:
        tex_path = out_path.with_name(
            out_path.stem + "_" + metric).with_suffix(".tex")
        tex_path.write_text(render_latex(grid, metric))
        print(f"Wrote LaTeX ({metric}): {tex_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

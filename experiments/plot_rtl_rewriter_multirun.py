#!/usr/bin/env python3
"""CLI: Plot rtl_rewriter_multirun results.

A multirun summary is just several multistages chained (phase 1 → phase 2
seeded from phase 1 → …) for each ``(case × language)`` combination. This
script re-uses the plot style of ``plot_multistage.py`` but lays phases
end-to-end on one x-axis per plot, so you can see the seed carry-over
across phases directly.

Usage:
  python experiments/plot_rtl_rewriter_multirun.py \\
      --input runs/rtl_rewriter_multirun_<ts>/summary.json
  python experiments/plot_rtl_rewriter_multirun.py \\
      --input runs/rtl_rewriter_multirun_<ts>/    # auto-finds summary.json
  python experiments/plot_rtl_rewriter_multirun.py \\
      --input <summary.json> --case 2 --language spirehdl
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent

_PHASE_RE = re.compile(r"^phase(\d+)$")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _fmt_cost(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float) and v != int(v):
        return f"{v:.4g}"
    return str(int(v))


def _discover_phases(summary: Dict[str, Any]) -> List[str]:
    """Return all ``phaseN`` keys in encounter order across any record."""
    phases: set = set()
    for per_lang in summary.get("results", {}).values():
        if not isinstance(per_lang, dict):
            continue
        for rec in per_lang.values():
            if not isinstance(rec, dict):
                continue
            for k in rec:
                if _PHASE_RE.match(k):
                    phases.add(k)
    return sorted(phases, key=lambda k: int(_PHASE_RE.match(k).group(1)))


def _load_rtlr_target(benchmark_path: Optional[str], metric: str) -> Optional[int]:
    """RTLR paper target for this case — prefers our reproduction."""
    if not benchmark_path:
        return None
    meta = REPO_ROOT / benchmark_path / "metadata.json"
    if not meta.exists():
        return None
    try:
        ref = (json.loads(meta.read_text()) or {}).get("reference", {}) or {}
    except Exception:
        return None
    return (ref.get(f"reproduced_rtlr_{metric}")
            or ref.get(f"paper_rtlr_{metric}"))


def _metric_from_cost(cost_metric: str) -> str:
    """'yosys_cells' → 'cells', 'yosys_wires' → 'wires', else cells."""
    if cost_metric == "yosys_wires":
        return "wires"
    return "cells"


def _collect_phase_runs(rec: Dict[str, Any], phases: List[str]
                        ) -> List[Tuple[str, Dict[str, Any]]]:
    """Concatenate every phase's ``runs`` into a single list of (phase, run)."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    for phase in phases:
        p = rec.get(phase) or {}
        for r in sorted(p.get("runs", []), key=lambda r: r.get("run_index", 0)):
            out.append((phase, r))
    return out


def _running_min(values: List[Optional[float]]) -> List[Optional[float]]:
    """Cumulative min ignoring None (None means 'no valid cost here')."""
    best = None
    out: List[Optional[float]] = []
    for v in values:
        if v is not None and (best is None or v < best):
            best = v
        out.append(best)
    return out


def _find_seed_x(combined: List[Tuple[str, Dict[str, Any]]],
                 target_idx: int, at_position: int) -> Optional[int]:
    """Find the chronological x-position of the run whose run_index matches
    ``target_idx`` and which completed before ``at_position``. Search
    backward so the most recent pool entry wins (matches multistage's
    most-recent-overwrites-pool semantics)."""
    for j in range(at_position - 1, -1, -1):
        if combined[j][1].get("run_index") == target_idx:
            return j
    return None


def plot_case_language(rec: Dict[str, Any], case_id: str, language: str,
                       summary: Dict[str, Any], output_dir: Path,
                       source: str = "") -> Optional[Path]:
    """Render a single (case × language) figure. Returns the saved path or
    None if there's nothing to plot."""
    phases = _discover_phases(summary)
    combined = _collect_phase_runs(rec, phases)
    if not combined:
        return None

    # ``best_cost`` is in the cost metric the agent optimised; use it directly
    # (bitmap-via-metric_field on best_wires/best_cells also works but may be
    # None on failed runs while best_cost / cost_value are set consistently).
    metric_label = _metric_from_cost(summary.get("cost_metric", "yosys_cells")).capitalize()
    metric_field = _metric_from_cost(summary.get("cost_metric", "yosys_cells"))

    # -- X-axis layout ------------------------------------------------------
    # Each run n occupies a 1-unit slot [n, n+1). Within the slot, the run's
    # `npoints` passing evals are evenly distributed across [n, n + 1 − 1/npoints]
    # at pitch 1/npoints (so the leftmost eval sits at the slot start and the
    # rightmost eval sits at 1 − 1/npoints, leaving a 1/npoints-wide gap
    # before the next run). The run's "best" marker is placed at the same
    # x-position as the last eval — the right end of the filled span.
    #
    # Runs with 0 passing evals (complete failures): best marker goes at the
    # slot centre so there's still something to render. Runs with 1 eval:
    # single point at n.
    run_ix: List[int] = list(range(len(combined)))

    def _npoints(seq_len: int) -> int:
        return seq_len if seq_len >= 1 else 1

    def _eval_x(n: int, i: int, seq_len: int) -> float:
        k = _npoints(seq_len)
        return float(n) + i / k if k > 0 else float(n)

    def _best_x(n: int, seq_len: int) -> float:
        k = _npoints(seq_len)
        if k == 0:
            return float(n) + 0.5
        return float(n) + 1.0 - 1.0 / k

    # -- Extract per-run data, x-axis = chronological position ----------------
    costs:     List[Optional[float]] = []
    passed:    List[bool] = []
    is_fresh:  List[bool] = []
    initial_costs: List[Optional[float]] = []  # first passing eval per run
    eval_seqs: List[List[float]] = []          # every passing eval cost per run
    for _, r in combined:
        cost = r.get("best_cost")
        costs.append(float(cost) if cost is not None else None)
        passed.append(bool(r.get("passed")))
        is_fresh.append(bool(r.get("is_fresh", True)))
        # initial + all eval costs for this run
        seq: List[float] = []
        init_c: Optional[float] = None
        for ev in r.get("all_evals", []) or []:
            if not ev.get("passed"):
                continue
            cv = ev.get("cost_value")
            if cv is None:
                continue
            cv = float(cv)
            seq.append(cv)
            if init_c is None:
                init_c = cv
        initial_costs.append(init_c)
        eval_seqs.append(seq)

    # Phase-boundary x positions — between the end of one phase's last
    # run's slot and the start of the next phase's first run's slot.
    # Slots always end at integer n+1 from a layout perspective (even if
    # the last eval is at n + 1 − 1/npoints and there's whitespace after).
    phase_boundaries: List[Tuple[float, str]] = []
    for i, (p, _) in enumerate(combined):
        if i == 0:
            continue
        if combined[i-1][0] != p:
            phase_boundaries.append((float(i), p))

    # -- Split into marker categories (x = run's best-marker position) -------
    x_pass_fresh, y_pass_fresh = [], []
    x_pass_seed,  y_pass_seed  = [], []
    x_fail                      = []
    for n, c, p, f, seq in zip(run_ix, costs, passed, is_fresh, eval_seqs):
        x = _best_x(n, len(seq))
        if not p or c is None:
            x_fail.append(x)
        elif f:
            x_pass_fresh.append(x); y_pass_fresh.append(c)
        else:
            x_pass_seed.append(x);  y_pass_seed.append(c)

    # -- Y range -------------------------------------------------------------
    valid_costs = [c for c in costs if c is not None]
    valid_initials = [c for c in initial_costs if c is not None]
    all_eval_points = [c for seq in eval_seqs for c in seq]
    baseline    = rec.get(f"baseline_{metric_field}")
    # RTLR target (language-agnostic), from the case's metadata.
    bench_path = rec.get("benchmark_path") or ""
    rtlr = _load_rtlr_target(bench_path, metric_field)

    y_anchors = valid_costs + valid_initials + all_eval_points
    if baseline is not None: y_anchors.append(baseline)
    if rtlr     is not None: y_anchors.append(rtlr)
    if y_anchors:
        y_min, y_max = min(y_anchors), max(y_anchors)
        y_range = y_max - y_min if y_max != y_min else (y_max * 0.1 or 1.0)
        y_bottom = y_min - y_range * 0.15
        y_top    = y_max + y_range * 0.15
    else:
        y_bottom, y_top = 0, 1

    # -- Plot ----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(max(8, len(combined) * 0.8), 5))

    # Reference lines: baseline + RTLR target (if present)
    if baseline is not None:
        ax.axhline(baseline, color="#666", linestyle="--", linewidth=0.9,
                   alpha=0.7, zorder=1,
                   label=f"baseline ({metric_label.lower()}={_fmt_cost(baseline)})")
    if rtlr is not None:
        ax.axhline(rtlr, color="#555", linestyle="-.", linewidth=1.0,
                   alpha=0.9, zorder=1,
                   label=f"RTLR target ({_fmt_cost(rtlr)})")

    # Phase boundary separators + phase labels at the top
    for bx, phase_name in phase_boundaries:
        ax.axvline(bx, color="#cccccc", linestyle=":", linewidth=1, zorder=1)
        ax.text(bx + 0.05, y_top, f" {phase_name}", fontsize=8, color="#888",
                va="top", ha="left")
    # Label the first phase too
    if combined:
        ax.text(0.0, y_top, f" {combined[0][0]}", fontsize=8,
                color="#888", va="top", ha="left")

    # -- In-run evaluation trails -------------------------------------------
    # Each run's `npoints` passing evals are evenly distributed across
    # [n, n + 1 − 1/npoints] at pitch 1/npoints. One ax.plot call per run
    # means each line segment stays WITHIN a run — no lines connect evals
    # across runs.
    eval_trail_plotted = False
    for n, seq in zip(run_ix, eval_seqs):
        if len(seq) < 1:
            continue
        xs = [_eval_x(n, i, len(seq)) for i in range(len(seq))]
        ax.plot(xs, seq, color="#bbbbbb", linewidth=0.8, zorder=1.5, alpha=0.9)
        ax.scatter(xs, seq, marker=".", c="#888888", s=16, zorder=1.8, alpha=0.9)
        eval_trail_plotted = True
    if eval_trail_plotted:
        ax.scatter([], [], marker=".", c="#888888", s=16, label="Evals in run")

    # NOTE: no separate "initial-cost tick + diagonal line to best" marker.
    # In the plot_multistage layout, initial and best shared the same
    # integer x-position so the connecting line was a clean vertical
    # delta indicator. Here, initial sits at x=n and best at
    # x=n + 1 − 1/npoints — any connector would go diagonal and look odd.
    # The eval trail (first-to-last dot, connected by a thin line) already
    # conveys the same initial→best progression and in more detail.

    # -- Seed → seeded arrows -----------------------------------------------
    # From the seed run's best marker (at _best_x(seed_n, ...)) to this
    # run's first-eval position (at _eval_x(n, 0, ...)) — the seed's output
    # IS this run's starting point.
    arrows_drawn = False
    for n, (_phase, r) in enumerate(combined):
        if r.get("is_fresh", True):
            continue
        seed_idx = r.get("seed_run_index")
        if seed_idx is None:
            continue
        seed_n = _find_seed_x(combined, seed_idx, n)
        if seed_n is None:
            continue
        seed_y = costs[seed_n]
        dest_y = initial_costs[n] if initial_costs[n] is not None else costs[n]
        if seed_y is None or dest_y is None:
            continue
        ax.annotate(
            "", xy=(_eval_x(n, 0, len(eval_seqs[n])), dest_y),
            xytext=(_best_x(seed_n, len(eval_seqs[seed_n])), seed_y),
            arrowprops=dict(arrowstyle="->", color="#7570b3",
                            lw=1.0, alpha=0.7,
                            shrinkA=3, shrinkB=3,
                            connectionstyle="arc3,rad=-0.15"),
            zorder=1.7,
        )
        arrows_drawn = True
    if arrows_drawn:
        from matplotlib.lines import Line2D
        ax.add_line(Line2D([], [], color="#7570b3", lw=1.0, alpha=0.8,
                           label="Seed → seeded"))

    # Scatter: passing fresh runs (green circles)
    if x_pass_fresh:
        ax.scatter(x_pass_fresh, y_pass_fresh, marker="o", c="#1b9e77", s=60,
                   zorder=3, label="Fresh (pass)")
    # Scatter: passing seeded runs (diamonds with black edge)
    if x_pass_seed:
        ax.scatter(x_pass_seed, y_pass_seed, marker="D", c="#1b9e77", s=60,
                   edgecolors="black", linewidths=1.2, zorder=3,
                   label="Seeded (pass)")
    # Scatter: failed runs (orange cross at bottom)
    if x_fail:
        ax.scatter(x_fail, [y_bottom + (y_top - y_bottom) * 0.03] * len(x_fail),
                   marker="x", c="#d95f02", s=60, linewidths=2, zorder=3,
                   label="Failed")

    # Step line: running best across all runs. `None` costs carry forward.
    # Tied to each run's best-marker x-position. Since best markers are at
    # varying positions within their slots (n + 1 − 1/npoints), the step
    # line has visible horizontal segments between them — NOT a line
    # connecting evals (those live in the in-run trail).
    best_seq = _running_min(costs)
    step_x: List[float] = []
    step_y: List[float] = []
    for n, v, seq in zip(run_ix, best_seq, eval_seqs):
        if v is None:
            continue
        step_x.append(_best_x(n, len(seq)))
        step_y.append(v)
    if step_x:
        ax.step(step_x, step_y, where="post", color="black", linewidth=1.5,
                zorder=2, label="Running best")

    ax.set_ylim(y_bottom, y_top)
    ax.set_xlabel("Run index (run n occupies [n, n+1); evals fill [n, n + 1−1/npoints])")
    ax.set_ylabel(metric_label)
    # Anchor exactly at 0 on the left. All data lives in [0, N], so nothing
    # should ever fall to negative x.
    ax.set_xlim(0, len(combined))
    # Ticks at integer slot boundaries (0, 1, 2, …, N). Tick "0" sits at the
    # left edge of run 0's slot, tick "1" at the left edge of run 1's slot
    # (= right edge of run 0's slot), etc. Unambiguous about where each run
    # begins and ends.
    ax.set_xticks(list(range(len(combined) + 1)))
    ax.set_xticklabels([str(n) for n in range(len(combined) + 1)])

    # -- Titles / footer -----------------------------------------------------
    module    = rec.get("module_name") or case_id
    model     = summary.get("model", "?")
    cost_name = summary.get("cost_metric", "?")
    best      = None
    for c in costs:
        if c is not None and (best is None or c < best):
            best = c
    fig.suptitle(
        f"{case_id}: {module} — {language}   "
        f"Best {metric_label.lower()}: {_fmt_cost(best)}",
        fontsize=11, y=0.98,
    )
    phase_flags = summary.get("phase_flags", {}) or {}
    flag_bits = []
    for ph in phases:
        pf = (phase_flags.get(ph, {}) or {}).get(language, {}) or {}
        on = [k for k, v in pf.items() if v]
        flag_bits.append(f"{ph}: " + (",".join(on) if on else "(none)"))
    ax.set_title(
        f"model={model}  cost={cost_name}  phases={len(phases)}  "
        f"runs/phase≈{summary.get('total_runs_per_phase','?')}  │  "
        + "   ".join(flag_bits),
        fontsize=8, color="gray",
    )
    if source:
        fig.text(0.5, 0.01, source, fontsize=6, color="gray",
                 ha="center", va="bottom", transform=fig.transFigure)

    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"multirun_{case_id}_{language}.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Plot rtl_rewriter_multirun results (one figure per case × language)."
    )
    parser.add_argument("--input", required=True,
                        help="Path to the multirun summary.json (or its directory).")
    parser.add_argument("--output-dir", default=None,
                        help="Where to write the PNGs. Default: <input-dir>/plots/")
    parser.add_argument("--case", type=int, nargs="+", default=None,
                        help="Filter to these case numbers (e.g. --case 2 7). "
                             "Omit to plot all cases in the summary.")
    parser.add_argument("--language", nargs="+",
                        choices=["verilog", "spirehdl"], default=None,
                        help="Filter to these languages. Omit to plot both.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_dir():
        input_path = input_path / "summary.json"
    if not input_path.exists():
        raise SystemExit(f"Summary not found: {input_path}")

    summary = load_json(input_path)
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent / "plots"
    source = str(input_path)

    case_filter = set(f"case{n}" for n in args.case) if args.case else None
    lang_filter = set(args.language) if args.language else None

    saved: List[Path] = []
    for case_id, per_lang in summary.get("results", {}).items():
        if case_filter and case_id not in case_filter:
            continue
        for language, rec in per_lang.items():
            if lang_filter and language not in lang_filter:
                continue
            path = plot_case_language(rec, case_id, language, summary,
                                      output_dir, source)
            if path is not None:
                saved.append(path)

    if not saved:
        print("No plots produced. Check --case / --language filters and summary contents.")
        return
    for p in saved:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()

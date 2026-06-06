#!/usr/bin/env python3
"""Paper-quality plots for multirun Pareto front analysis.

Generates publication-ready figures:
  1. Single-run area vs delay scatter with cost evolution
  2. Multi-run Pareto front with per-run contributions
  3. Aligned Pareto comparison (two sets overlaid)

Usage:
    # Single multirun run — all plots
    python plot_pareto_paper.py runs/multirun_20260318_090431 -o plots/

    # Compare two pareto sets (from extract_pareto / align_pareto)
    python plot_pareto_paper.py --compare pareto_fpmul/ pareto_fpmul_no_flowy/ -o plots/
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

# ── Style constants ──────────────────────────────────────────────────────────

# Colour-blind-friendly palette (Tol's muted)
_PALETTE = [
    "#332288", "#88CCEE", "#44AA99", "#117733",
    "#999933", "#DDCC77", "#CC6677", "#882255",
    "#AA4499", "#661100", "#6699CC", "#888888",
]
_FRESH_COLOR = "#332288"    # indigo
_SEEDED_COLOR = "#44AA99"   # teal
_FAIL_COLOR = "#CC6677"     # rose
_PARETO_COLOR = "#222222"   # near-black
_PARETO_COLOR_B = "#CC6677" # rose for second set

_MARKER_FRESH = "o"
_MARKER_SEEDED = "D"

# Shared rcParams for paper style
_RC = {
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "axes.spines.top": False,
    "axes.spines.right": False,
}


def _apply_style():
    plt.rcParams.update(_RC)


def _fmt_cost(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float) and v != int(v):
        return f"{v:.4g}"
    return str(int(v))


_METRIC_LABELS = {
    "area": r"Area ($\mathrm{\mu m^2}$)",
    "delay": "Delay (ps)",
    "transistors": "Transistors",
}

def _metric_label(metric: str) -> str:
    return _METRIC_LABELS.get(metric, metric.capitalize())


# ── Pareto helpers ───────────────────────────────────────────────────────────

def _pareto_front(points):
    """Return Pareto-optimal (area, delay) points (lower is better)."""
    pts = sorted(points, key=lambda p: (p[0], p[1]))
    front = []
    best_y = float("inf")
    for x, y in pts:
        if y < best_y:
            front.append((x, y))
            best_y = y
    return front


def _stepify(front):
    """Convert sorted Pareto front to staircase (xs, ys)."""
    if not front:
        return [], []
    xs = [front[0][0]]
    ys = [front[0][1]]
    for i in range(1, len(front)):
        xs.extend([front[i][0], front[i][0]])
        ys.extend([front[i - 1][1], front[i][1]])
    return xs, ys


# ── Data loading ─────────────────────────────────────────────────────────────

def load_multirun(path: Path) -> Dict[str, Any]:
    """Load a multirun_summary.json (or auto-find in directory)."""
    if path.is_dir():
        path = path / "multirun_summary.json"
    return json.loads(path.read_text())


def load_pareto_manifest(path: Path) -> tuple[list[dict], str]:
    """Load pareto_front.json; return (entries, label)."""
    if path.is_dir():
        label = path.name
        path = path / "pareto_front.json"
    else:
        label = path.stem
    entries = json.loads(path.read_text())
    return entries, label


# ── Plot 1: Single run — area vs delay with step evolution ───────────────────

def plot_single_run(run_data: dict, config: dict, output_dir: Path,
                    run_index: int = 0) -> Path:
    """Area vs delay scatter for a single agent run, coloured by eval step.

    Shows the design-space exploration trajectory: lighter = earlier step,
    darker = later step. Passing and failing evals distinguished by shape.
    """
    _apply_style()

    evals = run_data.get("all_evals", [])
    if not evals:
        return None

    metric = config.get("cost_metric", "area")
    benchmark = config.get("benchmark", run_data.get("benchmark_name", "?"))
    model = config.get("model", run_data.get("model", "?"))

    # Separate passing/failing with PPA
    passing = []
    failing_with_ppa = []
    for ev in evals:
        ppa = ev.get("metrics") or {}
        if ppa.get("area") is None or ppa.get("delay") is None:
            continue
        rec = {
            "area": ppa["area"], "delay": ppa["delay"],
            "step": ev.get("eval_index", 0),
            "passed": ev.get("passed", False),
            "cost": ev.get("cost_value"),
        }
        if rec["passed"]:
            passing.append(rec)
        else:
            failing_with_ppa.append(rec)

    if not passing and not failing_with_ppa:
        return None

    fig, ax = plt.subplots(figsize=(5.5, 4))

    # Colour by step index (sequential colourmap)
    all_steps = [r["step"] for r in passing + failing_with_ppa]
    vmin, vmax = min(all_steps), max(all_steps)
    cmap = plt.cm.viridis

    # Plot failing evals as x markers
    if failing_with_ppa:
        steps_f = [r["step"] for r in failing_with_ppa]
        colors_f = [cmap((s - vmin) / max(vmax - vmin, 1)) for s in steps_f]
        ax.scatter(
            [r["area"] for r in failing_with_ppa],
            [r["delay"] for r in failing_with_ppa],
            c=colors_f, marker="x", s=30, linewidths=1, zorder=2,
            alpha=0.5,
        )

    # Plot passing evals as circles
    if passing:
        steps_p = [r["step"] for r in passing]
        sc = ax.scatter(
            [r["area"] for r in passing],
            [r["delay"] for r in passing],
            c=steps_p, cmap=cmap, vmin=vmin, vmax=vmax,
            marker="o", s=50, zorder=3,
            edgecolors="white", linewidths=0.4,
        )
        cb = fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.85)
        cb.set_label("Eval step", fontsize=9)

    # Pareto front of passing designs
    if passing:
        front = _pareto_front([(r["area"], r["delay"]) for r in passing])
        xs, ys = _stepify(front)
        ax.plot(xs, ys, color=_PARETO_COLOR, linewidth=1.5, zorder=4,
                label="Pareto front")

    # Mark the best design
    if passing:
        best = min(passing, key=lambda r: r[metric] if r.get(metric) is not None else float("inf"))
        ax.scatter(
            best["area"], best["delay"],
            marker="*", s=200, c="gold", edgecolors="black",
            linewidths=0.8, zorder=5,
            label=f"Best {metric}: {_fmt_cost(best.get(metric, best.get('cost')))}"
        )

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")
    # No title — use figure caption instead

    # Legend
    handles, labels = ax.get_legend_handles_labels()
    if failing_with_ppa:
        handles.append(Line2D([], [], marker="x", color="gray", linestyle="None",
                              markersize=6))
        labels.append("Failing")
    ax.legend(handles=handles, labels=labels, loc="best", framealpha=0.9)

    fig.tight_layout()
    path = output_dir / f"single_run_{run_index:03d}_area_delay.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


# ── Plot 2: Multirun overview — Pareto front across all runs ───────────────

def plot_multirun_pareto(data: Dict[str, Any], output_dir: Path) -> Path:
    """Area vs delay for all passing evals across the entire multirun run.

    Fresh runs are circles, seeded runs are diamonds. Colour encodes run
    index via a sequential colourmap. The combined Pareto front is overlaid.
    """
    _apply_style()

    runs = data.get("runs", [])
    if not runs:
        return None

    benchmark = data.get("benchmark", "?")
    model = data.get("model", "?").split(":")[-1]
    metric = data.get("cost_metric", "area")
    n_runs = len(runs)

    fig, ax = plt.subplots(figsize=(5.5, 4))

    all_passing = []
    # Collect all points with run metadata
    fresh_areas, fresh_delays, fresh_ridxs = [], [], []
    seeded_areas, seeded_delays, seeded_ridxs = [], [], []

    for run in sorted(runs, key=lambda r: r.get("run_index", 0)):
        ridx = run.get("run_index", 0)
        is_fresh = run.get("is_fresh", True)

        for ev in run.get("all_evals", []):
            if not ev.get("passed"):
                continue
            ppa = ev.get("metrics") or {}
            a, d = ppa.get("area"), ppa.get("delay")
            if a is None or d is None:
                continue
            all_passing.append((a, d))
            if is_fresh:
                fresh_areas.append(a)
                fresh_delays.append(d)
                fresh_ridxs.append(ridx)
            else:
                seeded_areas.append(a)
                seeded_delays.append(d)
                seeded_ridxs.append(ridx)

    cmap = plt.cm.viridis
    vmin, vmax = 0, max(n_runs - 1, 1)

    # Plot fresh and seeded with different markers, colour by run index
    if fresh_areas:
        ax.scatter(
            fresh_areas, fresh_delays, c=fresh_ridxs, cmap=cmap,
            vmin=vmin, vmax=vmax, marker=_MARKER_FRESH, s=35,
            zorder=3, edgecolors="white", linewidths=0.3, alpha=0.7,
        )
    if seeded_areas:
        sc = ax.scatter(
            seeded_areas, seeded_delays, c=seeded_ridxs, cmap=cmap,
            vmin=vmin, vmax=vmax, marker=_MARKER_SEEDED, s=35,
            zorder=3, edgecolors="white", linewidths=0.3, alpha=0.7,
        )
    # Add colourbar
    scatter_for_cb = sc if seeded_areas else (
        ax.scatter(fresh_areas, fresh_delays, c=fresh_ridxs, cmap=cmap,
                   vmin=vmin, vmax=vmax, s=0)  # invisible, just for cb
    ) if fresh_areas else None
    if scatter_for_cb is not None or fresh_areas:
        mappable = plt.cm.ScalarMappable(cmap=cmap,
                                         norm=plt.Normalize(vmin=vmin, vmax=vmax))
        mappable.set_array([])
        cb = fig.colorbar(mappable, ax=ax, pad=0.02, shrink=0.85)
        cb.set_label("Run index", fontsize=9)

    # Combined Pareto front
    if all_passing:
        front = _pareto_front(all_passing)
        xs, ys = _stepify(front)
        ax.plot(xs, ys, color=_PARETO_COLOR, linewidth=2.0, zorder=5)

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")

    # No title — use figure caption instead

    # Compact shape legend (no per-run entries)
    handles = [
        Line2D([], [], marker=_MARKER_FRESH, color="gray", linestyle="None",
               markersize=6, label="Fresh run"),
        Line2D([], [], marker=_MARKER_SEEDED, color="gray", linestyle="None",
               markersize=6, label="Seeded run"),
        Line2D([], [], color=_PARETO_COLOR, linewidth=2.0, label="Pareto front"),
    ]
    ax.legend(handles=handles, loc="best", framealpha=0.9)

    fig.tight_layout()
    path = output_dir / "multirun_pareto_area_delay.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


# ── Plot 3: Cost evolution across runs ───────────────────────────────────────

def plot_cost_evolution(data: Dict[str, Any], output_dir: Path) -> Path:
    """Best cost per run with seed-provenance arrows.

    Each seeded run gets a curved arrow from its seed source run,
    showing the lineage of designs through the elite pool.
    """
    _apply_style()
    from matplotlib.patches import FancyArrowPatch

    runs = sorted(data.get("runs", []), key=lambda r: r.get("run_index", 0))
    if not runs:
        return None

    metric_raw = data.get("cost_metric", "area")
    metric = _metric_label(metric_raw)
    benchmark = data.get("benchmark", "?")
    model = data.get("model", "?").split(":")[-1]

    x_all = [r["run_index"] for r in runs]
    costs = [r.get("best_cost") for r in runs]
    is_fresh = [r.get("is_fresh", True) for r in runs]

    # Build run_index → best_cost lookup
    cost_by_run = {r["run_index"]: r.get("best_cost") for r in runs}

    fig, ax = plt.subplots(figsize=(max(5, len(runs) * 0.55 + 1.5), 3.5))

    valid_costs = [c for c in costs if c is not None]
    if valid_costs:
        y_min, y_max = min(valid_costs), max(valid_costs)
        y_range = y_max - y_min if y_max != y_min else y_max * 0.1 or 1.0
        ax.set_ylim(y_min - y_range * 0.15, y_max + y_range * 0.15)

    # Scatter: fresh vs seeded
    for x, c, fresh in zip(x_all, costs, is_fresh):
        if c is None:
            ax.scatter(x, ax.get_ylim()[0], marker="x", c=_FAIL_COLOR,
                       s=55, linewidths=1.5, zorder=3)
        elif fresh:
            ax.scatter(x, c, marker=_MARKER_FRESH, c=_FRESH_COLOR,
                       s=65, zorder=3, edgecolors="white", linewidths=0.4)
        else:
            ax.scatter(x, c, marker=_MARKER_SEEDED, c=_SEEDED_COLOR,
                       s=65, zorder=3, edgecolors="white", linewidths=0.4)

    # Seed-provenance arrows: curved arrow from seed source to seeded run
    _ARROW_COLOR = "#AAAAAA"
    for r in runs:
        if r.get("is_fresh", True):
            continue
        seed_ridx = r.get("seed_run_index")
        if seed_ridx is None:
            continue
        src_cost = cost_by_run.get(seed_ridx)
        dst_cost = r.get("best_cost")
        dst_ridx = r["run_index"]
        if src_cost is None or dst_cost is None:
            continue
        arrow = FancyArrowPatch(
            (seed_ridx, src_cost), (dst_ridx, dst_cost),
            arrowstyle="-|>",
            mutation_scale=10,
            color=_ARROW_COLOR,
            linewidth=1.0,
            connectionstyle="arc3,rad=-0.2",
            zorder=1,
        )
        ax.add_patch(arrow)

    ax.set_xlabel("Run index")
    ax.set_ylabel(metric)
    # No title — use figure caption instead
    ax.set_xticks(x_all)

    # Legend
    handles = [
        Line2D([], [], marker=_MARKER_FRESH, color=_FRESH_COLOR,
               linestyle="None", markersize=7, label="Fresh"),
        Line2D([], [], marker=_MARKER_SEEDED, color=_SEEDED_COLOR,
               linestyle="None", markersize=7, label="Seeded"),
        FancyArrowPatch((0, 0), (1, 0), arrowstyle="-|>", color=_ARROW_COLOR,
                        mutation_scale=8, linewidth=1.0, label="Seed source"),
    ]
    if any(c is None for c in costs):
        handles.append(Line2D([], [], marker="x", color=_FAIL_COLOR,
                              linestyle="None", markersize=7, label="Failed"))
    ax.legend(handles=handles, loc="best", framealpha=0.9)

    fig.tight_layout()
    path = output_dir / "multirun_cost_evolution.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


# ── Plot 4: Pareto comparison (two sets) ─────────────────────────────────────

def plot_pareto_comparison(path_a: Path, path_b: Path, output_dir: Path,
                           label_a: Optional[str] = None,
                           label_b: Optional[str] = None,
                           starting_point: Optional[tuple] = None) -> Path:
    """Overlay two Pareto front sets for direct comparison."""
    _apply_style()

    entries_a, auto_label_a = load_pareto_manifest(path_a)
    entries_b, auto_label_b = load_pareto_manifest(path_b)
    label_a = label_a or auto_label_a
    label_b = label_b or auto_label_b

    fig, ax = plt.subplots(figsize=(5.5, 4))

    # Set A — circles
    areas_a = [e["area"] for e in entries_a]
    delays_a = [e["delay"] for e in entries_a]
    ax.scatter(areas_a, delays_a, color=_PALETTE[0], marker="o", s=55,
               zorder=3, edgecolors="white", linewidths=0.4,
               label=label_a)

    # Set B — triangles
    areas_b = [e["area"] for e in entries_b]
    delays_b = [e["delay"] for e in entries_b]
    ax.scatter(areas_b, delays_b, color=_PALETTE[6], marker="^", s=55,
               zorder=3, edgecolors="white", linewidths=0.4,
               label=label_b)

    # Pareto front A
    front_a = _pareto_front(list(zip(areas_a, delays_a)))
    xs_a, ys_a = _stepify(front_a)
    ax.plot(xs_a, ys_a, color=_PALETTE[0], linewidth=1.8, zorder=4,
            alpha=0.7)

    # Pareto front B
    front_b = _pareto_front(list(zip(areas_b, delays_b)))
    xs_b, ys_b = _stepify(front_b)
    ax.plot(xs_b, ys_b, color=_PALETTE[6], linewidth=1.8, zorder=4,
            linestyle="--", alpha=0.7)

    if starting_point is not None:
        sp_area, sp_delay = starting_point
        ax.scatter([sp_area], [sp_delay], marker="*", s=200, c="#222222",
                   zorder=10, edgecolors="white", linewidths=0.5,
                   label="Starting point")

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")
    # No title — use figure caption instead
    ax.legend(loc="best", framealpha=0.9)

    fig.tight_layout()
    path = output_dir / "pareto_comparison.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


# ── Plot 5b: Side-by-side multirun Pareto (area vs delay metric) ────────────

def plot_pareto_side_by_side(path_a: Path, path_b: Path, output_dir: Path,
                             label_a: str = "Area target",
                             label_b: str = "Delay target") -> Path:
    """Two multirun Pareto plots side by side, sharing axes."""
    _apply_style()

    data_a = load_multirun(path_a)
    data_b = load_multirun(path_b)

    fig = plt.figure(figsize=(11, 4.5))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.05], wspace=0.08)
    ax_l = fig.add_subplot(gs[0, 0])
    ax_r = fig.add_subplot(gs[0, 1], sharey=ax_l)
    cax = fig.add_subplot(gs[0, 2])

    for ax, data, label in [(ax_l, data_a, label_a), (ax_r, data_b, label_b)]:
        runs = data.get("runs", [])
        n_runs = len(runs)
        cmap = plt.cm.viridis
        vmin, vmax = 0, max(n_runs - 1, 1)

        all_passing = []
        fresh_a, fresh_d, fresh_r = [], [], []
        seeded_a, seeded_d, seeded_r = [], [], []

        for run in sorted(runs, key=lambda r: r.get("run_index", 0)):
            ridx = run.get("run_index", 0)
            is_fresh = run.get("is_fresh", True)
            for ev in run.get("all_evals", []):
                if not ev.get("passed"):
                    continue
                ppa = ev.get("metrics") or {}
                a, d = ppa.get("area"), ppa.get("delay")
                if a is None or d is None:
                    continue
                all_passing.append((a, d))
                if is_fresh:
                    fresh_a.append(a); fresh_d.append(d); fresh_r.append(ridx)
                else:
                    seeded_a.append(a); seeded_d.append(d); seeded_r.append(ridx)

        if fresh_a:
            ax.scatter(fresh_a, fresh_d, c=fresh_r, cmap=cmap,
                       vmin=vmin, vmax=vmax, marker=_MARKER_FRESH, s=30,
                       zorder=3, edgecolors="white", linewidths=0.3, alpha=0.7)
        if seeded_a:
            ax.scatter(seeded_a, seeded_d, c=seeded_r, cmap=cmap,
                       vmin=vmin, vmax=vmax, marker=_MARKER_SEEDED, s=30,
                       zorder=3, edgecolors="white", linewidths=0.3, alpha=0.7)

        if all_passing:
            front = _pareto_front(all_passing)
            xs, ys = _stepify(front)
            ax.plot(xs, ys, color=_PARETO_COLOR, linewidth=2.0, zorder=5)

        ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
        ax.set_title(label, fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.3)

    ax_l.set_ylabel("Delay (ps)")

    # Shared colourbar (use the right panel's run count for the scale)
    n_runs_max = max(len(data_a.get("runs", [])), len(data_b.get("runs", [])))
    mappable = plt.cm.ScalarMappable(cmap=plt.cm.viridis,
                                     norm=plt.Normalize(vmin=0, vmax=max(n_runs_max - 1, 1)))
    mappable.set_array([])
    cb = fig.colorbar(mappable, cax=cax)
    cb.set_label("Run index", fontsize=9)

    # Shared legend
    handles = [
        Line2D([], [], marker=_MARKER_FRESH, color="gray", linestyle="None",
               markersize=6, label="Fresh run"),
        Line2D([], [], marker=_MARKER_SEEDED, color="gray", linestyle="None",
               markersize=6, label="Seeded run"),
        Line2D([], [], color=_PARETO_COLOR, linewidth=2.0, label="Pareto front"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8,
               framealpha=0.9, bbox_to_anchor=(0.45, -0.01))

    fig.subplots_adjust(bottom=0.15)
    path = output_dir / "pareto_area_vs_delay_metric.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


# ── Plot 5b: Combined side-by-side (single axes) ─────────────────────────────

def plot_pareto_side_by_side_combined(
    path_a: Path, path_b: Path, output_dir: Path,
    label_a: str = "Area target",
    label_b: str = "Delay target",
) -> Path:
    """Overlay two multirun campaigns on a single area-vs-delay plot.

    Marker shape encodes the campaign (circle vs triangle).
    Marker colour encodes run index within each campaign, using two
    distinct sequential colormaps (Purples for A, Reds for B).
    """
    _apply_style()

    data_a = load_multirun(path_a)
    data_b = load_multirun(path_b)

    fig = plt.figure(figsize=(5.5, 4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 0.03], wspace=0.03)
    ax = fig.add_subplot(gs[0, 0])
    cax = fig.add_subplot(gs[0, 1])

    # Pareto front line colours (darkest shade of each cmap)
    _FRONT_A = "#332288"   # indigo
    _FRONT_B = "#CC6677"   # rose

    def _extract_per_run(data):
        """Return (areas, delays, run_indices, n_runs)."""
        areas, delays, ridxs = [], [], []
        for run in sorted(data.get("runs", []),
                          key=lambda r: r.get("run_index", 0)):
            ridx = run.get("run_index", 0)
            for ev in run.get("all_evals", []):
                if not ev.get("passed"):
                    continue
                ppa = ev.get("metrics") or {}
                a, d = ppa.get("area"), ppa.get("delay")
                if a is not None and d is not None:
                    areas.append(a)
                    delays.append(d)
                    ridxs.append(ridx)
        n_runs = len(data.get("runs", []))
        return areas, delays, ridxs, n_runs

    # Use the maximum run count across both campaigns for a shared scale
    _, _, ridxs_a, n_a = _extract_per_run(data_a)
    _, _, ridxs_b, n_b = _extract_per_run(data_b)
    vmin, vmax = 0, max(max(n_a, n_b) - 1, 1)

    _CMAP_LO = 0.35  # minimum colormap intensity (avoids invisible early runs)

    def _truncated_cmap(name, lo=_CMAP_LO, hi=1.0, n=256):
        """Return a colormap that uses only the [lo, hi] range of *name*."""
        base = matplotlib.colormaps[name]
        colors = base(np.linspace(lo, hi, n))
        return matplotlib.colors.LinearSegmentedColormap.from_list(
            f"{name}_trunc", colors, N=n)

    for data, cmap_name, front_col, marker, label, zoff in [
        (data_a, "Purples", _FRONT_A, "o", label_a, 0),
        (data_b, "Oranges", _FRONT_B, "^", label_b, 1),
    ]:
        areas, delays, ridxs, _ = _extract_per_run(data)
        if not areas:
            continue
        cmap = _truncated_cmap(cmap_name)
        ax.scatter(areas, delays, c=ridxs, cmap=cmap, vmin=vmin, vmax=vmax,
                   marker=marker, s=25, alpha=0.55, zorder=3 + zoff,
                   edgecolors="white", linewidths=0.3)

        front = _pareto_front(list(zip(areas, delays)))
        xs, ys = _stepify(front)
        ax.plot(xs, ys, color=front_col, linewidth=2.0, zorder=5 + zoff)

    # Starting point: most common first eval across both campaigns
    from collections import Counter
    first_evals = []
    for data in [data_a, data_b]:
        for run in data.get("runs", []):
            evals = run.get("all_evals", [])
            if evals and evals[0].get("passed"):
                ppa = evals[0].get("metrics") or {}
                a, d = ppa.get("area"), ppa.get("delay")
                if a is not None and d is not None:
                    first_evals.append((float(a), float(d)))
    if first_evals:
        (sp_area, sp_delay), _ = Counter(first_evals).most_common(1)[0]
        ax.scatter([sp_area], [sp_delay], marker="*", s=200, c="#222222",
                   zorder=10, edgecolors="white", linewidths=0.5)

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")

    # Shared colourbar for run index (truncated to match point colours)
    mappable = plt.cm.ScalarMappable(
        cmap=_truncated_cmap("Greys"),
        norm=plt.Normalize(vmin=vmin, vmax=vmax))
    mappable.set_array([])
    cb = fig.colorbar(mappable, cax=cax)
    cb.set_label("Run index", fontsize=9)

    # Legend: one entry per campaign (mid-shade marker + Pareto line)
    handles = [
        Line2D([], [], marker="o", color=_FRONT_A, linestyle="-",
               linewidth=1.8, markersize=5,
               markerfacecolor=plt.cm.Purples(0.55),
               markeredgecolor="none", label=label_a),
        Line2D([], [], marker="^", color=_FRONT_B, linestyle="-",
               linewidth=1.8, markersize=5,
               markerfacecolor=plt.cm.Oranges(0.55),
               markeredgecolor="none", label=label_b),
        Line2D([], [], marker="*", color="#222222", linestyle="None",
               markersize=10, markeredgecolor="none", label="Starting point"),
    ]
    ax.legend(handles=handles, loc="upper right", framealpha=0.9)

    fig.subplots_adjust(left=0.12, right=0.92, bottom=0.14, top=0.96)
    path = output_dir / "pareto_area_vs_delay_metric_combined.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


# ── Plot 6: Step-by-step cost per evaluation (bar chart) ─────────────────────

def plot_step_cost(run_data: dict, config: dict, output_dir: Path,
                   run_index: int = 0) -> Path:
    """Bar chart of cost per evaluation step within a single run.

    Bar colour encodes correctness: green = 100% pass, yellow = partial,
    orange = failed. Cost values annotated above each bar.
    """
    _apply_style()
    # Larger text for step_cost plots
    plt.rcParams.update({
        "font.size": 17,
        "axes.labelsize": 18,
        "legend.fontsize": 14,
        "xtick.labelsize": 16,
        "ytick.labelsize": 16,
    })
    from matplotlib.patches import Patch

    evals = run_data.get("all_evals", [])
    if not evals:
        return None

    metric_raw = config.get("cost_metric", "area")
    metric = _metric_label(metric_raw)

    eval_indices = [e.get("eval_index", i + 1) for i, e in enumerate(evals)]
    cost_values = [e.get("cost_value") for e in evals]
    pass_rates = [e.get("correctness", {}).get("pass_rate",
                  e.get("pass_rate", 0)) for e in evals]

    def _pass_rate_color(rate):
        if rate >= 1.0:
            return "#44AA99"  # teal (pass)
        if rate <= 0.0:
            return "#CC6677"  # rose (fail)
        return "#DDCC77"      # sand (partial)

    plot_costs = [cv if cv is not None else 0 for cv in cost_values]
    colors = [_pass_rate_color(pr) for pr in pass_rates]

    fig, ax = plt.subplots(figsize=(max(5, len(evals) * 0.4 + 1), 3.5))

    bars = ax.bar(eval_indices, plot_costs, color=colors, width=0.8)
    for bar, cv in zip(bars, cost_values):
        if cv is not None:
            ax.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height(),
                    _fmt_cost(cv), ha="center", va="bottom", fontsize=13)

    ax.set_xlabel("Evaluation step")
    ax.set_ylabel(metric)

    # Y limits: zoom to cost range
    valid = [cv for cv in cost_values if cv is not None]
    if valid:
        delta = max(valid) - min(valid) if len(valid) > 1 else max(valid) * 0.1 or 1
        ax.set_ylim(min(valid) - delta * 0.1, max(valid) + delta * 0.25)

    # Y-axis ticks at multiples of 5, x-axis integer
    from matplotlib.ticker import MultipleLocator, MaxNLocator
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # Annotate partial/failed below bars
    y_bottom = ax.get_ylim()[0]
    delta = (ax.get_ylim()[1] - y_bottom)
    for idx, pr, cv in zip(eval_indices, pass_rates, cost_values):
        if pr < 1.0:
            pct = f"{pr:.0%}"
            if cv is not None and cv > 0:
                ax.text(idx, y_bottom + delta * 0.02, pct,
                        ha="center", va="bottom", fontsize=10,
                        color="#CC6677", fontweight="bold")
            else:
                ax.plot(idx, y_bottom + delta * 0.01, "x",
                        color=_pass_rate_color(pr), markersize=6, markeredgewidth=1.5)

    legend_elements = [
        Patch(facecolor="#44AA99", label="100% correct"),
        Patch(facecolor="#DDCC77", label="Partial"),
        Patch(facecolor="#CC6677", label="Failed"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", framealpha=0.9)

    fig.tight_layout()
    path = output_dir / f"step_cost_run_{run_index:03d}.png"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    # Restore default rcParams for subsequent plots
    _apply_style()
    return path


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Paper-quality plots for multirun Pareto front analysis.")
    parser.add_argument(
        "input", nargs="?", type=Path, default=None,
        help="Multirun run directory (contains multirun_summary.json)")
    parser.add_argument(
        "--compare", nargs=2, type=Path, default=None, metavar=("SET_A", "SET_B"),
        help="Compare two Pareto sets (directories or JSON files)")
    parser.add_argument(
        "--side-by-side", nargs=2, type=Path, default=None, metavar=("RUN_A", "RUN_B"),
        help="Side-by-side multirun Pareto plots (e.g. area-opt vs delay-opt)")
    parser.add_argument(
        "--side-by-side-combined", nargs=2, type=Path, default=None,
        metavar=("RUN_A", "RUN_B"),
        help="Combined single-plot overlay of two multirun campaigns")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output directory (default: <input>/plots)")
    parser.add_argument(
        "--label-a", default=None,
        help="Label for first comparison/side-by-side set")
    parser.add_argument(
        "--label-b", default=None,
        help="Label for second comparison/side-by-side set")
    parser.add_argument(
        "--run", type=int, default=None,
        help="Plot a specific run index for single-run plot (default: best run)")
    parser.add_argument(
        "--starting-point", nargs=2, type=float, default=None,
        metavar=("AREA", "DELAY"),
        help="Plot a starting-point star at the given area and delay")
    args = parser.parse_args()

    if not args.input and not args.compare and not args.side_by_side and not args.side_by_side_combined:
        parser.error("Provide a multirun run directory, --compare, --side-by-side, or --side-by-side-combined")

    saved = []

    if args.compare:
        output_dir = args.output or Path("plots")
        output_dir.mkdir(parents=True, exist_ok=True)
        sp = tuple(args.starting_point) if args.starting_point else None
        p = plot_pareto_comparison(
            args.compare[0], args.compare[1], output_dir,
            label_a=args.label_a, label_b=args.label_b,
            starting_point=sp)
        if p:
            saved.append(p)

    if args.side_by_side:
        output_dir = args.output or Path("plots")
        output_dir.mkdir(parents=True, exist_ok=True)
        p = plot_pareto_side_by_side(
            args.side_by_side[0], args.side_by_side[1], output_dir,
            label_a=args.label_a or "Area target",
            label_b=args.label_b or "Delay target")
        if p:
            saved.append(p)

    if args.side_by_side_combined:
        output_dir = args.output or Path("plots")
        output_dir.mkdir(parents=True, exist_ok=True)
        p = plot_pareto_side_by_side_combined(
            args.side_by_side_combined[0], args.side_by_side_combined[1],
            output_dir,
            label_a=args.label_a or "Area target",
            label_b=args.label_b or "Delay target")
        if p:
            saved.append(p)

    if args.input:
        output_dir = args.output or args.input / "plots"
        output_dir.mkdir(parents=True, exist_ok=True)

        data = load_multirun(args.input)
        config_path = (args.input if args.input.is_dir() else args.input.parent) / "config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else data

        # Plot 1: Single run (best or specified)
        runs = data.get("runs", [])
        if runs:
            if args.run is not None:
                run_data = next((r for r in runs if r.get("run_index") == args.run), None)
                run_idx = args.run
            else:
                # Pick the run with the best cost
                passing_runs = [r for r in runs if r.get("passed") and r.get("best_cost") is not None]
                if passing_runs:
                    run_data = min(passing_runs, key=lambda r: r["best_cost"])
                    run_idx = run_data.get("run_index", 0)
                else:
                    run_data = runs[0]
                    run_idx = 0
            if run_data:
                p = plot_single_run(run_data, config, output_dir, run_index=run_idx)
                if p:
                    saved.append(p)
                p = plot_step_cost(run_data, config, output_dir, run_index=run_idx)
                if p:
                    saved.append(p)

        # Plot 2: Multirun Pareto overview
        p = plot_multirun_pareto(data, output_dir)
        if p:
            saved.append(p)

        # Plot 3: Cost evolution
        p = plot_cost_evolution(data, output_dir)
        if p:
            saved.append(p)

    for p in saved:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()

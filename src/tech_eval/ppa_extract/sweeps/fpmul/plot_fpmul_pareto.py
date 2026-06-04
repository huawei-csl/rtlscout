#!/usr/bin/env python3
"""Paper-quality area vs delay plot for FP multiplier design-space exploration.

Groups sweep results by generation stage:
  1. Initial design (pareto_front_init)
  2. Without flowy optimisation (pareto_fpmul_no_flowy)
  3. Including flowy optimisation (pareto_fpmul_no_flowy + pareto_fpmul, deduplicated)

Usage:
    python plot_fpmul_pareto.py results/ppa/FpMul_e5f10_results.json -o plots/
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# ── Style constants ──────────────────────────────────────────────────────────

# Colour-blind-friendly palette (Tol's muted)
_COLORS = {
    "initial_op": "#222222",  # near-black
    "initial":    "#CC6677",  # rose
    "no_flowy":   "#44AA99",  # teal-green
    "flowy_op":   "#332288",  # indigo (same hue, full strength)
    "flowy":      "#332288",  # indigo
}

_MARKERS = {
    "initial_op": "x",  # cross
    "initial":    "s",  # square
    "no_flowy":   "^",  # triangle
    "flowy_op":   "+",  # plus
    "flowy":      "o",  # circle
}

_LINESTYLES = {
    "initial_op": "-",           # solid
    "initial":    "-",           # solid
    "no_flowy":   (0, (6, 3)),   # dashed
    "flowy_op":   ":",           # dotted
    "flowy":      "-",           # solid
}

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


# ── Pareto helpers ───────────────────────────────────────────────────────────

def _pareto_front(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Return Pareto-optimal (area, delay) points (lower is better)."""
    pts = sorted(points, key=lambda p: (p[0], p[1]))
    front = []
    best_y = float("inf")
    for x, y in pts:
        if y < best_y:
            front.append((x, y))
            best_y = y
    return front


def _stepify(front: List[Tuple[float, float]]) -> Tuple[List[float], List[float]]:
    """Convert sorted Pareto front to staircase (xs, ys)."""
    if not front:
        return [], []
    xs = [front[0][0]]
    ys = [front[0][1]]
    for i in range(1, len(front)):
        xs.extend([front[i][0], front[i][0]])
        ys.extend([front[i - 1][1], front[i][1]])
    return xs, ys


# ── Data grouping ────────────────────────────────────────────────────────────

def _collect_points(
    case_results: Dict[str, List[Dict[str, Any]]],
    gen_sources: List[str],
    use_operator: bool = None,
) -> List[Tuple[float, float]]:
    """Collect (area, delay) points for cases matching any of *gen_sources*.

    If *use_operator* is not None, only include entries where
    ``mult_use_operator`` matches ``str(use_operator)``.
    """
    points = []
    for case_key, entries in case_results.items():
        if not entries:
            continue
        if entries[0].get("gen_source") not in gen_sources:
            continue
        for e in entries:
            if use_operator is not None:
                if e.get("mult_use_operator") != str(use_operator):
                    continue
            a, d = e.get("area"), e.get("delay")
            if a is not None and d is not None:
                points.append((float(a), float(d)))
    return points


# ── Plot ─────────────────────────────────────────────────────────────────────

def plot_fpmul_pareto(
    results_path: str,
    output_dir: str,
    max_area: float = 130.0,
    max_delay: float = 2200.0,
    show_operator: bool = False,
) -> Path:
    _apply_style()

    with open(results_path) as f:
        data = json.load(f)

    case_results = data["case_results"]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    def _clip(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        return [(a, d) for a, d in pts if a <= max_area and d <= max_delay]

    _SRC_INIT = ["pareto_front_init"]
    _SRC_NO_FLOWY = ["pareto_fpmul_no_flowy"]
    _SRC_ALL = ["pareto_fpmul_no_flowy", "pareto_fpmul"]

    # Build groups — _op groups filter use_operator=True; others include all
    groups = []

    if show_operator:
        groups.append((
            "initial_op", "Initial design",
            _clip(_collect_points(case_results, _SRC_INIT, use_operator=True)),
        ))

    groups.append((
        "initial", "Phase 3 only (init + arch sweep)",
        _clip(_collect_points(case_results, _SRC_INIT)),
    ))

    groups.append((
        "no_flowy", "Phases 1,3 (no Flowy agent)",
        _clip(_collect_points(case_results, _SRC_NO_FLOWY)),
    ))

    if show_operator:
        pts_flowy_op = _clip(_collect_points(case_results, _SRC_ALL, use_operator=True))
        groups.append((
            "flowy_op", "Phases 1,2 (no arch sweep)",
            list(set(pts_flowy_op)),
        ))

    pts_flowy = _clip(_collect_points(case_results, _SRC_ALL))
    groups.append((
        "flowy", "Phases 1\u20133",
        list(set(pts_flowy)),
    ))

    fig, ax = plt.subplots(figsize=(5.5, 4))

    # Plot scatter + Pareto front for each group.
    for zbase, (key, label, pts) in enumerate(groups):
        if not pts:
            continue
        areas, delays = zip(*pts)
        z_scatter = 3 + zbase
        z_front = 4 + zbase

        is_op = key.endswith("_op")
        scatter_kw = dict(
            color=_COLORS[key],
            marker=_MARKERS[key],
            s=60 if is_op else 25,
            alpha=0.12,
            zorder=z_scatter,
        )
        # Unfilled markers (+, x) ignore edgecolors — skip to avoid warning
        if _MARKERS[key] not in ("+", "x"):
            scatter_kw["edgecolors"] = "none"
        ax.scatter(areas, delays, **scatter_kw)

        front = _pareto_front(pts)
        xs, ys = _stepify(front)
        ax.plot(
            xs, ys,
            color=_COLORS[key],
            linewidth=2.0,
            linestyle=_LINESTYLES[key],
            alpha=1.0,
            zorder=z_front,
        )

    # ── Redraw overlapping fronts for readability ────────────────────────
    # "no_flowy" often overlaps with "flowy" — redraw with dashes on top.
    no_flowy_pts = next((pts for k, _, pts in groups if k == "no_flowy"), [])
    if no_flowy_pts:
        front_nf = _pareto_front(no_flowy_pts)
        xs_nf, ys_nf = _stepify(front_nf)
        ax.plot(
            xs_nf, ys_nf,
            color=_COLORS["no_flowy"],
            linewidth=1.6,
            linestyle=(0, (6, 3)),
            zorder=10,
        )

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")

    # Custom legend
    handles = []
    for key, label, pts in groups:
        if not pts:
            continue
        mkw = dict(
            marker=_MARKERS[key],
            color=_COLORS[key],
            linestyle=_LINESTYLES[key],
            linewidth=1.8,
            markersize=6,
            label=label,
        )
        if _MARKERS[key] not in ("+", "x"):
            mkw["markeredgecolor"] = "none"
        handles.append(Line2D([], [], **mkw))
    ax.legend(handles=handles, loc="upper right", framealpha=0.9)

    fig.tight_layout()
    suffix = "_with_op" if show_operator else ""
    path = out / f"fpmul_pareto_area_delay{suffix}.pdf"
    fig.savefig(path)
    fig.savefig(path.with_suffix(".png"))
    plt.close(fig)
    print(f"Saved: {path}")
    print(f"Saved: {path.with_suffix('.png')}")
    return path


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Paper-quality area vs delay plot for FP multiplier designs.")
    parser.add_argument(
        "results", type=str,
        help="Path to FpMul_e5f10_results.json")
    parser.add_argument(
        "-o", "--output", type=str, default="results/ppa/plots",
        help="Output directory (default: results/ppa/plots)")
    parser.add_argument(
        "--show-operator", action="store_true", default=False,
        help="Add groups for use_operator=True (orig Verilog operators)")
    args = parser.parse_args()

    plot_fpmul_pareto(args.results, args.output, show_operator=args.show_operator)


if __name__ == "__main__":
    main()

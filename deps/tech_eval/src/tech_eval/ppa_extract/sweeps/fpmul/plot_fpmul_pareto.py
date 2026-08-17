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


# Half-text-width variant: rendered at print size so LaTeX does not downscale
# it and the fonts stay physically legible when used as a paper subfigure.
_RC_NARROW = {**_RC, "font.size": 7, "axes.labelsize": 7,
              "xtick.labelsize": 6, "ytick.labelsize": 6}


def _apply_style(narrow: bool = False):
    plt.rcParams.update(_RC_NARROW if narrow else _RC)


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
    narrow: bool = False,
) -> Path:
    _apply_style(narrow)
    ms = 0.45 if narrow else 1.0        # marker scale

    with open(results_path) as f:
        data = json.load(f)

    case_results = data["case_results"]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    def _clip(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        return [(a, d) for a, d in pts if a <= max_area and d <= max_delay]

    _SRC_INIT = ["pareto_front_init"]
    _SRC_NO_FLOWY = ["pareto_fpmul_no_abc"]
    _SRC_ALL = ["pareto_fpmul_no_abc", "pareto_fpmul_abc"]

    # Build groups — _op groups filter use_operator=True; others include all
    groups = []

    if show_operator:
        groups.append((
            "initial_op", "Initial design",
            _clip(_collect_points(case_results, _SRC_INIT, use_operator=True)),
        ))

    groups.append((
        "initial", ("Phase 3 only" if narrow else "Phase 3 only (init + arch sweep)"),
        _clip(_collect_points(case_results, _SRC_INIT)),
    ))

    groups.append((
        "no_flowy", ("Phases 1,3" if narrow else "Phases 1,3 (no ABC agent)"),
        _clip(_collect_points(case_results, _SRC_NO_FLOWY)),
    ))

    if show_operator:
        pts_flowy_op = _clip(_collect_points(case_results, _SRC_ALL, use_operator=True))
        groups.append((
            "flowy_op", ("Phases 1,2" if narrow else "Phases 1,2 (no arch sweep)"),
            list(set(pts_flowy_op)),
        ))

    pts_flowy = _clip(_collect_points(case_results, _SRC_ALL))
    groups.append((
        "flowy", "Phases 1\u20133",
        list(set(pts_flowy)),
    ))

    fig, ax = plt.subplots(figsize=(2.75, 2.15) if narrow else (5.5, 4))

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
            s=(60 if is_op else 25) * ms,
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
    if narrow:                       # headroom so the legend clears the fronts
        ax.set_ylim(top=ax.get_ylim()[1] * 1.05)

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
            markersize=6 * (0.7 if narrow else 1.0),
            label=label,
        )
        if _MARKERS[key] not in ("+", "x"):
            mkw["markeredgecolor"] = "none"
        handles.append(Line2D([], [], **mkw))
    # zorder: Pareto fronts draw at 4-10, legends default to 5.
    # 6pt is the floor neurips_2026.sty enforces (it forces \tiny to 6pt);
    # upper-left is the emptiest region, so the legend occludes no front there.
    leg = ax.legend(handles=handles,
              loc="upper left" if narrow else "lower left",
              framealpha=1.0 if narrow else 0.9,
              **({"fontsize": 6, "handlelength": 1.2, "borderpad": 0.25,
                  "labelspacing": 0.25, "handletextpad": 0.4} if narrow else {}))
    leg.set_zorder(20)

    fig.tight_layout()
    suffix = ("_with_op" if show_operator else "") + ("_narrow" if narrow else "")
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
    parser.add_argument(
        "--narrow", action="store_true", default=False,
        help="Render at half text width (paper subfigure)")
    args = parser.parse_args()

    plot_fpmul_pareto(args.results, args.output,
                      show_operator=args.show_operator, narrow=args.narrow)


if __name__ == "__main__":
    main()

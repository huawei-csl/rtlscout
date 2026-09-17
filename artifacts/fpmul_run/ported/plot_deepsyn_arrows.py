#!/usr/bin/env python3
"""Plot area vs delay arrows showing original→Deepsyn-optimized movement.

Usage:
    python plot_deepsyn_arrows.py -o plots/fpmul/

    # Custom JSON files
    python plot_deepsyn_arrows.py \
        --data "10% Deepsyn" pareto_fronts/aligned/pareto_fpmul_deepsyn/batch_deepsyn_results.json \
        --data "100% Deepsyn" pareto_fronts/aligned/pareto_fpmul_deepsyn_full/batch_deepsyn_results.json \
        --standalone "Standalone Deepsyn" pareto_fronts/fpmul_f16_deepsyn_standalone/pareto_front.json 121 1618 \
        -o plots/fpmul/
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

_RC = {
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
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

# Half-text-width variant: rendered at print size so nothing is downscaled in
# LaTeX and the fonts stay physically legible (see paper FIGURE_PAIRS).
_RC_NARROW = {**_RC, "font.size": 7, "axes.labelsize": 7,
              "xtick.labelsize": 6, "ytick.labelsize": 6}

# Indigo of "Phases 1-3" in plot_fpmul_pareto.py: the pre-Deepsyn front here is
# the SAME front as that panel's, so they share a colour to make the link visible.
_PHASE13_COLOR = "#332288"

_COLORS = ["#6699DD", "#2D8C7E", "#CC6677", "#88CCEE", "#DDCC77"]


def _load_paired(path: Path, orig_area=None, orig_delay=None,
                  originals_manifest: list[dict] | None = None):
    """Load (original, optimized) pairs from a JSON file.

    If original_area/original_delay fields exist in the entries, use those.
    If originals_manifest is provided, join by 'design' field.
    Otherwise use the provided orig_area/orig_delay as the shared original.
    """
    entries = json.loads(path.read_text())

    # Build lookup from originals manifest if provided
    orig_by_name = {}
    if originals_manifest:
        for e in originals_manifest:
            name = e.get("extracted_file", "").split("/")[0]
            if name:
                orig_by_name[name] = e

    pairs = []
    for e in entries:
        if e.get("status") != "ok" or not e.get("passed", True):
            continue
        # batch_eval can emit original_* keys with value None (manifest join
        # miss) — treat None the same as a missing key.
        oa = e.get("original_area")
        od = e.get("original_delay")
        if oa is None:
            oa = orig_area
        if od is None:
            od = orig_delay
        # Fall back to originals manifest. Join on source_design (the SEED) —
        # fpmul names the seed in 'design' too, but pdpu puts the trajectory there.
        key = e.get("source_design") or e.get("design")
        if (oa is None or od is None) and key in orig_by_name:
            o = orig_by_name[key]
            oa = oa or o.get("area")
            od = od or o.get("delay")
        a = e.get("area")
        d = e.get("delay")
        if oa is None or od is None or a is None or d is None:
            continue
        pairs.append((float(oa), float(od), float(a), float(d)))
    return pairs


_COMMERCIAL_REF = [
    {"timing_ps": 905.8, "area_um2": 134.9},
    {"timing_ps": 1004.6, "area_um2": 118.8},
    {"timing_ps": 1200.3, "area_um2": 90.9},
    {"timing_ps": 1401.7, "area_um2": 84.4},
    {"timing_ps": 2001.9, "area_um2": 78.6},
    {"timing_ps": 3002.4, "area_um2": 77.6},
]


def plot_arrows(datasets: list, output_dir: Path,
                originals_manifest: list[dict] | None = None,
                show_commercial: bool = False,
                show_equi_adp: bool = False,
                xlim: tuple[float, float] | None = None,
                ylim: tuple[float, float] | None = None,
                front_only_labels: set | None = None,
                front_with_originals: set | None = None,
                originals_label: str = "Phases 1\u20133 Pareto",
                narrow: bool = False) -> Path:
    """Plot arrows from original to optimized for each dataset.

    Args:
        datasets: list of (label, pairs, color) where pairs = [(orig_a, orig_d, opt_a, opt_d), ...]
        originals_manifest: optional list of dicts with 'area' and 'delay' keys for ALL
            original Pareto points (used for the before-Pareto front staircase).
            If None, the before-front is computed from the arrow origins only.
    """
    plt.rcParams.update(_RC_NARROW if narrow else _RC)
    fig, ax = plt.subplots(figsize=(2.75, 2.15) if narrow else (7, 5))

    front_only_labels = front_only_labels or set()
    front_with_originals = front_with_originals or set()
    ms = 0.45 if narrow else 1.0        # marker scale
    handles = []
    for label, pairs, color in datasets:
        if label in front_only_labels:
            # Comparison dataset rendered as its Pareto staircase only (no
            # arrow fan / points) — e.g. the double-effort from-scratch arm.
            handles.append(Line2D([], [], color=color, linestyle="-",
                                  linewidth=2.0, label=label))
            continue
        for oa, od, a, d in pairs:
            ax.annotate(
                "", xy=(a, d), xytext=(oa, od),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=color,
                    lw=0.8,
                    mutation_scale=8,
                    alpha=0.07,
                ),
                zorder=3,
            )
            # Original point
            ax.scatter([oa], [od], c="gray", marker="o", s=20 * ms,
                       zorder=4, edgecolors="none", alpha=0.12)

        handles.append(
            Line2D([], [], color=color, linestyle="-", linewidth=2.0, label=label)
        )

    # Pareto fronts (before and after)
    from plot_pareto_paper import _pareto_front, _stepify

    # Before-front: use originals_manifest if provided, else arrow origins
    if originals_manifest:
        all_orig = [(e["area"], e["delay"]) for e in originals_manifest]
        # Also plot any original points not covered by arrows
        arrow_orig_set = {(oa, od) for _, pairs, _ in datasets for oa, od, _, _ in pairs}
        for a, d in all_orig:
            if (a, d) not in arrow_orig_set:
                ax.scatter([a], [d], c="gray", marker="o", s=50 * ms,
                           zorder=4, edgecolors="none", alpha=0.7)
    else:
        all_orig = [(oa, od) for _, pairs, _ in datasets for oa, od, _, _ in pairs]

    all_opt = [(a, d) for _, pairs, _ in datasets for _, _, a, d in pairs]

    if all_orig:
        front_orig = _pareto_front(all_orig)
        xs, ys = _stepify(front_orig)
        ax.plot(xs, ys, color=_PHASE13_COLOR, linewidth=2.0, linestyle="-",
                zorder=8, alpha=0.8)

    # Per-dataset Pareto fronts (same color as dataset, full opacity). Cumulative
    # for refined sets: a Phase-3 design deepsyn failed to beat is still RTLScout's.
    for label, pairs, color in datasets:
        opt_pts = [(a, d) for _, _, a, d in pairs]
        if originals_manifest and label in front_with_originals:
            opt_pts = opt_pts + list(all_orig)
        if opt_pts:
            front = _pareto_front(opt_pts)
            xs, ys = _stepify(front)
            ax.plot(xs, ys, color=color, linewidth=2.0, zorder=8)

    # Axis limits — include every drawn arrow origin: with an originals
    # manifest, all_orig holds only manifest points, so a standalone
    # dataset's shared origin (the stage-0 baseline) would otherwise fall
    # outside the computed range (and annotate arrows are not clipped).
    import numpy as np
    arrow_origins = [(oa, od) for _, pairs, _ in datasets for oa, od, _, _ in pairs]
    all_points = list(all_orig) + list(all_opt) + arrow_origins
    if all_points:
        a_min = xlim[0] if xlim else min(a for a, _ in all_points) * 0.95
        a_max = xlim[1] if xlim else max(a for a, _ in all_points) * 1.05
        d_min_auto = min(d for _, d in all_points) * 0.95
        # Extra top headroom in the narrow variant so the legend clears the data.
        d_max_auto = max(d for _, d in all_points) * (1.28 if narrow else 1.05)
        d_min = ylim[0] if (ylim and ylim[0] > 0) else d_min_auto
        d_max = ylim[1] if (ylim and ylim[1] > 0) else d_max_auto

        # Equi-area-delay-product lines (hyperbolas: area * delay = const)
        if show_equi_adp:
            adp_values = sorted(set(int(a * d / 10000) * 10000
                                    for a, d in all_points))
            if len(adp_values) > 4:
                step = len(adp_values) // 4
                adp_values = adp_values[::step]

            a_line = np.linspace(a_min, a_max, 200)
            for i, adp in enumerate(adp_values):
                d_line = adp / a_line
                mask = (d_line >= d_min) & (d_line <= d_max)
                if mask.any():
                    ax.plot(a_line[mask], d_line[mask], color="#999999", linewidth=0.8,
                            linestyle=":", zorder=1, alpha=0.7)

        ax.set_xlim(a_min, a_max)
        ax.set_ylim(d_min, d_max)

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")

    # Commercial reference (optional) — plotted after limits are set,
    # then limits are re-applied so commercial data doesn't expand the view.
    if show_commercial:
        ref_areas = [p["area_um2"] for p in _COMMERCIAL_REF]
        ref_delays = [p["timing_ps"] for p in _COMMERCIAL_REF]
        ref_sorted = sorted(zip(ref_areas, ref_delays), key=lambda x: x[0])
        ref_a_sorted = [a for a, _ in ref_sorted]
        ref_d_sorted = [d for _, d in ref_sorted]
        ax.plot(ref_a_sorted, ref_d_sorted, color="#555555", linewidth=1.5,
                linestyle="-.", zorder=8, alpha=0.8, clip_on=True)
        for a, d in zip(ref_areas, ref_delays):
            if a_min <= a <= a_max and d_min <= d <= d_max:
                ax.scatter([a], [d], c="#555555", marker="*", s=80 * ms, zorder=9,
                           edgecolors="none")
        ax.set_xlim(a_min, a_max)
        ax.set_ylim(d_min, d_max)

    # Add marker legend entries
    handles.append(Line2D([], [], marker="o", color="gray", linestyle="None",
                          markersize=5 * (0.7 if narrow else 1.0),
                          markeredgecolor="none",
                          alpha=0.7, label="Before Deepsyn"))
    handles.append(Line2D([], [], color=_PHASE13_COLOR, linestyle="-", linewidth=1.5,
                          alpha=0.8, label=originals_label))
    if show_equi_adp:
        handles.append(Line2D([], [], color="#AAAAAA", linestyle=":", linewidth=0.8,
                              alpha=0.6, label="Equi-ADP"))
    if show_commercial:
        handles.append(Line2D([], [], marker="*", color="#555555", linestyle="-.",
                              markeredgecolor="none", markeredgewidth=0,
                              linewidth=1.5, markersize=8 * (0.7 if narrow else 1.0), alpha=0.8,
                              label="Commercial (Cadence Genus)"))
    # zorder: fronts/commercial ref draw at 8-10, legends default to 5.
    leg = ax.legend(handles=handles, loc="upper right", framealpha=0.9,
              fontsize=6 if narrow else 8,   # 6pt = the floor neurips_2026.sty enforces
              handlelength=1.2 if narrow else 2.0,
              borderpad=0.25 if narrow else 0.4,
              labelspacing=0.25 if narrow else 0.5,
              handletextpad=0.4 if narrow else 0.8)
    leg.set_zorder(20)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("deepsyn_arrows_narrow.png" if narrow
                         else "deepsyn_arrows.png")
    fig.savefig(path)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Plot area-delay arrows: original → Deepsyn-optimized")
    parser.add_argument("--data", nargs=2, action="append", default=[],
                        metavar=("LABEL", "JSON"),
                        help="Dataset with original_area/original_delay in entries")
    parser.add_argument("--front-only", action="append", default=[],
                        metavar="LABEL",
                        help="Render this dataset's Pareto staircase only "
                             "(no arrows/points); may repeat.")
    parser.add_argument("--standalone", nargs=4, action="append", default=[],
                        metavar=("LABEL", "JSON", "ORIG_AREA", "ORIG_DELAY"),
                        help="Dataset with shared original point")
    parser.add_argument("--default", action="store_true",
                        help="Use default fpmul datasets")
    parser.add_argument("--originals", type=Path, default=None,
                        help="JSON manifest with ALL original Pareto points (for before-front). "
                             "Entries must have 'area' and 'delay' fields.")
    parser.add_argument("--narrow", action="store_true",
                        help="render at half text width (paper subfigure)")
    parser.add_argument("--originals-label", default="Phases 1\u20133 Pareto",
                        help="legend label for the originals (pre-deepsyn) front")
    parser.add_argument("--commercial", action="store_true",
                        help="Overlay commercial reference data (Cadence Genus on ASAP7)")
    parser.add_argument("--equi-adp", action="store_true",
                        help="Show equi-area-delay-product hyperbola lines")
    parser.add_argument("--xlim", nargs=2, type=float, default=None,
                        metavar=("MIN", "MAX"), help="Manual x-axis limits (area)")
    parser.add_argument("--ylim", nargs=2, type=float, default=None,
                        metavar=("MIN", "MAX"), help="Manual y-axis limits (delay)")
    parser.add_argument("-o", "--output", type=Path, default=Path("plots/fpmul"),
                        help="Output directory")
    args = parser.parse_args()

    datasets = []

    if args.default or (not args.data and not args.standalone):
        # Default fpmul datasets
        pairs_10 = _load_paired(Path("pareto_fronts/aligned/pareto_fpmul_deepsyn/batch_deepsyn_results.json"))
        pairs_100 = _load_paired(Path("pareto_fronts/aligned/pareto_fpmul_deepsyn_full/batch_deepsyn_results.json"))
        pairs_sa = _load_paired(Path("pareto_fronts/fpmul_f16_deepsyn_standalone_all/pareto_front.json"),
                                orig_area=121.0, orig_delay=1618.1757)
        datasets = [
            ("Agent + Deepsyn 10%", pairs_10, _COLORS[0]),
            ("Agent + Deepsyn 100%", pairs_100, _COLORS[1]),
            ("Standalone Deepsyn", pairs_sa, _COLORS[2]),
        ]
    else:
        for i, (label, json_path) in enumerate(args.data):
            pairs = _load_paired(Path(json_path))
            datasets.append((label, pairs, _COLORS[i % len(_COLORS)]))
        for i, (label, json_path, oa, od) in enumerate(args.standalone):
            pairs = _load_paired(Path(json_path), orig_area=float(oa), orig_delay=float(od))
            datasets.append((label, pairs, _COLORS[(len(args.data) + i) % len(_COLORS)]))

    # Load originals manifest if provided
    originals_manifest = None
    if args.originals:
        originals_manifest = json.loads(args.originals.read_text())

    # Re-load datasets with originals manifest for joining
    if originals_manifest and not args.default:
        datasets = []
        for i, (label, json_path) in enumerate(args.data):
            pairs = _load_paired(Path(json_path), originals_manifest=originals_manifest)
            datasets.append((label, pairs, _COLORS[i % len(_COLORS)]))
        for i, (label, json_path, oa, od) in enumerate(args.standalone):
            pairs = _load_paired(Path(json_path), orig_area=float(oa), orig_delay=float(od))
            datasets.append((label, pairs, _COLORS[(len(args.data) + i) % len(_COLORS)]))

    path = plot_arrows(datasets, args.output, originals_manifest=originals_manifest,
                        show_commercial=args.commercial,
                        show_equi_adp=args.equi_adp,
                        xlim=tuple(args.xlim) if args.xlim else None,
                        ylim=tuple(args.ylim) if args.ylim else None,
                        front_only_labels=set(args.front_only),
                        front_with_originals={lbl for lbl, _ in args.data},
                        originals_label=args.originals_label,
                        narrow=args.narrow)
    print(f"Saved: {path}")
    print(f"Saved: {path.with_suffix('.pdf')}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Agent-campaign area-vs-delay with the Phase-1-only front drawn separately.

Same visual language as plot_pareto_paper.py's combined figure (marker shape per
campaign, colour = run index, shared colourbar), but each campaign gets TWO
Pareto fronts: Phase 1 alone (dashed) and Phases 1+2 (solid), so Phase 2's
incremental contribution is visible per objective.

Run indices follow the same offset rule as the paper figure: within a campaign,
Phase 1 keeps 0..n-1 and Phase 2 continues at n, so the colourbar also separates
the phases.

    plot_phase_fronts.py --campaign "area-targeted" runs/p1_area runs/p2_area \\
                         --campaign "delay-targeted" runs/p1_delay runs/p2_delay \\
                         -o figures/phase_fronts [--narrow]
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from plot_pareto_paper import load_multirun, _pareto_front, _stepify

_RC = {
    "font.family": "serif", "font.size": 10, "axes.labelsize": 11,
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05, "axes.grid": True, "grid.alpha": 0.3,
    "grid.linestyle": "--", "axes.spines.top": False, "axes.spines.right": False,
}
# Half-text-width twin, rendered at print size so LaTeX does not downscale it.
_RC_NARROW = {**_RC, "font.size": 7, "axes.labelsize": 7,
              "xtick.labelsize": 6, "ytick.labelsize": 6}

# cmap / Pareto-line colour / marker, in campaign order
_STYLES = [("Purples", "#332288", "o"), ("Oranges", "#B34700", "^"),
           ("Greens", "#117733", "s"), ("Blues", "#6699DD", "D")]
_CMAP_LO = 0.35   # avoids invisible early runs
# Explicit dash pattern (not "--"): at a 6pt legend the default period is long
# enough that only one dash lands in the handle, which does not read as dashed.
_P1_DASH = (0, (2.2, 1.1))


def _truncated_cmap(name, lo=_CMAP_LO, hi=1.0, n=256):
    base = matplotlib.colormaps[name]
    return matplotlib.colors.LinearSegmentedColormap.from_list(
        f"{name}_trunc", base(np.linspace(lo, hi, n)), N=n)


def _per_run(root: Path, offset: int = 0):
    """[(area, delay, run_index)] over every passing eval, plus the run count."""
    pts = []
    runs = sorted(load_multirun(Path(root)).get("runs", []),
                  key=lambda r: r.get("run_index", 0))
    for run in runs:
        ridx = run.get("run_index", 0) + offset
        for ev in run.get("all_evals", []):
            if not ev.get("passed"):
                continue
            m = ev.get("metrics") or {}
            if m.get("area") is not None and m.get("delay") is not None:
                pts.append((m["area"], m["delay"], ridx))
    return pts, len(runs)


def plot_phase_fronts(campaigns, output_dir: Path, starting_point=None,
                      narrow: bool = False) -> Path:
    plt.rcParams.update(_RC_NARROW if narrow else _RC)
    ms = 0.45 if narrow else 1.0
    # narrower than the other half-width figures: the colourbar still adds
    # ~0.19in, and the PDF must land at ~2.7in so LaTeX does not downscale it
    # (which would push the 6pt legend under the neurips 6pt floor).
    fig = plt.figure(figsize=(2.515, 2.15) if narrow else (6.6, 4.6))
    # right column split: the colourbar takes the lower rows, leaving the top
    # for an upright "Run index" title (cheaper than the rotated side label,
    # which cost ~0.17in of width and had to be dropped in the narrow twin)
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 0.03],
                          height_ratios=[0.15, 0.85], wspace=0.03, hspace=0.0)
    ax, cax = fig.add_subplot(gs[:, 0]), fig.add_subplot(gs[1, 1])

    series, vmax = [], 0
    for i, (label, p1_root, p2_root) in enumerate(campaigns):
        p1, n1 = _per_run(p1_root)
        p2, _ = _per_run(p2_root, offset=n1)
        if not (p1 or p2):
            continue
        series.append((label, p1, p2, *_STYLES[i % len(_STYLES)]))
        vmax = max(vmax, max(r for *_, r in p1 + p2))

    for z, (label, p1, p2, cmap_name, front_col, marker) in enumerate(series):
        pts = p1 + p2
        ax.scatter([a for a, _, _ in pts], [d for _, d, _ in pts],
                   c=[r for *_, r in pts], cmap=_truncated_cmap(cmap_name),
                   vmin=0, vmax=vmax, marker=marker, s=25 * ms, alpha=0.55,
                   zorder=3 + z, edgecolors="none")
        # the delay-targeted Phases-1+2 front draws above the other fronts for
        # readability; Phase-1 fronts, scatter stacking, and legend order all
        # stay in campaign order
        solid_z = 6 + (len(series) if "delay" in label else z)
        for subset, style, width, fz in (
                ([(a, d) for a, d, _ in p1], _P1_DASH, 2.2, 6 + z),
                ([(a, d) for a, d, _ in pts], "-", 2.2, solid_z)):
            xs, ys = _stepify(_pareto_front(subset))
            ax.plot(xs, ys, color=front_col, linestyle=style,
                    linewidth=width * (0.8 if narrow else 1.0), zorder=fz)

    if starting_point:
        ax.scatter([starting_point[0]], [starting_point[1]], marker="*",
                   s=200 * ms, c="#222222", zorder=10, edgecolors="none")

    ax.set_xlabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_ylabel("Delay (ps)")
    if narrow:                      # headroom so the legend clears the data
        ax.set_ylim(top=ax.get_ylim()[1] * 1.05)

    mappable = plt.cm.ScalarMappable(cmap=_truncated_cmap("Greys"),
                                     norm=plt.Normalize(vmin=0, vmax=vmax))
    mappable.set_array([])
    cb = fig.colorbar(mappable, cax=cax)
    cax.set_title("Run\nindex", fontsize=5 if narrow else 8, pad=3)
    cb.ax.tick_params(labelsize=5 if narrow else 8, pad=1)

    handles = [Line2D([], [], marker=mk, color=col, linestyle="-", linewidth=1.8,
                      markersize=(5 if not narrow else 3.5),
                      markerfacecolor=matplotlib.colormaps[cm](0.55),
                      markeredgecolor="none", label=lbl)
               for lbl, _, _, cm, col, mk in series]
    handles += [Line2D([], [], color="#555555", linestyle=_P1_DASH, linewidth=2.2,
                       label="Phase 1 front"),
                Line2D([], [], color="#555555", linestyle="-", linewidth=2.2,
                       label="Phases 1+2 front")]
    leg = ax.legend(handles=handles, loc="upper right", framealpha=1.0,
                    fontsize=6 if narrow else 8,
                    **({"handlelength": 1.9, "borderpad": 0.25,
                        "labelspacing": 0.25, "handletextpad": 0.4}
                       if narrow else {"labelspacing": 0.35}))
    leg.set_zorder(20)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (f"phase_fronts{'_narrow' if narrow else ''}.pdf")
    fig.savefig(path)
    fig.savefig(path.with_suffix(".png"))
    plt.close(fig)
    print(f"Saved: {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", nargs=3, action="append", required=True,
                    metavar=("LABEL", "P1_ROOT", "P2_ROOT"),
                    help="campaign label and its phase-1 / phase-2 multirun roots")
    ap.add_argument("--starting-point", nargs=2, type=float, default=None,
                    metavar=("AREA", "DELAY"))
    ap.add_argument("--narrow", action="store_true",
                    help="render at half text width (paper subfigure)")
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()
    plot_phase_fronts([(l, p1, p2) for l, p1, p2 in args.campaign],
                      args.output, starting_point=args.starting_point,
                      narrow=args.narrow)


if __name__ == "__main__":
    main()

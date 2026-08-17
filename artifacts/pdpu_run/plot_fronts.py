#!/usr/bin/env python3
"""One area-vs-delay figure holding every PDPU front: each phase, each language.

Colour encodes the phase, linestyle/marker the language. Faint markers are all
evaluated points of that series (one per design x eval target delay); the solid
step line is that series' own Pareto front.

    plot_fronts.py                 # the profile's latest run
    plot_fronts.py -o /tmp/fig     # explicit output stem
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.lines import Line2D                   # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdpu_config as cfg                             # noqa: E402

# Paul Tol qualitative palette, as in plot_pareto_paper.py
_PHASE_STYLE = {
    "Starting design":             ("#888888", "*", 11),
    "Phase 1 (agent)":             ("#332288", "o", 5),
    "Phase 2 (+decorators)":       ("#88CCEE", "o", 5),
    "Phase 4 (deepsyn refine)":    ("#117733", "s", 5),
    "From scratch, equal compute": ("#DDCC77", "^", 5),
    "From scratch, 2x effort":     ("#CC6677", "v", 5),
}
_LANG_STYLE = {"verilog": ("-", "Verilog"), "spirehdl": ("--", "Spire")}

_RC = {
    "font.family": "serif", "font.size": 10, "axes.labelsize": 11,
    "axes.titlesize": 12, "legend.fontsize": 8, "xtick.labelsize": 9,
    "ytick.labelsize": 9, "figure.dpi": 300, "savefig.dpi": 300,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.05,
    "axes.grid": True, "grid.alpha": 0.3, "grid.linestyle": "--",
    "axes.spines.top": False, "axes.spines.right": False,
}


def _pareto(points: list) -> list:
    """Non-dominated (delay, area) pairs, sorted by delay."""
    out = []
    for p in sorted(points):
        if not out or p[1] < out[-1][1]:        # strictly better area
            out.append(p)
    return out


def _series(lang: str) -> list:
    """(label, [(delay, area), ...]) for every phase of one language."""
    import run_all                              # row sources live with the pipeline
    series = []
    for label, path in run_all._row_sources(lang):
        if path is None:
            pts = [(d, a) for a, d in run_all._baseline_points(lang)]
        else:
            pts = [(d, a) for a, d in run_all._points(path)]
        if pts:
            series.append((label, pts))
    return series


def plot(out_stem: Path) -> Path:
    plt.rcParams.update(_RC)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    seen_phases, drawn = [], 0

    for lang in ("verilog", "spirehdl"):
        ls, _ = _LANG_STYLE[lang]
        for label, pts in _series(lang):
            colour, marker, ms = _PHASE_STYLE.get(label, ("#000000", "o", 5))
            ax.plot([d for d, _ in pts], [a for _, a in pts], linestyle="None",
                    marker=marker, markersize=ms * 0.6, color=colour,
                    alpha=0.18, zorder=2)
            front = _pareto(pts)
            # The baseline is ONE design measured at each target delay, not a
            # front of distinct designs — draw its points, never a staircase.
            step = label != "Starting design" and len(front) > 1
            ax.plot([d for d, _ in front], [a for _, a in front],
                    linestyle=ls if step else "None",
                    marker=marker, markersize=ms, color=colour,
                    linewidth=1.4, alpha=0.95, zorder=3,
                    drawstyle="steps-post" if step else "default")
            if label not in seen_phases:
                seen_phases.append(label)
            drawn += 1

    if not drawn:
        raise RuntimeError("no front data found — run the pipeline first")

    ax.set_xlabel("Delay (ps)")
    ax.set_ylabel(r"Area ($\mathrm{\mu m^2}$)")
    ax.set_title(f"PDPU: area/delay fronts by phase and language "
                 f"({cfg.RUN_NAME})", fontsize=10)

    phase_handles = [Line2D([], [], color=_PHASE_STYLE[p][0],
                            marker=_PHASE_STYLE[p][1], linestyle="-",
                            markersize=_PHASE_STYLE[p][2], label=p)
                     for p in seen_phases]
    lang_handles = [Line2D([], [], color="#444444", linestyle=ls, label=name)
                    for ls, name in _LANG_STYLE.values()]
    leg_phase = ax.legend(handles=phase_handles, loc="upper left", frameon=False,
                          bbox_to_anchor=(1.01, 1.0), title="Phase",
                          title_fontsize=8, alignment="left")
    ax.add_artist(leg_phase)
    leg_lang = ax.legend(handles=lang_handles, loc="lower left", frameon=False,
                         bbox_to_anchor=(1.01, 0.0), title="Language",
                         title_fontsize=8, alignment="left")

    out_stem.parent.mkdir(parents=True, exist_ok=True)
    # legends sit outside the axes — name them so the tight bbox keeps them
    extra = [leg_phase, leg_lang]
    fig.savefig(out_stem.with_suffix(".pdf"), bbox_inches="tight",
                bbox_extra_artists=extra)
    fig.savefig(out_stem.with_suffix(".png"), bbox_inches="tight",
                bbox_extra_artists=extra)
    plt.close(fig)
    return out_stem.with_suffix(".pdf")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", type=Path,
                    default=cfg.DATA / "figures" / "fronts_area_delay")
    args = ap.parse_args()
    print(f"wrote {plot(args.output)}")


if __name__ == "__main__":
    main()

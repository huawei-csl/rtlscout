#!/usr/bin/env python3
"""Plot area (x) vs delay (y) overlaying agent sweep results and tech_eval reference data.

The agent records come from a runs directory (same formats as plot_area_delay.py).
The reference records come from one or more tech_eval PPA JSON files whose
``case_results`` contain per-architecture, per-target-delay measurements.

Visual convention
-----------------
- Agent results : filled circles  (●), one colour per LLM model
- Reference data: filled triangles (▲), one colour per architecture (fsa_cls_name)
- Agent Pareto front  : black step line  — best area/delay trade-off across all agent models
- Ref Pareto front    : dark-red step line — best area/delay trade-off across all ref architectures

A secondary legend shows the marker/line shapes so the source is always clear.

Usage
-----
  python plot_area_delay_with_ref.py runs/cost_lang_sweep_20260223_073255 \\
      --ref deps/tech_eval/results/ppa/Add_a16_results.json \\
      [--ref-benchmark add16] \\
      [--output-dir plots/] \\
      [--variant verilog_area]

  # Multiple ref files, each with its own benchmark mapping:
  python plot_area_delay_with_ref.py runs/sweep/ \\
      --ref deps/tech_eval/results/ppa/Add_a16_results.json --ref-benchmark add16 \\
      --ref deps/tech_eval/results/ppa/Add_a4_results.json  --ref-benchmark add4
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.lines as mlines
import matplotlib.pyplot as plt

# Re-use the agent-side loader from the sibling script.
from plot_area_delay import load_results, _COLORS, _short_model
from tech_eval.ppa_extract.core.ppa_extraction import PPA_REPORT_TIME_UNIT


# ── Pareto helpers (ported from tech_eval/src/…/plotting2.py) ─────────────────

def _pareto_front(points):
    """Return the Pareto-optimal (area, delay) points (lower is better for both).

    Sorts by area ascending, then keeps only points where delay is
    non-increasing — i.e. the staircase lower-left boundary.
    """
    pts = sorted(points, key=lambda p: (p[0], p[1]))
    front = []
    best_y = float("inf")
    for x, y in pts:
        if y <= best_y:
            front.append((x, y))
            best_y = y
    return front


def _stepify(front):
    """Convert a sorted Pareto front into a staircase (xs, ys) for plt.plot().

    Each step goes horizontally to the next x value, then drops vertically
    to the next y value, producing the characteristic staircase shape.
    """
    if not front:
        return [], []
    xs = [front[0][0]]
    ys = [front[0][1]]
    for (x_next, y_next), (_, y_prev) in zip(front[1:], front[:-1]):
        xs.extend([x_next, x_next])
        ys.extend([y_prev, y_next])
    return xs, ys


# ── colour / marker constants ─────────────────────────────────────────────────

# Agent models use the first palette; ref architectures use the second.
# Both palettes are long enough for typical use; they wrap if exceeded.
_AGENT_COLORS = [
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a",
    "#66a61e", "#e6ab02", "#a6761d", "#666666",
]
_REF_COLORS = [
    "#4477AA", "#EE6677", "#228833", "#CCBB44",
    "#66CCEE", "#AA3377", "#BBBBBB", "#332288",
]

_AGENT_MARKER = "o"   # filled circle
_REF_MARKER   = "^"   # filled triangle-up

# Step-line colours for the two combined Pareto fronts.
_AGENT_PARETO_COLOR = "#111111"   # near-black
_REF_PARETO_COLOR   = "#cc2222"   # dark red


# ── tech_eval loader ───────────────────────────────────────────────────────────

def load_tech_eval_records(
    path: Path,
    benchmark_override: Optional[str] = None,
    group_by: str = "fsa_cls_name",
    case_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Parse a tech_eval ``*_results.json`` file into flat records.

    Parameters
    ----------
    path:
        Path to the tech_eval JSON file.
    benchmark_override:
        When given, every case in ``case_results`` is placed under this
        benchmark label (useful for aligning with an agent benchmark name,
        e.g. ``"add16"``).  When ``None`` the case name itself is used as the
        benchmark label (e.g. ``"add_signed"``).
    group_by:
        Entry field used to colour/group reference points (default
        ``"fsa_cls_name"``).  Use ``"ppa_cls_name"`` to group by multiplier
        architecture instead of prefix-adder stage.
    case_filter:
        When given, only case names present in this list are loaded.
        When ``None`` (default) all cases are included.

    Returns
    -------
    List of dicts with at least: benchmark, model, area, delay, power,
    target_delay, case, source="ref".

    Exact duplicates — same (case, group_by value, area, delay) — are
    removed; the tech_eval files contain two identical runs per point.
    """
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read {path}: {exc}")
        return []

    case_results = data.get("case_results", {})
    if not case_results:
        print(f"Warning: no case_results found in {path}")
        return []

    allowed_cases = set(case_filter) if case_filter else None

    records: List[Dict[str, Any]] = []
    seen: set = set()

    for case_name, entries in case_results.items():
        if allowed_cases is not None and case_name not in allowed_cases:
            continue
        benchmark = benchmark_override if benchmark_override is not None else case_name

        for entry in entries:
            group_val = entry.get(group_by, "unknown")
            area      = entry.get("area")
            delay     = entry.get("delay")

            if area is None or delay is None:
                continue

            # Drop exact duplicates (same synthesis outcome regardless of seed/run).
            key = (case_name, group_val, float(area), float(delay))
            if key in seen:
                continue
            seen.add(key)

            records.append({
                "benchmark":    benchmark,
                "model":        group_val,
                "area":         float(area),
                "delay":        float(delay),
                "power":        float(entry.get("power") or 0.0),
                "target_delay": entry.get("target_delay"),
                "case":         case_name,
                "source":       "ref",
                # Keep these fields so the record is uniform with agent records.
                "variant":      "",
                "language":     "",
                "eval_index":   None,
            })

    return records


# ── plotting ──────────────────────────────────────────────────────────────────

def _add_source(fig, source: str, ax=None):
    """Add a small source path annotation just above the plot title.

    If *ax* is given, the y position is computed from the axes bounding box so
    the text lands right above the title rather than at the very top of the
    figure.  Falls back to fig-top placement when *ax* is None (combined grid).
    Returns the Text object or None.
    """
    if not source:
        return None
    if ax is not None:
        # ax.get_position().y1 is the axes top in figure coordinates.
        # Adding ~0.06 (≈18 pt on a 5-inch figure) clears the axes title.
        y = ax.get_position().y1 + 0.06
    else:
        y = 0.99
    return fig.text(0.5, y, source, fontsize=6, color="gray",
                    ha="center", va="bottom", transform=fig.transFigure)


def plot_area_delay_with_ref(
    agent_records: List[Dict[str, Any]],
    ref_records:   List[Dict[str, Any]],
    output_dir:    Path,
    variant_filter: Optional[str] = None,
    source: str = "",
    combine: bool = False,
) -> List[Path]:
    if variant_filter:
        agent_records = [r for r in agent_records if r["variant"] == variant_filter]

    # Force all records onto a single plot by unifying benchmark labels.
    if combine:
        all_benchmarks = sorted({r["benchmark"] for r in agent_records + ref_records})
        combined_label = " + ".join(all_benchmarks)
        for r in agent_records:
            r["benchmark"] = combined_label
        for r in ref_records:
            r["benchmark"] = combined_label

    all_records = agent_records + ref_records

    if not all_records:
        print("No records with PPA (area + delay) data found.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all benchmarks that have at least one record from either source.
    benchmarks = sorted({r["benchmark"] for r in all_records})

    # Separate model lists so each gets its own colour palette.
    agent_models = sorted({r["model"] for r in agent_records})
    ref_models   = sorted({r["model"] for r in ref_records})

    agent_color_map = {m: _AGENT_COLORS[i % len(_AGENT_COLORS)] for i, m in enumerate(agent_models)}
    ref_color_map   = {m: _REF_COLORS[i   % len(_REF_COLORS)]   for i, m in enumerate(ref_models)}

    saved: List[Path] = []

    for bench in benchmarks:
        bench_agent = [r for r in agent_records if r["benchmark"] == bench]
        bench_ref   = [r for r in ref_records   if r["benchmark"] == bench]
        if not bench_agent and not bench_ref:
            continue

        fig, ax = plt.subplots(figsize=(12, 5))

        # ── agent points ──────────────────────────────────────────────────────
        for model in agent_models:
            model_recs = [r for r in bench_agent if r["model"] == model]
            if not model_recs:
                continue
            color = agent_color_map[model]
            ax.scatter(
                [r["area"]  for r in model_recs],
                [r["delay"] for r in model_recs],
                color=color,
                marker=_AGENT_MARKER,
                s=70,
                zorder=4,
                label=_short_model(model),
                edgecolors="white",
                linewidths=0.5,
            )

        # ── reference points ──────────────────────────────────────────────────
        for arch in ref_models:
            arch_recs = [r for r in bench_ref if r["model"] == arch]
            if not arch_recs:
                continue
            color = ref_color_map[arch]
            # Shorten long class names for the legend.
            short_arch = arch.replace("PrefixFinalStage", "").replace("FinalAdder", "").replace("Prefix", "")
            ax.scatter(
                [r["area"]  for r in arch_recs],
                [r["delay"] for r in arch_recs],
                color=color,
                marker=_REF_MARKER,
                s=80,
                zorder=3,
                label=f"ref: {short_arch}",
                edgecolors="white",
                linewidths=0.5,
            )

        # ── Pareto fronts ─────────────────────────────────────────────────────
        if bench_agent:
            front = _pareto_front((r["area"], r["delay"]) for r in bench_agent)
            xs, ys = _stepify(front)
            ax.plot(xs, ys, color=_AGENT_PARETO_COLOR, linewidth=2.0,
                    zorder=5, label="Agent Pareto")

        if bench_ref:
            front = _pareto_front((r["area"], r["delay"]) for r in bench_ref)
            xs, ys = _stepify(front)
            ax.plot(xs, ys, color=_REF_PARETO_COLOR, linewidth=2.0,
                    zorder=5, label="Ref Pareto")

        ax.set_xlabel("Area (µm²)", fontsize=11)
        ax.set_ylabel(f"Delay ({PPA_REPORT_TIME_UNIT})", fontsize=11)
        ax.set_title(f"{bench} — Area vs Delay", fontsize=12)
        ax.grid(True, linestyle="--", alpha=0.4)

        # Primary legend: model / architecture labels + Pareto lines (outside right).
        primary_legend = ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            borderaxespad=0,
            fontsize=7,
            title="Model / Architecture",
        )

        # Secondary legend: source shape key.
        source_handles = []
        if bench_agent:
            source_handles.append(
                mlines.Line2D([], [], marker=_AGENT_MARKER, color="gray",
                              linestyle="None", markersize=7, label="Agent output")
            )
            source_handles.append(
                mlines.Line2D([], [], color=_AGENT_PARETO_COLOR,
                              linewidth=2.0, label="Agent Pareto")
            )
        if bench_ref:
            source_handles.append(
                mlines.Line2D([], [], marker=_REF_MARKER, color="gray",
                              linestyle="None", markersize=7, label="Reference (tech_eval)")
            )
            source_handles.append(
                mlines.Line2D([], [], color=_REF_PARETO_COLOR,
                              linewidth=2.0, label="Ref Pareto")
            )
        extra_artists = [primary_legend]
        if source_handles:
            ax.add_artist(primary_legend)
            source_legend = ax.legend(
                handles=source_handles,
                loc="lower left",
                bbox_to_anchor=(1.02, 0),
                borderaxespad=0,
                fontsize=7,
                title="Source",
            )
            extra_artists.append(source_legend)

        fig.subplots_adjust(right=0.58)
        source_txt = _add_source(fig, source, ax=ax)
        if source_txt is not None:
            extra_artists.append(source_txt)
        path = output_dir / f"area_delay_ref_{bench}.png"
        fig.savefig(path, dpi=160, bbox_inches="tight",
                    bbox_extra_artists=extra_artists)
        plt.close(fig)
        saved.append(path)
        print(f"  {bench}: {len(bench_agent)} agent points, {len(bench_ref)} ref points")

    # ── combined grid: all benchmarks ─────────────────────────────────────────
    if len(benchmarks) > 1:
        ncols = min(3, len(benchmarks))
        nrows = (len(benchmarks) + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols,
                                 figsize=(5.5 * ncols, 4.5 * nrows),
                                 squeeze=False)

        for idx, bench in enumerate(benchmarks):
            ax = axes[idx // ncols][idx % ncols]
            bench_agent = [r for r in agent_records if r["benchmark"] == bench]
            bench_ref   = [r for r in ref_records   if r["benchmark"] == bench]

            for model in agent_models:
                model_recs = [r for r in bench_agent if r["model"] == model]
                if not model_recs:
                    continue
                ax.scatter(
                    [r["area"] for r in model_recs], [r["delay"] for r in model_recs],
                    color=agent_color_map[model], marker=_AGENT_MARKER,
                    s=55, zorder=4,
                    label=_short_model(model),
                    edgecolors="white", linewidths=0.4,
                )

            for arch in ref_models:
                arch_recs = [r for r in bench_ref if r["model"] == arch]
                if not arch_recs:
                    continue
                short_arch = arch.replace("PrefixFinalStage", "").replace("FinalAdder", "").replace("Prefix", "")
                ax.scatter(
                    [r["area"] for r in arch_recs], [r["delay"] for r in arch_recs],
                    color=ref_color_map[arch], marker=_REF_MARKER,
                    s=65, zorder=3,
                    label=f"ref: {short_arch}",
                    edgecolors="white", linewidths=0.4,
                )

            # Pareto fronts in grid subplots.
            if bench_agent:
                front = _pareto_front((r["area"], r["delay"]) for r in bench_agent)
                xs, ys = _stepify(front)
                ax.plot(xs, ys, color=_AGENT_PARETO_COLOR, linewidth=1.6, zorder=5)
            if bench_ref:
                front = _pareto_front((r["area"], r["delay"]) for r in bench_ref)
                xs, ys = _stepify(front)
                ax.plot(xs, ys, color=_REF_PARETO_COLOR, linewidth=1.6, zorder=5)

            ax.set_title(bench, fontsize=10)
            ax.set_xlabel("Area (µm²)", fontsize=8)
            ax.set_ylabel(f"Delay ({PPA_REPORT_TIME_UNIT})", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(True, linestyle="--", alpha=0.35)

        for idx in range(len(benchmarks), nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)

        handles, labels = axes[0][0].get_legend_handles_labels()
        if handles:
            # Append Pareto line entries to the shared legend.
            handles.append(mlines.Line2D([], [], color=_AGENT_PARETO_COLOR,
                                         linewidth=2.0, label="Agent Pareto"))
            handles.append(mlines.Line2D([], [], color=_REF_PARETO_COLOR,
                                         linewidth=2.0, label="Ref Pareto"))
            labels.append("Agent Pareto")
            labels.append("Ref Pareto")
            fig.legend(
                handles, labels,
                loc="lower center",
                ncol=min(len(agent_models) + len(ref_models) + 2, 6),
                fontsize=7,
                title="Model / Architecture  (● agent  ▲ reference)",
                bbox_to_anchor=(0.5, -0.02),
            )

        fig.suptitle("Area vs Delay — All Benchmarks", fontsize=13, y=1.01)
        fig.tight_layout()
        _add_source(fig, source)
        path = output_dir / "area_delay_ref_all.png"
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        saved.append(path)

    return saved


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scatter-plot area vs delay combining agent sweeps and tech_eval reference data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "runs_dir", nargs="+",
        help="One or more runs directories with agent results (sweep_summary.json, "
             "all_results.json, or result.json files).  Records from all directories "
             "are combined before plotting.",
    )
    parser.add_argument(
        "--ref", metavar="PATH", action="append", default=[],
        help="tech_eval PPA JSON file to overlay as reference data (may be repeated)",
    )
    parser.add_argument(
        "--ref-benchmark", metavar="NAME", action="append", default=[],
        help=(
            "Agent benchmark name to associate with the preceding --ref file "
            "(e.g. 'add16').  When omitted the tech_eval case name is used as-is. "
            "Repeat once per --ref in the same order."
        ),
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory to write plots (default: <first runs_dir>/plots)",
    )
    parser.add_argument(
        "--variant", default=None,
        help="Filter agent results to a specific variant, e.g. 'verilog_area'",
    )
    parser.add_argument(
        "--ref-group-by", default="fsa_cls_name",
        help="Entry field used to colour/group reference points "
             "(default: 'fsa_cls_name'; try 'ppa_cls_name')",
    )
    parser.add_argument(
        "--ref-case", metavar="CASE", action="append", default=[],
        help=(
            "Include only this case name from case_results in the reference data "
            "(may be repeated to allow multiple cases; default: include all cases). "
            "Example: --ref-case add_signed --ref-case add_unsigned"
        ),
    )
    parser.add_argument(
        "--cost-metric", default=None,
        help="Only include agent runs that used this cost objective "
             "(e.g. 'delay', 'area', 'power'). Read from each run's result.json.",
    )
    parser.add_argument(
        "--delay-threshold", type=float, default=None,
        help=f"Filter out results with delay above this value ({PPA_REPORT_TIME_UNIT}).",
    )
    parser.add_argument(
        "--area-threshold", type=float, default=None,
        help="Filter out results with area above this value.",
    )
    parser.add_argument(
        "--combine", action="store_true",
        help="Plot all agent and reference data on a single plot, ignoring benchmark names.",
    )
    args = parser.parse_args()

    runs_dirs = [Path(p) for p in args.runs_dir]
    for rd in runs_dirs:
        if not rd.exists():
            parser.error(f"Path not found: {rd}")

    # Pair each --ref with its optional --ref-benchmark (None if not provided).
    ref_paths      = args.ref
    ref_benchmarks = args.ref_benchmark
    if len(ref_benchmarks) > len(ref_paths):
        parser.error("More --ref-benchmark values than --ref files")
    # Pad with None for any --ref files that have no corresponding --ref-benchmark.
    ref_benchmarks += [None] * (len(ref_paths) - len(ref_benchmarks))

    first_dir = runs_dirs[0]
    output_dir = Path(args.output_dir) if args.output_dir else (
        first_dir.parent / "plots" if first_dir.is_file() else first_dir / "plots"
    )

    # ── load agent records (all runs dirs combined) ───────────────────────────
    agent_records: List[Dict[str, Any]] = []
    for rd in runs_dirs:
        recs = load_results(rd)
        print(f"Loaded {len(recs)} agent records from {rd}")
        agent_records.extend(recs)
    if len(runs_dirs) > 1:
        print(f"Combined: {len(agent_records)} agent records total")

    if args.cost_metric:
        before = len(agent_records)
        agent_records = [r for r in agent_records if r.get("cost_metric") == args.cost_metric]
        print(f"After cost-metric filter ('{args.cost_metric}'): {len(agent_records)}/{before} agent records")

    # ── load reference records ────────────────────────────────────────────────
    case_filter = args.ref_case if args.ref_case else None

    ref_records: List[Dict[str, Any]] = []
    for ref_path_str, bench_override in zip(ref_paths, ref_benchmarks):
        ref_path = Path(ref_path_str)
        recs = load_tech_eval_records(ref_path, benchmark_override=bench_override,
                                     group_by=args.ref_group_by,
                                     case_filter=case_filter)
        print(
            f"Loaded {len(recs)} reference records from {ref_path.name}"
            + (f"  →  benchmark='{bench_override}'" if bench_override else "")
            + (f"  →  cases={case_filter}" if case_filter else "")
        )
        ref_records.extend(recs)
        
    # for the dalys in agent_record which are < 500, multiply by 1000 to convert from seconds to ms (some files are in seconds, some in ms)
    for r in agent_records:
        if r["delay"] is not None and r["delay"] < 500:
            r["delay"] *= 1000
        
    if args.delay_threshold is not None:
        agent_records = [r for r in agent_records if r["delay"] <= args.delay_threshold]
        ref_records   = [r for r in ref_records   if r["delay"] <= args.delay_threshold]
        print(f"After delay threshold ({args.delay_threshold} {PPA_REPORT_TIME_UNIT}): "
              f"{len(agent_records)} agent, {len(ref_records)} ref records")
    if args.area_threshold is not None:
        agent_records = [r for r in agent_records if r["area"] <= args.area_threshold]
        ref_records   = [r for r in ref_records   if r["area"] <= args.area_threshold]
        print(f"After area threshold ({args.area_threshold}): "
              f"{len(agent_records)} agent, {len(ref_records)} ref records")

    if not agent_records and not ref_records:
        print("Nothing to plot.")
        return

    benchmarks = sorted({r["benchmark"] for r in agent_records + ref_records})
    agent_models = sorted({r["model"] for r in agent_records})
    ref_models   = sorted({r["model"] for r in ref_records})
    print(f"Benchmarks : {benchmarks}")
    print(f"Agent models: {[_short_model(m) for m in agent_models]}")
    print(f"Ref architectures: {ref_models}")
                
    saved = plot_area_delay_with_ref(
        agent_records, ref_records, output_dir,
        variant_filter=args.variant,
        source="  +  ".join(str(rd) for rd in runs_dirs),
        combine=args.combine,
    )
    for p in saved:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()

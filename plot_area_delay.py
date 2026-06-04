#!/usr/bin/env python3
"""Plot area (x) vs delay (y) scatter for each benchmark, grouped by model.

Loads results from a runs directory that contains PPA metrics.
Supports three input formats:
  - sweep_summary.json  (from run_cost_language_sweep.py)
  - all_results.json    (from run_sweep.py / run_benchmarks.py)
  - Crawled result.json files (any runs directory)

Usage:
    python experiments/plot_area_delay.py runs/cost_lang_sweep_20260223_073255
    python experiments/plot_area_delay.py runs/cost_lang_sweep_*/  --output-dir plots/
    python experiments/plot_area_delay.py runs/20260216_132421 --variant verilog_area
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from tech_eval.ppa_extract.core.ppa_extraction import PPA_REPORT_TIME_UNIT


# ── colour / marker cycle ────────────────────────────────────────────────────

_COLORS = [
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a",
    "#66a61e", "#e6ab02", "#a6761d", "#666666",
    "#4477AA", "#EE6677", "#228833", "#CCBB44",
    "#66CCEE", "#AA3377", "#BBBBBB",
]
_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "h", "<", ">"]


def _short_model(model: str) -> str:
    return model.split("/")[-1] if "/" in model else model


# ── data loading ─────────────────────────────────────────────────────────────

def _flatten_records(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Expand result dicts into one record per valid (passed) evaluation.

    Each entry in all_evals that has metrics with area+delay contributes
    one point. Runs with no valid evals are silently skipped.
    """
    out = []
    for r in raw:
        if r.get("status") == "error":
            continue
        benchmark = r.get("benchmark_name", "?")
        model = r.get("model", "?")
        variant = r.get("variant", "")
        language = r.get("language", "")
        cost_metric = r.get("cost_metric", "")

        for ev in r.get("all_evals", []):
            if not ev.get("passed"):
                continue
            m = ev.get("metrics") or {}
            if "area" not in m or "delay" not in m:
                continue
            out.append({
                "benchmark": benchmark,
                "model": model,
                "variant": variant,
                "language": language,
                "cost_metric": cost_metric,
                "area": float(m["area"]),
                "delay": float(m["delay"]),
                "power": float(m.get("power") or 0.0),
                "eval_index": ev.get("eval_index"),
            })
    return out


def _load_json_file(path: Path) -> List[Dict[str, Any]]:
    """Parse a single JSON file into a flat list of result records."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"Warning: could not parse {path}: {e}")
        return []

    # sweep_summary.json  →  data["results"]
    if "results" in data and isinstance(data["results"], list):
        return _flatten_records(data["results"])

    # all_results.json  →  data["model_results"][*]["benchmarks"]
    if "model_results" in data:
        flat = []
        for mr in data["model_results"]:
            flat.extend(mr.get("benchmarks", []))
        return _flatten_records(flat)

    # experiments_summary.json  →  data["experiments"]
    if "experiments" in data and isinstance(data["experiments"], list):
        return _flatten_records(data["experiments"])

    # Single result.json / experiment_result.json
    return _flatten_records([data])


def load_results(path: Path) -> List[Dict[str, Any]]:
    """Return a flat list of records with PPA data from any supported format.

    ``path`` may be a JSON file or a directory. Supported summary files
    (tried in order):
      sweep_summary.json        – run_cost_language_sweep.py
      all_results.json          – run_sweep.py
      experiments_summary.json  – run_experiments_parallel.py / run_experiments_beat_baseline.py
    Falls back to crawling for result.json / experiment_result.json files.

    Only records where passed=True and best_metrics contain area+delay are kept.
    Runs using the 'transistors' metric produce no PPA data and are skipped.
    """
    if path.is_file():
        return _load_json_file(path)

    runs_dir = path
    for summary_name in ("sweep_summary.json", "all_results.json", "experiments_summary.json"):
        summary = runs_dir / summary_name
        if summary.exists():
            records = _load_json_file(summary)
            if records:
                return records

    # Crawl for per-run JSON files (exclude eval_* snapshot subdirs)
    records = []
    for fname in ("result.json", "experiment_result.json"):
        for p in runs_dir.rglob(fname):
            if any(part.startswith("eval_") for part in p.parts):
                continue
            try:
                records.append(json.loads(p.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    return _flatten_records(records)


# ── plotting ─────────────────────────────────────────────────────────────────

def plot_area_delay(
    records: List[Dict[str, Any]],
    output_dir: Path,
    variant_filter: Optional[str] = None,
) -> List[Path]:
    if variant_filter:
        records = [r for r in records if r["variant"] == variant_filter]

    if not records:
        print("No records with PPA (area + delay) data found.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    benchmarks = sorted({r["benchmark"] for r in records})
    models = sorted({r["model"] for r in records})
    variants = sorted({r["variant"] for r in records if r["variant"]})

    color_map = {m: _COLORS[i % len(_COLORS)] for i, m in enumerate(models)}
    marker_map = {v: _MARKERS[i % len(_MARKERS)] for i, v in enumerate(variants or [""])}

    short_models = {m: _short_model(m) for m in models}

    saved: List[Path] = []

    # ── one figure per benchmark ──────────────────────────────────────────────
    for bench in benchmarks:
        bench_recs = [r for r in records if r["benchmark"] == bench]
        if not bench_recs:
            continue

        fig, ax = plt.subplots(figsize=(7, 5))

        # Group by model so legend has one entry per model
        for model in models:
            model_recs = [r for r in bench_recs if r["model"] == model]
            if not model_recs:
                continue

            color = color_map[model]
            label_added = False
            for rec in model_recs:
                vkey = rec["variant"] if rec["variant"] else ""
                marker = marker_map.get(vkey, "o")
                ax.scatter(
                    rec["area"], rec["delay"],
                    color=color,
                    marker=marker,
                    s=80,
                    zorder=3,
                    label=short_models[model] if not label_added else "_nolegend_",
                    edgecolors="white",
                    linewidths=0.5,
                )
                label_added = True

        ax.set_xlabel("Area (µm²)", fontsize=11)
        ax.set_ylabel(f"Delay ({PPA_REPORT_TIME_UNIT})", fontsize=11)
        ax.set_title(f"{bench} — Area vs Delay by Model", fontsize=12)

        # Put legend outside to avoid hiding points
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            borderaxespad=0,
            fontsize=8,
            title="Model",
        )

        # Add variant legend if multiple variants present
        if len(variants) > 1:
            from matplotlib.lines import Line2D
            variant_handles = [
                Line2D([0], [0], marker=marker_map[v], color="gray",
                       linestyle="None", markersize=7, label=v)
                for v in variants if any(r["variant"] == v for r in bench_recs)
            ]
            if variant_handles:
                ax.add_artist(ax.legend(
                    handles=variant_handles,
                    loc="lower left",
                    bbox_to_anchor=(1.02, 0),
                    borderaxespad=0,
                    fontsize=7,
                    title="Variant",
                ))

        ax.grid(True, linestyle="--", alpha=0.4)
        fig.tight_layout()
        path = output_dir / f"area_delay_{bench}.png"
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        saved.append(path)

    # ── combined grid: all benchmarks in one figure ───────────────────────────
    if len(benchmarks) > 1:
        ncols = min(3, len(benchmarks))
        nrows = (len(benchmarks) + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols,
                                 figsize=(5.5 * ncols, 4.5 * nrows),
                                 squeeze=False)

        for idx, bench in enumerate(benchmarks):
            ax = axes[idx // ncols][idx % ncols]
            bench_recs = [r for r in records if r["benchmark"] == bench]

            for model in models:
                model_recs = [r for r in bench_recs if r["model"] == model]
                if not model_recs:
                    continue
                color = color_map[model]
                label_added = False
                for rec in model_recs:
                    vkey = rec["variant"] if rec["variant"] else ""
                    ax.scatter(
                        rec["area"], rec["delay"],
                        color=color,
                        marker=marker_map.get(vkey, "o"),
                        s=60,
                        zorder=3,
                        label=short_models[model] if not label_added else "_nolegend_",
                        edgecolors="white",
                        linewidths=0.4,
                    )
                    label_added = True

            ax.set_title(bench, fontsize=10)
            ax.set_xlabel("Area (µm²)", fontsize=8)
            ax.set_ylabel(f"Delay ({PPA_REPORT_TIME_UNIT})", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(True, linestyle="--", alpha=0.35)

        # Hide unused subplots
        for idx in range(len(benchmarks), nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)

        # Shared legend beneath the grid
        handles, labels = axes[0][0].get_legend_handles_labels()
        if handles:
            fig.legend(
                handles, labels,
                loc="lower center",
                ncol=min(len(models), 4),
                fontsize=8,
                title="Model",
                bbox_to_anchor=(0.5, -0.02),
            )

        fig.suptitle("Area vs Delay — All Benchmarks", fontsize=13, y=1.01)
        fig.tight_layout()
        path = output_dir / "area_delay_all.png"
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        saved.append(path)

    return saved


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scatter-plot area vs delay for each benchmark, coloured by model"
    )
    parser.add_argument(
        "runs_dir",
        help="Runs directory (contains sweep_summary.json, all_results.json, or result.json files)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Where to write plots (default: <runs_dir>/plots)",
    )
    parser.add_argument(
        "--variant", default=None,
        help="Filter to a specific variant, e.g. 'verilog_area'",
    )
    parser.add_argument(
        "--delay-threshold", type=float, default=None,
        help=f"Filter out results with delay above this value ({PPA_REPORT_TIME_UNIT}).",
    )
    parser.add_argument(
        "--area-threshold", type=float, default=None,
        help="Filter out results with area above this value.",
    )
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    if not runs_dir.exists():
        parser.error(f"Path not found: {runs_dir}")

    output_dir = Path(args.output_dir) if args.output_dir else (
        runs_dir.parent / "plots" if runs_dir.is_file() else runs_dir / "plots"
    )

    records = load_results(runs_dir)
    print(f"Loaded {len(records)} records with PPA data from {runs_dir}")
    if args.delay_threshold is not None:
        records = [r for r in records if r["delay"] <= args.delay_threshold]
        print(f"After delay threshold ({args.delay_threshold} {PPA_REPORT_TIME_UNIT}): {len(records)} records")
    if args.area_threshold is not None:
        records = [r for r in records if r["area"] <= args.area_threshold]
        print(f"After area threshold ({args.area_threshold}): {len(records)} records")

    if not records:
        print("Nothing to plot — no passed results with area+delay metrics found.")
        return

    benchmarks = sorted({r["benchmark"] for r in records})
    models = sorted({r["model"] for r in records})
    print(f"Benchmarks: {benchmarks}")
    print(f"Models:     {[_short_model(m) for m in models]}")

    saved = plot_area_delay(records, output_dir, variant_filter=args.variant)
    for p in saved:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()

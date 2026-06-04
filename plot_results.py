#!/usr/bin/env python3
"""CLI: Plot results at various levels.

Usage:
  # Plot a single benchmark result
  python plot_results.py --input runs/<path>/result.json --level benchmark

  # Plot a model summary (across benchmarks)
  python plot_results.py --input runs/<path>/summary_*.json --level model

  # Plot a sweep (across models and benchmarks)
  python plot_results.py --input runs/<path>/all_results.json --level sweep
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _fmt_cost(v) -> str:
    """Format a cost value: integers without decimals, floats with 4 sig figs."""
    if v is None:
        return "N/A"
    if isinstance(v, float) and v != int(v):
        return f"{v:.4g}"
    return str(int(v))


def _get_cost_value(d: Dict[str, Any], key_new: str, key_old: str, default=None):
    """Read cost value with fallback for old JSON format."""
    return d.get(key_new, d.get(key_old, default))


def _add_source(fig, source: str) -> None:
    """Add a small source path label at the top of a figure."""
    if source:
        fig.text(0.5, 0.99, source, fontsize=6, color="gray",
                 ha="center", va="top", transform=fig.transFigure)


def _get_metric_label(data: Dict[str, Any], default: str = "Transistors") -> str:
    """Extract metric label from data, with fallback."""
    name = data.get("cost_metric", "")
    if name:
        return name.capitalize()
    return default


def _pass_rate_color(rate: float) -> str:
    """Map pass rate 0..1 to a red→orange→green color.

    Green (#1b9e77) is reserved for exactly 100%.
    Everything below 100% interpolates between red (#d95f02) and yellow (#e6ab02).
    """
    if rate >= 1.0:
        return "#1b9e77"
    if rate <= 0.0:
        return "#d95f02"
    # 0..1 (exclusive) maps from red (#d95f02) to yellow (#e6ab02)
    t = rate
    r = int(0xd9 + (0xe6 - 0xd9) * t)
    g = int(0x5f + (0xab - 0x5f) * t)
    b = 0x02
    return f"#{r:02x}{g:02x}{b:02x}"


def plot_benchmark(data: Dict[str, Any], output_dir: Path, source: str = "",
                   show_accuracy: bool = True) -> List[Path]:
    """Plot results for a single benchmark run (step-level detail).

    Args:
        show_accuracy: If True, show pass rate on a secondary y-axis.
            If False, encode pass rate in bar color (green=100%, orange/red=lower)
            and annotate bars that are not 100% correct.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    evals = data.get("all_evals", [])
    if not evals:
        print("No evaluation data found.")
        return outputs

    metric_label = _get_metric_label(data)

    eval_indices = [e.get("eval_index", e.get("step", i + 1)) for i, e in enumerate(evals)]
    cost_values = [_get_cost_value(e, "cost_value", "estimated_num_transistors") for e in evals]
    passed = [e.get("passed", False) for e in evals]
    pass_rates = [e.get("correctness", {}).get("pass_rate", 0) for e in evals]

    # Plot 1: Cost per step (treat None as 0 for bar height)
    plot_costs = [cv if cv is not None else 0 for cv in cost_values]
    fig, ax1 = plt.subplots(figsize=(10, 5))

    if show_accuracy:
        colors = ["#1b9e77" if p else "#d95f02" for p in passed]
    else:
        colors = [_pass_rate_color(pr) for pr in pass_rates]

    bars = ax1.bar(eval_indices, plot_costs, color=colors)
    for bar, cv in zip(bars, cost_values):
        if cv is not None:
            ax1.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height(),
                     _fmt_cost(cv), ha="center", va="bottom", fontsize=6)
    ax1.set_xlabel("Evaluation")
    ax1.set_ylabel(f"Estimated {metric_label}")
    ax1.set_title(f"Benchmark: {data.get('benchmark_name', 'unknown')} | Model: {data.get('model', 'unknown')}")
    _add_source(fig, source)
    plot_cost_filt = [cv for cv in cost_values if cv is not None]
    delta_max_min = max(plot_cost_filt) - min(plot_cost_filt) if plot_cost_filt else 1
    ax1.set_ylim(min(plot_cost_filt) - delta_max_min * 0.1, max(plot_cost_filt) + delta_max_min * 0.2)

    from matplotlib.patches import Patch

    if show_accuracy:
        # Binary pass/fail legend + pass rate on secondary axis
        legend_elements = [
            Patch(facecolor="#1b9e77", label="PASS"),
            Patch(facecolor="#d95f02", label="FAIL"),
        ]
        ax1.legend(handles=legend_elements, loc="upper right")

        ax2 = ax1.twinx()
        ax2.plot(eval_indices, pass_rates, "k--o", markersize=4, label="Pass Rate")
        ax2.set_ylabel("Pass Rate")
        ax2.set_ylim(-0.05, 1.05)
        ax2.legend(loc="upper left")
    else:
        # No secondary axis — encode pass rate in bar color and annotate
        y_bottom = ax1.get_ylim()[0]
        for idx, pr, cv in zip(eval_indices, pass_rates, cost_values):
            if pr < 1.0:
                pct = f"{pr:.0%}"
                if cv is not None and cv > 0:
                    # Annotate inside/below the bar
                    ax1.text(idx, y_bottom + delta_max_min * 0.02, pct,
                             ha="center", va="bottom", fontsize=6,
                             color="#d95f02", fontweight="bold")
                else:
                    # No bar — place a cross marker at baseline
                    ax1.plot(idx, y_bottom + delta_max_min * 0.01, "x",
                             color=_pass_rate_color(pr), markersize=7, markeredgewidth=2)
                    ax1.text(idx, y_bottom + delta_max_min * 0.03, pct,
                             ha="center", va="bottom", fontsize=6,
                             color="#d95f02", fontweight="bold")

        legend_elements = [
            Patch(facecolor="#1b9e77", label="100% correct"),
            Patch(facecolor="#e6ab02", label="Partial"),
            Patch(facecolor="#d95f02", label="Failed / eval error"),
        ]
        ax1.legend(handles=legend_elements, loc="upper right")

    fig.tight_layout()
    path = output_dir / "benchmark_evaluations.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    outputs.append(path)

    return outputs


def plot_model(data: Dict[str, Any], output_dir: Path, source: str = "") -> List[Path]:
    """Plot results for one model across benchmarks."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    benchmarks = data.get("benchmarks", [])
    if not benchmarks:
        print("No benchmark data found.")
        return outputs

    # Detect metric label from first benchmark that has it
    metric_label = "Transistors"
    for b in benchmarks:
        ml = _get_metric_label(b)
        if ml != "Transistors" or b.get("cost_metric"):
            metric_label = ml
            break

    names = [b.get("benchmark_name", "?") for b in benchmarks]
    passed = [b.get("passed", False) for b in benchmarks]
    cost_values = [_get_cost_value(b, "best_cost", "best_transistor_count") for b in benchmarks]

    # Plot 1: Pass/Fail bar
    fig, ax = plt.subplots(figsize=(max(8, len(names) * 1.2), 5))
    colors = ["#1b9e77" if p else "#d95f02" for p in passed]
    ax.bar(names, [1 if p else 0 for p in passed], color=colors)
    ax.set_ylabel("Pass (1) / Fail (0)")
    ax.set_title(f"Model: {data.get('model', 'unknown')} | {data.get('passed', 0)}/{data.get('total', 0)} passed")
    _add_source(fig, source)
    ax.tick_params(axis="x", labelrotation=45)
    for tick in ax.get_xticklabels():
        tick.set_ha("right")
    fig.tight_layout()
    path = output_dir / "model_pass_fail.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    outputs.append(path)

    # Plot 2: Cost for passed benchmarks
    passed_names = [n for n, p in zip(names, passed) if p]
    passed_cv = [c for c, p in zip(cost_values, passed) if p and c is not None]
    if passed_names and passed_cv:
        fig, ax = plt.subplots(figsize=(max(8, len(passed_names) * 1.2), 5))
        ax.bar(passed_names[:len(passed_cv)], passed_cv, color="#1b9e77")
        ax.set_ylabel(f"Estimated {metric_label}")
        ax.set_title(f"Model: {data.get('model', 'unknown')} | {metric_label} (correct designs)")
        _add_source(fig, source)
        ax.tick_params(axis="x", labelrotation=45)
        for tick in ax.get_xticklabels():
            tick.set_ha("right")
        for i, v in enumerate(passed_cv):
            ax.text(i, v + max(passed_cv) * 0.01, _fmt_cost(v), ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        path = output_dir / "model_cost.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        outputs.append(path)

    return outputs


def plot_sweep(data: Dict[str, Any], output_dir: Path, source: str = "") -> List[Path]:
    """Plot results for a sweep across models and benchmarks."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    model_results = data.get("model_results", [])
    if not model_results:
        print("No model results found.")
        return outputs

    # Detect metric label from first available benchmark result
    metric_label = "Transistors"
    for mr in model_results:
        if mr.get("status") != "ok":
            continue
        for b in mr.get("benchmarks", []):
            ml = _get_metric_label(b)
            if ml != "Transistors" or b.get("cost_metric"):
                metric_label = ml
                break
        if metric_label != "Transistors":
            break

    # Plot 1: Pass rate by model
    labels = [mr.get("model", "?") for mr in model_results]
    short_labels = [l.split("/")[-1] if "/" in l else l for l in labels]
    pass_rates = [mr.get("pass_rate", 0) for mr in model_results if mr.get("status") == "ok"]
    ok_labels = [l.split("/")[-1] if "/" in l else l for l, mr in zip(labels, model_results) if mr.get("status") == "ok"]

    if ok_labels:
        fig, ax = plt.subplots(figsize=(max(8, len(ok_labels) * 1.5), 5))
        bars = ax.bar(ok_labels, pass_rates, color="#1b9e77")
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel("Pass Rate")
        ax.set_title("Benchmark Pass Rate by Model")
        _add_source(fig, source)
        ax.tick_params(axis="x", labelrotation=45)
        for tick in ax.get_xticklabels():
            tick.set_ha("right")
        for bar, rate in zip(bars, pass_rates):
            ax.text(bar.get_x() + bar.get_width() / 2.0, rate + 0.02, f"{rate:.2f}",
                    ha="center", va="bottom")
        fig.tight_layout()
        path = output_dir / "sweep_pass_rate.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        outputs.append(path)

    # Plot 2: Heatmap of pass/fail per benchmark per model
    all_bench_names = sorted({
        b.get("benchmark_name", "?")
        for mr in model_results if mr.get("status") == "ok"
        for b in mr.get("benchmarks", [])
    })

    if all_bench_names and ok_labels:
        matrix = []
        for bench_name in all_bench_names:
            row = []
            for mr in model_results:
                if mr.get("status") != "ok":
                    continue
                found = False
                for b in mr.get("benchmarks", []):
                    if b.get("benchmark_name") == bench_name:
                        row.append(1 if b.get("passed", False) else 0)
                        found = True
                        break
                if not found:
                    row.append(-1)
            matrix.append(row)

        fig, ax = plt.subplots(figsize=(max(8, len(ok_labels) * 1.5), max(5, len(all_bench_names) * 0.5)))
        cmap = ListedColormap(["#bdbdbd", "#d95f02", "#1b9e77"])
        shifted = [[v + 1 for v in row] for row in matrix]
        ax.imshow(shifted, cmap=cmap, aspect="auto", vmin=0, vmax=2)
        ax.set_xticks(range(len(ok_labels)))
        ax.set_xticklabels(ok_labels, rotation=45, ha="right")
        ax.set_yticks(range(len(all_bench_names)))
        ax.set_yticklabels(all_bench_names)
        ax.set_title("Benchmark Pass/Fail Heatmap (gray=missing, orange=fail, green=pass)")
        _add_source(fig, source)
        fig.tight_layout()
        path = output_dir / "sweep_heatmap.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        outputs.append(path)

    # Plot 3: Relative cost heatmap (normalized per benchmark to best)
    if all_bench_names and ok_labels:
        # Build cost matrix: rows=benchmarks, cols=models
        tc_matrix = np.full((len(all_bench_names), len(ok_labels)), np.nan)
        for row_i, bench_name in enumerate(all_bench_names):
            col_i = 0
            for mr in model_results:
                if mr.get("status") != "ok":
                    continue
                for b in mr.get("benchmarks", []):
                    if b.get("benchmark_name") == bench_name and b.get("passed"):
                        tc = _get_cost_value(b, "best_cost", "best_transistor_count")
                        if tc is not None:
                            tc_matrix[row_i, col_i] = tc
                        break
                col_i += 1

        # Normalize each row to its minimum (best) value
        row_mins = np.nanmin(tc_matrix, axis=1, keepdims=True)
        # Avoid division by zero for rows that are all NaN
        with np.errstate(invalid="ignore"):
            norm_matrix = tc_matrix / row_mins

        fig, ax = plt.subplots(figsize=(max(8, len(ok_labels) * 1.8), max(5, len(all_bench_names) * 0.6)))

        # Use a sequential colormap: 1.0 (best) = green, higher = yellow/red
        cmap = plt.cm.RdYlGn_r.copy()
        cmap.set_bad(color="#e0e0e0")  # gray for missing/failed

        vmax = np.nanmax(norm_matrix) if not np.all(np.isnan(norm_matrix)) else 1.0
        im = ax.imshow(norm_matrix, cmap=cmap, aspect="auto", vmin=1.0, vmax=max(vmax, 1.01))

        # Annotate cells with ratio and absolute count
        for row_i in range(len(all_bench_names)):
            for col_i in range(len(ok_labels)):
                tc = tc_matrix[row_i, col_i]
                ratio = norm_matrix[row_i, col_i]
                if np.isnan(tc):
                    ax.text(col_i, row_i, "---", ha="center", va="center",
                            fontsize=8, color="#888888")
                else:
                    label = f"{ratio:.2f}x\n({_fmt_cost(tc)})"
                    text_color = "white" if ratio > 1.6 else "black"
                    ax.text(col_i, row_i, label, ha="center", va="center",
                            fontsize=7, color=text_color, fontweight="bold" if ratio == 1.0 else "normal")

        ax.set_xticks(range(len(ok_labels)))
        ax.set_xticklabels(ok_labels, rotation=45, ha="right")
        ax.set_yticks(range(len(all_bench_names)))
        ax.set_yticklabels(all_bench_names)
        ax.set_title(f"Relative {metric_label} (normalized to best per benchmark)")
        _add_source(fig, source)
        cbar = fig.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label("Ratio to best (1.0 = best)")
        fig.tight_layout()
        path = output_dir / "sweep_relative_heatmap.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        outputs.append(path)

    # Plot 4: Cost comparison across models for each benchmark
    if all_bench_names and ok_labels:
        fig, ax = plt.subplots(figsize=(max(10, len(all_bench_names) * 1.5), 6))
        x = np.arange(len(all_bench_names))
        width = 0.8 / max(len(ok_labels), 1)

        for i, mr in enumerate(model_results):
            if mr.get("status") != "ok":
                continue
            tc_values = []
            for bench_name in all_bench_names:
                tc = 0
                for b in mr.get("benchmarks", []):
                    if b.get("benchmark_name") == bench_name and b.get("passed"):
                        v = _get_cost_value(b, "best_cost", "best_transistor_count")
                        tc = v if v is not None else 0
                        break
                tc_values.append(tc)
            label = mr.get("model", "?").split("/")[-1]
            offset = (i - len(ok_labels) / 2 + 0.5) * width
            ax.bar(x + offset, tc_values, width, label=label)

        ax.set_xlabel("Benchmark")
        ax.set_ylabel(f"{metric_label} (0 = not passed)")
        ax.set_title(f"{metric_label} by Benchmark and Model (correct designs only)")
        _add_source(fig, source)
        ax.set_xticks(x)
        ax.set_xticklabels(all_bench_names, rotation=45, ha="right")
        ax.legend()
        fig.tight_layout()
        path = output_dir / "sweep_cost.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        outputs.append(path)

    return outputs


def main():
    parser = argparse.ArgumentParser(description="Plot RTL agent results")
    parser.add_argument("--input", required=True, help="Path to result JSON file or directory")
    parser.add_argument("--level", choices=["benchmark", "model", "sweep"], default=None,
                        help="Plot level (auto-detected if not specified)")
    parser.add_argument("--output-dir", default=None, help="Output directory for plots (default: <input>/plots)")
    parser.add_argument("--no-accuracy", action="store_true",
                        help="Hide the accuracy/pass-rate axis in benchmark plots (pass rate shown via bar color)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_dir():
        # Try to find the right JSON
        for candidate in ["all_results.json", "summary.json"]:
            p = input_path / candidate
            if p.exists():
                input_path = p
                break

    data = load_json(input_path)
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent / "plots"
    source = str(input_path)

    # Auto-detect level
    level = args.level
    if level is None:
        if "model_results" in data:
            level = "sweep"
        elif "benchmarks" in data and "model" in data:
            level = "model"
        elif "all_evals" in data:
            level = "benchmark"
        else:
            print("Cannot auto-detect level. Use --level.")
            return

    if level == "benchmark":
        plots = plot_benchmark(data, output_dir, source, show_accuracy=not args.no_accuracy)
    elif level == "model":
        plots = plot_model(data, output_dir, source)
    elif level == "sweep":
        plots = plot_sweep(data, output_dir, source)
    else:
        plots = []

    for p in plots:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()

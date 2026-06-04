#!/usr/bin/env python3
"""CLI: Plot multistage optimiser results.

Usage:
  python plot_multistage.py --input runs/multistage_<ts>/multistage_summary.json
  python plot_multistage.py --input runs/multistage_<ts>/  # auto-finds multistage_summary.json
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _fmt_cost(v) -> str:
    """Format a cost value: integers without decimals, floats with 4 sig figs."""
    if v is None:
        return "N/A"
    if isinstance(v, float) and v != int(v):
        return f"{v:.4g}"
    return str(int(v))


def plot_cost_evolution(data: Dict[str, Any], output_dir: Path, source: str = "") -> List[Path]:
    """Plot cost evolution across multistage agent runs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    runs = sorted(data.get("runs", []), key=lambda r: r.get("run_index", 0))
    progression = data.get("cost_progression", [])

    if not runs:
        print("No run data found.")
        return outputs

    _labels = {
        "area": r"Area ($\mathrm{\mu m^2}$)",
        "delay": "Delay (ps)",
        "transistors": "Transistors",
    }
    metric_raw = data.get("cost_metric", "cost")
    metric_label = _labels.get(metric_raw, metric_raw.capitalize())

    # Extract run data
    x_all = [r["run_index"] for r in runs]
    costs = [r.get("best_cost") for r in runs]
    passed = [r.get("passed", False) for r in runs]
    is_fresh = [r.get("is_fresh", True) for r in runs]

    # Extract first passing eval cost per run (the initial/baseline cost)
    initial_costs = []
    for r in runs:
        init = None
        for ev in r.get("all_evals", []):
            if ev.get("passed") and ev.get("cost_value") is not None:
                init = ev["cost_value"]
                break
        initial_costs.append(init)

    # Separate into categories for scatter
    x_pass_fresh, y_pass_fresh = [], []
    x_pass_seed, y_pass_seed = [], []
    x_fail = []

    for x, c, p, f in zip(x_all, costs, passed, is_fresh):
        if not p or c is None:
            x_fail.append(x)
        elif f:
            x_pass_fresh.append(x)
            y_pass_fresh.append(c)
        else:
            x_pass_seed.append(x)
            y_pass_seed.append(c)

    fig, ax = plt.subplots(figsize=(max(8, len(runs) * 0.8), 5))

    # Determine y limits from valid costs
    valid_costs = [c for c in costs if c is not None]
    valid_initials = [c for c in initial_costs if c is not None]
    prog_costs = [p["best_cost"] for p in progression]
    all_costs = valid_costs + valid_initials + prog_costs
    if all_costs:
        y_min = min(all_costs)
        y_max = max(all_costs)
        y_range = y_max - y_min if y_max != y_min else y_max * 0.1 or 1.0
        y_bottom = y_min - y_range * 0.15
        y_top = y_max + y_range * 0.15
    else:
        y_bottom, y_top = 0, 1

    # Plot scatter: fresh passing runs (green circles)
    if x_pass_fresh:
        ax.scatter(x_pass_fresh, y_pass_fresh, marker="o", c="#1b9e77", s=60,
                   zorder=3, label="Fresh (pass)")

    # Plot scatter: seeded passing runs (diamonds with black edge)
    if x_pass_seed:
        ax.scatter(x_pass_seed, y_pass_seed, marker="D", c="#1b9e77", s=60,
                   edgecolors="black", linewidths=1.2, zorder=3, label="Seeded (pass)")

    # Plot scatter: failed runs (orange cross at bottom)
    if x_fail:
        ax.scatter(x_fail, [y_bottom + (y_top - y_bottom) * 0.03] * len(x_fail),
                   marker="x", c="#d95f02", s=60, linewidths=2, zorder=3, label="Failed")

    # Plot initial costs (first passing eval) with vertical lines to best
    init_plotted = False
    for x, init, best in zip(x_all, initial_costs, costs):
        if init is not None and best is not None and init != best:
            ax.plot([x, x], [init, best], color="#aaaaaa", linewidth=1, zorder=1)
            ax.scatter(x, init, marker="_", c="#888888", s=60, linewidths=1.5, zorder=2)
            init_plotted = True
        elif init is not None and best is not None and init == best:
            # No improvement — just show the tick at same position (overlaps with best)
            pass
    if init_plotted:
        ax.scatter([], [], marker="_", c="#888888", s=60, linewidths=1.5, label="Initial cost")

    # Plot step line: elite pool best cost after each completion
    if progression:
        step_x = [p["run_index"] for p in progression]
        step_y = [p["best_cost"] for p in progression]
        ax.step(step_x, step_y, where="post", color="black", linewidth=1.5,
                zorder=2, label="Elite best")

    ax.set_ylim(y_bottom, y_top)
    ax.set_xlabel("Agent Run Index")
    ax.set_ylabel(metric_label)
    ax.set_xticks(x_all)

    # Title with benchmark, model, global best; subtitle with config
    benchmark = data.get("benchmark", "unknown")
    model = data.get("model", "unknown")
    global_best = data.get("global_best_cost")
    total_runs = data.get("total_runs", "?")
    elite_size = data.get("elite_size", "?")
    temperature = data.get("temperature", "?")
    fig.suptitle(f"{benchmark} | {model} | Best {metric_label}: {_fmt_cost(global_best)}",
                 fontsize=11, y=0.98)
    ax.set_title(f"runs={total_runs}  elite_size={elite_size}  temperature={temperature}",
                 fontsize=8, color="gray")

    # Source label at bottom
    if source:
        fig.text(0.5, 0.01, source, fontsize=6, color="gray",
                 ha="center", va="bottom", transform=fig.transFigure)

    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    path = output_dir / "multistage_cost_evolution.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    outputs.append(path)

    return outputs


def main():
    parser = argparse.ArgumentParser(description="Plot multistage optimiser results")
    parser.add_argument("--input", required=True, help="Path to multistage_summary.json or its directory")
    parser.add_argument("--output-dir", default=None, help="Output directory for plots (default: <input>/plots)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_dir():
        input_path = input_path / "multistage_summary.json"

    data = load_json(input_path)
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent / "plots"
    source = str(input_path)

    plots = plot_cost_evolution(data, output_dir, source)

    for p in plots:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()

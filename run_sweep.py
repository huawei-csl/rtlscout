#!/usr/bin/env python3
"""CLI: Execute agent across multiple models and benchmarks."""

import argparse
import json
from pathlib import Path

from core.cost import COST_METRICS, make_cost_metric
from core.runner import DEFAULT_BENCHMARKS_ROOT, run_agent_across_models_and_benchmarks


DEFAULT_MODELS = [
    "deepinfra:meta-llama/Llama-3.3-70B-Instruct-Turbo",
]


def main():
    parser = argparse.ArgumentParser(description="Run RTL agent across models and benchmarks")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                        help="Model specs as '<provider>:<model>' (provider prefix required), e.g. "
                             "'anthropic:claude-sonnet-4-5-20250929 deepinfra:meta-llama/Llama-3.3-70B-Instruct-Turbo'.")
    parser.add_argument("--benchmarks", nargs="*", default=None, help="Specific benchmarks (default: all)")
    parser.add_argument("--benchmarks-root", default=str(DEFAULT_BENCHMARKS_ROOT), help="Benchmarks directory")
    parser.add_argument("--runs-dir", default=None, help="Output directory for runs")
    parser.add_argument("--max-steps", type=int, default=20, help="Max agent steps")
    parser.add_argument("--api-key", default=None, help="API key (provider-specific)")
    parser.add_argument("--cost-metric", nargs="+", default=["transistors"],
                        choices=sorted(COST_METRICS),
                        help="Cost metric(s) to optimize. Multiple values run in parallel "
                             "(default: transistors)")
    parser.add_argument("--target-delay", type=float, default=500.0,
                        help="Target delay in ps for PPA metrics (default: 500)")
    parser.add_argument("--language", default="verilog", choices=["verilog", "spirehdl", "amaranth"],
                        help="Source language: verilog (direct RTL), spirehdl (Python EDSL → Verilog), or amaranth (Amaranth HDL → Verilog)")
    parser.add_argument("--dont-save-workspaces", action="store_true",
                        help="Skip saving a workspace snapshot before each "
                             "evaluation (by default snapshots ARE saved)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Max parallel workers. >1 runs models in parallel (default: 1 = sequential)")
    args = parser.parse_args()

    from datetime import datetime
    base_runs_dir = Path(args.runs_dir) if args.runs_dir else Path("runs") / datetime.now().strftime("%Y%m%d_%H%M%S")
    multi_metric = len(args.cost_metric) > 1

    for metric_name in args.cost_metric:
        cost_metric = make_cost_metric(metric_name, target_delay=args.target_delay)
        runs_dir = base_runs_dir / metric_name if multi_metric else base_runs_dir

        if multi_metric:
            print(f"\n{'='*60}")
            print(f"  Cost metric: {metric_name}")
            print(f"{'='*60}")

        all_results = run_agent_across_models_and_benchmarks(
            models=args.models,
            benchmarks_root=Path(args.benchmarks_root),
            benchmark_names=args.benchmarks,
            runs_dir=runs_dir,
            max_steps=args.max_steps,
            api_key=args.api_key,
            cost_metric=cost_metric,
            language=args.language,
            save_workspaces=not args.dont_save_workspaces,
            workers=args.workers,
        )

        print(f"\nSweep complete ({metric_name}): {len(all_results['model_results'])} models, "
              f"{all_results['total_duration_s']:.1f}s total")
        for mr in all_results["model_results"]:
            if mr.get("status") == "ok":
                print(f"  {mr['model']}: {mr['passed']}/{mr['total']} "
                      f"({mr['pass_rate']:.0%})")
            else:
                print(f"  {mr['model']}: ERROR - {mr.get('error', 'unknown')}")


if __name__ == "__main__":
    main()

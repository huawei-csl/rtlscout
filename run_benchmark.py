#!/usr/bin/env python3
"""CLI: Execute agent on a single benchmark with a given model."""

import argparse
import sys
from pathlib import Path

from core.benchmarks import load_benchmark, load_benchmarks
from core.cost import COST_METRICS, make_cost_metric
from core.runner import DEFAULT_BENCHMARKS_ROOT, parse_model_spec, run_agent_on_benchmark


def main():
    parser = argparse.ArgumentParser(description="Run RTL agent on a single benchmark")
    parser.add_argument("--benchmark", required=True, help="Benchmark name (directory name)")
    parser.add_argument("--model", default="deepinfra:meta-llama/Llama-3.3-70B-Instruct-Turbo",
                        help="Model spec as '<provider>:<model>' (e.g. 'anthropic:claude-sonnet-4-5-20250929'). "
                             "Provider prefix is required (deepinfra, anthropic, openrouter, fake)")
    parser.add_argument("--benchmarks-root", default=str(DEFAULT_BENCHMARKS_ROOT), help="Benchmarks directory")
    parser.add_argument("--runs-dir", default="runs", help="Output directory for runs")
    parser.add_argument("--max-steps", type=int, default=20, help="Max agent steps")
    parser.add_argument("--api-key", default=None, help="API key (provider-specific)")
    parser.add_argument("--cost-metric", default="transistors", choices=sorted(COST_METRICS),
                        help="Cost metric to optimize (default: transistors)")
    parser.add_argument("--target-delay", type=float, default=500.0,
                        help="Target delay in ps for PPA metrics (default: 500)")
    parser.add_argument("--technology", default="asap7",
                        help="Process technology for PPA metrics: asap7, nangate45, freepdk45 (default: asap7)")
    parser.add_argument("--language", default="verilog", choices=["verilog", "spirehdl", "amaranth"],
                        help="Source language: verilog (direct RTL), spirehdl (Python EDSL → Verilog), or amaranth (Amaranth HDL → Verilog)")
    parser.add_argument("--dont-save-workspaces", action="store_true",
                        help="Skip saving a workspace snapshot before each "
                             "evaluation (by default snapshots ARE saved)")
    parser.add_argument("--flowy-optimize", action="store_true",
                        help="Enable @flowy_optimized decorator guidance in system prompt (SpireHDL only)")
    parser.add_argument("--abc-optimize", action="store_true",
                        help="Enable @abc_optimized decorator guidance in system prompt (SpireHDL only)")
    parser.add_argument("--arith-autoconfig", action="store_true",
                        help="Enable replace_arithmetic_ops() guidance in system prompt (SpireHDL only)")
    parser.add_argument("--dont-touch-main-arith", action="store_true",
                        help="Tell agent to not modify core multiplier/adder configs (for later-stage arithmetic sweeps)")
    args = parser.parse_args()

    model_provider, model = parse_model_spec(args.model)
    cost_metric = make_cost_metric(args.cost_metric, target_delay=args.target_delay,
                                   technology=args.technology)

    benchmarks_root = Path(args.benchmarks_root)
    benchmarks = load_benchmarks(benchmarks_root, [args.benchmark])
    if not benchmarks:
        print(f"Benchmark not found: {args.benchmark}")
        sys.exit(1)

    result = run_agent_on_benchmark(
        benchmarks[0],
        model=model,
        runs_dir=Path(args.runs_dir),
        max_steps=args.max_steps,
        api_key=args.api_key,
        provider=model_provider,
        cost_metric=cost_metric,
        language=args.language,
        save_workspaces=not args.dont_save_workspaces,
        flowy_optimize=args.flowy_optimize,
        abc_optimize=args.abc_optimize,
        arith_autoconfig=args.arith_autoconfig,
        dont_touch_main_arith=args.dont_touch_main_arith,
    )

    if result.passed:
        best_step = result.best_eval.get("eval_index", "?") if result.best_eval else "?"
        print(f"\nBest: PASS | {result.best_cost} {result.cost_metric_name} (step {best_step})")
    else:
        print(f"\nBest: FAIL | No fully correct design found")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CLI: Async elite-pool multi-stage optimisation.

Runs multiple agents in parallel on a single benchmark.  An elite pool
of the best designs evolves over time — new agents are seeded from the
pool (exploitation) or start fresh (exploration).

Usage:
  python run_multistage.py \
      --benchmark fpmul_f16 \
      --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
      --total-runs 6 --max-concurrent 2 --max-steps 15 \
      --cost-metric delay --language spirehdl
"""

import argparse
from pathlib import Path
from datetime import datetime

from core.cost import COST_METRICS
from core.multistage import run_multistage
from core.runner import DEFAULT_BENCHMARKS_ROOT


def main():
    parser = argparse.ArgumentParser(
        description="Async elite-pool multi-stage optimisation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--benchmark", required=True, help="Benchmark name")
    parser.add_argument("--model", required=True,
                        help="Model spec with provider prefix (e.g. 'deepinfra:MiniMaxAI/MiniMax-M2.5')")
    parser.add_argument("--total-runs", type=int, default=10,
                        help="Total agent runs to complete (default: 10)")
    parser.add_argument("--max-concurrent", type=int, default=4,
                        help="Max parallel agents (default: 4)")
    parser.add_argument("--max-steps", type=int, default=30,
                        help="Max steps per agent (default: 30)")
    parser.add_argument("--elite-size", type=int, default=5,
                        help="Max designs in elite pool (default: 5)")
    parser.add_argument("--temperature", type=float, default=1.0,
                        help="Softmax temperature for pool sampling (default: 1.0)")
    parser.add_argument("--fresh-base", type=float, default=0.5,
                        help="Initial probability of starting fresh (default: 0.5)")
    parser.add_argument("--fresh-min", type=float, default=0.1,
                        help="Minimum fresh probability (default: 0.1)")
    parser.add_argument("--fresh-first", type=int, default=0,
                        help="Force the first N runs to start fresh (default: 0)")
    parser.add_argument("--cost-metric", default="transistors", choices=sorted(COST_METRICS),
                        help="Cost metric to optimize (default: transistors)")
    parser.add_argument("--target-delay", type=float, default=500.0,
                        help="Target delay in ps for PPA metrics (default: 500)")
    parser.add_argument("--technology", default="asap7",
                        help="Process technology for PPA metrics: asap7, nangate45, freepdk45 (default: asap7)")
    parser.add_argument("--language", default="verilog",
                        choices=["verilog", "spirehdl", "amaranth"],
                        help="Source language (default: verilog)")
    parser.add_argument("--benchmarks-root", default=str(DEFAULT_BENCHMARKS_ROOT),
                        help="Benchmarks directory")
    parser.add_argument("--runs-root", default=None,
                        help="Output directory (default: runs/multistage_<timestamp>)")
    parser.add_argument("--seed-from", default=None,
                        help="Seed elite pool from a previous run. Accepts a directory or "
                             "JSON file: multistage_summary.json, pareto_front.json "
                             "(from extract_pareto.py), or best_designs.json "
                             "(from extract_best_designs.py)")
    parser.add_argument("--flowy-optimize", action="store_true",
                        help="Enable @flowy_optimized decorator guidance in system prompt (SpireHDL only)")
    parser.add_argument("--abc-optimize", action="store_true",
                        help="Enable @abc_optimized decorator guidance in system prompt (SpireHDL only)")
    parser.add_argument("--arith-autoconfig", action="store_true",
                        help="Enable replace_arithmetic_ops() guidance in system prompt (SpireHDL only)")
    parser.add_argument("--dont-touch-main-arith", action="store_true",
                        help="Tell agent to not modify core multiplier/adder configs (for later-stage arithmetic sweeps)")
    parser.add_argument("--fsm-optimize", action="store_true",
                        help="Enable FSM / state-encoding optimization guidance (optimized_fsm / optimized_encoding) in the system prompt (SpireHDL only)")
    args = parser.parse_args()

    runs_root = None
    if args.runs_root:
        runs_root = Path(args.runs_root)

    run_multistage(
        benchmark_name=args.benchmark,
        model=args.model,
        total_runs=args.total_runs,
        max_concurrent=args.max_concurrent,
        max_steps=args.max_steps,
        elite_size=args.elite_size,
        temperature=args.temperature,
        fresh_base=args.fresh_base,
        fresh_min=args.fresh_min,
        fresh_first=args.fresh_first,
        cost_metric=args.cost_metric,
        target_delay=args.target_delay,
        technology=args.technology,
        language=args.language,
        benchmarks_root=Path(args.benchmarks_root),
        runs_root=runs_root,
        seed_from=args.seed_from,
        flowy_optimize=args.flowy_optimize,
        abc_optimize=args.abc_optimize,
        arith_autoconfig=args.arith_autoconfig,
        dont_touch_main_arith=args.dont_touch_main_arith,
        fsm_optimize=args.fsm_optimize,
    )


if __name__ == "__main__":
    main()

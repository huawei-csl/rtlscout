#!/usr/bin/env python3
"""CLI: Execute agent across all benchmarks for a given model."""

import argparse
import json
from pathlib import Path

from core.runner import DEFAULT_BENCHMARKS_ROOT, run_agent_across_benchmarks


def main():
    parser = argparse.ArgumentParser(description="Run RTL agent across benchmarks for a model")
    parser.add_argument("--model", default="meta-llama/Llama-3.3-70B-Instruct-Turbo", help="Model name")
    parser.add_argument("--benchmarks", nargs="*", default=None, help="Specific benchmarks (default: all)")
    parser.add_argument("--benchmarks-root", default=str(DEFAULT_BENCHMARKS_ROOT), help="Benchmarks directory")
    parser.add_argument("--runs-dir", default=None, help="Output directory for runs")
    parser.add_argument("--max-steps", type=int, default=20, help="Max agent steps")
    parser.add_argument("--api-key", default=None, help="DeepInfra API key")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir) if args.runs_dir else None
    summary = run_agent_across_benchmarks(
        model=args.model,
        benchmarks_root=Path(args.benchmarks_root),
        benchmark_names=args.benchmarks,
        runs_dir=runs_dir,
        max_steps=args.max_steps,
        api_key=args.api_key,
    )

    print(f"\nSummary: {summary['passed']}/{summary['total']} passed "
          f"({summary['pass_rate']:.0%}) in {summary['duration_s']:.1f}s")


if __name__ == "__main__":
    main()

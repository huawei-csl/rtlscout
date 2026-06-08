#!/usr/bin/env python3
"""CLI: Execute agent across all benchmarks for a given model."""

import argparse
import json
from pathlib import Path

from core.runner import DEFAULT_BENCHMARKS_ROOT, parse_model_spec, run_agent_across_benchmarks


def main():
    parser = argparse.ArgumentParser(description="Run RTL agent across benchmarks for a model")
    parser.add_argument("--model", default="deepinfra:meta-llama/Llama-3.3-70B-Instruct-Turbo",
                        help="Model spec as '<provider>:<model>' (provider prefix required: "
                             "deepinfra, anthropic, openrouter, fake)")
    parser.add_argument("--benchmarks", nargs="*", default=None, help="Specific benchmarks (default: all)")
    parser.add_argument("--benchmarks-root", default=str(DEFAULT_BENCHMARKS_ROOT), help="Benchmarks directory")
    parser.add_argument("--runs-dir", default=None, help="Output directory for runs")
    parser.add_argument("--max-steps", type=int, default=20, help="Max agent steps")
    parser.add_argument("--api-key", default=None, help="API key (provider-specific)")
    parser.add_argument("--skip-cec", action="store_true",
                        help="Skip the combinational equivalence check (yosys-abc cec). "
                             "CEC runs by default against each benchmark's golden_reference "
                             "(if any) and gates pass/fail on it")
    args = parser.parse_args()

    provider, model = parse_model_spec(args.model)
    runs_dir = Path(args.runs_dir) if args.runs_dir else None
    summary = run_agent_across_benchmarks(
        model=model,
        benchmarks_root=Path(args.benchmarks_root),
        benchmark_names=args.benchmarks,
        runs_dir=runs_dir,
        max_steps=args.max_steps,
        api_key=args.api_key,
        provider=provider,
        run_cec=not args.skip_cec,
    )

    print(f"\nSummary: {summary['passed']}/{summary['total']} passed "
          f"({summary['pass_rate']:.0%}) in {summary['duration_s']:.1f}s")


if __name__ == "__main__":
    main()

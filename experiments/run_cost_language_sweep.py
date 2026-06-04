#!/usr/bin/env python3
"""Parallel experiment: sweep cost metrics and languages.

Runs all combinations of (model × benchmark × cost_metric × language)
in parallel using ProcessPoolExecutor.

Usage:
    python experiments/run_cost_language_sweep.py
    python experiments/run_cost_language_sweep.py --workers 6
    python experiments/run_cost_language_sweep.py --only verilog_delay verilog_transistors
"""

import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Dict, List

from core.benchmarks import load_benchmarks
from core.cost import make_cost_metric
from core.runner import (
    DEFAULT_BENCHMARKS_ROOT,
    parse_model_spec,
    run_agent_on_benchmark,
)
from tech_eval.ppa_extract.core.template import target_delay_time_unit

# ── configuration ────────────────────────────────────────────────────────

MODELS = [
     #"deepinfra:deepseek-ai/DeepSeek-V3.2",
     #"deepinfra:zai-org/GLM-5",
     "deepinfra:MiniMaxAI/MiniMax-M2.5",
     "deepinfra:moonshotai/Kimi-K2.5"
]

# not used:
#     "deepinfra:Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo"

# MODELS = [
#     "deepinfra:moonshotai/Kimi-K2.5",
#     "claude:claude-opus-4-6"
# ]

#BENCHMARKS = ["fifo_sync4", "mult8", "mult16", "alu8"]
BENCHMARKS = ["add16", "mult16"]  # for quick testing
BENCHMARKS = ["mult16"]  # for quick testing

COST_METRICS = ["delay", "area"] #, "transistors", "power"]
LANGUAGES = ["verilog"] #, "spirehdl"]

MAX_STEPS = 40
_DEFAULT_TARGET_DELAY = 500.0  # ps

# Cross-product of (language, cost_metric) → variant name like "verilog_delay"
VARIANTS = [(f"{lang}_{metric}", metric, lang)
            for lang, metric in product(LANGUAGES, COST_METRICS)]

# ── worker function (runs in subprocess) ─────────────────────────────────

def _run_one(task: dict, runs_root: str) -> dict:
    """Run a single (model, benchmark, variant) combo."""

    variant = task["variant"]
    model_spec = task["model"]
    benchmark_name = task["benchmark"]
    cost_metric_name = task["cost_metric"]
    language = task["language"]
    target_delay = task["target_delay"]

    provider, model = parse_model_spec(model_spec)
    benchmarks = load_benchmarks(DEFAULT_BENCHMARKS_ROOT, [benchmark_name])
    bench = benchmarks[0]
    cost_metric = make_cost_metric(cost_metric_name, target_delay=target_delay)

    exp_dir = Path(runs_root) / variant
    exp_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    try:
        result = run_agent_on_benchmark(
            bench,
            model=model,
            runs_dir=exp_dir,
            max_steps=MAX_STEPS,
            provider=provider,
            cost_metric=cost_metric,
            language=language,
            save_workspaces=True,
        )
        result_dict = result.to_dict()
        result_dict["status"] = "ok"
    except Exception as e:
        traceback.print_exc()
        result_dict = {
            "benchmark_name": benchmark_name,
            "model": model,
            "status": "error",
            "error": str(e),
        }

    result_dict["variant"] = variant
    result_dict["language"] = language
    result_dict["cost_metric_requested"] = cost_metric_name
    result_dict["target_delay"] = target_delay
    result_dict["duration_s"] = round(time.time() - start, 2)

    tag = f"{variant}/{model.split('/')[-1]}/{benchmark_name}"
    cost = result_dict.get("best_cost", "N/A")
    print(f"[DONE] {tag}  status={result_dict['status']}  "
          f"cost={cost}  dur={result_dict['duration_s']}s", flush=True)
    return result_dict


# ── main ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sweep cost metrics and languages")
    parser.add_argument("--workers", type=int, default=8,
                        help="Max parallel workers (default 8)")
    parser.add_argument("--runs-root", default=None,
                        help="Output directory (default: runs/cost_lang_sweep_<timestamp>)")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Run only named variants (e.g. verilog_delay spirehdl_transistors)")
    parser.add_argument("--target-delay", type=float, default=_DEFAULT_TARGET_DELAY,
                        help=f"PPA synthesis target delay in {target_delay_time_unit} (default {_DEFAULT_TARGET_DELAY}). "
                             "Passed to the synthesis tool and shown in the agent's system prompt.")
    args = parser.parse_args()
    target_delay = args.target_delay

    variants = VARIANTS
    if args.only:
        variants = [v for v in VARIANTS if v[0] in args.only]
        if not variants:
            print(f"No matches. Available: {[v[0] for v in VARIANTS]}")
            sys.exit(1)

    # Build task list: cross-product of variants × models × benchmarks
    tasks = []
    for variant_name, cost_metric, language in variants:
        for model in MODELS:
            for bench in BENCHMARKS:
                tasks.append({
                    "variant": variant_name,
                    "model": model,
                    "benchmark": bench,
                    "cost_metric": cost_metric,
                    "language": language,
                    "target_delay": target_delay,
                })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    runs_root = Path(args.runs_root) if args.runs_root else Path("runs") / f"cost_lang_sweep_{ts}"
    runs_root.mkdir(parents=True, exist_ok=True)

    print(f"Running {len(tasks)} tasks ({len(variants)} variants × "
          f"{len(MODELS)} models × {len(BENCHMARKS)} benchmarks)")
    print(f"Variants: {[v[0] for v in variants]}")
    print(f"Workers: {args.workers}")
    print(f"Output: {runs_root}")
    print()

    grand_start = time.time()
    all_results: List[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_run_one, task, str(runs_root)): task
            for task in tasks
        }
        for future in as_completed(futures):
            task = futures[future]
            tag = f"{task['variant']}/{task['model'].split('/')[-1]}/{task['benchmark']}"
            try:
                result_dict = future.result()
                all_results.append(result_dict)
            except Exception as e:
                print(f"[ERROR] {tag}: {e}", flush=True)
                all_results.append({
                    "variant": task["variant"],
                    "model": task["model"],
                    "benchmark": task["benchmark"],
                    "status": "error",
                    "error": str(e),
                })

    grand_duration = time.time() - grand_start

    # Summary
    summary = {
        "timestamp": ts,
        "models": MODELS,
        "benchmarks": BENCHMARKS,
        "variants": [v[0] for v in variants],
        "max_steps": MAX_STEPS,
        "target_delay": target_delay,
        "total_tasks": len(tasks),
        "total_duration_s": round(grand_duration, 2),
        "workers": args.workers,
        "results": sorted(all_results, key=lambda r: (
            r.get("variant", ""), r.get("model", ""), r.get("benchmark_name", "")
        )),
    }

    summary_path = runs_root / "sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    # Print recap
    print(f"\n{'='*70}")
    print(f"All {len(tasks)} tasks done in {grand_duration/60:.1f} min")

    for variant_name, _, _ in variants:
        vr = [r for r in all_results if r.get("variant") == variant_name]
        ok = sum(1 for r in vr if r.get("passed"))
        total = len(vr)
        print(f"  {variant_name}: {ok}/{total} passed")

    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()

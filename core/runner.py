"""Runner: execute agent across models and benchmarks, collect results."""

import json
import os
import shutil
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from core.agent import AgentResult, RTLAgent
from core.benchmarks import Benchmark, load_benchmark, load_benchmarks
from core.cost import CostMetric, YosysTransistorCost
from core.llm_client import AnthropicClient, DeepInfraClient, OpenRouterClient, LLMClient

# Load .env for API keys
_ENV_PATHS = [
    Path(__file__).parent.parent / ".env",
    Path("/workspaces/rtl_scout/.env"),
]
for p in _ENV_PATHS:
    if p.exists():
        load_dotenv(p)
        break


DEFAULT_BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"


def _write_chat_log(result: "AgentResult", path: Path) -> None:
    """Write the full agent chat history to a human-readable text file."""
    SEP = "=" * 80
    lines = []

    lines.append(SEP)
    lines.append(f"BENCHMARK : {result.benchmark_name}")
    lines.append(f"MODEL     : {result.model}")
    lines.append(f"METRIC    : {result.cost_metric_name}")
    lines.append(f"RESULT    : {'PASS' if result.passed else 'FAIL'}"
                 + (f"  |  best cost: {result.best_cost:.4g} {result.cost_metric_name}"
                    f"  (eval {result.best_eval.get('eval_index', '?')})"
                    if result.best_cost is not None else ""))
    lines.append(f"STEPS: {result.num_steps}  |  duration: {result.duration_s}s")
    lines.append(SEP)
    lines.append("")

    for msg in result.messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls", [])

        if role == "SYSTEM":
            lines.append(f"[{role}]")
            lines.append(content)
            lines.append("")
            continue

        if role == "TOOL":
            lines.append(f"[TOOL RESULT]")
            lines.append(content)
            lines.append("")
            continue

        # ASSISTANT or USER
        lines.append(f"[{role}]")
        if content:
            lines.append(content)
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "?")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                args = fn.get("arguments", "")
            # Pretty-print args: inline for short ones, one-per-line otherwise
            arg_str = ", ".join(
                f"{k}={repr(v)}" for k, v in args.items()
            ) if isinstance(args, dict) else repr(args)
            lines.append(f"  -> {name}({arg_str})")
        lines.append("")

    lines.append(SEP)
    path.write_text("\n".join(lines))


KNOWN_PROVIDERS = {"deepinfra", "anthropic", "openrouter", "fake"}


def parse_model_spec(spec: str) -> tuple:
    """Parse a '<provider>:<model>' spec into (provider, model).

    The provider prefix is required — there is no default provider. Examples:
        'anthropic:claude-sonnet-4-5-20250929' -> ('anthropic', 'claude-sonnet-4-5-20250929')
        'deepinfra:meta-llama/Llama-3.3-70B-Instruct-Turbo' -> ('deepinfra', 'meta-llama/Llama-3.3-70B-Instruct-Turbo')

    Raises ValueError if the spec has no recognised '<provider>:' prefix.
    """
    parts = spec.split(":", 1)
    if len(parts) == 2 and parts[0] in KNOWN_PROVIDERS:
        return parts[0], parts[1]
    raise ValueError(
        f"--model must be specified as '<provider>:<model>' with provider one of "
        f"{sorted(KNOWN_PROVIDERS)}; got {spec!r}"
    )


def build_client(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
) -> LLMClient:
    """Construct the appropriate LLM client based on provider."""
    if provider == "deepinfra":
        key = api_key or os.environ.get("DEEPINFRA_API_KEY")
        if not key:
            raise ValueError("DEEPINFRA_API_KEY not set")
        return DeepInfraClient(model=model, api_key=key)
    elif provider == "openrouter":
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return OpenRouterClient(model=model, api_key=key)
    elif provider == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return AnthropicClient(model=model, api_key=key)
    elif provider == "fake":
        from core.fake_provider import build_fake_client
        return build_fake_client(model)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'deepinfra', 'openrouter', 'anthropic', or 'fake'.")


def run_agent_on_benchmark(
    benchmark: Benchmark,
    model: str,
    runs_dir: Path,
    max_steps: int = 20,
    api_key: Optional[str] = None,
    provider: str = "deepinfra",
    cost_metric: Optional[CostMetric] = None,
    system_prompt_extra: str = "",
    language: str = "verilog",
    save_workspaces: bool = True,
    flowy_optimize: bool = False,
    abc_optimize: bool = False,
    arith_autoconfig: bool = False,
    dont_touch_main_arith: bool = False,
    fsm_optimize: bool = False,
    run_cec: bool = True,
) -> AgentResult:
    """Execute the agent on a single benchmark and return the result."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workdir = runs_dir / benchmark.name / model.replace("/", "_") / timestamp
    workdir.mkdir(parents=True, exist_ok=True)

    # Resolve the golden reference once (compiles a .py reference if needed).
    # CEC is on by default but only runs when the benchmark ships a golden
    # reference — benchmarks without one simply skip the check.
    cec_reference = None
    if run_cec and benchmark.golden_reference is not None:
        from core.equivalence import resolve_golden_reference
        cec_reference = resolve_golden_reference(benchmark, workdir / "_golden")

    client = build_client(provider, model, api_key)
    agent = RTLAgent(
        client=client,
        workdir=workdir,
        max_steps=max_steps,
        cost_metric=cost_metric,
        system_prompt_extra=system_prompt_extra,
        language=language,
        save_workspaces=save_workspaces,
        flowy_optimize=flowy_optimize,
        abc_optimize=abc_optimize,
        arith_autoconfig=arith_autoconfig,
        dont_touch_main_arith=dont_touch_main_arith,
        fsm_optimize=fsm_optimize,
        run_cec=run_cec and cec_reference is not None,
        cec_reference=cec_reference,
    )

    # Copy testbench into the agent's workspace subdirectory
    shutil.copy2(benchmark.testbench, agent.workspace / "tb.sv")

    # Copy any data files (.dat) used by data-driven testbenches
    for dat_file in benchmark.root.glob("*.dat"):
        shutil.copy2(dat_file, agent.workspace / dat_file.name)

    # Copy optional context folder contents into the workspace.
    # Skip any path whose name starts with `_` (convention for
    # auxiliary dirs like `_debug/` that live inside a benchmark
    # but should not leak into the agent's workspace).
    # Also skip locally-generated build artifacts that may be sitting in the
    # context dir from a prior run: `obj_dir/` (Verilator build) is never a
    # legitimate input, and `design.v` is generated output for python-based
    # benchmarks (spirehdl/amaranth) where only the `.py` is the real source —
    # only verilog benchmarks legitimately ship a `design.v`.
    if benchmark.context_dir is not None:
        for item in benchmark.context_dir.iterdir():
            if item.name.startswith("_"):
                continue
            if item.name == "obj_dir":
                continue
            if item.name == "design.v" and language != "verilog":
                continue
            dest = agent.workspace / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    agent.design_top_module = benchmark.module_name

    print(f"\n{'='*60}")
    print(f"Benchmark: {benchmark.name} | Model: {model}")
    print(f"Workdir: {workdir}")
    print(f"{'='*60}")

    start = time.time()
    result = agent.run(benchmark.description, benchmark.name)
    result.duration_s = round(time.time() - start, 2)

    metric_label = result.cost_metric_name.capitalize()
    cost_str = f"{result.best_cost:.4g}" if result.best_cost is not None else "N/A"
    best_step = result.best_eval.get("eval_index", "?") if result.best_eval else "?"
    print(f"\nBest: {'PASS' if result.passed else 'FAIL'} | "
          f"{metric_label}: {cost_str} (step {best_step}) | "
          f"Steps: {result.num_steps} | "
          f"Duration: {result.duration_s}s")
    if result.token_usage.total_input or result.token_usage.output_tokens:
        print(f"Tokens: {result.token_usage.summary()}")
    if result.error:
        print(f"Error: {result.error}")

    best_design_dir = workdir / "best_design"
    if best_design_dir.exists():
        print(f"Best design saved: {best_design_dir}")

    # Save result JSON
    result_dict = result.to_dict()
    result_dict["workdir"] = str(workdir)
    result_path = workdir / "result.json"
    result_path.write_text(json.dumps(result_dict, indent=2))

    # Save full chat history as a readable text file
    _write_chat_log(result, workdir / "chat_log.txt")

    print(f"Results stored in: {workdir}")

    return result


def run_agent_across_benchmarks(
    model: str,
    benchmarks_root: Path = DEFAULT_BENCHMARKS_ROOT,
    benchmark_names: Optional[List[str]] = None,
    runs_dir: Optional[Path] = None,
    max_steps: int = 20,
    api_key: Optional[str] = None,
    provider: str = "deepinfra",
    cost_metric: Optional[CostMetric] = None,
    language: str = "verilog",
    save_workspaces: bool = True,
    run_cec: bool = True,
) -> Dict[str, Any]:
    """Execute the agent across multiple benchmarks for a single model."""
    if runs_dir is None:
        runs_dir = Path("runs") / datetime.now().strftime("%Y%m%d_%H%M%S")
    runs_dir.mkdir(parents=True, exist_ok=True)

    benchmarks = load_benchmarks(benchmarks_root, benchmark_names)
    results: List[Dict[str, Any]] = []

    start = time.time()
    for bench in benchmarks:
        try:
            result = run_agent_on_benchmark(
                bench, model, runs_dir,
                max_steps=max_steps, api_key=api_key,
                provider=provider, cost_metric=cost_metric,
                language=language, save_workspaces=save_workspaces,
                run_cec=run_cec,
            )
            result_dict = result.to_dict()
            result_dict["status"] = "ok"
            results.append(result_dict)
        except Exception as e:
            print(f"Error on {bench.name}: {e}")
            results.append({
                "benchmark_name": bench.name,
                "model": model,
                "status": "error",
                "error": str(e),
            })
    total_duration = time.time() - start

    total = len(results)
    passed = sum(1 for r in results if r.get("passed", False))

    summary = {
        "model": model,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total > 0 else 0,
        "duration_s": round(total_duration, 2),
        "benchmarks": results,
    }

    summary_path = runs_dir / f"summary_{model.replace('/', '_')}.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nModel summary saved: {summary_path}")
    return summary


def _run_model_benchmarks(task: dict) -> Dict[str, Any]:
    """Worker function for parallel execution (must be module-level for pickling)."""
    model_provider = task["provider"]
    model = task["model"]
    benchmarks_root = Path(task["benchmarks_root"])
    benchmark_names = task["benchmark_names"]
    runs_dir = Path(task["runs_dir"])
    max_steps = task["max_steps"]
    api_key = task["api_key"]
    cost_metric_cfg = task["cost_metric_cfg"]
    language = task["language"]
    save_workspaces = task["save_workspaces"]
    run_cec = task.get("run_cec", True)

    # Reconstruct cost metric in worker process
    if cost_metric_cfg:
        from core.cost import make_cost_metric
        cost_metric = make_cost_metric(
            cost_metric_cfg["name"],
            target_delay=cost_metric_cfg.get("target_delay", 500.0),
        )
    else:
        cost_metric = None

    print(f"\n{'#'*60}")
    print(f"# Model: {model} (provider: {model_provider})")
    print(f"{'#'*60}", flush=True)
    try:
        summary = run_agent_across_benchmarks(
            model, benchmarks_root, benchmark_names,
            runs_dir=runs_dir, max_steps=max_steps,
            api_key=api_key, provider=model_provider,
            cost_metric=cost_metric, language=language,
            save_workspaces=save_workspaces, run_cec=run_cec,
        )
        summary["status"] = "ok"
        return summary
    except Exception as e:
        traceback.print_exc()
        return {
            "model": model,
            "status": "error",
            "error": str(e),
        }


def run_agent_across_models_and_benchmarks(
    models: List[str],
    benchmarks_root: Path = DEFAULT_BENCHMARKS_ROOT,
    benchmark_names: Optional[List[str]] = None,
    runs_dir: Optional[Path] = None,
    max_steps: int = 20,
    api_key: Optional[str] = None,
    cost_metric: Optional[CostMetric] = None,
    language: str = "verilog",
    save_workspaces: bool = True,
    workers: int = 1,
    run_cec: bool = True,
) -> Dict[str, Any]:
    """Execute the agent across multiple models and benchmarks.

    Each model must be a '<provider>:<model>' spec (e.g.
    'anthropic:claude-sonnet-4-5-20250929') — there is no default provider.

    When *workers* > 1, models run in parallel using ProcessPoolExecutor.
    """
    if runs_dir is None:
        runs_dir = Path("runs") / datetime.now().strftime("%Y%m%d_%H%M%S")
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Parse provider:model specs
    parsed = [parse_model_spec(m) for m in models]

    # Serialisable cost-metric config (CostMetric objects can't be pickled)
    cost_metric_cfg = None
    if cost_metric is not None:
        cost_metric_cfg = {
            "name": cost_metric.metric_name,
            "target_delay": getattr(cost_metric, "target_delay", 500.0),
        }

    model_results: List[Dict[str, Any]] = []
    start = time.time()

    if workers > 1:
        # ── parallel mode ──────────────────────────────────────────
        tasks = [
            {
                "provider": mp,
                "model": m,
                "benchmarks_root": str(benchmarks_root),
                "benchmark_names": benchmark_names,
                "runs_dir": str(runs_dir),
                "max_steps": max_steps,
                "api_key": api_key,
                "cost_metric_cfg": cost_metric_cfg,
                "language": language,
                "save_workspaces": save_workspaces,
                "run_cec": run_cec,
            }
            for mp, m in parsed
        ]
        print(f"Running {len(tasks)} models in parallel (workers={workers})")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_model_benchmarks, t): t for t in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    summary = future.result()
                    model_results.append(summary)
                except Exception as e:
                    print(f"[ERROR] {task['model']}: {e}", flush=True)
                    model_results.append({
                        "model": task["model"],
                        "status": "error",
                        "error": str(e),
                    })
    else:
        # ── sequential mode (original behaviour) ──────────────────
        for model_provider, model in parsed:
            print(f"\n{'#'*60}")
            print(f"# Model: {model} (provider: {model_provider})")
            print(f"{'#'*60}")
            try:
                summary = run_agent_across_benchmarks(
                    model, benchmarks_root, benchmark_names,
                    runs_dir=runs_dir, max_steps=max_steps,
                    api_key=api_key, provider=model_provider,
                    cost_metric=cost_metric, language=language,
                    save_workspaces=save_workspaces, run_cec=run_cec,
                )
                summary["status"] = "ok"
                model_results.append(summary)
            except Exception as e:
                print(f"Error with model {model}: {e}")
                model_results.append({
                    "model": model,
                    "status": "error",
                    "error": str(e),
                })

    total_duration = time.time() - start

    all_results = {
        "models": [m for _, m in parsed],
        "total_duration_s": round(total_duration, 2),
        "model_results": model_results,
    }

    all_path = runs_dir / "all_results.json"
    all_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nAll results saved: {all_path}")
    return all_results

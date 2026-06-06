"""Async elite-pool multi-run optimisation.

Runs a configurable number of agent runs in parallel.  An *elite pool*
(top-K passing designs, sorted by cost) is maintained across runs.  When
an agent finishes, the pool is updated and a new agent is spawned — either
seeded from a pool entry (exploitation, sampled via softmax) or starting
fresh (exploration, with decaying probability).
"""

import json
import math
import random
import shutil
import tempfile
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.benchmarks import Benchmark, load_benchmark, load_benchmarks
from core.cost import COST_METRICS, make_cost_metric
from core.runner import (
    DEFAULT_BENCHMARKS_ROOT,
    parse_model_spec,
    run_agent_on_benchmark,
)


# ── dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class EliteEntry:
    cost: float
    cost_metric: str
    design_dir: Path          # path to best_design/ directory
    design_file: str          # from _best_meta.json
    summary: str              # from summary.txt (truncated)
    run_index: int
    model: str
    secondary_cost: Optional[float] = None  # tiebreaker when primary cost is equal
    target_delay: Optional[float] = None    # synthesis timing constraint (ps)


def _metric_keys(cost_metric: str) -> tuple[Optional[str], Optional[str]]:
    """Look up (primary_key, tiebreaker_key) for a registered metric name."""
    cls = COST_METRICS.get(cost_metric)
    if cls is None:
        return None, None
    return getattr(cls, "primary_key", None), getattr(cls, "tiebreaker_key", None)


def _cost_from_metrics(metrics: Dict[str, Any], cost_metric: str) -> Optional[float]:
    """Return the cost for *cost_metric* by reading the flat metrics dict."""
    primary_key, _ = _metric_keys(cost_metric)
    return metrics.get(primary_key) if primary_key else None


def _tiebreaker_from_metrics(metrics: Dict[str, Any], cost_metric: str) -> Optional[float]:
    """Return the natural tiebreaker value from the flat metrics dict."""
    _, tiebreaker_key = _metric_keys(cost_metric)
    return metrics.get(tiebreaker_key) if tiebreaker_key else None


def _sort_key(e: EliteEntry) -> tuple:
    """Sort key: primary cost, then secondary (None → +inf)."""
    return (e.cost, e.secondary_cost if e.secondary_cost is not None else float("inf"))


# ── elite pool ───────────────────────────────────────────────────────────────

class ElitePool:
    """Top-K pool of passing designs with softmax sampling."""

    def __init__(self, max_size: int = 5, temperature: float = 1.0):
        self.entries: List[EliteEntry] = []
        self.max_size = max_size
        self.temperature = temperature

    def update(self, entry: EliteEntry) -> bool:
        """Add *entry* if it qualifies.  Returns True if pool changed."""
        if len(self.entries) < self.max_size:
            self.entries.append(entry)
            self.entries.sort(key=_sort_key)
            return True
        worst = self.entries[-1]
        if _sort_key(entry) < _sort_key(worst):
            self.entries[-1] = entry
            self.entries.sort(key=_sort_key)
            return True
        return False

    def sample(self) -> EliteEntry:
        """Sample an entry using softmax over z-scored negative cost.

        Costs are normalised to z-scores (subtract mean, divide by std)
        before applying the temperature, so the temperature parameter is
        scale-independent: T=1.0 gives a standard softmax over z-scores,
        T>1 flattens (more exploration), T<1 sharpens (more greedy).
        """
        if len(self.entries) == 1:
            return self.entries[0]
        costs = [e.cost for e in self.entries]
        mean = sum(costs) / len(costs)
        variance = sum((c - mean) ** 2 for c in costs) / len(costs)
        std = math.sqrt(variance) if variance > 0 else 1.0
        # z-score: lower cost → lower z → we negate so lower cost gets
        # higher logit → higher sampling probability.
        logits = [-(c - mean) / (std * self.temperature) for c in costs]
        max_logit = max(logits)
        exps = [math.exp(l - max_logit) for l in logits]
        total = sum(exps)
        probs = [e / total for e in exps]
        r = random.random()
        cumul = 0.0
        for entry, p in zip(self.entries, probs):
            cumul += p
            if r <= cumul:
                return entry
        return self.entries[-1]  # fallback

    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def best(self) -> Optional[EliteEntry]:
        return self.entries[0] if self.entries else None

    def to_list(self) -> List[Dict[str, Any]]:
        return [
            {"cost": e.cost, "run_index": e.run_index,
             "design_file": e.design_file, "design_dir": str(e.design_dir)}
            for e in self.entries
        ]


# ── helpers ──────────────────────────────────────────────────────────────────

_SKIP_NAMES = {"_best_meta.json", "tb.sv", "obj_dir", "vectors.dat"}
_MAX_SUMMARY_LEN = 500


def compute_fresh_probability(
    completed: int, total: int,
    base: float = 0.5, minimum: float = 0.1,
) -> float:
    if total <= 0:
        return base
    return max(minimum, base * (1.0 - completed / total))


def _read_best_meta(design_dir: Path) -> Dict[str, Any]:
    meta_path = design_dir / "_best_meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def _read_summary(workdir: Path) -> str:
    summary_path = workdir / "summary.txt"
    if summary_path.exists():
        text = summary_path.read_text().strip()
        if len(text) > _MAX_SUMMARY_LEN:
            text = text[:_MAX_SUMMARY_LEN] + "..."
        return text
    return ""


def _metrics_from_entry(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return the flat metrics dict from a manifest/result entry, or ``{}``.

    Manifest entries (pareto_front.json, best_designs.json) carry ``metrics``;
    multirun summary entries carry ``best_metrics``.
    """
    for key in ("metrics", "best_metrics"):
        sub = d.get(key)
        if isinstance(sub, dict) and sub:
            return sub
    return {}


def make_elite_entry(result_dict: Dict[str, Any], run_index: int,
                     override_cost_metric: Optional[str] = None) -> Optional[EliteEntry]:
    """Build an EliteEntry from a multirun result dict, or None if not eligible.

    If *override_cost_metric* differs from the original, cost is re-read from the flat
    metrics so the pool sorts by the current run's metric, not the seed run's.
    """
    if not result_dict.get("passed"):
        return None
    original_metric = result_dict.get("cost_metric", "")
    cost_metric = override_cost_metric or original_metric
    metrics = _metrics_from_entry(result_dict)
    cost = _cost_from_metrics(metrics, cost_metric) if cost_metric != original_metric else result_dict.get("best_cost")
    if cost is None:
        return None
    workdir = Path(result_dict["workdir"])
    design_dir = workdir / "best_design"
    if not design_dir.exists():
        return None
    meta = _read_best_meta(design_dir)
    return EliteEntry(
        cost=cost, cost_metric=cost_metric, design_dir=design_dir,
        design_file=meta.get("design_file", ""), summary=_read_summary(workdir),
        run_index=run_index, model=result_dict.get("model", ""),
        secondary_cost=_tiebreaker_from_metrics(metrics, cost_metric),
        target_delay=(result_dict.get("best_eval") or {}).get("target_delay"),
    )


def _prepare_extract_seed_dir(entry_dict: Dict[str, Any], extract_dir: Path,
                              seed_dir: Path) -> Optional[Path]:
    """Copy an extracted design file (and any siblings) into a best_design-like seed_dir.

    Returns the created directory, or None if the source file is missing.  When the
    entry's ``extracted_file`` lives in a subdir (extract_pareto --separate-dirs), sibling
    files and dirs are carried along — especially ``.spirehdl_cache/`` and local .py deps,
    so ``build_seed_context`` can then flow the cache into the agent workspace.
    """
    extracted_file = entry_dict.get("extracted_file", "")
    if not extracted_file:
        return None
    src = extract_dir / extracted_file
    if not src.exists():
        return None
    seed_dir.mkdir(parents=True, exist_ok=True)
    dest_name = Path(extracted_file).name  # strip any subdir from dest
    if src.parent != extract_dir:
        for item in src.parent.iterdir():
            if item == src:
                continue
            dest = seed_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    shutil.copy2(src, seed_dir / dest_name)
    (seed_dir / "_best_meta.json").write_text(json.dumps({"design_file": dest_name}, indent=2))
    return seed_dir


def make_elite_entry_from_extract(entry_dict: Dict[str, Any], design_dir: Path, index: int,
                                  override_cost_metric: Optional[str] = None) -> Optional[EliteEntry]:
    """Build an EliteEntry from an extract-script manifest entry.

    If *override_cost_metric* differs from the original, cost is re-read from the flat
    metrics dict so the pool sorts by the new objective.
    """
    original_metric = entry_dict.get("cost_metric", "")
    cost_metric = override_cost_metric or original_metric
    metrics = _metrics_from_entry(entry_dict)
    cost = _cost_from_metrics(metrics, cost_metric) if cost_metric != original_metric else entry_dict.get("cost_value")
    if cost is None:
        return None
    meta = _read_best_meta(design_dir)
    return EliteEntry(
        cost=cost, cost_metric=cost_metric, design_dir=design_dir,
        design_file=meta.get("design_file", ""), summary="", run_index=index, model="",
        secondary_cost=_tiebreaker_from_metrics(metrics, cost_metric),
        target_delay=entry_dict.get("target_delay"),
    )


def build_seed_context(benchmark: Benchmark, entry: EliteEntry) -> Path:
    """Create a temp context dir with original context + seed design files."""
    temp_dir = Path(tempfile.mkdtemp(prefix="multirun_ctx_"))

    # Copy original context
    if benchmark.context_dir and benchmark.context_dir.is_dir():
        for item in benchmark.context_dir.iterdir():
            dest = temp_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    # Overlay seed files on the context under their original names so cross-file `from X import …` inside the 
    # seed keeps resolving; seed files shadow the matching baseline files in the workspace.
    if entry.design_dir.is_dir():
        for item in entry.design_dir.iterdir():
            if item.name in _SKIP_NAMES:
                continue
            # Whitelist `.spirehdl_cache/` so that spirehdl's content-addressed
            # optimize cache (populated by the predecessor's @flowy_optimized /
            # @abc_optimized calls) flows to the seeded agent. Other dotfiles
            # (.git, .DS_Store, editor caches) remain skipped.
            if item.name == ".spirehdl_cache" and item.is_dir():
                shutil.copytree(item, temp_dir / item.name, dirs_exist_ok=True)
                continue
            if item.name.startswith("."):
                continue
            if item.is_dir():
                continue
            shutil.copy2(item, temp_dir / item.name)

    return temp_dir


def build_seed_prompt(
    entry: Optional[EliteEntry],
    pool: ElitePool,
    run_index: int,
    total_runs: int,
    is_fresh: bool,
) -> str:
    """Build system_prompt_extra for a seeded or fresh agent."""
    lines: List[str] = []

    if not pool.is_empty():
        best = pool.best()
        lines.append(f"## Multi-run optimisation — run {run_index + 1}/{total_runs}")
        lines.append(f"Previous best cost: {best.cost:.4g} {best.cost_metric}")
        lines.append("")

    if not is_fresh and entry is not None:
        seed_name = entry.design_file if entry.design_file else "design.py"
        lines.append("### Seed design (in your workspace)")
        seed_desc = (
            f"A verified correct design has been placed in your workspace as "
            f"`{seed_name}` (along with any helper files it depends on) with cost "
            f"{entry.cost:.4g} {entry.cost_metric}. These files overlay the baseline "
            f"context — `{seed_name}` and its dependencies are the seed design, not "
            f"the starting point. Start by reading `{seed_name}` and evaluating it, "
            f"then try to improve it."
        )
        if entry.target_delay is not None:
            seed_desc += (
                f" This design was evaluated with target_delay={entry.target_delay:.0f} ps."
            )
        lines.append(seed_desc)
        lines.append("")

    # Summaries from the pool
    summaries = [(e.cost, e.cost_metric, e.summary) for e in pool.entries if e.summary]
    if summaries:
        lines.append("### Lessons from previous agents")
        for cost, metric, summary in summaries:
            lines.append(f"- Agent ({cost:.4g} {metric}): \"{summary}\"")
        lines.append("")

    if is_fresh and not pool.is_empty():
        lines.append(
            "Try a DIFFERENT approach from what previous agents attempted. "
            "Be creative and explore unconventional strategies."
        )

    return "\n".join(lines)


# ── worker function (module-level for pickling) ─────────────────────────────

def _run_one_agent(task: Dict[str, Any], runs_root_str: str) -> Dict[str, Any]:
    """Execute a single agent run.  Runs in a subprocess."""
    from core.benchmarks import Benchmark, load_benchmark
    from core.cost import make_cost_metric
    from core.runner import parse_model_spec, run_agent_on_benchmark

    runs_root = Path(runs_root_str)
    run_index = task["run_index"]
    model_spec = task["model"]
    benchmark_root = Path(task["benchmark_root"])
    is_fresh = task["is_fresh"]
    seed_context_dir = task.get("seed_context_dir")
    prompt_extra = task.get("prompt_extra", "")
    max_steps = task["max_steps"]
    cost_metric_name = task["cost_metric"]
    target_delay = task["target_delay"]
    language = task["language"]
    flowy_optimize = task.get("flowy_optimize", False)
    abc_optimize = task.get("abc_optimize", False)
    arith_autoconfig = task.get("arith_autoconfig", False)
    dont_touch_main_arith = task.get("dont_touch_main_arith", False)
    fsm_optimize = task.get("fsm_optimize", False)
    technology = task.get("technology", "asap7")

    provider, model = parse_model_spec(model_spec)
    cost_metric = make_cost_metric(cost_metric_name, target_delay=target_delay,
                                   technology=technology)
    bench = load_benchmark(benchmark_root)

    # Augment context dir with seed files if provided
    if seed_context_dir:
        bench = Benchmark(
            name=bench.name,
            root=bench.root,
            description=bench.description,
            testbench=bench.testbench,
            module_name=bench.module_name,
            context_dir=Path(seed_context_dir),
        )

    run_dir = runs_root / f"run_{run_index:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    try:
        result = run_agent_on_benchmark(
            bench,
            model=model,
            runs_dir=run_dir,
            max_steps=max_steps,
            provider=provider,
            cost_metric=cost_metric,
            system_prompt_extra=prompt_extra,
            language=language,
            save_workspaces=True,
            flowy_optimize=flowy_optimize,
            abc_optimize=abc_optimize,
            arith_autoconfig=arith_autoconfig,
            dont_touch_main_arith=dont_touch_main_arith,
            fsm_optimize=fsm_optimize,
        )
        result_dict = result.to_dict()
        result_dict["status"] = "ok"
    except Exception as e:
        traceback.print_exc()
        result_dict = {
            "benchmark_name": bench.name,
            "model": model,
            "status": "error",
            "error": str(e),
            "passed": False,
            "best_cost": None,
        }

    duration = round(time.time() - start, 2)
    result_dict["run_index"] = run_index
    result_dict["is_fresh"] = is_fresh
    result_dict["seed_cost"] = task.get("seed_cost")
    result_dict["seed_run_index"] = task.get("seed_run_index")
    result_dict["duration_s"] = duration

    # Resolve workdir — run_agent_on_benchmark creates a nested dir
    if "workdir" not in result_dict:
        # Try to find it from the run_dir
        candidates = list(run_dir.rglob("result.json"))
        if candidates:
            result_dict["workdir"] = str(candidates[0].parent)
        else:
            result_dict["workdir"] = str(run_dir)

    tag = f"run_{run_index:03d}"
    cost = result_dict.get("best_cost", "N/A")
    if isinstance(cost, float):
        cost = f"{cost:.4g}"
    status = "PASS" if result_dict.get("passed") else "FAIL"
    mode = "fresh" if is_fresh else f"seed:{task.get('seed_cost', '?')}"
    print(f"[DONE] {tag}: {status} cost={cost} ({mode}) dur={duration}s", flush=True)

    # Clean up temp context dir
    if seed_context_dir:
        shutil.rmtree(seed_context_dir, ignore_errors=True)

    return result_dict


# ── main orchestrator ────────────────────────────────────────────────────────

def run_multirun(
    benchmark_name: str,
    model: str,
    total_runs: int = 10,
    max_concurrent: int = 4,
    max_steps: int = 30,
    elite_size: int = 5,
    temperature: float = 1.0,
    fresh_base: float = 0.5,
    fresh_min: float = 0.1,
    fresh_first: int = 0,
    cost_metric: str = "transistors",
    target_delay: float = 500.0,
    technology: str = "asap7",
    language: str = "verilog",
    benchmarks_root: Path = DEFAULT_BENCHMARKS_ROOT,
    runs_root: Optional[Path] = None,
    seed_from: Optional[str] = None,
    flowy_optimize: bool = False,
    abc_optimize: bool = False,
    arith_autoconfig: bool = False,
    dont_touch_main_arith: bool = False,
    fsm_optimize: bool = False,
) -> Dict[str, Any]:
    """Run the async elite-pool multi-run optimization."""
    from datetime import datetime

    if runs_root is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        runs_root = Path("runs") / f"multirun_{ts}"
    runs_root.mkdir(parents=True, exist_ok=True)

    # Load benchmark
    benchmarks = load_benchmarks(benchmarks_root, [benchmark_name])
    if not benchmarks:
        raise ValueError(f"Benchmark not found: {benchmark_name}")
    bench = benchmarks[0]

    pool = ElitePool(max_size=elite_size, temperature=temperature)
    completed = 0
    submitted = 0
    outcomes: List[Dict[str, Any]] = []
    cost_progression: List[Dict[str, Any]] = []

    # Seed pool from a previous run or extract output
    if seed_from is not None:
        seed_path = Path(seed_from)
        if seed_path.is_dir():
            for name in ("pareto_front.json", "best_designs.json",
                         "multirun_summary.json"):
                candidate = seed_path / name
                if candidate.exists():
                    seed_path = candidate
                    break
            else:
                raise FileNotFoundError(
                    f"No manifest found in {seed_path}. Expected "
                    "pareto_front.json, best_designs.json, or multirun_summary.json")
        prev = json.loads(seed_path.read_text())
        seeded = 0
        if isinstance(prev, dict) and "runs" in prev:
            # multirun_summary.json format
            for run in prev["runs"]:
                entry = make_elite_entry(run, run.get("run_index", -1),
                                        override_cost_metric=cost_metric)
                if entry is not None:
                    pool.update(entry)
                    seeded += 1
        elif isinstance(prev, list):
            # extract format (pareto_front.json or best_designs.json)
            extract_dir = seed_path.parent
            seeds_dir = runs_root / "_seeds"
            for i, item in enumerate(prev):
                design_dir = _prepare_extract_seed_dir(
                    item, extract_dir, seeds_dir / f"seed_{i:03d}")
                if design_dir is None:
                    continue
                entry = make_elite_entry_from_extract(item, design_dir, index=i,
                                                     override_cost_metric=cost_metric)
                if entry is not None:
                    pool.update(entry)
                    seeded += 1
        else:
            raise ValueError(f"Unrecognized seed format in {seed_path}")
        print(f"Seeded elite pool from {seed_path}: "
              f"{seeded} eligible entries → {len(pool.entries)} pool entries")
        if not pool.is_empty():
            print(f"  Pool best: {pool.best().cost:.4g}")

    # Save config
    config = {
        "benchmark": benchmark_name,
        "model": model,
        "total_runs": total_runs,
        "max_concurrent": max_concurrent,
        "max_steps": max_steps,
        "elite_size": elite_size,
        "temperature": temperature,
        "fresh_base": fresh_base,
        "fresh_min": fresh_min,
        "fresh_first": fresh_first,
        "cost_metric": cost_metric,
        "target_delay": target_delay,
        "technology": technology,
        "language": language,
        "seed_from": seed_from,
        "flowy_optimize": flowy_optimize,
        "abc_optimize": abc_optimize,
        "arith_autoconfig": arith_autoconfig,
        "dont_touch_main_arith": dont_touch_main_arith,
        "fsm_optimize": fsm_optimize,
    }
    (runs_root / "config.json").write_text(json.dumps(config, indent=2))

    print(f"{'=' * 60}")
    print(f"Multi-run optimisation")
    print(f"Benchmark: {benchmark_name} | Model: {model}")
    print(f"Total runs: {total_runs} | Max concurrent: {max_concurrent}")
    print(f"Elite size: {elite_size} | Temperature: {temperature}")
    fresh_str = f"Fresh: base={fresh_base}, min={fresh_min}"
    if fresh_first > 0:
        fresh_str += f", first={fresh_first}"
    print(fresh_str)
    print(f"Output: {runs_root}")
    print(f"{'=' * 60}\n")

    grand_start = time.time()

    def _make_task(idx: int) -> Dict[str, Any]:
        """Build a task dict for run *idx*."""
        p_fresh = compute_fresh_probability(completed, total_runs, fresh_base, fresh_min)
        is_fresh = pool.is_empty() or idx < fresh_first or random.random() < p_fresh
        seed_entry = None
        seed_context_dir = None
        seed_cost = None
        prompt_extra = ""

        seed_run_index = None
        if not is_fresh:
            seed_entry = pool.sample()
            seed_context_dir = str(build_seed_context(bench, seed_entry))
            seed_cost = seed_entry.cost
            seed_run_index = seed_entry.run_index

        prompt_extra = build_seed_prompt(
            entry=seed_entry, pool=pool,
            run_index=idx, total_runs=total_runs,
            is_fresh=is_fresh,
        )

        mode = "fresh" if is_fresh else f"seed (cost={seed_cost:.4g})"
        print(f"[SUBMIT] run_{idx:03d}: {mode}  p_fresh={p_fresh:.2f}", flush=True)

        return {
            "run_index": idx,
            "model": model,
            "benchmark_root": str(bench.root),
            "is_fresh": is_fresh,
            "seed_context_dir": seed_context_dir,
            "seed_cost": seed_cost,
            "seed_run_index": seed_run_index,
            "prompt_extra": prompt_extra,
            "max_steps": max_steps,
            "cost_metric": cost_metric,
            "target_delay": target_delay,
            "technology": technology,
            "language": language,
            "flowy_optimize": flowy_optimize,
            "abc_optimize": abc_optimize,
            "arith_autoconfig": arith_autoconfig,
            "dont_touch_main_arith": dont_touch_main_arith,
            "fsm_optimize": fsm_optimize,
        }

    with ProcessPoolExecutor(max_workers=max_concurrent) as executor:
        futures: Dict[Any, Dict[str, Any]] = {}

        # Submit initial batch
        while submitted < min(total_runs, max_concurrent):
            task = _make_task(submitted)
            future = executor.submit(_run_one_agent, task, str(runs_root))
            futures[future] = task
            submitted += 1

        # Process completions, submit replacements
        while futures:
            for done_future in as_completed(futures):
                task = futures.pop(done_future)
                completed += 1

                try:
                    result_dict = done_future.result()
                except Exception as e:
                    print(f"[ERROR] run_{task['run_index']:03d}: {e}", flush=True)
                    result_dict = {
                        "run_index": task["run_index"],
                        "is_fresh": task["is_fresh"],
                        "seed_cost": task.get("seed_cost"),
                        "seed_run_index": task.get("seed_run_index"),
                        "passed": False,
                        "best_cost": None,
                        "status": "error",
                        "error": str(e),
                        "workdir": "",
                    }

                outcomes.append(result_dict)

                # Update elite pool
                entry = make_elite_entry(result_dict, task["run_index"])
                pool_changed = False
                if entry is not None:
                    pool_changed = pool.update(entry)
                    if pool_changed:
                        print(f"  -> Elite pool updated! Best: {pool.best().cost:.4g}", flush=True)

                best_cost = pool.best().cost if not pool.is_empty() else None
                cost_progression.append({
                    "run_completed": completed,
                    "run_index": task["run_index"],
                    "best_cost": best_cost,
                    "pool_changed": pool_changed,
                    "pool": pool.to_list(),
                })

                status = "PASS" if result_dict.get("passed") else "FAIL"
                rc = result_dict.get("best_cost")
                rc_str = f"{rc:.4g}" if rc is not None else "N/A"
                pool_str = f"{pool.best().cost:.4g}" if not pool.is_empty() else "N/A"
                mode = "fresh" if task["is_fresh"] else f"seed:{task.get('seed_cost', '?')}"
                print(
                    f"[{completed}/{total_runs}] run_{task['run_index']:03d}: "
                    f"{status} cost={rc_str} ({mode}) "
                    f"pool_best={pool_str}  pool_size={len(pool.entries)}",
                    flush=True,
                )

                # Submit next if budget remains
                if submitted < total_runs:
                    new_task = _make_task(submitted)
                    new_future = executor.submit(_run_one_agent, new_task, str(runs_root))
                    futures[new_future] = new_task
                    submitted += 1

                break  # back to as_completed loop

    grand_duration = round(time.time() - grand_start, 2)

    # Copy global best design
    if not pool.is_empty():
        best = pool.best()
        global_best_dir = runs_root / "best_design"
        if global_best_dir.exists():
            shutil.rmtree(global_best_dir)
        shutil.copytree(best.design_dir, global_best_dir)
        global_best_cost = best.cost
        global_best_workdir = str(best.design_dir.parent)
    else:
        global_best_cost = None
        global_best_workdir = None

    # Write summary
    summary = {
        "benchmark": benchmark_name,
        "model": model,
        "total_runs": total_runs,
        "max_concurrent": max_concurrent,
        "elite_size": elite_size,
        "temperature": temperature,
        "cost_metric": cost_metric,
        "total_duration_s": grand_duration,
        "global_best_cost": global_best_cost,
        "global_best_workdir": global_best_workdir,
        "elite_pool_final": pool.to_list(),
        "cost_progression": cost_progression,
        "runs": sorted(outcomes, key=lambda r: r.get("run_index", 0)),
    }
    summary_path = runs_root / "multirun_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"\n{'=' * 60}")
    print(f"Multi-run complete: {completed} runs in {grand_duration}s")
    if global_best_cost is not None:
        print(f"Global best: {global_best_cost:.4g} {cost_metric}")
    else:
        print("No passing designs found.")
    print(f"Summary: {summary_path}")
    print(f"{'=' * 60}")

    return summary

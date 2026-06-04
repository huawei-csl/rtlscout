#!/usr/bin/env python3
"""Parallel runner for the rtl_rewriter + rtl_rewriter_spirehdl benchmarks.

Spins up (case × language) agent runs in parallel with ProcessPoolExecutor.
Each task maps to a single `benchmarks/rtl_rewriter{_spirehdl}/case<N>/`
benchmark and is executed via `core.runner.run_agent_on_benchmark`.

After each run succeeds the script re-measures both `yosys_wires` and
`yosys_cells` on the agent's saved `best_design/` so the summary JSON
carries both numbers side by side — the cost metric the agent optimised
for drives `best_cost` and is one of the two.

The summary JSON produced at the end maps each (case, language) to its
run directory and headline numbers, and is the input to
`experiments/table_rtl_rewriter.py`.

Usage:
    python experiments/run_rtl_rewriter.py                    # all 10 cases, both languages
    python experiments/run_rtl_rewriter.py --cases 1 7 13     # only case1, case7, case13
    python experiments/run_rtl_rewriter.py --workers 4 \\
        --model claude:claude-opus-4-6 --cost-metric yosys_cells
"""

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.benchmarks import load_benchmark  # noqa: E402
from core.cost import COST_METRICS, make_cost_metric  # noqa: E402
from core.runner import parse_model_spec, run_agent_on_benchmark  # noqa: E402

# Case IDs that exist under benchmarks/rtl_rewriter/ (confidence ≥ medium).
AVAILABLE_CASES = [1, 2, 3, 4, 6, 7, 9, 10, 11, 13]
LANGUAGES = ["verilog", "spirehdl"]

BASELINE_PATHS = {
    "verilog":   REPO_ROOT / "benchmarks" / "rtl_rewriter" / "eval_verify.json",
    "spirehdl": REPO_ROOT / "benchmarks" / "rtl_rewriter_spirehdl" / "eval_verify.json",
}


def _load_baselines() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return {language: {case_id: {"wires": int, "cells": int}}}."""
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for lang, path in BASELINE_PATHS.items():
        rows = json.loads(path.read_text()) if path.exists() else []
        out[lang] = {r["case"]: {"wires": r["wires"], "cells": r["cells"]}
                    for r in rows}
    return out


def _benchmark_path(case_num: int, language: str) -> Path:
    root = "rtl_rewriter_spirehdl" if language == "spirehdl" else "rtl_rewriter"
    return REPO_ROOT / "benchmarks" / root / f"case{case_num}"


def _resolve_best_design(best_dir: Path, language: Optional[str]) -> Optional[Path]:
    """Locate the synthesisable verilog inside best_design/.

    - spirehdl: the agent emits Python; the actual verilog is always
      `design.v` (written by `m.to_verilog_file("design.v")`).
    - verilog:   the agent's best submission is recorded in
      `_best_meta.json.design_file` (e.g. `design_v5.sv`); fall back to
      `design.v` / `design.sv` if that metadata is missing.
    """
    if language == "spirehdl":
        design_v = best_dir / "design.v"
        return design_v if design_v.exists() else None

    meta_path = best_dir / "_best_meta.json"
    if meta_path.exists():
        try:
            design_file = json.loads(meta_path.read_text()).get("design_file")
            if design_file:
                cand = best_dir / design_file
                if cand.exists():
                    return cand
        except Exception:
            pass
    for name in ("design.v", "design.sv"):
        cand = best_dir / name
        if cand.exists():
            return cand
    return None


def _measure_best(best_dir: Path, top_module: str,
                  language: Optional[str] = None) -> Dict[str, Optional[int]]:
    """Re-run yosys_wires + yosys_cells on the best-design verilog."""
    design_file = _resolve_best_design(best_dir, language)
    if design_file is None:
        return {"wires": None, "cells": None,
                "error": f"no design file in {best_dir}"}
    try:
        w = make_cost_metric("yosys_wires").evaluate(best_dir, top_module=top_module, design_file=design_file)
        c = make_cost_metric("yosys_cells").evaluate(best_dir, top_module=top_module, design_file=design_file)
        return {
            "wires": int(w.value) if w.ok else None,
            "cells": int(c.value) if c.ok else None,
            "design_file": design_file.name,
            "error": "" if (w.ok and c.ok) else (w.error or c.error),
        }
    except Exception as e:
        return {"wires": None, "cells": None, "error": str(e)}


def _locate_workdir(lang_runs: Path, bench_name: str, model: str) -> Optional[Path]:
    """Locate the runner's workdir by globbing <lang_runs>/<bench>/<model_slug>/<ts>/.

    `AgentResult.to_dict()` doesn't carry the workdir back — the runner adds
    it only when writing result.json to disk — so we reconstruct it by
    picking the most-recent timestamp subdir under the model folder.
    """
    model_slug = model.replace("/", "_")
    parent = lang_runs / bench_name / model_slug
    if not parent.is_dir():
        return None
    candidates = [p for p in parent.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _finalize_record(rec: Dict[str, Any], workdir: Optional[Path],
                     module_name: str, language: Optional[str] = None) -> None:
    """Populate workdir, best_design_dir, best_wires, best_cells on a record.

    Reads result.json from disk (authoritative: the runner added workdir
    and the full best_eval) and re-measures best_design/design.v for the
    two yosys metrics. Safe to run multiple times — idempotent.
    """
    if workdir is None or not workdir.is_dir():
        rec["workdir"] = None
        rec["best_design_dir"] = None
        rec["best_wires"] = None
        rec["best_cells"] = None
        rec["best_measure_error"] = "workdir not found on disk"
        return

    rec["workdir"] = str(workdir)

    rj = workdir / "result.json"
    if rj.exists():
        try:
            disk = json.loads(rj.read_text())
            for k in ("best_cost", "cost_metric", "num_steps", "passed",
                     "duration_s", "best_eval"):
                if k in disk:
                    rec[k] = disk[k]
            # pass_rate lives inside best_eval; surface it at top level too
            be = disk.get("best_eval") or {}
            if be.get("pass_rate") is not None:
                rec["pass_rate"] = be["pass_rate"]
        except Exception as e:
            rec["result_json_error"] = str(e)

    best_dir = workdir / "best_design"
    if best_dir.is_dir():
        rec["best_design_dir"] = str(best_dir)
        meta = _measure_best(best_dir, module_name, language=language)
        rec["best_wires"] = meta["wires"]
        rec["best_cells"] = meta["cells"]
        rec["best_design_file"] = meta.get("design_file")
        rec["best_measure_error"] = meta["error"]
    else:
        rec["best_design_dir"] = None
        rec["best_wires"] = None
        rec["best_cells"] = None
        rec["best_measure_error"] = "no best_design/ on disk"


def _run_one(task: dict) -> dict:
    """Run a single (case, language) combo in a worker process."""
    case_num = task["case_num"]
    language = task["language"]
    model_spec = task["model"]
    cost_metric_name = task["cost_metric"]
    max_steps = task["max_steps"]
    runs_root = Path(task["runs_root"])

    bench_path = _benchmark_path(case_num, language)
    benchmark = load_benchmark(bench_path)
    provider, model = parse_model_spec(model_spec)
    cost_metric = make_cost_metric(cost_metric_name)

    # Separate per-language subroot so `case1` doesn't collide between variants.
    lang_runs = runs_root / language

    start = time.time()
    tag = f"case{case_num:<2}/{language:<9}"
    try:
        result = run_agent_on_benchmark(
            benchmark,
            model=model,
            runs_dir=lang_runs,
            max_steps=max_steps,
            provider=provider,
            cost_metric=cost_metric,
            language=language,
            save_workspaces=True,
        )
        rec: Dict[str, Any] = result.to_dict()
        rec["status"] = "ok"
        workdir = _locate_workdir(lang_runs, benchmark.name, model)
        _finalize_record(rec, workdir, benchmark.module_name, language=language)
    except Exception as e:
        traceback.print_exc()
        rec = {
            "benchmark_name": benchmark.name,
            "model": model,
            "status": "error",
            "error": str(e),
            "workdir": None,
            "best_wires": None,
            "best_cells": None,
        }

    rec["case_num"] = case_num
    rec["case_id"] = f"case{case_num}"
    rec["language"] = language
    rec["benchmark_path"] = str(bench_path.relative_to(REPO_ROOT))
    rec["cost_metric_requested"] = cost_metric_name
    rec["duration_s"] = round(time.time() - start, 2)

    passed = rec.get("passed")
    cost = rec.get("best_cost", "N/A")
    print(f"[DONE] {tag}  status={rec['status']:<5}  passed={passed}  "
          f"cost={cost}  wires/cells={rec.get('best_wires')}/{rec.get('best_cells')}  "
          f"dur={rec['duration_s']}s", flush=True)
    return rec


def _recompute_deltas(rec: Dict[str, Any]) -> None:
    """Recompute delta_{wires,cells}_pct from baseline_* and best_*."""
    bw = rec.get("baseline_wires")
    bc = rec.get("baseline_cells")
    bw_opt = rec.get("best_wires")
    bc_opt = rec.get("best_cells")
    rec["delta_wires_pct"] = (
        (bw_opt - bw) / bw * 100.0
        if (bw not in (None, 0) and bw_opt is not None) else None
    )
    rec["delta_cells_pct"] = (
        (bc_opt - bc) / bc * 100.0
        if (bc not in (None, 0) and bc_opt is not None) else None
    )


def backfill_summary(summary_path: Path) -> int:
    """Heal an existing summary.json by re-reading on-disk run dirs.

    Locates each (case, language) record's workdir under the summary's
    `runs_root` and re-applies `_finalize_record` so `workdir`,
    `best_design_dir`, `best_wires`, `best_cells`, and `delta_*_pct` are
    populated from the authoritative disk state. Returns the number of
    records that now carry both best_wires and best_cells.
    """
    summary = json.loads(summary_path.read_text())
    runs_root = Path(summary.get("runs_root") or summary_path.parent).resolve()
    model = summary["model"]
    _, model_name = parse_model_spec(model)

    # Re-load baselines from the shipped eval_verify.json so a core.cost
    # measurement-convention change (e.g. `clean -purge`) flows through.
    baselines = _load_baselines()

    healed = 0
    for case_id, per_lang in summary.get("results", {}).items():
        for language, rec in per_lang.items():
            lang_runs = runs_root / language
            bench_name = rec.get("benchmark_name") or case_id
            bench_path = REPO_ROOT / rec["benchmark_path"]
            try:
                module_name = load_benchmark(bench_path).module_name
            except Exception:
                module_name = rec.get("module_name") or bench_name
            rec["module_name"] = module_name
            workdir = _locate_workdir(lang_runs, bench_name, model_name)
            _finalize_record(rec, workdir, module_name, language=language)
            # Refresh baselines from disk (stale if the cost metric evolved)
            base = baselines.get(language, {}).get(case_id, {})
            if base:
                rec["baseline_wires"] = base.get("wires")
                rec["baseline_cells"] = base.get("cells")
            _recompute_deltas(rec)
            if rec.get("best_wires") is not None and rec.get("best_cells") is not None:
                healed += 1

    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return healed


def _parse_cases(arg: Optional[List[int]]) -> List[int]:
    if not arg:
        return list(AVAILABLE_CASES)
    bad = [c for c in arg if c not in AVAILABLE_CASES]
    if bad:
        raise SystemExit(
            f"Unknown case number(s): {bad}. Available: {AVAILABLE_CASES}"
        )
    return sorted(set(arg))


def main():
    parser = argparse.ArgumentParser(
        description="Run agent across rtl_rewriter + rtl_rewriter_spirehdl cases in parallel.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--cases", type=int, nargs="+", default=None,
                        help=f"Case numbers to include (subset of {AVAILABLE_CASES}). "
                             f"Omit to run all.")
    parser.add_argument("--languages", nargs="+", default=LANGUAGES,
                        choices=LANGUAGES,
                        help="Which language variants to run")
    parser.add_argument("--workers", type=int, default=8,
                        help="Max parallel workers")
    parser.add_argument("--model", default="claude:claude-opus-4-6",
                        help="Model spec (e.g. 'claude:claude-opus-4-6', "
                             "'deepinfra:moonshotai/Kimi-K2.5')")
    parser.add_argument("--cost-metric", default="yosys_cells",
                        choices=sorted(COST_METRICS),
                        help="Cost metric the agent optimises (default yosys_cells)")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--runs-root", default=None,
                        help="Output directory (default: runs/rtl_rewriter_<timestamp>)")
    parser.add_argument("--summary-out", default=None,
                        help="Path for the summary JSON (default: <runs-root>/summary.json)")
    parser.add_argument("--backfill", type=Path, default=None,
                        help="Path to an existing summary.json. Skip running "
                             "anything, re-locate each record's workdir under the "
                             "summary's runs_root, re-measure best_design/design.v "
                             "for both yosys metrics, recompute deltas, and rewrite "
                             "the summary in place. Useful after a run where the "
                             "script failed to capture on-disk results.")
    args = parser.parse_args()

    if args.backfill is not None:
        if not args.backfill.exists():
            raise SystemExit(f"Summary not found: {args.backfill}")
        healed = backfill_summary(args.backfill)
        print(f"Healed {healed} records in {args.backfill}")
        print(f"Render a table with:  "
              f"python experiments/table_rtl_rewriter.py {args.backfill}")
        return

    cases = _parse_cases(args.cases)
    languages = sorted(set(args.languages))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    runs_root = (Path(args.runs_root) if args.runs_root
                 else REPO_ROOT / "runs" / f"rtl_rewriter_{ts}").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    summary_path = Path(args.summary_out) if args.summary_out else runs_root / "summary.json"

    tasks = [
        {
            "case_num": c,
            "language": lang,
            "model": args.model,
            "cost_metric": args.cost_metric,
            "max_steps": args.max_steps,
            "runs_root": str(runs_root),
        }
        for c in cases for lang in languages
    ]

    print(f"Running {len(tasks)} tasks  "
          f"(cases={cases}, languages={languages})")
    print(f"Model:      {args.model}")
    print(f"Cost:       {args.cost_metric}  max_steps={args.max_steps}")
    print(f"Workers:    {args.workers}")
    print(f"Runs root:  {runs_root}")
    print()

    grand_start = time.time()
    results: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run_one, task): task for task in tasks}
        for fut in as_completed(futures):
            task = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"[ERROR] case{task['case_num']}/{task['language']}: {e}",
                      flush=True)
                results.append({
                    "case_num": task["case_num"],
                    "case_id":  f"case{task['case_num']}",
                    "language": task["language"],
                    "status": "error",
                    "error": str(e),
                })

    duration = time.time() - grand_start

    # Re-shape into {case_id: {language: rec}} for easy table consumption.
    baselines = _load_baselines()
    by_case: Dict[str, Dict[str, Any]] = {}
    for rec in results:
        by_case.setdefault(rec["case_id"], {})[rec["language"]] = rec

    # Decorate with baseline numbers and deltas.
    for case_id, per_lang in by_case.items():
        for lang, rec in per_lang.items():
            base = baselines.get(lang, {}).get(case_id, {})
            bw, bc = base.get("wires"), base.get("cells")
            rec["baseline_wires"] = bw
            rec["baseline_cells"] = bc
            rec["delta_wires_pct"] = (
                (rec["best_wires"] - bw) / bw * 100.0
                if (bw not in (None, 0) and rec.get("best_wires") is not None) else None
            )
            rec["delta_cells_pct"] = (
                (rec["best_cells"] - bc) / bc * 100.0
                if (bc not in (None, 0) and rec.get("best_cells") is not None) else None
            )

    summary = {
        "timestamp": ts,
        "model": args.model,
        "cost_metric": args.cost_metric,
        "max_steps": args.max_steps,
        "workers": args.workers,
        "cases": cases,
        "languages": languages,
        "total_tasks": len(tasks),
        "total_duration_s": round(duration, 2),
        "runs_root": str(runs_root),
        "results": by_case,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    passed = sum(1 for r in results if r.get("passed"))
    print()
    print(f"All {len(tasks)} tasks done in {duration/60:.1f} min  "
          f"({passed} passed correctness)")
    print(f"Summary: {summary_path}")
    print(f"Render a table with:  "
          f"python experiments/table_rtl_rewriter.py {summary_path}")


if __name__ == "__main__":
    main()

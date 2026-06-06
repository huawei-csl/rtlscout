#!/usr/bin/env python3
"""Parallel multi-run + two-phase pipeline on dr_rtl / dr_rtl_spirehdl.

Near-copy of ``experiments/rtl_rewriter_multirun.py`` adapted for the
DR-RTL benchmark. Differences from the rtl_rewriter version:

- Cases are identified by **string names** (e.g. ``ticket``, ``router``)
  rather than integers — DR-RTL designs have descriptive names from the
  upstream DR_RTL paper.
- Only the 6 cases whose SpireHDL port currently passes 2000/2000 are
  in scope here: ``ticket``, ``controller``, ``router``, ``pcie``,
  ``cpu_pipe``, ``datapath``.
- Per-case baselines are measured at runtime (the DR-RTL eval json
  carries one-off Nangate45 PPA, not the per-case wires/cells/transistors
  records that rtl_rewriter's ``eval_verify.json`` does).
- Recipe and CLI surface are identical to rtl_rewriter — same
  ``_phase_flags`` (Phase 1: no decorators, Phase 2: arith + abc + flowy),
  same ``--fsm-optimize``, ``--no-decorators``, ``--cost-metric``, etc.

The summary JSON that comes out of this script is the input to
``experiments/table_dr_rtl_multirun.py``.
"""

import argparse
import json
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.benchmarks import load_benchmark  # noqa: E402
from core.cost import COST_METRICS, make_cost_metric  # noqa: E402

AVAILABLE_CASES = [
    "ticket",
    "controller",
    "router",
    "pcie",
    "cpu_pipe",
    "datapath",
]
LANGUAGES = ["verilog", "spirehdl"]


def _load_baselines() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Measure each case's starting-point transistors/cells/wires once,
    in-process, by reading the `context/starting_point.{v,py}` and running
    the shared cost metrics. Cached lazily on disk under
    `benchmarks/dr_rtl{,_spirehdl}/baselines.json` so subsequent runs reuse
    the measurements (deleting that file forces a re-measure)."""
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for language in LANGUAGES:
        root = "dr_rtl_spirehdl" if language == "spirehdl" else "dr_rtl"
        cache = REPO_ROOT / "benchmarks" / root / "baselines.json"
        cached: Dict[str, Dict[str, Any]] = {}
        if cache.exists():
            try:
                cached = json.loads(cache.read_text())
            except Exception:
                cached = {}
        per_case: Dict[str, Dict[str, Any]] = {}
        updated = False
        for case in AVAILABLE_CASES:
            if case in cached:
                per_case[case] = cached[case]
                continue
            bench = _benchmark_path(case, language)
            try:
                bench_info = load_benchmark(bench)
            except Exception:
                per_case[case] = {"wires": None, "cells": None, "transistors": None}
                continue
            top = bench_info.module_name
            design = bench / "context" / (
                "starting_point.py" if language == "spirehdl" else "starting_point.v")
            if language == "spirehdl":
                # Emit the SpireHDL Python to Verilog in a tempdir so the cost
                # metric sees a single .v file. Use a tempdir per measurement
                # so concurrent baseline reads can't trample each other.
                import subprocess, tempfile, shutil
                td = Path(tempfile.mkdtemp(prefix="drrtl_base_"))
                try:
                    # copy all .py files in case starting_point.py imports siblings
                    for aux in (bench / "context").glob("*.py"):
                        shutil.copy2(aux, td / aux.name)
                    # pcie / datapath have deep expression trees — raise the
                    # recursion limit before exec'ing, matching the pattern
                    # in deps/spire-hdl/.../run_arithmetic_eval.py.
                    proc = subprocess.run(
                        ["python", "-c",
                         f"import sys; sys.setrecursionlimit(50000); "
                         f"exec(open({design.name!r}).read())"],
                        cwd=td, capture_output=True, text=True, timeout=120,
                    )
                    if proc.returncode != 0:
                        per_case[case] = {"wires": None, "cells": None,
                                          "transistors": None,
                                          "error": "spire emit failed"}
                        continue
                    v_file = td / "design.v"
                    if not v_file.exists():
                        per_case[case] = {"wires": None, "cells": None,
                                          "transistors": None,
                                          "error": "no design.v emitted"}
                        continue
                    c = make_cost_metric("yosys_cells").evaluate(
                        v_file.parent, top_module=top, design_file=v_file)
                    w = make_cost_metric("yosys_wires").evaluate(
                        v_file.parent, top_module=top, design_file=v_file)
                finally:
                    shutil.rmtree(td, ignore_errors=True)
            else:
                c = make_cost_metric("yosys_cells").evaluate(
                    design.parent, top_module=top, design_file=design)
                w = make_cost_metric("yosys_wires").evaluate(
                    design.parent, top_module=top, design_file=design)
            t_stats = c.stats if c.ok else (w.stats if w.ok else {})
            per_case[case] = {
                "wires": int(w.value) if w.ok else None,
                "cells": int(c.value) if c.ok else None,
                "transistors": int(t_stats["transistors"])
                    if "transistors" in t_stats else None,
            }
            updated = True
        if updated:
            cache.write_text(json.dumps(per_case, indent=2) + "\n")
        out[language] = per_case
    return out


def _benchmark_path(case_name: str, language: str) -> Path:
    root = "dr_rtl_spirehdl" if language == "spirehdl" else "dr_rtl"
    return REPO_ROOT / "benchmarks" / root / case_name


def _benchmark_name(case_name: str, language: str) -> str:
    """Name accepted by load_benchmarks (matched as rel path under benchmarks/)."""
    root = "dr_rtl_spirehdl" if language == "spirehdl" else "dr_rtl"
    return f"{root}/{case_name}"


def _phase_flags(language: str, phase: int,
                 fsm_optimize: bool = False,
                 no_decorators: bool = False) -> Dict[str, bool]:
    """Spirehdl-only agent prompt flags per phase.

    `fsm_optimize` opts the spirehdl agent into the FSM / state-encoding
    optimization README context (`optimized_fsm`, `optimized_encoding`); applied
    to both phases when on.

    `no_decorators` suppresses every decorator-related flag
    (`arith_autoconfig`, `flowy_optimize`, `abc_optimize`) so the spire prompt
    doesn't advertise `@arithmetic_optimized` / `@flowy_optimized` /
    `@abc_optimized` to the agent. `fsm_optimize` is left alone (it's a
    structural/state-machine context, not a decorator).
    """
    if language != "spirehdl":
        return {}
    if no_decorators:
        flags: Dict[str, bool] = {}
    elif phase == 1:
        # Phase 1 = structural exploration. No decorators in the prompt so
        # the agent doesn't reach for `@arithmetic_optimized` early and lock
        # into a mux-tree dataflow before discovering bigger structural
        # rewrites (operand-gating, shared multi-input adders, sub-as-add via
        # two's complement, etc.). Empirically: with phase-1 decorators on,
        # case7 lands at ~2040 trans; without, the agent finds the gate-level
        # pattern in ~40 steps and seeds phase 2 with a much better
        # structural base. Phase 2 then layers the decorators as polish.
        flags: Dict[str, bool] = {}
    else:
        # Phase 2 = polish via decorators. The agent seeds from phase 1's
        # elite pool (already structurally good) and can now apply
        # `@arithmetic_optimized` / `@abc_optimized` / `@flowy_optimized` to
        # squeeze out the final 1-2% on top.
        flags = {"arith_autoconfig": True, "flowy_optimize": True, "abc_optimize": True}
    if fsm_optimize:
        flags["fsm_optimize"] = True
    return flags


# ---------------------------------------------------------------------------
# Best-design measurement (shared across phases / languages)
# ---------------------------------------------------------------------------
def _resolve_best_design(best_dir: Path, language: Optional[str]) -> Optional[Path]:
    """Same heuristic as run_rtl_rewriter._resolve_best_design.

    spirehdl: design.v (always, emitted by m.to_verilog_file).
    verilog:   _best_meta.json.design_file (e.g. design_v5.sv), falling back
               to design.v / design.sv.
    """
    if language == "spirehdl":
        d = best_dir / "design.v"
        return d if d.exists() else None
    meta = best_dir / "_best_meta.json"
    if meta.exists():
        try:
            name = json.loads(meta.read_text()).get("design_file")
            if name and (best_dir / name).exists():
                return best_dir / name
        except Exception:
            pass
    for n in ("design.v", "design.sv"):
        cand = best_dir / n
        if cand.exists():
            return cand
    return None


def _measure_design(design_file: Path, top_module: str) -> Dict[str, Optional[int]]:
    try:
        w = make_cost_metric("yosys_wires").evaluate(
            design_file.parent, top_module=top_module, design_file=design_file)
        c = make_cost_metric("yosys_cells").evaluate(
            design_file.parent, top_module=top_module, design_file=design_file)
        # Both wires and cells metrics now carry `transistors` as a side-stat
        # (core/cost.py); read it off whichever evaluation succeeded.
        t_stats = c.stats if c.ok else (w.stats if w.ok else {})
        t_val = t_stats.get("transistors")
        return {
            "wires": int(w.value) if w.ok else None,
            "cells": int(c.value) if c.ok else None,
            "transistors": int(t_val) if t_val is not None else None,
            "error": "" if (w.ok and c.ok) else (w.error or c.error),
        }
    except Exception as e:
        return {"wires": None, "cells": None, "transistors": None, "error": str(e)}


def _enrich_run(run: Dict[str, Any], language: str, top_module: str) -> Dict[str, Any]:
    """Annotate a multirun outcome with best_wires / best_cells / best_transistors."""
    r = dict(run)  # shallow copy
    workdir = r.get("workdir")
    best_dir = Path(workdir) / "best_design" if workdir else None
    if best_dir and best_dir.is_dir():
        design_file = _resolve_best_design(best_dir, language)
        if design_file is not None:
            meta = _measure_design(design_file, top_module)
            r["best_wires"] = meta["wires"]
            r["best_cells"] = meta["cells"]
            r["best_transistors"] = meta["transistors"]
            r["best_design_file"] = design_file.name
            r["best_design_dir"] = str(best_dir)
            if meta["error"]:
                r["best_measure_error"] = meta["error"]
            return r
    r["best_wires"] = None
    r["best_cells"] = None
    r["best_transistors"] = None
    r["best_design_file"] = None
    r["best_design_dir"] = None
    return r


def _phase_stats(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for metric in ("wires", "cells", "transistors"):
        vals = [r[f"best_{metric}"] for r in runs
                if r.get("passed") and r.get(f"best_{metric}") is not None]
        if vals:
            out[metric] = {
                "min": min(vals), "max": max(vals),
                "mean": round(mean(vals), 2), "count": len(vals),
            }
        else:
            out[metric] = {"min": None, "max": None, "mean": None, "count": 0}
    return out


def _summarize_phase(phase_runs_root: Path, language: str,
                     top_module: str) -> Dict[str, Any]:
    """Read multirun_summary.json and enrich each run with wires/cells."""
    summary_path = phase_runs_root / "multirun_summary.json"
    if not summary_path.exists():
        return {
            "multirun_summary_path": None,
            "runs": [],
            "stats": _phase_stats([]),
            "error": "no multirun_summary.json on disk",
        }
    ms = json.loads(summary_path.read_text())
    enriched = [_enrich_run(r, language, top_module) for r in ms.get("runs", [])]
    return {
        "multirun_summary_path": str(summary_path),
        "total_runs": ms.get("total_runs"),
        "global_best_cost": ms.get("global_best_cost"),
        "global_best_workdir": ms.get("global_best_workdir"),
        "total_duration_s": ms.get("total_duration_s"),
        "runs": enriched,
        "stats": _phase_stats(enriched),
    }


# ---------------------------------------------------------------------------
# Per-task worker — runs phase 1 (+ phase 2) sequentially for one (case, lang)
# ---------------------------------------------------------------------------
def _run_one(task: Dict[str, Any]) -> Dict[str, Any]:
    from core.multirun import run_multirun

    case_name = task["case_name"]
    language = task["language"]
    runs_root = Path(task["runs_root"])
    phases = task["phases"]
    fsm_optimize = task.get("fsm_optimize", False)
    no_decorators = task.get("no_decorators", False)
    bench_path = _benchmark_path(case_name, language)
    top_module = load_benchmark(bench_path).module_name

    bench_name_for_multirun = _benchmark_name(case_name, language)

    common_kwargs = dict(
        model=task["model"],
        total_runs=task["total_runs"],
        max_concurrent=task["max_concurrent"],
        max_steps=task["max_steps"],
        elite_size=task["elite_size"],
        cost_metric=task["cost_metric"],
        target_delay=task["target_delay"],
        technology=task["technology"],
        language=language,
    )

    rec: Dict[str, Any] = {
        "case_name": case_name,
        "case_id": case_name,
        "language": language,
        "benchmark_path": str(bench_path.relative_to(REPO_ROOT)),
        "module_name": top_module,
    }

    # -- Phase 1 -----------------------------------------------------------
    p1_root = runs_root / "phase1" / language / case_name
    p1_root.mkdir(parents=True, exist_ok=True)
    tag = f"{case_name:<12}/{language:<9}"
    print(f"[START phase1] {tag}", flush=True)
    try:
        run_multirun(
            benchmark_name=bench_name_for_multirun,
            runs_root=p1_root,
            **common_kwargs,
            **_phase_flags(language, 1, fsm_optimize=fsm_optimize,
                           no_decorators=no_decorators),
        )
        rec["phase1"] = _summarize_phase(p1_root, language, top_module)
        rec["phase1"]["runs_root"] = str(p1_root)
        rec["phase1"]["flags"] = _phase_flags(language, 1, fsm_optimize=fsm_optimize,
                                              no_decorators=no_decorators)
        rec["phase1"]["status"] = "ok"
    except Exception as e:
        traceback.print_exc()
        rec["phase1"] = {"status": "error", "error": str(e),
                         "runs": [], "stats": _phase_stats([]),
                         "runs_root": str(p1_root)}

    # -- Phase 2 (optional) ------------------------------------------------
    if phases >= 2 and rec["phase1"].get("status") == "ok":
        p2_root = runs_root / "phase2" / language / case_name
        p2_root.mkdir(parents=True, exist_ok=True)
        p1_summary = rec["phase1"].get("multirun_summary_path")
        print(f"[START phase2] {tag}  seed_from={p1_summary}", flush=True)
        try:
            # Phase 2 is the exploitation phase: force every agent to seed
            # from the pool (pre-populated from phase 1's summary) by pinning
            # the fresh-agent probability to 0. This reverses core.multirun's
            # default 0.5 → 0.1 schedule, which is tuned for a cold-start
            # exploration-then-exploitation run inside a single multirun
            # call — appropriate for phase 1, wasted budget for phase 2.
            run_multirun(
                benchmark_name=bench_name_for_multirun,
                runs_root=p2_root,
                seed_from=p1_summary,
                fresh_base=0.0,
                fresh_min=0.0,
                fresh_first=0,
                **common_kwargs,
                **_phase_flags(language, 2, fsm_optimize=fsm_optimize,
                               no_decorators=no_decorators),
            )
            rec["phase2"] = _summarize_phase(p2_root, language, top_module)
            rec["phase2"]["runs_root"] = str(p2_root)
            rec["phase2"]["flags"] = _phase_flags(language, 2, fsm_optimize=fsm_optimize,
                                                  no_decorators=no_decorators)
            rec["phase2"]["seed_from"] = p1_summary
            rec["phase2"]["status"] = "ok"
        except Exception as e:
            traceback.print_exc()
            rec["phase2"] = {"status": "error", "error": str(e),
                             "runs": [], "stats": _phase_stats([]),
                             "runs_root": str(p2_root)}
    elif phases >= 2:
        rec["phase2"] = {"status": "skipped",
                         "error": "phase1 failed; phase2 skipped",
                         "runs": [], "stats": _phase_stats([])}

    dur = round(time.time(), 2)
    p1_stats = rec["phase1"]["stats"]
    p2_stats = rec.get("phase2", {}).get("stats", _phase_stats([]))
    print(f"[DONE] {tag}  "
          f"p1 cells min/mean={p1_stats['cells']['min']}/{p1_stats['cells']['mean']}  "
          f"p2 cells min/mean={p2_stats['cells']['min']}/{p2_stats['cells']['mean']}",
          flush=True)
    return rec


# ---------------------------------------------------------------------------
# Backfill (same idea as run_rtl_rewriter.py: re-read disk without re-running)
# ---------------------------------------------------------------------------
def backfill_summary(summary_path: Path) -> int:
    summary = json.loads(summary_path.read_text())
    # Re-load baselines (stale whenever the core.cost measurement changes).
    baselines = _load_baselines()
    healed = 0
    for case_id, per_lang in summary.get("results", {}).items():
        for language, rec in per_lang.items():
            bench_path = REPO_ROOT / rec["benchmark_path"]
            try:
                top_module = load_benchmark(bench_path).module_name
            except Exception:
                top_module = rec.get("module_name") or case_id
            rec["module_name"] = top_module
            base = baselines.get(language, {}).get(case_id, {})
            if base:
                rec["baseline_wires"] = base.get("wires")
                rec["baseline_cells"] = base.get("cells")
                rec["baseline_transistors"] = base.get("transistors")
            for phase_key in ("phase1", "phase2"):
                phase = rec.get(phase_key)
                if not phase or not phase.get("runs_root"):
                    continue
                refreshed = _summarize_phase(
                    Path(phase["runs_root"]), language, top_module)
                refreshed["runs_root"] = phase["runs_root"]
                refreshed["flags"] = phase.get("flags", _phase_flags(language,
                    1 if phase_key == "phase1" else 2))
                if "seed_from" in phase:
                    refreshed["seed_from"] = phase["seed_from"]
                refreshed["status"] = phase.get("status", "ok")
                rec[phase_key] = refreshed
                if refreshed["stats"]["cells"]["min"] is not None:
                    healed += 1
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return healed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_cases(arg: Optional[List[str]]) -> List[str]:
    if not arg:
        return list(AVAILABLE_CASES)
    bad = [c for c in arg if c not in AVAILABLE_CASES]
    if bad:
        raise SystemExit(f"Unknown case name(s): {bad}. "
                        f"Available: {AVAILABLE_CASES}")
    # Preserve canonical AVAILABLE_CASES order rather than alphabetical.
    return [c for c in AVAILABLE_CASES if c in set(arg)]


def main():
    parser = argparse.ArgumentParser(
        description="Two-phase, multi-run agent pipeline on DR-RTL benchmarks",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--cases", type=str, nargs="+", default=None,
                        help=f"Subset of {AVAILABLE_CASES}; omit to run all.")
    parser.add_argument("--languages", nargs="+", default=LANGUAGES,
                        choices=LANGUAGES)
    parser.add_argument("--phases", type=int, default=2, choices=[1, 2],
                        help="1 = single multirun phase, 2 = two phases "
                             "(phase 2 seeds from phase 1)")
    parser.add_argument("--model", default="claude:claude-opus-4-6")
    parser.add_argument("--cost-metric", default="yosys_cells",
                        choices=sorted(COST_METRICS))
    parser.add_argument("--technology", default="asap7",
                        choices=["asap7", "nangate45"],
                        help="Process technology for PPA cost metrics (delay, "
                             "area, power, area_delay_product). Ignored for "
                             "yosys_* / sky130_* / transistors metrics.")
    parser.add_argument("--target-delay", type=float, default=500.0,
                        help="Synthesis timing constraint in ps for PPA cost "
                             "metrics. The DR-RTL paper uses 100 ps under "
                             "Nangate45; the codebase default is 500 ps under "
                             "ASAP7.")
    parser.add_argument("--total-runs", type=int, default=6,
                        help="Agents per phase (passed to run_multirun)")
    parser.add_argument("--max-concurrent", type=int, default=2,
                        help="Parallel agents INSIDE each run_multirun call")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--elite-size", type=int, default=5,
                        help="Elite pool size per run_multirun call")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel OUTER workers (case × language pairs)")
    parser.add_argument("--runs-root", default=None,
                        help="Output root (default: runs/dr_rtl_multirun_<ts>)")
    parser.add_argument("--summary-out", default=None,
                        help="Summary JSON path (default: <runs-root>/summary.json)")
    parser.add_argument("--backfill", type=Path, default=None,
                        help="Re-read each phase's multirun_summary.json and "
                             "rewrite the given summary in place.")
    parser.add_argument("--fsm-optimize", action="store_true",
                        help="Include the spirehdl FSM / state-encoding "
                             "optimization README (optimized_fsm / "
                             "optimized_encoding) in the spirehdl system "
                             "prompt for both phases.")
    parser.add_argument("--no-decorators", action="store_true",
                        help="Suppress all spirehdl decorator-related prompt "
                             "flags (arith_autoconfig, flowy_optimize, "
                             "abc_optimize) for both phases. Use to isolate "
                             "whether the agent's decorator-leaning behavior "
                             "is the cause of structural-rewrite gaps vs "
                             "verilog. --fsm-optimize is still honored.")
    args = parser.parse_args()

    if args.backfill is not None:
        if not args.backfill.exists():
            raise SystemExit(f"Summary not found: {args.backfill}")
        healed = backfill_summary(args.backfill)
        print(f"Healed {healed} phase-records in {args.backfill}")
        print(f"Render a table with: "
              f"python experiments/table_dr_rtl_multirun.py {args.backfill}")
        return

    cases = _parse_cases(args.cases)
    languages = sorted(set(args.languages))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    runs_root = (Path(args.runs_root) if args.runs_root
                 else REPO_ROOT / "runs" / f"dr_rtl_multirun_{ts}").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    summary_path = Path(args.summary_out) if args.summary_out else runs_root / "summary.json"

    tasks = [
        {
            "case_name": c, "language": lang,
            "phases": args.phases,
            "model": args.model,
            "cost_metric": args.cost_metric,
            "target_delay": args.target_delay,
            "technology": args.technology,
            "total_runs": args.total_runs,
            "max_concurrent": args.max_concurrent,
            "max_steps": args.max_steps,
            "elite_size": args.elite_size,
            "runs_root": str(runs_root),
            "fsm_optimize": args.fsm_optimize,
            "no_decorators": args.no_decorators,
        }
        for c in cases for lang in languages
    ]

    print(f"Running {len(tasks)} (case × language) tasks  "
          f"(cases={cases}, languages={languages}, phases={args.phases})")
    print(f"Model:          {args.model}")
    print(f"Cost:           {args.cost_metric}  max_steps={args.max_steps}")
    print(f"PPA:            technology={args.technology}  target_delay={args.target_delay} ps "
          f"(used only for PPA cost metrics)")
    print(f"Per-phase runs: {args.total_runs}  "
          f"max_concurrent={args.max_concurrent}  elite={args.elite_size}")
    print(f"Outer workers:  {args.workers}")
    print(f"Runs root:      {runs_root}")
    print()

    grand_start = time.time()
    results: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run_one, t): t for t in tasks}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"[ERROR] {t['case_name']}/{t['language']}: {e}", flush=True)
                results.append({
                    "case_name": t["case_name"],
                    "case_id": t["case_name"],
                    "language": t["language"],
                    "status": "error",
                    "error": str(e),
                })

    duration = time.time() - grand_start

    # Reshape: {case_id: {language: rec}}
    by_case: Dict[str, Dict[str, Any]] = {}
    for rec in results:
        by_case.setdefault(rec["case_id"], {})[rec["language"]] = rec

    # Attach baseline numbers to every record for downstream deltas.
    baselines = _load_baselines()
    for case_id, per_lang in by_case.items():
        for lang, rec in per_lang.items():
            base = baselines.get(lang, {}).get(case_id, {})
            rec["baseline_wires"] = base.get("wires")
            rec["baseline_cells"] = base.get("cells")
            rec["baseline_transistors"] = base.get("transistors")

    summary = {
        "timestamp": ts,
        "model": args.model,
        "cost_metric": args.cost_metric,
        "technology": args.technology,
        "target_delay": args.target_delay,
        "phases": args.phases,
        "total_runs_per_phase": args.total_runs,
        "max_concurrent": args.max_concurrent,
        "max_steps": args.max_steps,
        "elite_size": args.elite_size,
        "outer_workers": args.workers,
        "cases": cases,
        "languages": languages,
        "phase_flags": {
            "phase1": {lang: _phase_flags(lang, 1, fsm_optimize=args.fsm_optimize,
                                          no_decorators=args.no_decorators)
                       for lang in LANGUAGES},
            "phase2": {lang: _phase_flags(lang, 2, fsm_optimize=args.fsm_optimize,
                                          no_decorators=args.no_decorators)
                       for lang in LANGUAGES},
        },
        "phase_exploration": {
            # Phase-1 uses core.multirun's default fresh schedule
            # (0.5 → 0.1, half-explore / half-exploit). Phase-2 overrides
            # with fresh=0 so every agent seeds from phase-1's elite pool.
            "phase1": {"fresh_base": 0.5, "fresh_min": 0.1, "fresh_first": 0},
            "phase2": {"fresh_base": 0.0, "fresh_min": 0.0, "fresh_first": 0},
        },
        "total_duration_s": round(duration, 2),
        "runs_root": str(runs_root),
        "results": by_case,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print()
    print(f"All {len(tasks)} tasks done in {duration/60:.1f} min")
    print(f"Summary: {summary_path}")
    print(f"Render a table with: "
          f"python experiments/table_dr_rtl_multirun.py {summary_path}")


if __name__ == "__main__":
    main()

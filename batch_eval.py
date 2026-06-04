#!/usr/bin/env python3
"""Batch PPA evaluation on a directory of designs.

Evaluates each design_NNN/ at the target_delay from the manifest entry
(or a global --target-delay override). Outputs results in standard format.

Usage:
    # Use per-entry target_delay from manifest
    python batch_eval.py pareto_fronts/fpmul_sweep_flowy/ \
        --benchmark benchmarks/fpmul_f16

    # Override with global target delays
    python batch_eval.py pareto_fronts/fpmul_sweep_flowy/ \
        --benchmark benchmarks/fpmul_f16 \
        --target-delay 800 1800

    # Evaluate un-optimized designs (no Flowy)
    python batch_eval.py pareto_fronts/fpmul_sweep/ \
        --benchmark benchmarks/fpmul_f16
"""

import argparse
import json
import re
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def _eval_single(design_dir: Path, design_file_name: str, td: float,
                 eval_top: str | None, entry: dict | None) -> dict:
    """Evaluate a single design file at a single target delay (worker function).

    When running in parallel, copies the design to a temp directory to avoid
    workers overwriting each other's compilation artifacts.
    """
    import tempfile

    from core.cost import make_cost_metric
    from core.evaluation import evaluate

    name = design_dir.name
    label = f"{name}/{design_file_name}"
    cost_metric = make_cost_metric("area", target_delay=td)

    # Use a temp dir to isolate parallel workers
    tmpdir = tempfile.mkdtemp(prefix="batch_eval_")
    work_dir = Path(tmpdir)
    try:
        # Copy design file + testbench to temp dir
        shutil.copy2(design_dir / design_file_name, work_dir / design_file_name)
        for aux in ("tb.sv", "vectors.dat"):
            src = design_dir / aux
            if src.exists():
                shutil.copy2(src, work_dir / aux)

        eval_result = evaluate(
            workdir=work_dir,
            cost_metric=cost_metric,
            design_top_module=eval_top,
            language="verilog",
            design_file=design_file_name,
        )
        ppa = {
            "area": eval_result.cost.stats.get("area") if eval_result.cost.ok else None,
            "delay": eval_result.cost.stats.get("delay") if eval_result.cost.ok else None,
            "power": eval_result.cost.stats.get("power") if eval_result.cost.ok else None,
        }
        passed = eval_result.correctness.passed
        result_entry = {
            "design": name,
            "design_file": design_file_name,
            "target_delay": td,
            "status": "ok",
            "passed": passed,
            "area": ppa["area"],
            "delay": ppa["delay"],
            "power": ppa["power"],
            "metrics": ppa,
        }
        if entry:
            result_entry["original_area"] = entry.get("original_area", entry.get("area"))
            result_entry["original_delay"] = entry.get("original_delay", entry.get("delay"))
        status_str = "PASS" if passed else "FAIL"
        print(f"  {label} td={td:.0f}: {status_str} area={ppa['area']} delay={ppa['delay']}")
        return result_entry
    except Exception as e:
        print(f"  {label} td={td:.0f}: ERROR {e}")
        return {"design": name, "design_file": design_file_name,
                "target_delay": td, "status": "eval_error", "error": str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Batch PPA evaluation on design directories")
    parser.add_argument("design_dir", type=Path,
                        help="Directory with design_NNN/ subdirs and optionally "
                             "pareto_front.json or flowy_optimize_results.json")
    parser.add_argument("--benchmark", type=Path, required=True,
                        help="Benchmark directory (for testbench)")
    parser.add_argument("--target-delay", nargs="+", type=float, default=None,
                        help="Target delay(s) in ps. If omitted, uses target_delay "
                             "from each entry in the manifest.")
    parser.add_argument("--manifest", type=str, default=None,
                        help="Manifest JSON filename (default: auto-detect)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel evaluation workers (default: 1)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output JSON path (default: <design_dir>/batch_eval_results.json)")
    args = parser.parse_args()

    design_root = args.design_dir
    output_path = args.output or design_root / "batch_eval_results.json"

    # Load manifest
    manifest = []
    for name in (args.manifest, "pareto_front.json", "flowy_optimize_results.json",
                 "batch_flowy_results.json", "multirun_results.json"):
        if name is None:
            continue
        p = design_root / name
        if p.exists():
            manifest = json.loads(p.read_text())
            print(f"Loaded manifest: {p} ({len(manifest)} entries)")
            break

    # Find design dirs
    design_dirs = sorted(design_root.glob("design_*"))
    if not design_dirs:
        print(f"No design_NNN/ dirs in {design_root}")
        sys.exit(1)

    # Detect expected module name from testbench
    eval_top = None
    tb_path = args.benchmark / "tb.sv"
    if tb_path.exists():
        tb_match = re.search(r'(\w+)\s+dut\s*\(', tb_path.read_text())
        if tb_match:
            eval_top = tb_match.group(1)

    from core.cost import make_cost_metric
    from core.evaluation import evaluate

    global_tds = args.target_delay
    td_desc = str(global_tds) if global_tds else "per-entry"
    print(f"Batch evaluation: {len(design_dirs)} design dirs")
    print(f"  Benchmark: {args.benchmark}")
    print(f"  Target delays: {td_desc}")
    print(f"  Top module: {eval_top}")
    print()

    # Collect all eval jobs (prepare files first, then run evals)
    jobs = []  # list of (design_dir, design_file_name, td, entry)

    for design_dir in design_dirs:
        name = design_dir.name

        # Find manifest entry
        entry = next((e for e in manifest
                       if e.get("design") == name
                       or e.get("extracted_file", "").startswith(name + "/")), None)

        # Fall back to per-design metrics.json (from batch_flowy_multirun)
        if entry is None:
            per_design_metrics = design_dir / "metrics.json"
            if per_design_metrics.exists():
                entry = json.loads(per_design_metrics.read_text())

        # Find design files (single .v or multiple run_*.v)
        v_files = sorted(design_dir.glob("*.v"))
        # Exclude testbench
        v_files = [f for f in v_files if f.name not in ("tb.sv", "tb.v")]
        if not v_files:
            print(f"  {name}: no .v files, skipping")
            continue

        # Determine target delays for this entry
        if global_tds:
            tds = global_tds
        elif entry and entry.get("target_delay") is not None:
            tds = [float(entry["target_delay"])]
        else:
            tds = [500.0]  # fallback

        # Fix module names in all Verilog files to match testbench
        if eval_top:
            for vf in v_files:
                v_text = vf.read_text()
                v_match = re.search(r'module\s+(\w+)', v_text)
                if v_match and v_match.group(1) != eval_top:
                    v_text = re.sub(r'module\s+\w+', f'module {eval_top}', v_text, count=1)
                    vf.write_text(v_text)

        # Copy testbench if not present
        for src_name in ("tb.sv", "vectors.dat"):
            src = args.benchmark / src_name
            dst = design_dir / src_name
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

        for design_file in v_files:
            for td in tds:
                jobs.append((design_dir, design_file.name, td, entry))

    print(f"  Total eval jobs: {len(jobs)}, workers: {args.workers}")
    print()

    results = []
    if args.workers <= 1:
        for design_dir, df_name, td, entry in jobs:
            results.append(_eval_single(design_dir, df_name, td, eval_top, entry))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(_eval_single, dd, df, td, eval_top, entry): (dd, df, td)
                for dd, df, td, entry in jobs
            }
            for future in as_completed(futures):
                results.append(future.result())

    # Save results
    output_path.write_text(json.dumps(results, indent=2))
    n_ok = sum(1 for r in results if r.get("status") == "ok" and r.get("passed"))
    print(f"\nDone: {n_ok}/{len(results)} passed. Results: {output_path}")


if __name__ == "__main__":
    main()

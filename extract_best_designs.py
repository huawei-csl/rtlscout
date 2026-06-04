#!/usr/bin/env python3
"""Extract the N best passing designs from a run directory.

Works with both multistage and run_benchmark directory layouts.
Scans all eval_*/result.json files, filters to passing evals,
sorts by cost, and copies the top N design files + a summary JSON
into the output folder.

Usage:
    python extract_best_designs.py runs/multistage_20260316_143944 -n 5 -o best_5/
    python extract_best_designs.py runs/mult8 -n 3 -o best_mult8/
    python extract_best_designs.py runs/multistage_... -n 5 --sort-by delay
"""

import argparse
import json
import shutil
from pathlib import Path


def find_passing_evals(run_dir: Path) -> list[dict]:
    """Find all passing eval results under run_dir."""
    results = []
    for result_path in run_dir.rglob("eval_*/result.json"):
        with open(result_path) as f:
            data = json.load(f)
        if not data.get("passed"):
            continue
        cost = data.get("cost_value")
        if cost is None:
            continue
        workspace = result_path.parent / "workspace"
        design_file = data.get("design_file")
        if design_file and (workspace / design_file).exists():
            design_path = workspace / design_file
        else:
            # fallback: look for design.v or design.py
            for name in ("design.v", "design.py"):
                if (workspace / name).exists():
                    design_path = workspace / name
                    break
            else:
                continue
        results.append({
            "cost_value": cost,
            "cost_metric": data.get("cost_metric"),
            "metrics": data.get("metrics") or {},
            "pass_rate": data.get("pass_rate"),
            "eval_index": data.get("eval_index"),
            "design_file": data.get("design_file"),
            "target_delay": data.get("target_delay"),
            "original_result_json": str(result_path),
            "original_workspace": str(workspace),
            "_design_path": design_path,
        })
    return results


def _sort_key(entry: dict, sort_by: str):
    """Return the value to sort by.

    ``cost`` uses the ``cost_value`` field; any other key is looked up in
    the flat ``metrics`` dict.
    """
    if sort_by == "cost":
        return entry["cost_value"]
    metrics = entry.get("metrics") or {}
    val = metrics.get(sort_by)
    if val is None:
        return float("inf")
    return val


def extract(run_dir: Path, output_dir: Path, n: int, sort_by: str = "cost") -> None:
    evals = find_passing_evals(run_dir)
    if not evals:
        print("No passing evaluations found.")
        return

    evals.sort(key=lambda e: _sort_key(e, sort_by))
    top = evals[:n]

    output_dir.mkdir(parents=True, exist_ok=True)

    # Track used filenames to avoid collisions
    used_names: dict[str, int] = {}
    manifest = []

    for entry in top:
        src: Path = entry.pop("_design_path")
        stem = src.stem
        suffix = src.suffix

        # Deduplicate filename
        if stem + suffix in used_names:
            used_names[stem + suffix] += 1
            out_name = f"{stem}_{used_names[stem + suffix]}{suffix}"
        else:
            used_names[stem + suffix] = 0
            out_name = stem + suffix

        shutil.copy2(src, output_dir / out_name)
        entry["extracted_file"] = out_name
        manifest.append(entry)

    manifest_path = output_dir / "best_designs.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Extracted {len(manifest)} designs to {output_dir}/")
    for i, e in enumerate(manifest, 1):
        val = _sort_key(e, sort_by)
        print(f"  {i}. {e['extracted_file']}  {sort_by}={val} (cost={e['cost_value']} {e['cost_metric']})")
    print(f"Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract the N best passing designs from a run directory.")
    parser.add_argument("run_dir", type=Path,
                        help="Root of a multistage or benchmark run")
    parser.add_argument("-n", "--top", type=int, default=5,
                        help="Number of best designs to extract (default: 5)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output directory (default: <run_dir>/best_extracted)")
    parser.add_argument("--sort-by", default="cost",
                        help="Metric key to sort by. 'cost' (default) uses "
                             "cost_value; any other value is looked up in the "
                             "flat per-eval metrics dict (e.g. area, delay, "
                             "power, size, depth, wires, cells, transistors).")
    args = parser.parse_args()

    output = args.output or args.run_dir / "best_extracted"
    extract(args.run_dir, output, args.top, sort_by=args.sort_by)


if __name__ == "__main__":
    main()

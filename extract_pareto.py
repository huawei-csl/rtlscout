#!/usr/bin/env python3
"""Extract designs on the Pareto front over a pair of dimensions.

Works with both multirun and run_benchmark directory layouts.  Scans
``eval_*/result.json`` files, filters to passing evals that have both
chosen dimensions, computes the Pareto front, and copies the
Pareto-optimal design files + a summary JSON into the output folder.

Any two numeric keys from the per-eval ``metrics`` dict can be selected
as Pareto dimensions (both minimized).  Typical choices:
  * ``area``, ``delay``, ``power`` — from PPA-backed metrics (``delay``,
    ``area_delay_product``, ``sky130_adp``, …).
  * ``size``, ``depth`` — from AIG-based metrics (``aig_count``,
    ``aig_depth``, ``aig_count_resyn2``, ``aig_count_deepsyn``, …).
  * ``wires``, ``cells``, ``transistors`` — from yosys-backed metrics.

Pareto front determination
--------------------------
A design D is on the Pareto front if no other design is strictly better
in both objectives simultaneously. Formally, D is Pareto-optimal iff
there is no other design D' such that:

    D'.x <= D.x  AND  D'.y <= D.y

with at least one of the two inequalities being strict (<).

Equivalently: sort all designs by x ascending. Walk through them and
keep a running minimum y seen so far. A design is on the front iff
its y is <= that running minimum (i.e. no previous design with
smaller-or-equal x also had smaller-or-equal y). This gives an
O(n log n) algorithm.

Usage:
    python extract_pareto.py runs/multirun_20260316_143944 -o pareto_front/
    python extract_pareto.py runs/mult8 -o pareto_mult8/
    python extract_pareto.py runs/mult8 --dims size,depth -o pareto_aig/
"""

import argparse
import ast
import json
import shutil
from pathlib import Path


def _uses_flowy(design_path: Path) -> bool:
    """Check if a design uses @flowy_optimized (decorator in source or cache on disk)."""
    workspace = design_path.parent
    if (workspace / ".spirehdl_cache").is_dir():
        return True
    if design_path.suffix == ".py":
        try:
            text = design_path.read_text()
            if "flowy_optimized" in text:
                return True
        except OSError:
            pass
    return False


def _find_local_deps(py_file: Path, workspace: Path) -> list[Path]:
    """Recursively find local .py dependencies via AST import tracing.

    Returns a list of .py files in *workspace* that *py_file* transitively
    imports (excluding the file itself).  Only local imports are followed —
    anything that doesn't resolve to a .py file in the workspace is skipped.
    """
    seen: set[Path] = set()
    queue = [py_file.resolve()]

    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            tree = ast.parse(current.read_text(), filename=str(current))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules = [node.module]
            for mod in modules:
                # Convert dotted module name to a relative path
                rel = mod.replace(".", "/") + ".py"
                candidate = workspace / rel
                if candidate.is_file() and candidate.resolve() not in seen:
                    queue.append(candidate.resolve())

    seen.discard(py_file.resolve())
    return [p for p in seen if p.is_file()]


def find_passing_evals(run_dir: Path, no_flowy: bool = False,
                       benchmark: str | None = None,
                       dim_x: str = "area", dim_y: str = "delay") -> list[dict]:
    """Find all passing eval results with both *dim_x* and *dim_y* under run_dir."""
    results = []
    for result_path in run_dir.rglob("eval_*/result.json"):
        if benchmark and f"/{benchmark}/" not in str(result_path):
            continue
        with open(result_path) as f:
            data = json.load(f)
        if not data.get("passed"):
            continue
        metrics = data.get("metrics") or {}
        vx = metrics.get(dim_x)
        vy = metrics.get(dim_y)
        if vx is None or vy is None:
            continue
        workspace = result_path.parent / "workspace"
        design_file = data.get("design_file")
        if design_file and (workspace / design_file).exists():
            design_path = workspace / design_file
        else:
            for name in ("design.v", "design.py"):
                if (workspace / name).exists():
                    design_path = workspace / name
                    break
            else:
                continue
        if no_flowy and _uses_flowy(design_path):
            continue
        entry = {
            dim_x: vx,
            dim_y: vy,
            "cost_value": data.get("cost_value"),
            "cost_metric": data.get("cost_metric"),
            "metrics": metrics,
            "pass_rate": data.get("pass_rate"),
            "eval_index": data.get("eval_index"),
            "design_file": data.get("design_file"),
            "target_delay": data.get("target_delay"),
            "original_result_json": str(result_path),
            "original_workspace": str(workspace),
            "_design_path": design_path,
        }
        results.append(entry)
    return results


def pareto_front(evals: list[dict], dim_x: str = "area",
                 dim_y: str = "delay") -> list[dict]:
    """Return the subset of evals on the *dim_x*-vs-*dim_y* Pareto front.

    Both dimensions are minimized.

    Algorithm:
      1. Sort by dim_x ascending (tie-break by dim_y ascending).
      2. Walk through the sorted list. A design is Pareto-optimal iff its
         dim_y is strictly less than the best dim_y seen so far (i.e. no
         earlier design — which has dim_x <= this one — also had dim_y <= this
         one's). The first design is always on the front.
    """
    if not evals:
        return []
    evals_sorted = sorted(evals, key=lambda e: (e[dim_x], e[dim_y]))
    front = []
    best_y = float("inf")
    for e in evals_sorted:
        if e[dim_y] < best_y:
            front.append(e)
            best_y = e[dim_y]
    return front


def _normalized_score(entries: list[dict], dim_x: str = "area",
                      dim_y: str = "delay") -> list[float]:
    """Combined normalized score: dim_x/mean(dim_x) + dim_y/mean(dim_y).

    Lower is better. Same scoring as align_pareto.py.
    """
    n = len(entries)
    if n == 0:
        return []
    mean_x = sum(e[dim_x] for e in entries) / n
    mean_y = sum(e[dim_y] for e in entries) / n
    return [e[dim_x] / mean_x + e[dim_y] / mean_y for e in entries]


def _select_top_n(evals: list[dict], front: list[dict], n: int,
                  dim_x: str = "area", dim_y: str = "delay") -> list[dict]:
    """Select up to n designs: all Pareto points first, then best-scored non-Pareto.

    Pareto-optimal designs are always included. If n > len(front), the remaining
    slots are filled from non-Pareto evals with the lowest normalized score.
    Pareto extremes (min dim_x, min dim_y) are pinned.
    """
    if n >= len(evals):
        front_set = {id(e) for e in front}
        non_front = [e for e in evals if id(e) not in front_set]
        scores = _normalized_score(non_front, dim_x, dim_y)
        ranked = sorted(zip(scores, non_front), key=lambda x: x[0])
        return list(front) + [e for _, e in ranked]

    if n <= len(front):
        if n <= 0:
            return []
        min_x_idx = min(range(len(front)), key=lambda i: front[i][dim_x])
        min_y_idx = min(range(len(front)), key=lambda i: front[i][dim_y])
        pinned = {min_x_idx, min_y_idx}
        scores = _normalized_score(front, dim_x, dim_y)
        candidates = sorted(
            ((scores[i], i) for i in range(len(front)) if i not in pinned),
            key=lambda x: x[0],
        )
        remaining = n - len(pinned)
        chosen = pinned | {i for _, i in candidates[:max(0, remaining)]}
        return [front[i] for i in sorted(chosen)]

    selected = list(front)
    front_set = {id(e) for e in front}
    non_front = [e for e in evals if id(e) not in front_set]
    scores = _normalized_score(non_front, dim_x, dim_y)
    ranked = sorted(zip(scores, non_front), key=lambda x: x[0])
    remaining = n - len(selected)
    selected.extend(e for _, e in ranked[:remaining])
    return selected


def extract(run_dirs: list[Path] | Path, output_dir: Path, separate_dirs: bool = False,
            no_flowy: bool = False, benchmark: str | None = None,
            max_points: int | None = None,
            dim_x: str = "area", dim_y: str = "delay") -> None:
    if isinstance(run_dirs, Path):
        run_dirs = [run_dirs]
    evals = []
    for d in run_dirs:
        evals.extend(find_passing_evals(d, no_flowy=no_flowy, benchmark=benchmark,
                                        dim_x=dim_x, dim_y=dim_y))
    if not evals:
        print(f"No passing evaluations with both {dim_x} and {dim_y} found.")
        return

    front = pareto_front(evals, dim_x=dim_x, dim_y=dim_y)

    if max_points is not None:
        selected = _select_top_n(evals, front, max_points, dim_x=dim_x, dim_y=dim_y)
        n_pareto = min(len(front), max_points)
        n_extra = len(selected) - n_pareto
        if n_extra > 0:
            print(f"Selected {len(selected)} designs: {n_pareto} Pareto + {n_extra} best-scored non-Pareto")
    else:
        selected = front

    output_dir.mkdir(parents=True, exist_ok=True)

    used_names: dict[str, int] = {}
    manifest = []

    # Sort by dim_x for readable output
    selected.sort(key=lambda e: e[dim_x])

    for idx, entry in enumerate(selected):
        src: Path = entry.pop("_design_path")
        workspace: Path = src.parent
        stem = src.stem
        suffix = src.suffix

        if stem + suffix in used_names:
            used_names[stem + suffix] += 1
            out_name = f"{stem}_{used_names[stem + suffix]}{suffix}"
        else:
            used_names[stem + suffix] = 0
            out_name = stem + suffix

        if separate_dirs:
            dest_dir = output_dir / f"design_{idx:03d}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / out_name)
            # Copy local .py dependencies (found via AST import tracing)
            if src.suffix == ".py":
                for dep in _find_local_deps(src, workspace):
                    dep_name = dep.name
                    if not (dest_dir / dep_name).exists():
                        shutil.copy2(dep, dest_dir / dep_name)
            # Copy .spirehdl_cache if present
            cache_dir = workspace / ".spirehdl_cache"
            if cache_dir.is_dir():
                shutil.copytree(cache_dir, dest_dir / ".spirehdl_cache", dirs_exist_ok=True)
            entry["extracted_file"] = f"design_{idx:03d}/{out_name}"
        else:
            shutil.copy2(src, output_dir / out_name)
            # Copy local .py dependencies to the same flat directory
            if src.suffix == ".py":
                for dep in _find_local_deps(src, workspace):
                    dep_name = dep.name
                    if not (output_dir / dep_name).exists():
                        shutil.copy2(dep, output_dir / dep_name)
            entry["extracted_file"] = out_name

        manifest.append(entry)

    manifest_path = output_dir / "pareto_front.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    n_pareto_in_output = sum(1 for e in manifest if any(
        e[dim_x] == f[dim_x] and e[dim_y] == f[dim_y] for f in front
    ))
    extra_label = f" ({n_pareto_in_output} Pareto + {len(manifest) - n_pareto_in_output} non-Pareto)" if len(manifest) > n_pareto_in_output else ""
    print(f"Extracted: {len(manifest)} designs{extra_label} (from {len(evals)} passing evals)")
    print(f"Extracted to {output_dir}/")
    for i, e in enumerate(manifest, 1):
        print(f"  {i}. {e['extracted_file']}  {dim_x}={e[dim_x]}  {dim_y}={e[dim_y]}")
    print(f"Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract Pareto-optimal designs over a pair of dimensions.")
    parser.add_argument("run_dirs", nargs="+", type=Path,
                        help="Root(s) of multirun or benchmark runs (multiple dirs are aggregated)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output directory (default: <first_run_dir>/pareto_front)")
    parser.add_argument("--separate-dirs", action="store_true",
                        help="Put each design in its own subdirectory and copy "
                             ".spirehdl_cache alongside it")
    parser.add_argument("--no-flowy", action="store_true",
                        help="Exclude designs that use @flowy_optimized "
                             "(detected by decorator in source or .spirehdl_cache)")
    parser.add_argument("--benchmark", default=None,
                        help="Only include evals from this benchmark (e.g. fpmul_f16)")
    parser.add_argument("--dims", default="area,delay",
                        help="Comma-separated Pareto dimension pair "
                             "(default: area,delay). Any two keys present in "
                             "the per-eval `metrics` dict are accepted — "
                             "typical choices: area, delay, power, size, "
                             "depth, wires, cells, transistors.")
    parser.add_argument("-n", "--max-points", type=int, default=None,
                        help="Maximum number of designs to extract. Pareto-optimal "
                             "designs are always included first; remaining slots are "
                             "filled by best normalized score "
                             "(dim_x/mean + dim_y/mean)")
    args = parser.parse_args()

    parts = [p.strip() for p in args.dims.split(",")]
    if len(parts) != 2 or any(not p for p in parts):
        parser.error(
            f"--dims must be two comma-separated keys, got {args.dims!r}"
        )
    dim_x, dim_y = parts

    output = args.output or args.run_dirs[0] / "pareto_front"
    extract(args.run_dirs, output, separate_dirs=args.separate_dirs,
            no_flowy=args.no_flowy, benchmark=args.benchmark,
            max_points=args.max_points, dim_x=dim_x, dim_y=dim_y)


if __name__ == "__main__":
    main()

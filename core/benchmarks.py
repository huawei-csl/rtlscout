"""Benchmark loading utilities."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Benchmark:
    name: str
    root: Path
    description: str
    testbench: Path
    module_name: str
    context_dir: Optional[Path] = None


def load_benchmark(benchmark_root: Path) -> Benchmark:
    description = (benchmark_root / "description.txt").read_text().strip()
    testbench = benchmark_root / "tb.sv"
    metadata = json.loads((benchmark_root / "metadata.json").read_text())
    context_dir = benchmark_root / "context"
    return Benchmark(
        name=metadata["name"],
        root=benchmark_root,
        description=description,
        testbench=testbench,
        module_name=metadata.get("module_name", metadata["name"]),
        context_dir=context_dir if context_dir.is_dir() else None,
    )


def discover_benchmarks(benchmarks_root: Path) -> List[Path]:
    """Find all benchmark directories under *benchmarks_root*, at any depth.

    A directory is a benchmark if it contains description.txt, metadata.json,
    and tb.sv.  Supports nested grouping (e.g. ``benchmarks/fp/fpmul_f16/``).

    Paths whose path-segments start with ``_`` are skipped — convention for
    auxiliary directories (e.g. ``_debug/`` artifacts, ``_scratch/``) that
    live inside a benchmark dir but are not themselves benchmarks.
    """
    def _has_underscore_segment(p: Path) -> bool:
        return any(part.startswith("_") for part in p.relative_to(benchmarks_root).parts)

    return sorted(
        p.parent for p in benchmarks_root.rglob("metadata.json")
        if (p.parent / "description.txt").exists()
        and (p.parent / "tb.sv").exists()
        and not _has_underscore_segment(p.parent)
    )


def load_benchmarks(
    benchmarks_root: Path,
    benchmark_names: Optional[List[str]] = None,
) -> List[Benchmark]:
    available = [load_benchmark(p) for p in discover_benchmarks(benchmarks_root)]
    if not benchmark_names:
        return available

    # Build lookup dicts: relative path > leaf dir name > metadata name.
    by_rel = {str(b.root.relative_to(benchmarks_root)): b for b in available}
    by_dir = {b.root.name: b for b in available}
    by_name = {b.name: b for b in available}

    selected: List[Benchmark] = []
    for name in benchmark_names:
        bench = by_rel.get(name) or by_dir.get(name) or by_name.get(name)
        if bench is None:
            known = sorted(set(by_rel) | set(by_dir) | set(by_name))
            raise ValueError(f"Unknown benchmark: {name}. Available: {', '.join(known)}")
        if bench not in selected:
            selected.append(bench)
    return selected

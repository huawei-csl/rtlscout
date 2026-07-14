"""Benchmark loading utilities."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Union

# One root or several. Every discovery/loading entry point accepts both, so callers can
# scan additional trees (e.g. a gitignored private internal/benchmarks/ checkout) in the
# same sweep as the public benchmarks/.
RootsLike = Union[str, Path, Sequence[Union[str, Path]]]


def normalize_roots(roots: RootsLike) -> List[Path]:
    """Coerce one path or a sequence of paths into a de-duplicated Path list."""
    if isinstance(roots, (str, Path)):
        roots = [roots]
    out: List[Path] = []
    for r in roots:
        p = Path(r)
        if p not in out:
            out.append(p)
    return out


@dataclass
class Benchmark:
    name: str
    root: Path
    description: str
    testbench: Path
    module_name: str
    context_dir: Optional[Path] = None
    golden_reference: Optional[Path] = None # Optional golden reference for combinational equivalence checking (CEC).
    golden_reference_language: str = "spirehdl" ## A .v/.sv used directly, or a .py compiled to Verilog


def load_benchmark(benchmark_root: Path) -> Benchmark:
    description = (benchmark_root / "description.txt").read_text().strip()
    testbench = benchmark_root / "tb.sv"
    metadata = json.loads((benchmark_root / "metadata.json").read_text())
    context_dir = benchmark_root / "context"
    gr = metadata.get("golden_reference")
    golden_reference = (benchmark_root / gr).resolve() if gr else None
    return Benchmark(
        name=metadata["name"],
        root=benchmark_root,
        description=description,
        testbench=testbench,
        module_name=metadata.get("module_name", metadata["name"]),
        context_dir=context_dir if context_dir.is_dir() else None,
        golden_reference=golden_reference,
        golden_reference_language=metadata.get("golden_reference_language", "spirehdl"),
    )


def discover_benchmarks(benchmarks_root: RootsLike) -> List[Path]:
    """Find all benchmark directories under *benchmarks_root*, at any depth.

    ``benchmarks_root`` may be a single root or a sequence of roots; the roots
    are scanned in order and the result is sorted per root. A directory is a
    benchmark if it contains description.txt, metadata.json, and tb.sv.
    Supports nested grouping (e.g. ``benchmarks/fp/fpmul_f16/``).

    Paths whose path-segments start with ``_`` are skipped — convention for
    auxiliary directories (e.g. ``_debug/`` artifacts, ``_scratch/``) that
    live inside a benchmark dir but are not themselves benchmarks.
    """
    found: List[Path] = []
    for root in normalize_roots(benchmarks_root):
        def _has_underscore_segment(p: Path) -> bool:
            return any(part.startswith("_") for part in p.relative_to(root).parts)

        found.extend(sorted(
            p.parent for p in root.rglob("metadata.json")
            if (p.parent / "description.txt").exists()
            and (p.parent / "tb.sv").exists()
            and not _has_underscore_segment(p.parent)
        ))
    return found


def load_benchmarks(
    benchmarks_root: RootsLike,
    benchmark_names: Optional[List[str]] = None,
) -> List[Benchmark]:
    roots = normalize_roots(benchmarks_root)
    available = [load_benchmark(p) for p in discover_benchmarks(roots)]
    if not benchmark_names:
        return available

    def _rel(b: Benchmark) -> str:
        for root in roots:
            try:
                return str(b.root.relative_to(root))
            except ValueError:
                continue
        return str(b.root)

    # Build lookup dicts: relative path > leaf dir name > metadata name.
    by_rel = {_rel(b): b for b in available}
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

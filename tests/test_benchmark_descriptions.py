"""Benchmark descriptions must cite context files by their path inside context/:
the provisioning step (core.runner.provision_workspace) places the contents of a
benchmark's context/ directory at the agent workspace root, subfolders kept, so
`context/starting_point.py` names a path that does not exist there (it cost every
run one wasted step before the 2026-10 sweep)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROOTS = [ROOT / "benchmarks", ROOT / "internal" / "benchmarks",
         ROOT / "internal" / "task_level" / "benchmarks"]
CONTEXT_FILE = re.compile(r"context/[A-Za-z0-9_.-]+\.(?:py|sv|v)\b")


def _descriptions():
    for root in ROOTS:
        if root.is_dir():
            yield from sorted(root.rglob("description.txt"))


def test_descriptions_cite_context_files_by_bare_name():
    offenders = [str(f.relative_to(ROOT)) for f in _descriptions() if CONTEXT_FILE.search(f.read_text())]
    assert not offenders, "descriptions citing context/<file> (workspace is flat):\n" + "\n".join(offenders)


def test_provisioning_copies_context_flat(tmp_path):
    """Pin the layout the descriptions rely on."""
    from core.benchmarks import load_benchmark
    from core.runner import provision_workspace
    bench_dir = ROOT / "benchmarks" / "fpadd_f16"
    if not (bench_dir / "context").is_dir():
        pytest.skip("fpadd_f16 benchmark with context/ not present")
    bench = load_benchmark(bench_dir)
    ws, _ = provision_workspace(bench, tmp_path, language="spirehdl", run_cec=False)
    assert (ws / "starting_point.py").exists()
    assert not (ws / "context").exists()

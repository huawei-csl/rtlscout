"""rtlscout.paths: every lookup outside the installed package (workspace root, .env, benchmark trees, cache,
spire-hdl sources). A checkout must resolve to the repository paths that were hard-wired before."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from rtlscout import paths

REPO = Path(__file__).resolve().parent.parent
VARIABLES = ("RTLSCOUT_HOME", "RTLSCOUT_ENV_FILE", "RTLSCOUT_BENCHMARKS", "RTLSCOUT_CACHE_DIR",
             "RTLSCOUT_SPIRE_HDL_DIR")


@pytest.fixture
def env(monkeypatch):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_checkout_defaults_are_the_repository_paths(env):
    assert paths.source_checkout() == REPO
    assert paths.workspace_root() == REPO
    assert paths.cache_dir() == REPO / ".cache"
    roots = paths.benchmark_roots()
    assert roots[0] == REPO / "benchmarks"
    assert set(roots) <= {REPO / "benchmarks", REPO / "internal" / "benchmarks"}    # no packaged smoke set


def test_rtlscout_home_moves_the_workspace(env, tmp_path):
    home = tmp_path.resolve()
    env.setenv("RTLSCOUT_HOME", str(home))
    assert paths.workspace_root() == home
    assert paths.benchmark_roots() == [paths.SMOKE_BENCHMARKS_ROOT]     # no tree there: the packaged smoke set only
    (home / "benchmarks").mkdir()
    assert paths.benchmark_roots() == [home / "benchmarks", paths.SMOKE_BENCHMARKS_ROOT]


def test_env_file(env, tmp_path):
    home = tmp_path.resolve()
    env.setenv("RTLSCOUT_HOME", str(home))
    (home / ".env").write_text("RTLSCOUT_TEST_KEY=from-workspace\n")
    assert paths.env_file() == home / ".env"
    other = home / "other.env"
    other.write_text("RTLSCOUT_TEST_KEY=from-explicit\n")
    env.setenv("RTLSCOUT_ENV_FILE", str(other))
    env.delenv("RTLSCOUT_TEST_KEY", raising=False)
    assert paths.load_env() == other
    assert os.environ["RTLSCOUT_TEST_KEY"] == "from-explicit"
    env.setenv("RTLSCOUT_ENV_FILE", str(home / "missing.env"))
    with pytest.raises(FileNotFoundError, match="RTLSCOUT_ENV_FILE"):
        paths.env_file()


def test_benchmark_roots_from_the_environment(env, tmp_path):
    a, b = tmp_path.resolve() / "a", tmp_path.resolve() / "b"
    a.mkdir()
    b.mkdir()
    env.setenv("RTLSCOUT_BENCHMARKS", f"{a}{os.pathsep}{b}")
    assert paths.benchmark_roots() == [a, b, paths.SMOKE_BENCHMARKS_ROOT]
    env.setenv("RTLSCOUT_BENCHMARKS", str(a / "missing"))
    with pytest.raises(FileNotFoundError, match="RTLSCOUT_BENCHMARKS"):
        paths.benchmark_roots()


def test_cache_dir_override(env, tmp_path):
    env.setenv("RTLSCOUT_CACHE_DIR", str(tmp_path))
    assert paths.cache_dir() == tmp_path.resolve()


def test_packaged_smoke_benchmark_is_a_copy_of_the_shipped_one():
    shipped, packaged = REPO / "benchmarks" / "simple_adder", paths.SMOKE_BENCHMARKS_ROOT / "simple_adder"
    assert sorted(p.name for p in packaged.iterdir()) == sorted(p.name for p in shipped.iterdir())
    for f in shipped.iterdir():
        assert (packaged / f.name).read_bytes() == f.read_bytes(), f.name


def test_packaged_smoke_benchmark_loads():
    from rtlscout.benchmarks import load_benchmarks
    [bench] = load_benchmarks([paths.SMOKE_BENCHMARKS_ROOT], ["simple_adder"])
    assert bench.name == "simple_adder" and bench.testbench.is_file()


def test_spire_hdl_root(env, tmp_path):
    tree = tmp_path.resolve() / "spire-hdl"
    (tree / "docs").mkdir(parents=True)
    env.setenv("RTLSCOUT_SPIRE_HDL_DIR", str(tree))
    assert paths.spire_hdl_root() == tree
    env.setenv("RTLSCOUT_SPIRE_HDL_DIR", str(tree / "missing"))
    with pytest.raises(FileNotFoundError, match="RTLSCOUT_SPIRE_HDL_DIR"):
        paths.spire_hdl_root()


def test_spire_sources_inside_the_package_come_first(env, tmp_path):
    """spire-hdl >= 0.4.1 ships docs/ and examples/ in the package; 0.4.0 has them only in a source tree."""
    pkg, tree = tmp_path.resolve() / "site-packages" / "spire", tmp_path.resolve() / "spire-hdl"
    (tree / "docs").mkdir(parents=True)
    (tree / "docs" / "hints.md").write_text("tree\n")
    (tree / "testing" / "examples").mkdir(parents=True)
    (tree / "testing" / "examples" / "component_example.py").write_text("tree\n")
    env.setenv("RTLSCOUT_SPIRE_HDL_DIR", str(tree))
    env.setattr(paths, "spire_package_dir", lambda: pkg)
    pkg.mkdir(parents=True)                                       # a 0.4.0-style package: sources only
    assert paths.spire_docs_dir() == tree / "docs"
    assert paths.spire_example("component_example.py", "testing/examples/component_example.py") == \
        tree / "testing" / "examples" / "component_example.py"
    (pkg / "docs").mkdir()                                        # a package that ships its docs and examples
    (pkg / "docs" / "hints.md").write_text("package\n")
    (pkg / "examples").mkdir()
    (pkg / "examples" / "component_example.py").write_text("package\n")
    assert paths.spire_docs_dir() == pkg / "docs"
    assert paths.spire_example("component_example.py", "testing/examples/component_example.py") == \
        pkg / "examples" / "component_example.py"
    env.setattr(paths, "spire_package_dir", lambda: None)
    env.delenv("RTLSCOUT_SPIRE_HDL_DIR")
    env.setenv("RTLSCOUT_HOME", str(tmp_path.resolve() / "nowhere"))
    assert paths.spire_docs_dir() is None


def test_prompts_without_the_spire_hdl_sources():
    """An install without spire-hdl's documentation still builds the Verilog prompt; the Spire prompt says why not."""
    code = (
        "import rtlscout.paths as paths\n"
        "paths.spire_hdl_root = lambda: None\n"
        "paths.spire_package_dir = lambda: None\n"
        "import rtlscout.prompts as prompts\n"
        "assert 'RTL' in prompts.build_system_prompt('an adder', 'transistors')\n"
        "try:\n"
        "    prompts.build_spirehdl_system_prompt('an adder', 'transistors')\n"
        "except FileNotFoundError as e:\n"
        "    assert 'RTLSCOUT_SPIRE_HDL_DIR' in str(e)\n"
        "else:\n"
        "    raise SystemExit('the Spire prompt was built without its sources')\n")
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

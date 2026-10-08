"""The ``core`` package is a compatibility alias of ``rtlscout`` for one release (see core/__init__.py)."""

import importlib
import subprocess
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OLD = "core"    # spelled indirectly below so tools/restructure.sh has nothing to rewrite in this file


def _import_old(name: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return importlib.import_module(f"{OLD}.{name}")


def test_alias_returns_the_same_module_object():
    import rtlscout.benchmarks
    assert _import_old("benchmarks") is rtlscout.benchmarks
    assert rtlscout.benchmarks.__spec__.name == "rtlscout.benchmarks"
    assert rtlscout.benchmarks.__name__ == "rtlscout.benchmarks"


def test_from_import_through_the_alias():
    namespace = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        exec(f"from {OLD}.benchmarks import load_benchmark", namespace)
    from rtlscout.benchmarks import load_benchmark
    assert namespace["load_benchmark"] is load_benchmark


def test_importing_the_alias_warns():
    code = (f"import warnings\nwith warnings.catch_warnings(record=True) as w:\n"
            f"    warnings.simplefilter('always')\n    import {OLD}\n"
            f"assert any(issubclass(x.category, DeprecationWarning) and 'rtlscout' in str(x.message) for x in w), w\n")
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_python_dash_m_through_the_alias():
    proc = subprocess.run([sys.executable, "-W", "ignore", "-m", f"{OLD}.benchmarks"], cwd=REPO,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

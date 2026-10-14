"""The command-line tools live in the package (``python -m rtlscout.<module>``); the root scripts are wrappers."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODULES = ["run_benchmark", "run_eval", "run_multirun", "run_pipeline", "run_sweep", "batch_eval", "extract_pareto",
           "containers"]
WRAPPERS = {name: f"{name}.py" for name in MODULES if name != "containers"} | {"containers": "rtlscout_cli.py"}


@pytest.mark.parametrize("name", MODULES)
def test_module_has_main_taking_argv(name):
    main = importlib.import_module(f"rtlscout.{name}").main
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0


@pytest.mark.parametrize("name", MODULES)
def test_runs_as_module_from_any_directory(name, tmp_path):
    proc = subprocess.run([sys.executable, "-m", f"rtlscout.{name}", "--help"], cwd=tmp_path, capture_output=True,
                          text=True, env=_env_with_repo_on_path())
    assert proc.returncode == 0 and "usage:" in proc.stdout, proc.stderr


@pytest.mark.parametrize("name", MODULES)
def test_root_wrapper_still_works(name):
    proc = subprocess.run([sys.executable, WRAPPERS[name], "--help"], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0 and "usage:" in proc.stdout, proc.stderr


def test_wrapper_reexports_what_other_scripts_import():
    sys.path.insert(0, str(REPO))
    try:
        wrapper = importlib.import_module("extract_pareto")
    finally:
        sys.path.remove(str(REPO))
    from rtlscout import extract_pareto as packaged
    for attr in ("extract", "pareto_front", "_find_local_deps", "_normalized_score", "_select_top_n"):
        assert getattr(wrapper, attr) is getattr(packaged, attr)


def _env_with_repo_on_path():
    """The package may be importable only through the checkout (tests run without `pip install -e .` too)."""
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(REPO), env.get("PYTHONPATH")) if p)
    return env

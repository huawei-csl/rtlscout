"""Unit tests for the Phase-0 agent-backend seam (core.agent_backend) and the
factored-out workspace provisioning (core.runner.provision_workspace)."""

from pathlib import Path

import pytest

from core.agent_backend import BackendRequest, RunLimits, PythonReactBackend, make_backend

BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"
SIMPLE_ADDER_ROOT = BENCHMARKS_ROOT / "simple_adder"


def test_make_backend_react_default():
    backend = make_backend("react")
    assert isinstance(backend, PythonReactBackend)
    assert backend.name == "react"


def test_make_backend_rejects_unknown():
    with pytest.raises(ValueError):
        make_backend("bogus")


def test_run_limits_defaults():
    lim = RunLimits(max_steps=20)
    assert lim.max_steps == 20
    assert lim.wall_clock_s == 0      # react is step-bounded; opencode sets a wall-clock


def test_provision_workspace_lays_down_inputs(tmp_path):
    """provision_workspace creates workdir/workspace and copies the benchmark's
    testbench (the integrity-critical inputs the judge re-lays-down identically)."""
    from core.benchmarks import load_benchmark
    from core.runner import provision_workspace

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    workdir = tmp_path / "run"
    workdir.mkdir()

    # run_cec=False keeps this a pure file-copy test (no golden compile / EDA tools).
    workspace, cec_reference = provision_workspace(bench, workdir, language="verilog", run_cec=False)

    assert workspace == workdir / "workspace"
    assert (workspace / "tb.sv").exists(), "testbench must be provisioned into the workspace"
    assert cec_reference is None


def test_backend_request_is_constructible(tmp_path):
    """The seam's request object accepts the same config run_agent_on_benchmark passes."""
    from core.benchmarks import load_benchmark

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    req = BackendRequest(
        benchmark=bench,
        workdir=tmp_path,
        workspace=tmp_path / "workspace",
        model="simple_adder_pass",
        provider="fake",
        cost_metric=None,
        language="verilog",
        limits=RunLimits(max_steps=10),
    )
    assert req.provider == "fake"
    assert req.run_cec is True          # default
    assert req.save_workspaces is True  # default

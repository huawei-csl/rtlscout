"""Phase-2 tests for the OpenCode backend.

The rendering/config tests need no binary and run in normal pytest. The §4.8
non-interactive write-gate actually launches `opencode run` (spends API tokens), so it
is gated on BOTH the binary being installed AND an explicit opt-in env var
(RTLSCOUT_OPENCODE_LIVE=1) so it never runs/spends during ordinary CI.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"
SIMPLE_ADDER_ROOT = BENCHMARKS_ROOT / "simple_adder"

requires_opencode_live = pytest.mark.skipif(
    shutil.which("opencode") is None or os.environ.get("RTLSCOUT_OPENCODE_LIVE") != "1",
    reason="needs opencode installed and RTLSCOUT_OPENCODE_LIVE=1 (live, spends tokens)",
)


def _make_req(tmp_path, language="verilog", model="z-ai/glm-4.6", provider="openrouter",
              max_evals=2, wall_clock_s=0):
    from core.agent_backend import BackendRequest, RunLimits
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric
    from core.runner import provision_workspace

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    workdir = tmp_path / "wd"
    ws, cec = provision_workspace(bench, workdir, language=language, run_cec=False)
    return BackendRequest(
        benchmark=bench, workdir=workdir, workspace=ws, model=model, provider=provider,
        cost_metric=make_cost_metric("transistors"), language=language,
        limits=RunLimits(max_steps=20, max_evals=max_evals, wall_clock_s=wall_clock_s),
        cec_reference=cec, run_cec=False,
    )


def test_make_backend_opencode():
    from core.agent_backend import make_backend
    from core.opencode_backend import OpenCodeBackend
    assert isinstance(make_backend("opencode"), OpenCodeBackend)
    assert make_backend("opencode").name == "opencode"


def test_render_agents_md_overrides_react_mechanics(tmp_path):
    from core.opencode_backend import render_agents_md
    req = _make_req(tmp_path, language="verilog")
    md = render_agents_md(req)
    # The opencode execution section must be present and reference the eval wrapper +
    # the verbatim reflection prompts + the right design filename.
    assert "OpenCode execution environment" in md
    assert "./evaluate_design" in md
    assert "summary.txt" in md
    assert "What optimizations had the most impact?" in md
    assert "design.sv" in md  # verilog design filename


def test_render_agents_md_spirehdl_design_py(tmp_path):
    from core.opencode_backend import render_agents_md
    req = _make_req(tmp_path, language="spirehdl")
    md = render_agents_md(req)
    assert "design.py" in md


def test_render_opencode_config(tmp_path):
    from core.opencode_backend import render_opencode_config
    req = _make_req(tmp_path, model="z-ai/glm-4.6", provider="openrouter")
    cfg = render_opencode_config(req)
    assert cfg["model"] == "openrouter/z-ai/glm-4.6"
    assert cfg["instructions"] == ["AGENTS.md"]
    assert cfg["permission"]["edit"] == "allow"
    assert cfg["permission"]["bash"] == "allow"
    assert "rtl" in cfg["agent"]
    # Key must NOT be embedded in the config (handover O4).
    assert "OPENROUTER_API_KEY" not in json.dumps(cfg)


def test_write_eval_config_and_wrapper(tmp_path):
    from core.opencode_backend import write_eval_config, write_eval_wrapper
    req = _make_req(tmp_path, language="verilog")

    cfg_path = write_eval_config(req)
    cfg = json.loads(cfg_path.read_text())
    assert cfg_path == req.workdir / "_eval_config.json"
    assert cfg["design_top_module"] == req.benchmark.module_name
    assert cfg["cost_metric"] == "transistors"
    assert cfg["language"] == "verilog"

    wrapper = write_eval_wrapper(req)
    assert wrapper == req.workspace / "evaluate_design"
    assert os.access(wrapper, os.X_OK), "wrapper must be executable"
    body = wrapper.read_text()
    assert "core.eval_store" in body
    assert str(req.workspace.resolve()) in body


@requires_opencode_live
def test_opencode_noninteractive_write_gate(tmp_path):
    """§4.8 gate: a real opencode run must non-interactively create a design file and
    call the eval shim, producing at least one recorded evaluation."""
    from core.opencode_backend import OpenCodeBackend

    req = _make_req(tmp_path, language="verilog",
                    model=os.environ.get("RTLSCOUT_OPENCODE_MODEL", "z-ai/glm-4.6"),
                    provider="openrouter", max_evals=2, wall_clock_s=420)
    result = OpenCodeBackend().run(req)

    evals_path = req.workdir / "evals.jsonl"
    assert evals_path.exists(), "agent never ran the eval shim (non-interactive write/eval failed)"
    lines = [l for l in evals_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1, "no evaluation was recorded"
    # The agent must have authored a design file that the eval shim snapshotted.
    assert list(req.workdir.glob("eval_*/workspace/design.*"))

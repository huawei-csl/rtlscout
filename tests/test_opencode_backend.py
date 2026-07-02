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
              wall_clock_s=0):
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
        limits=RunLimits(max_steps=20, wall_clock_s=wall_clock_s),
        cec_reference=cec, run_cec=False,
    )


class _FakeSandbox:
    """Scripted sandbox for testing the nudge loop without an LLM. Each run_command uses the
    next script entry; `add_eval` appends a line to agent_evals.jsonl to simulate the agent scoring
    a new design that round."""
    runs_in_process = False

    def __init__(self, run_root, scripts):
        from pathlib import Path
        self.run_root = Path(run_root)
        self.scripts = scripts
        self.calls = 0

    def run_callable(self, fn, spec):
        raise NotImplementedError

    def run_command(self, argv, spec):
        from core.sandbox import CommandResult
        s = self.scripts[min(self.calls, len(self.scripts) - 1)]
        self.calls += 1
        if s.get("add_eval"):
            with open(self.run_root / "agent_evals.jsonl", "a") as f:
                f.write(json.dumps({"eval_index": self.calls, "passed": True,
                                    "cost": {"ok": True}, "cost_value": 1}) + "\n")
        return CommandResult(returncode=s.get("returncode", 0), stdout=s.get("stdout", ""),
                             stderr="", timed_out=s.get("timed_out", False))


def _run_with_fake(tmp_path, scripts, wall_clock_s=300):
    """Run OpenCodeBackend.run with a fake sandbox; return the provenance dict."""
    from core.opencode_backend import OpenCodeBackend
    req = _make_req(tmp_path, wall_clock_s=wall_clock_s)
    req.agent_sandbox = _FakeSandbox(req.workdir, scripts)
    OpenCodeBackend().run(req)
    return json.loads((req.workdir / "_opencode_provenance.json").read_text())


_SID = '{"type":"step_start","sessionID":"ses_test"}'


def test_nudge_loop_caps_at_max_rounds(tmp_path):
    """Agent returns early each round but keeps producing evals → nudged up to the hard cap."""
    from core.opencode_backend import NUDGE_MAX_ROUNDS
    scripts = [{"stdout": _SID, "add_eval": True}]  # every call adds an eval → never breaks early
    prov = _run_with_fake(tmp_path, scripts)
    assert prov["nudge_rounds"] == NUDGE_MAX_ROUNDS


def test_nudge_loop_breaks_when_no_new_eval(tmp_path):
    """A nudge that produces no new evaluation → agent is done/stuck → stop nudging."""
    scripts = [
        {"stdout": _SID, "add_eval": True},   # main run: one eval
        {"stdout": "", "add_eval": False},    # nudge 1: no new eval → break
    ]
    prov = _run_with_fake(tmp_path, scripts)
    assert prov["nudge_rounds"] == 1


def test_no_nudge_when_first_run_times_out(tmp_path):
    """If the agent used the whole wall-clock (timed_out), there's nothing to nudge."""
    scripts = [{"stdout": _SID, "add_eval": True, "timed_out": True}]
    prov = _run_with_fake(tmp_path, scripts)
    assert prov["nudge_rounds"] == 0


def test_no_nudge_without_wall_clock(tmp_path):
    """No wall-clock budget → no deadline → no nudging."""
    scripts = [{"stdout": _SID, "add_eval": True}]
    prov = _run_with_fake(tmp_path, scripts, wall_clock_s=0)
    assert prov["nudge_rounds"] == 0


def test_extract_session_id():
    from core.opencode_backend import _extract_session_id
    stream = ('{"type":"step_start","sessionID":"ses_abc123","part":{}}\n'
              '{"type":"text","part":{"text":"hi"}}\n')
    assert _extract_session_id(stream) == "ses_abc123"
    assert _extract_session_id("") is None
    assert _extract_session_id("not json\n") is None


def test_make_backend_opencode():
    from core.agent_backend import make_backend
    from core.opencode_backend import OpenCodeBackend
    assert isinstance(make_backend("opencode"), OpenCodeBackend)
    assert make_backend("opencode").name == "opencode"


def test_render_agents_md_workflow_present(tmp_path):
    from core.opencode_backend import render_agents_md
    req = _make_req(tmp_path, language="verilog")
    md = render_agents_md(req)
    # The clean workflow block + the eval wrapper + the right design filename.
    assert "## How you work here" in md
    assert "./evaluate_design" in md
    assert "design.sv" in md  # verilog design filename
    assert "./remaining_time" in md  # agent is told how to check its time budget
    assert "Time budget" in md
    assert "No wrap-up needed" in md          # finishing-up wording (no manual final eval)
    assert "terminated automatically" in md   # agent is told it won't need to self-stop
    assert "summary.txt" not in md            # summary is harness-driven, not asked of the agent
    assert "time wisely" in md.lower()  # steered to iterate, not dig through the harness


def test_write_remaining_time_wrapper(tmp_path):
    from core.opencode_backend import write_remaining_time_wrapper
    req = _make_req(tmp_path, wall_clock_s=300)
    (req.workdir / "_deadline_epoch").write_text("9999999999")
    w = write_remaining_time_wrapper(req)
    assert w == req.workspace / "remaining_time"
    assert os.access(w, os.X_OK), "remaining_time must be executable"
    assert "_deadline_epoch" in w.read_text()


def test_render_agents_md_spirehdl_design_py(tmp_path):
    from core.opencode_backend import render_agents_md
    req = _make_req(tmp_path, language="spirehdl")
    md = render_agents_md(req)
    assert "design.py" in md


def test_spirehdl_agents_md_points_to_readme_not_inlined(tmp_path):
    """OpenCode (shell + read access) should get compact pointers to the spire-hdl README +
    reference files, NOT ~tens of KB of inlined source — keeps AGENTS.md small."""
    from core.opencode_backend import render_agents_md
    from core.prompts import build_spirehdl_system_prompt

    md = render_agents_md(_make_req(tmp_path, language="spirehdl"))
    assert "deps/spire-hdl/README.md" in md          # points at the main README
    assert "read these files yourself" in md          # tells the agent to read them
    assert "Common mistakes" in md                    # the curated hints are inlined
    # the dedicated renderer must be far smaller than the react prompt that inlines the sources
    inlined = build_spirehdl_system_prompt("d", "area")
    assert len(md) < len(inlined) / 2                 # materially smaller (~80%+)


def test_spirehdl_agents_md_no_verbose_overview(tmp_path):
    """The verbose react 'Spire Overview' prose is dropped in the OpenCode renderer."""
    from core.opencode_backend import render_agents_md
    md = render_agents_md(_make_req(tmp_path, language="spirehdl"))
    assert "## Spire Overview" not in md


def test_all_hdls_are_clean_no_react_cruft(tmp_path):
    """Every OpenCode HDL prompt uses the lean renderer: a clean '## How you work here'
    workflow, and NONE of the react loop's tool mechanics (the in-house tool list, the
    'always call a tool' rule, the step budget, or the 'overrides/ignore' preamble)."""
    from core.opencode_backend import render_agents_md
    for lang in ("spirehdl", "verilog", "amaranth"):
        md = render_agents_md(_make_req(tmp_path / lang, language=lang))
        assert "## How you work here" in md, lang
        assert "./evaluate_design" in md, lang
        # no react cruft
        assert "overrides any tool notes above" not in md, lang
        assert "Ignore any earlier references" not in md, lang
        assert "Always call a tool in every response" not in md, lang
        assert "## Tools" not in md, lang               # react in-house tool list
        assert "maximum of" not in md.lower() or "step" not in md.lower(), lang  # no step budget


def test_amaranth_agents_md_clean(tmp_path):
    from core.opencode_backend import render_agents_md
    md = render_agents_md(_make_req(tmp_path, language="amaranth"))
    assert "Amaranth notes" in md                       # concise inline HDL note
    assert "Elaboratable" in md
    assert "design.py" in md                             # amaranth design filename
    assert "## Amaranth HDL Overview" not in md          # verbose react overview dropped


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
                    provider="openrouter", wall_clock_s=420)
    result = OpenCodeBackend().run(req)

    evals_path = req.workdir / "agent_evals.jsonl"
    assert evals_path.exists(), "agent never ran the eval shim (non-interactive write/eval failed)"
    lines = [l for l in evals_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1, "no evaluation was recorded"
    # The agent must have authored a design file that the eval shim snapshotted.
    assert list(req.workdir.glob("eval_*/workspace/design.*"))

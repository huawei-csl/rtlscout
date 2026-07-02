"""R3 tests: the rtl-dv-prep flow — agent authors stimulus, tooling freezes Tier 2, slot becomes
fillable. Stub `opencode` plays the agent (no LLM); the golden sim + freeze + gate are real."""
import json
import os
from pathlib import Path

import pytest

from spire import UInt
from spire.component import Netlist
from spire.design_db import DesignDBError, insert_design, register_slot
from spire.design_db.store import DB_ENV, VERSION_DIR

from core.design_db_agents import (dispatch_dv_prep, provision_dv_prep_workspace,
                                   provision_orchestrator_workspace, render_dv_prep_agents_md)
from core.design_db_shims import main as shims_main


@pytest.fixture
def db(tmp_path, monkeypatch):
    root = tmp_path / "design_db"
    monkeypatch.setenv(DB_ENV, str(root))
    monkeypatch.delenv("RTLSCOUT_DISPATCH_DEPTH", raising=False)
    return root


def _seq_slot():
    m = Netlist("seqm", with_clock=True, with_reset=True)
    din = m.input(UInt(4), "din")
    q = m.reg(UInt(4), "q", init=0)
    q <<= din
    dout = m.output(UInt(4), "dout")
    dout <<= q
    return register_slot(m)


STIMULUS_PY = """\
def generate(ports, n_vectors, seed):
    for i in range(n_vectors):
        yield {p["name"]: (i * 7 + 3) for p in ports}
"""

CORRECT_SEQ_V = """\
module cand_seq(input clk, input rst, input [3:0] din, output [3:0] dout);
  reg [3:0] q;
  always @(posedge clk or posedge rst)
    if (rst) q <= 4'd0;
    else q <= din;
  assign dout = q;
endmodule
"""


def test_render_and_provision_dv_prep(db, tmp_path):
    key = _seq_slot()
    w = provision_dv_prep_workspace(key, tmp_path / "w", budget_min=5)
    md = (w / "AGENTS.md").read_text()
    assert "stimulus.py" in md and "never see or write candidate designs" in md
    assert "stimulus only" in md and "./check-stimulus" in md
    assert "input  din" in md
    cfg = json.loads((w / "opencode.json").read_text())
    assert "rtl-dv-prep" in cfg["agent"]
    assert (w / "check-stimulus").stat().st_mode & 0o111


def test_stimulus_check_shim(db, tmp_path, capsys):
    key = _seq_slot()
    good = tmp_path / "stim.py"
    good.write_text(STIMULUS_PY)
    assert shims_main(["stimulus-check", "--slot", key, "--stimulus", str(good)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "OK" and out["data_inputs"] == ["din"]
    bad = tmp_path / "bad.py"
    bad.write_text("nope = 1\n")
    assert shims_main(["stimulus-check", "--slot", key, "--stimulus", str(bad)]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


def test_dv_prep_refuses_frozen_slot(db, tmp_path):
    key = _seq_slot()
    from spire.design_db import freeze_sim_verification
    freeze_sim_verification(key, n_vectors=16)
    with pytest.raises(DesignDBError, match="already has a frozen"):
        provision_dv_prep_workspace(key, tmp_path / "w")


def test_dv_prep_e2e_with_stub_agent(db, tmp_path, monkeypatch):
    """Agent authors stimulus → tooling freezes Tier 2 → the slot gates real inserts."""
    key = _seq_slot()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "opencode"
    stub.write_text("#!/usr/bin/env bash\n"
                    "cat > stimulus.py <<'SEOF'\n" + STIMULUS_PY + "SEOF\n"
                    "./check-stimulus stimulus.py > check_out.json\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    w = tmp_path / "dvprep_ws"
    report = dispatch_dv_prep(key, model="stub:model", budget_min=2, n_vectors=32, workdir=w)
    assert report["frozen"] is not None and "error" not in report
    slot = db / VERSION_DIR / key
    verification = json.loads((slot / "verification.json").read_text())
    assert verification["tier"] == 2
    assert verification["stimulus_author"] == "agent:rtl-dv-prep"
    assert (slot / "stimulus.py").exists()                     # the review artifact
    assert (slot / "tb.sv").exists() and (slot / "vectors.dat").exists()

    # the frozen verification now gates real inserts
    res = insert_design(key, CORRECT_SEQ_V, source="test")
    assert res.metrics["intrinsic"]["aig_latches"] > 0
    from spire.design_db import VerificationFailed
    with pytest.raises(VerificationFailed):
        insert_design(key, CORRECT_SEQ_V.replace("assign dout = q;",
                                                 "assign dout = q ^ 4'd1;"), source="test")


def test_dv_prep_stub_produces_nothing(db, tmp_path, monkeypatch):
    key = _seq_slot()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "opencode"
    stub.write_text("#!/usr/bin/env bash\ntrue\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    report = dispatch_dv_prep(key, model="stub:model", budget_min=1, workdir=tmp_path / "w2")
    assert report["frozen"] is None and "no stimulus.py" in report["error"]
    assert not (db / VERSION_DIR / key / "verification.json").exists()


def test_orchestrator_workspace_has_dv_prep(db, tmp_path):
    w = provision_orchestrator_workspace(tmp_path / "orch")
    assert (w / "dv-prep").stat().st_mode & 0o111
    assert "./dv-prep" in (w / "AGENTS.md").read_text()

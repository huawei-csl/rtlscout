"""R2 tests: agent definitions, workspace shims, the dispatch launcher, the trusted report.

The dispatch e2e uses a **stub `opencode`** (a bash script that plays the agent: writes a
candidate and pushes it through `./db-insert`) — the full handover protocol without an LLM.
"""
import json
import os
import stat
from pathlib import Path

import pytest

from spire import UInt
from spire.component import Netlist
from spire.design_db import DesignDBError, register_slot
from spire.design_db.store import DB_ENV, VERSION_DIR

from core.design_db_agents import (DISPATCH_DEPTH_CAP, DISPATCH_DEPTH_ENV, build_report,
                                   dispatch_subcircuit, provision_orchestrator_workspace,
                                   provision_slot_workspace)
from core.design_db_shims import main as shims_main


@pytest.fixture
def db(tmp_path, monkeypatch):
    root = tmp_path / "design_db"
    monkeypatch.setenv(DB_ENV, str(root))
    monkeypatch.delenv(DISPATCH_DEPTH_ENV, raising=False)
    return root


def _adder_slot():
    m = Netlist("adder", with_clock=False, with_reset=False)
    a = m.input(UInt(8), "a")
    b = m.input(UInt(8), "b")
    s = m.output(UInt(8), "sum")
    s <<= a + b
    return register_slot(m)


EQUIV_MOD256 = """\
module cand(input [7:0] a, input [7:0] b, output [7:0] sum);
  assign sum = a + b;
endmodule
"""

WRONG_MOD256 = EQUIV_MOD256.replace("a + b;", "a + b + 8'd1;")


def test_provision_slot_workspace(db, tmp_path):
    key = _adder_slot()
    w = provision_slot_workspace(key, tmp_path / "w", objective="area",
                                 model_spec="prov/model", budget_min=7)
    md = (w / "AGENTS.md").read_text()
    assert key[:12] in md and "./db-insert" in md and "minimize **area**" in md
    assert "input  a  (8 bits)" in md and "output sum  (8 bits)" in md
    cfg = json.loads((w / "opencode.json").read_text())
    assert cfg["agent"]["rtl-subcircuit"]["mode"] == "primary"
    for shim in ("eval", "db-insert"):
        mode = (w / shim).stat().st_mode
        assert mode & stat.S_IXUSR, f"{shim} not executable"
        assert key in (w / shim).read_text()


def test_provision_requires_frozen_verification(db, tmp_path):
    m = Netlist("seqp", with_clock=True, with_reset=True)
    din = m.input(UInt(4), "din")
    q = m.reg(UInt(4), "q", init=0)
    q <<= din
    out = m.output(UInt(4), "dout")
    out <<= q
    key = register_slot(m)
    with pytest.raises(DesignDBError, match="frozen verification"):
        provision_slot_workspace(key, tmp_path / "w")


def test_shims_eval_and_insert(db, tmp_path, capsys):
    key = _adder_slot()
    good = tmp_path / "good.v"
    good.write_text(EQUIV_MOD256)
    bad = tmp_path / "bad.v"
    bad.write_text(WRONG_MOD256)

    assert shims_main(["eval", "--slot", key, "--design", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"
    assert shims_main(["eval", "--slot", key, "--design", str(bad)]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"

    assert shims_main(["insert", "--slot", key, "--design", str(good),
                       "--source", "agent:test"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["verdict"] == "ADMITTED" and not first["deduped"]
    assert shims_main(["insert", "--slot", key, "--design", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["deduped"] is True
    assert shims_main(["insert", "--slot", key, "--design", str(bad)]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "REJECTED"

    report = build_report(key, objective="area")
    assert report["n_designs"] == 1 and report["best"]["design_id"] == first["design_id"]
    assert report["pareto"]


def test_dispatch_depth_cap(db, monkeypatch):
    key = _adder_slot()
    monkeypatch.setenv(DISPATCH_DEPTH_ENV, str(DISPATCH_DEPTH_CAP))
    with pytest.raises(DesignDBError, match="depth cap"):
        dispatch_subcircuit(key, model="fake:whatever")


def test_dispatch_e2e_with_stub_agent(db, tmp_path, monkeypatch):
    """The full handover: pointer in → (stub agent writes + gates a design) → trusted report out."""
    key = _adder_slot()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "opencode"
    distinct = EQUIV_MOD256.replace("a + b;", "(a ^ b) + ((a & b) << 1);")   # carry-save form
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$RTLSCOUT_DISPATCH_DEPTH\" > depth.txt\n"
        "cat > design.v <<'VEOF'\n" + distinct + "VEOF\n"
        "./eval design.v > eval_out.json\n"
        "./db-insert design.v > insert_out.json\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    w = tmp_path / "dispatch_ws"
    report = dispatch_subcircuit(key, model="stub:model", budget_min=2, workdir=w)
    assert report["seeded"].startswith("original:")          # the baseline floor was seeded
    assert report["n_added"] == 1 and report["n_designs"] == 2
    assert report["best"]["design_id"]                        # floor or agent — deterministic argmin
    assert (w / "report.json").exists() and (w / "opencode_session.log").exists()
    assert (w / "depth.txt").read_text().strip() == "1"       # the guard incremented
    manifest = json.loads((db / VERSION_DIR / "manifest.json").read_text())
    assert any(e.get("selected_id") for e in manifest["slots"].values()
               if e["spec_key"] == key)                        # report recorded the selection


def test_provision_orchestrator(db, tmp_path):
    w = provision_orchestrator_workspace(tmp_path / "orch", objective="area", budget_min=15)
    md = (w / "AGENTS.md").read_text()
    assert "./dispatch" in md and "spire db" in md
    assert (w / "dispatch").stat().st_mode & stat.S_IXUSR

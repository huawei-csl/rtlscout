"""Slot-first OpenCode run (`rtlscout_cli.py fill-slot --agent-backend opencode --flow direct`) on a Lean-gated slot — offline.

A stand-in `opencode` executable plays the agent: it does exactly what the skills instruct
(verify --workspace → write D<hash>_Proof.lean → insert --proof). Requires `lake` on PATH.
"""
from __future__ import annotations
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest

SPIRE = Path(__file__).resolve().parents[2] / "spire-hdl-autoproof"          # sibling checkout (lean-gated-design-db)
HELPERS = SPIRE / "testing" / "design_db"
pytestmark = pytest.mark.skipif(not (HELPERS / "lean_matmul_helper.py").exists(), reason="spire lean test helpers not found")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.path.insert(0, str(HELPERS)); spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def lean_slot(tmp_path):
    """A Lean-gated matmul slot with the Mmac layer, in a fresh DB."""
    from spire.design_db import add_spec, freeze_lean_verification, register_slot, seed_original
    from spire.design_db.lean.bridge import collect_signed_arith_shapes
    cand, helper = _load("mmac_candidates"), _load("lean_matmul_helper")
    db = tmp_path / "db"
    key = register_slot(cand.CANDIDATES["BalancedMmac"](), db=db, name="mmac")
    freeze_lean_verification(key, db=db); seed_original(key, db=db)
    shapes = collect_signed_arith_shapes(cand.CANDIDATES["BalancedMmac"]().to_netlist("g"))
    add_spec(key, "Mmac", cand.CONTRACT.spec_lean("Mmac"), helper.layer_proof_lean("Mmac", shapes), author="human", db=db)
    return dict(db=db, key=key)


def _fake_opencode(tmp_path) -> Path:
    """Stand-in agent: left-deep candidate, proof through the Mmac layer, insert."""
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    script = bin_dir / "opencode"
    script.write_text(f'''#!{sys.executable}
import json, re, subprocess, sys, os
from pathlib import Path
sys.path.insert(0, {str(HELPERS)!r})
from lean_matmul_helper import candidate_proof_lean
from spire.design_db.lean.bridge import collect_signed_arith_shapes, design_modules
from mmac_candidates import CANDIDATES
assert sys.argv[1] == "run" and "--agent" in sys.argv, sys.argv
db = os.environ["SPIREHDL_DB_PATH"]; slot = re.search(r"spec_key: `([0-9a-f]+)`", Path("AGENTS.md").read_text()).group(1)
Path("work").mkdir(exist_ok=True)
Path("work/design.py").write_text("import sys; sys.path.insert(0, {str(HELPERS)!r})\\nfrom mmac_candidates import CANDIDATES\\ndef build():\\n    return CANDIDATES['LeftDeepMmac']()\\n")
spire = [{sys.executable!r}, "-m", "spire.design_db.cli", "db"] if False else ["spire", "db"]
out = subprocess.run(spire + ["verify", "work/design.py", "--slot", slot, "--workspace", "work/ws", "--db", db], capture_output=True, text=True)
h = re.search(r"D([0-9a-f]{{10}})_Proof", out.stdout + out.stderr).group(1); circ, proof = design_modules(h)
Path(f"work/ws/{{proof}}.lean").write_text(candidate_proof_lean(collect_signed_arith_shapes(CANDIDATES["LeftDeepMmac"]().to_netlist("l")), circuit_module=circ, proof_module=proof))
ins = subprocess.run(spire + ["insert", "work/design.py", "--slot", slot, "--proof", f"work/ws/{{proof}}.lean", "--source", "agent:rtl-slot", "--db", db], capture_output=True, text=True)
print(json.dumps({{"type": "text", "text": "fake agent: verify → proof → insert", "insert_rc": ins.returncode, "insert": ins.stdout[:400]}}))
sys.exit(0)
''')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_provisioning_is_slot_first(lean_slot, tmp_path):
    from core.design_db_slot_run import _slot_info, render_slot_agents_md
    from spire.design_db import DesignDB
    d = DesignDB.open(lean_slot["db"]); info = _slot_info(d, lean_slot["key"])
    md = render_slot_agents_md(info, lean_slot["key"], source="agent:rtl-slot", db_root=Path(d.root))
    assert "evaluate_design" not in md and "spire db verify" in md and "spire db insert" in md
    assert "Lean-gated" in md and "design-db-lean-proof" in md and "`Mmac`" in md
    assert "| `a_0_0` | input | 8 | signed |" in md


def test_slot_run_with_stand_in_agent_admits_and_audits(lean_slot, tmp_path):
    from core.design_db_slot_run import run_slot_agent
    fake = _fake_opencode(tmp_path)
    venv_bin = Path(sys.executable).parent
    os.environ["PATH"] = f"{venv_bin}{os.pathsep}{os.environ['PATH']}"        # the stand-in calls `spire db …`
    rep = run_slot_agent(lean_slot["key"], model="openrouter:fake/model", db=lean_slot["db"], wall_clock_min=5,
                         work_root=tmp_path / "run", opencode_bin=str(fake))
    ws = tmp_path / "run" / "workspace"
    assert (ws / "AGENTS.md").exists() and not (ws / "evaluate_design").exists() and (ws / "remaining_time").exists()
    assert (ws / ".opencode" / "skills" / "design-db-lean-proof" / "SKILL.md").exists()
    assert json.loads((ws / "opencode.json").read_text())["agent"]["rtl"]["mode"] == "primary"
    assert rep.returncode == 0 and rep.admitted and all(a.startswith("agent:rtl-slot:") for a in rep.admitted)
    assert rep.audit and all(v["verdict"] == "PASS" for v in rep.audit.values()) and rep.ok
    assert (tmp_path / "run" / "slot_run_report.json").exists()


def test_audit_catches_a_design_written_around_the_gate(lean_slot):
    """A design dropped into designs/ by hand (bypassing insert) fails the post-run audit."""
    import shutil, time
    from core.design_db_slot_run import audit_admitted
    from spire.design_db import DesignDB
    d = DesignDB.open(lean_slot["db"]); slot = d.slot_dir(lean_slot["key"])
    src = next(p for p in (slot / "designs").iterdir() if p.name.startswith("original:"))
    rogue = slot / "designs" / "agent:rogue:0000000000"; shutil.copytree(src, rogue)
    prov = json.loads((rogue / "provenance.json").read_text()); prov["created"] = int(time.time()) + 1
    (rogue / "provenance.json").write_text(json.dumps(prov))
    (rogue / "design.v").write_text((rogue / "design.v").read_text().replace("a_0_0", "a_0_1", 1))   # tampered logic, no proof
    audit = audit_admitted(lean_slot["key"], int(time.time()), db=lean_slot["db"])
    assert audit["agent:rogue:0000000000"]["verdict"] == "FAIL"


def test_fill_slot_flow_validation(capsys):
    """Flag combinations are validated before any DB is touched."""
    from rtlscout_cli import main
    assert main(["fill-slot", "--slot", "x", "--model", "a:b", "--agent-backend", "react", "--flow", "direct"]) == 1
    assert "needs --agent-backend opencode" in capsys.readouterr().err
    assert main(["fill-slot", "--slot", "x", "--model", "a:b", "--agent-backend", "opencode", "--flow", "eval"]) == 1
    assert "not implemented yet" in capsys.readouterr().err


def test_fill_slot_direct_maps_to_fill_report(lean_slot, tmp_path):
    """`fill_slot(backend='opencode', flow='direct')` returns the unified FillReport with the audit."""
    from core.design_db_fill import fill_slot
    fake = _fake_opencode(tmp_path)
    os.environ["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
    rep = fill_slot(lean_slot["key"], model="openrouter:fake/model", db=lean_slot["db"], backend="opencode", flow="direct",
                    wall_clock_min=5, work_root=tmp_path / "run", opencode_bin=str(fake))
    assert rep.flow == "direct" and rep.backend == "opencode" and rep.ok
    assert rep.admitted and set(rep.audit) == set(rep.admitted) and rep.runs_root == str(tmp_path / "run")

"""R5 e2e: the full-design designer flow, offline, with a two-role stub `opencode`.

The stub plays:
  rtl-designer   → adds the @from_design_db decorator + import to design.py, ./compile,
                   ./dispatch on the registered slot, ./compile again
  rtl-subcircuit → submits the slot's own golden as its candidate (dedups against the seeded
                   original — the outer loop is under test here, not the insert gate)

Everything else is real: slot registration from the traced function, the CEC gate, seeding,
selection, the splice on recompile, and the tooling-derived before/after report.
"""
import json
import os
from pathlib import Path

import pytest

from spire.design_db.store import DB_ENV

from core.design_db_agents import DISPATCH_DEPTH_ENV, run_designer

DESIGN_SRC = '''\
"""adder_top — an 8-bit adder wrapped in a tiny top."""
from spire import UInt
from spire.component import Netlist


def add8(a, b):
    return a + b


def build():
    m = Netlist("adder_top", with_clock=False, with_reset=False)
    a = m.input(UInt(8), "a")
    b = m.input(UInt(8), "b")
    y = m.output(UInt(9), "y")
    y <<= add8(a, b)
    return m


if __name__ == "__main__":
    build().to_verilog_file("design.v")   # native spirehdl eval reads design.v (name = Netlist's)
'''

DESIGNER_EDIT = '''\
src = open("design.py").read()
src = src.replace("from spire.component import Netlist",
                  "from spire.component import Netlist\\nfrom spire.design_db import from_design_db")
src = src.replace("def add8(a, b):", "@from_design_db(objective=\\"area\\")\\ndef add8(a, b):")
open("design.py", "w").write(src)
'''


@pytest.fixture
def db(tmp_path, monkeypatch):
    root = tmp_path / "design_db"
    monkeypatch.setenv(DB_ENV, str(root))
    monkeypatch.delenv(DISPATCH_DEPTH_ENV, raising=False)
    return root


def test_designer_e2e_offline(db, tmp_path, monkeypatch):
    design = tmp_path / "adder_design.py"
    design.write_text(DESIGN_SRC)

    stub = tmp_path / "bin" / "opencode"
    stub.parent.mkdir()
    stub.write_text(f"""#!/usr/bin/env bash
args="$*"
case "$args" in
  *rtl-designer*)
    python3 - <<'PEOF'
{DESIGNER_EDIT}PEOF
    ./compile > c1.json
    key=$(python3 -c "import json; print(list(json.load(open('c1.json'))['slots'].values())[0]['spec_key'])")
    ./dispatch "$key" --objective area --budget-min 1 > d1.json
    ./compile > c2.json
    ;;
  *rtl-subcircuit*)
    key=$(grep -oP -- "--slot \\K[0-9a-f]{{64}}" db-insert)
    root=$(grep -oP -- "--db \\K\\S+" db-insert)
    cp "$root/v1/$key/golden.v" design.v
    ./db-insert design.v > insert_out.json
    ;;
esac
""")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub.parent}:{os.environ['PATH']}")

    ws = tmp_path / "designer_ws"
    report = run_designer(design, model="stub:model", objective="area", budget_min=5, workdir=ws)

    assert report["final_compile_error"] is None
    assert report["baseline_cost"] > 0 and report["final_cost"] is not None
    assert report["cost_metric"]                               # measured natively (transistors)
    assert "@from_design_db" in report["design_diff"]          # the agent's edit, for review
    assert design.read_text() == DESIGN_SRC                    # the original file is untouched

    slots = report["slots"]
    assert len(slots) == 1
    (slot,) = slots.values()
    # the stub candidate was the golden itself: deduped against the seed, selection = original
    assert slot["n_designs"] == 1 and slot["n_designs_before"] == 0
    assert slot["selected_id"].startswith("original:")

    assert (ws / "baseline.v").exists() and (ws / "final.v").exists()
    assert (ws / "report.json").exists() and (ws / "opencode_session.log").exists()
    nested = list((ws / "nested").glob("ddb_dispatch_*/report.json"))
    assert nested, "the ./dispatch child ran under the designer workspace"
    d1 = json.loads((ws / "d1.json").read_text())
    assert d1["seeded"].startswith("original:") and d1["n_designs"] == 1

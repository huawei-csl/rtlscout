"""R4 e2e: the full orchestrator flow, offline, with a three-role stub `opencode`.

The stub plays every agent by inspecting its --agent argument:
  rtl-orchestrator  → ./dv-prep <seq slot>, then ./dispatch <comb slot> and ./dispatch <seq slot>
  rtl-dv-prep       → writes stimulus.py (validated via ./check-stimulus)
  rtl-subcircuit    → writes a slot-appropriate candidate, ./db-insert; the comb one additionally
                      probes ./dispatch again — proving the depth cap trips at level 2.

Everything else is real: golden sim + Tier-2 freeze, the CEC/sim gates, selection, the manifest,
and the tooling-derived reports.
"""
import json
import os
from pathlib import Path

import pytest

from spire import UInt
from spire.component import Netlist
from spire.design_db import register_slot
from spire.design_db.store import DB_ENV, VERSION_DIR

from core.design_db_agents import run_orchestrator

COMB_CAND = """\
module cand(input [7:0] a, input [7:0] b, output [7:0] sum);
  assign sum = a + b;
endmodule
"""

SEQ_CAND = """\
module cand_seq(input clk, input rst, input [3:0] din, output [3:0] dout);
  reg [3:0] q;
  always @(posedge clk or posedge rst)
    if (rst) q <= 4'd0;
    else q <= din;
  assign dout = q;
endmodule
"""

STIMULUS_PY = """\
def generate(ports, n_vectors, seed):
    for i in range(n_vectors):
        yield {p["name"]: (i * 5 + 1) for p in ports}
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    root = tmp_path / "design_db"
    monkeypatch.setenv(DB_ENV, str(root))
    monkeypatch.delenv("RTLSCOUT_DISPATCH_DEPTH", raising=False)
    return root


def _slots():
    m = Netlist("adder", with_clock=False, with_reset=False)
    a, b = m.input(UInt(8), "a"), m.input(UInt(8), "b")
    s = m.output(UInt(8), "sum")
    s <<= a + b
    comb = register_slot(m)

    m2 = Netlist("seqm", with_clock=True, with_reset=True)
    din = m2.input(UInt(4), "din")
    q = m2.reg(UInt(4), "q", init=0)
    q <<= din
    dout = m2.output(UInt(4), "dout")
    dout <<= q
    seq = register_slot(m2)
    return comb, seq


def test_orchestrator_e2e_offline(db, tmp_path, monkeypatch):
    comb, seq = _slots()
    marker = tmp_path / "depth_cap.txt"

    stub = tmp_path / "bin" / "opencode"
    stub.parent.mkdir()
    stub.write_text(f"""#!/usr/bin/env bash
args="$*"
case "$args" in
  *rtl-orchestrator*)
    ./dv-prep {seq} --budget-min 1 --vectors 32 > orch_dvprep.json
    ./dispatch {comb} --objective area --budget-min 1 > orch_dispatch_comb.json
    ./dispatch {seq} --objective area --budget-min 1 > orch_dispatch_seq.json
    ;;
  *rtl-dv-prep*)
    cat > stimulus.py <<'SEOF'
{STIMULUS_PY}SEOF
    ./check-stimulus stimulus.py > check_out.json
    ;;
  *rtl-subcircuit*)
    if [[ "$args" == *{seq[:16]}* ]]; then
      cat > design.v <<'VEOF'
{SEQ_CAND}VEOF
    else
      cat > design.v <<'VEOF'
{COMB_CAND}VEOF
    fi
    ./db-insert design.v > insert_out.json
    if [[ "$args" != *{seq[:16]}* ]]; then
      ./dispatch {seq} --budget-min 1 > nested.json 2>&1 || echo "capped" > {marker}
    fi
    ;;
esac
""")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub.parent}:{os.environ['PATH']}")

    orch_ws = tmp_path / "orch_ws"
    report = run_orchestrator(model="stub:model", objective="area", budget_min=5,
                              workdir=orch_ws)

    slots = report["slots"]
    assert slots["adder"]["n_designs"] == 1 and slots["adder"]["n_designs_before"] == 0
    assert slots["adder"]["selected_id"].startswith("agent:rtl-subcircuit:")
    assert slots["seqm"]["n_designs"] == 1
    assert (orch_ws / "report.json").exists() and (orch_ws / "opencode_session.log").exists()

    seq_slot = db / VERSION_DIR / seq
    verification = json.loads((seq_slot / "verification.json").read_text())
    assert verification["tier"] == 2
    assert verification["stimulus_author"] == "agent:rtl-dv-prep"
    assert (seq_slot / "stimulus.py").exists()

    assert marker.exists() and "capped" in marker.read_text(), \
        "the depth-2 nested dispatch must be refused by the guard"

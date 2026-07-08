"""Tests for the skills-run visualization tools (visualize_db_run / measure_db_compositions).

The viz test runs on a synthetic run dir (pure python, no tools); the composition e2e is
tool-real: it compiles a tiny decorated design, fills its slot through the gate, and measures
real splice combinations.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import visualize_db_run as viz
from measure_db_compositions import aag_depth, pareto


def test_pareto_and_aag_depth():
    pts = [{"area": 10, "depth": 5}, {"area": 12, "depth": 3},
           {"area": 11, "depth": 5}, {"area": 20, "depth": 2}]
    front = pareto(pts)
    assert [(p["area"], p["depth"]) for p in front] == [(10, 5), (12, 3), (20, 2)]

    # y = AND(AND(i1,i2), i2): two levels
    aag = ["aag 4 2 0 1 2", "2", "4", "8", "6 2 4", "8 6 4", "i0 a", "i1 b", "o0 y"]
    assert aag_depth(aag) == 2


def _mk_design(ddir, source, created, area, depth):
    ddir.mkdir(parents=True)
    (ddir / "provenance.json").write_text(json.dumps(
        {"schema": 1, "source": source, "created": created, "struct_hash": "x"}))
    (ddir / "metrics.json").write_text(json.dumps(
        {"aig": {"metrics": {"aig_nodes": area // 5, "aig_depth": depth, "aig_latches": 0}},
         "transistors": {"metrics": {"transistors_heavy": area}}}))


@pytest.fixture
def synthetic_run(tmp_path):
    run = tmp_path / "runs" / "bench_x" / "some_model" / "20260101_000000"
    v1 = run / "workspace" / "design_db" / "v1"
    key = "k" * 64
    v1.mkdir(parents=True)
    (v1 / "manifest.json").write_text(json.dumps({"schema": 1, "slots": {
        "s1": {"spec_key": key, "objective": "area", "metric": "transistors",
               "selected_id": "agent:rtl-subcircuit:aaa", "class": "combinational"}}}))
    _mk_design(v1 / key / "designs" / "original:orig", "original", "2026-01-01T00:00:10", 100, 8)
    _mk_design(v1 / key / "designs" / "agent:rtl-subcircuit:aaa", "agent:rtl-subcircuit",
               "2026-01-01T00:02:00", 80, 9)
    _mk_design(v1 / key / "designs" / "agent:rtl-subcircuit:bbb", "agent:rtl-subcircuit",
               "2026-01-01T00:04:00", 90, 7)
    (run / "agent_evals.jsonl").write_text(
        json.dumps({"eval_index": 1, "passed": True, "cost_value": 200}) + "\n")
    (run / "eval_1").mkdir()
    (run / "_deadline_epoch").write_text(str(time.time() + 600))
    (run / "result.json").write_text("{}")
    return run


def test_generate_report_synthetic(synthetic_run):
    out = viz.generate(synthetic_run, synthetic_run / "visualization.html")
    html = out.read_text()
    assert "bench_x" in html and "some_model" in html
    assert "s1" in html and "agent:rtl-subcircuit" in html
    assert "selected" in html and "original (seed)" in html
    assert "composition space" not in html          # panel only after measurement
    assert "measure_db_compositions.py" in html     # ...and the report says how to get it

    (synthetic_run / "composition_space.json").write_text(json.dumps({
        "slots": ["s1"],
        "results": [
            {"picks": {"s1": "agent:rtl-subcircuit:aaa"}, "area": 80, "depth": 9,
             "baseline": False, "selected": True},
            {"picks": {"s1": "original:orig"}, "area": 100, "depth": 8,
             "baseline": True, "selected": False}],
        "starting_point": {"area": 105, "depth": 8},
        "evaluations": [
            {"eval_index": 1, "area": 105, "depth": 8, "recorded_cost": 200, "passed": True},
            {"eval_index": 2, "area": 82, "depth": 9, "recorded_cost": 190, "passed": True}]}))
    html = viz.generate(synthetic_run, synthetic_run / "visualization.html").read_text()
    assert "composition space" in html
    assert "main-agent eval 1" in html and "main-agent eval 2" in html
    assert "eval 1 (105)" in html                    # labeled on the plot
    assert "agent selection 80/9" in html
    assert "full-circuit evals over time" in html
    assert "selected composition (measured offline) 80" in html
    order = [html.index("admissions over time"), html.index("full-circuit composition space"),
             html.index("full-circuit evals over time"), html.index("who worked when")]
    assert order == sorted(order)                    # panel ordering


_DESIGN_PY = """\
from spire import Component, IORecord, Input, Output, UInt
from spire.design_db import from_design_db


@from_design_db(objective="area")
def add8(a, b):
    return (a + b)[0:8]


class Top(Component):
    def __init__(self):
        self.io = IORecord(a=Input(UInt(8)), b=Input(UInt(8)), y=Output(UInt(8)))
        self.elaborate()

    def elaborate(self):
        self.io.y <<= add8(self.io.a, self.io.b)


Top().to_verilog_file("design.v", name="top")
"""

# carry-select: two 4-bit adds + a mux — structurally lower depth than one 8-bit add (so it
# always lands on the (area, depth) front next to the original), at more area.
_CARRY_SELECT = """\
module cand(input [7:0] a, input [7:0] b, output [7:0] y);
  wire [4:0] lo = {1'b0, a[3:0]} + {1'b0, b[3:0]};
  wire [3:0] hi0 = a[7:4] + b[7:4];
  wire [3:0] hi1 = a[7:4] + b[7:4] + 4'd1;
  assign y = {lo[4] ? hi1 : hi0, lo[3:0]};
endmodule
"""


def test_measure_db_compositions_e2e(tmp_path, monkeypatch):
    """Tool-real: a decorated design + a gate-filled slot -> measured splice combinations."""
    pytest.importorskip("spire")
    from spire.design_db import DesignDB, insert_design, seed_original
    from spire.design_db.store import DB_ENV

    run = tmp_path / "run"
    ws = run / "workspace"
    ws.mkdir(parents=True)
    db_root = ws / "design_db"
    monkeypatch.setenv(DB_ENV, str(db_root))
    (ws / "design.py").write_text(_DESIGN_PY)
    proc = subprocess.run([sys.executable, "design.py"], cwd=ws, capture_output=True,
                          text=True, timeout=300, env=dict(os.environ))
    assert proc.returncode == 0, proc.stderr[-400:]

    d = DesignDB.open(db_root)
    man = d.read_json(d.manifest_path, {})
    (key,) = [e["spec_key"] for e in man["slots"].values()]
    seed_original(key, db=db_root)
    insert_design(key, _CARRY_SELECT, source="verilog", db=db_root)

    from measure_db_compositions import measure_run
    out = json.loads(measure_run(run, all_designs=True).read_text())   # deterministic combo count
    assert len(out["results"]) >= 2                          # front combos + baseline (deduped)
    areas = {r["area"] for r in out["results"]}
    assert len(areas) >= 2                                   # genuinely different compositions
    assert any(r["baseline"] for r in out["results"])
    assert all(r["area"] > 0 and r["depth"] > 0 for r in out["results"])
    assert "evaluations" not in out                          # no eval_N snapshots in this run

    # an eval snapshot (incl. its design_db state) gets measured as a main-agent eval point
    snap = run / "eval_1" / "workspace"
    import shutil
    shutil.copytree(ws, snap)
    (run / "agent_evals.jsonl").write_text(json.dumps({"eval_index": 1, "cost_value": 111,
                                                       "passed": True}) + "\n")
    out = json.loads(measure_run(run, all_designs=True).read_text())
    (ev,) = out["evaluations"]
    assert ev["eval_index"] == 1 and ev["area"] > 0 and ev["depth"] > 0
    assert ev["recorded_cost"] == 111
    assert out["starting_point"]["area"] == ev["area"]

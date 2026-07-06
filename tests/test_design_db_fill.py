"""R1 tests: the RTLScout design-DB filler (`fill_slot` / `rtlscout_fill`) and `db score`.

Offline: the campaign runs with the `fake:` provider; correctness is real (verilator + yosys +
yosys-abc CEC through Spire's gate). `db score` runs the real asap7 PPA flow on one tiny design.
"""
import json
from pathlib import Path

import pytest

from spire import UInt
from spire.component import Netlist
from spire.design_db import DesignDBError, register_slot, seed_original, select_design
from spire.design_db.store import DB_ENV, VERSION_DIR

from core.design_db_fill import FILL_MODEL_ENV, fill_slot, make_rtlscout_fill, score_designs


@pytest.fixture
def db(tmp_path, monkeypatch):
    root = tmp_path / "design_db"
    monkeypatch.setenv(DB_ENV, str(root))
    return root


def _adder_slot():
    """A slot matching the fake provider's canned design: module adder, a/b -> sum (mod 256)."""
    m = Netlist("adder", with_clock=False, with_reset=False)
    a = m.input(UInt(8), "a")
    b = m.input(UInt(8), "b")
    s = m.output(UInt(8), "sum")
    s <<= a + b                       # truncating assignment: mod-256, same as the fake design
    return register_slot(m)


def test_fill_slot_offline_fake(db):
    key = _adder_slot()
    report = fill_slot(key, model="fake:simple_adder_pass", total_runs=1, max_steps=8,
                       n_advisory_vectors=32)
    assert report.seeded and report.seeded.startswith("original:")
    assert report.attempted >= 1
    assert report.admitted or report.deduped >= 1        # fake adder may dedup vs the original
    assert not report.errors, report.errors
    index = json.loads((db / VERSION_DIR / key / "index.json").read_text())
    assert any(i.startswith("original:") for i in index)
    sel = select_design(key, objective="area")
    assert sel is not None and sel.metric == "transistors"


def test_fill_refuses_unverified_slot(db):
    m = Netlist("seqf", with_clock=True, with_reset=True)
    din = m.input(UInt(4), "din")
    q = m.reg(UInt(4), "q", init=0)
    q <<= din
    out = m.output(UInt(4), "dout")
    out <<= q
    key = register_slot(m)
    with pytest.raises(DesignDBError, match="frozen verification"):
        fill_slot(key, model="fake:simple_adder_pass")


def test_rtlscout_fill_hook(db, monkeypatch):
    key = _adder_slot()
    fill = make_rtlscout_fill(model="fake:simple_adder_pass", total_runs=1, max_steps=8,
                              n_advisory_vectors=32)
    fill(key, db_root=db, objective="area", metric=None)
    index = json.loads((db / VERSION_DIR / key / "index.json").read_text())
    assert len(index) >= 1

    from core.design_db_fill import rtlscout_fill
    monkeypatch.delenv(FILL_MODEL_ENV, raising=False)
    with pytest.raises(DesignDBError, match=FILL_MODEL_ENV):
        rtlscout_fill(key, db_root=db)


def test_db_score_asap7(db):
    key = _adder_slot()
    seed_original(key)

    # --dry-run measures and returns values but writes nothing (and ignores the already-stamped
    # skip logic — it is a pure measurement)
    dry = score_designs([key], technology="asap7", run_netlist_sim=False, dry_run=True)
    assert dry["dry_run"] is True and dry["scored"] == 1 and not dry["failed"], dry
    (dry_values,) = dry["measured"].values()
    assert dry_values["area"] > 0
    index = json.loads((db / VERSION_DIR / key / "index.json").read_text())
    assert "asap7" not in (next(iter(index.values()))["metrics"] or {}), \
        "dry-run must not annotate"

    report = score_designs([key], technology="asap7", run_netlist_sim=False, max_designs=1)
    assert report["scored"] == 1 and not report["failed"], report
    index = json.loads((db / VERSION_DIR / key / "index.json").read_text())
    entry = next(iter(index.values()))
    assert entry["metrics"]["asap7"]["metrics"]["area"] > 0            # self-describing block
    assert entry["metrics"]["asap7"]["objectives"]["area"] == "area"
    sel = select_design(key, objective="area", metric="asap7")
    assert sel is not None and sel.metric == "asap7"
    # idempotent: second run skips
    again = score_designs([key], technology="asap7", run_netlist_sim=False)
    assert again["scored"] == 0 and again["skipped"] >= 1

    # --design scopes to one design_id (unique prefix); force re-scores just that one
    design_id = next(iter(index))
    scoped = score_designs([key], technology="asap7", run_netlist_sim=False,
                           designs=[design_id[:12]], force=True)
    assert scoped["scored"] == 1 and list(scoped["measured"]) == [design_id]

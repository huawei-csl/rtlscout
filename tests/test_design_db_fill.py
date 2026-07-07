"""R1 tests: the RTLScout design-DB filler (`fill_slot` / `rtlscout_fill`).

Offline: the campaign runs with the `fake:` provider; correctness is real (verilator + yosys +
yosys-abc CEC through Spire's gate). The `db-score` tests live in test_design_db_score.py.
"""
import json
from pathlib import Path

import pytest

from spire import UInt
from spire.component import Netlist
from spire.design_db import DesignDBError, register_slot, seed_original, select_design
from spire.design_db.store import DB_ENV, VERSION_DIR

from core.design_db_fill import FILL_MODEL_ENV, fill_slot, make_rtlscout_fill


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

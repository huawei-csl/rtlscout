"""`db-score` tests: the per-technology PPA scorer (`core.design_db_score.score_designs`).

Runs the real asap7 PPA flow on one tiny design; backs the `design-db-score` skill.
"""
import json

import pytest

from tests.conftest import requires_openroad

from spire import UInt
from spire.component import Netlist
from spire.design_db import register_slot, seed_original, pick_design
from spire.design_db.store import DB_ENV, VERSION_DIR

from core.design_db_score import score_designs


@pytest.fixture
def db(tmp_path, monkeypatch):
    root = tmp_path / "design_db"
    monkeypatch.setenv(DB_ENV, str(root))
    return root


def _adder_slot():
    """A slot with a trivially-correct golden: module adder, a/b -> sum (mod 256)."""
    m = Netlist("adder", with_clock=False, with_reset=False)
    a = m.input(UInt(8), "a")
    b = m.input(UInt(8), "b")
    s = m.output(UInt(8), "sum")
    s <<= a + b
    return register_slot(m)


@requires_openroad
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
    sel = pick_design(key, objective="area", metric="asap7")
    assert sel is not None and sel.metric == "asap7"
    # idempotent: second run skips
    again = score_designs([key], technology="asap7", run_netlist_sim=False)
    assert again["scored"] == 0 and again["skipped"] >= 1

    # --design scopes to one design_id (unique prefix); force re-scores just that one
    design_id = next(iter(index))
    scoped = score_designs([key], technology="asap7", run_netlist_sim=False,
                           designs=[design_id[:12]], force=True)
    assert scoped["scored"] == 1 and list(scoped["measured"]) == [design_id]

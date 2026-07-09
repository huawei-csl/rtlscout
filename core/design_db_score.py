"""Per-technology PPA scoring for stored design-DB designs — the `db-score` command.

``score_designs`` measures area/delay/… on admitted designs via the existing cost metrics
(tech_eval/OpenROAD) and — unless ``dry_run`` — hands the values to spire's ``annotate`` gate,
unlocking ``pick_design(..., metric="asap7")``. This backs the ``design-db-score`` skill in
the OpenCode skills flow (via ``rtlscout_cli.py db-score``); the non-agentic campaign filler
lives separately in ``core.design_db_fill``.

Direction note: RTLScout imports Spire (this module imports ``spire.design_db``); Spire never
imports RTLScout back.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from spire.design_db import DesignDB, DesignDBError
from spire.design_db.verify_sim import _top_module_name


def score_designs(spec_keys: Optional[Sequence[str]] = None, *, db: Optional[Any] = None,
                  technology: str = "asap7", target_delay: float = 500.0,
                  run_netlist_sim: bool = False, force: bool = False,
                  max_designs: Optional[int] = None,
                  designs: Optional[Sequence[str]] = None,
                  dry_run: bool = False) -> Dict[str, Any]:
    """Measure per-technology PPA on stored designs and (unless ``dry_run``) annotate the DB.

    Adds ``metrics[<technology>] = {area, delay, ...}`` to each design's ``metrics.json`` and the
    slot ``index.json`` — after this, ``pick_design(..., metric=technology)`` works.
    ``designs`` limits scoring to the named design_ids (or unique prefixes) within the selected
    slots. ``dry_run`` runs the same cost flow but **writes nothing** — the measured values are
    only returned (report ``measured``), for looking at numbers without committing them.
    """
    from core.cost import make_cost_metric
    metric = make_cost_metric("area", target_delay=target_delay, technology=technology,
                              run_netlist_sim=run_netlist_sim)
    from spire.design_db import annotate
    d = DesignDB.open(db)
    keys = list(spec_keys) if spec_keys else \
        sorted(p.name for p in d.v1.iterdir() if p.is_dir()) if d.v1.is_dir() else []
    scored, skipped, failed = 0, 0, []
    measured: Dict[str, Dict[str, Any]] = {}
    for key in keys:
        slot = d.slot_dir(key)
        index = d.read_index(key)                   # derived from designs/ (source of truth)
        wanted = None
        if designs is not None:                 # exact ids or unique prefixes, within this slot
            wanted = set()
            for ref in designs:
                hits = [did for did in index if did == ref or did.startswith(ref)]
                if len(hits) == 1:
                    wanted.add(hits[0])
                elif len(hits) > 1:
                    raise DesignDBError(f"ambiguous design ref {ref!r} in slot {key[:12]}…: "
                                        f"{len(hits)} matches")
        for design_id in sorted(index):
            if wanted is not None and design_id not in wanted:
                continue
            if max_designs is not None and scored >= max_designs:
                break
            if not dry_run and not force and technology in (index[design_id].get("metrics") or {}):
                skipped += 1
                continue
            design_v = slot / "designs" / design_id / "design.v"
            if not design_v.exists():
                failed.append(f"{design_id}: design.v missing")
                continue
            with tempfile.TemporaryDirectory(prefix="db_score_") as td:
                w = Path(td)
                shutil.copyfile(design_v, w / "design.v")
                top = _top_module_name(design_v.read_text())
                cost = metric.evaluate(w, top_module=top, design_file=w / "design.v")
            if not cost.ok:
                failed.append(f"{design_id}: {getattr(cost, 'error', 'cost evaluation failed')}")
                continue
            stats = dict(cost.stats or {})
            values = {"area": stats.get("area"),
                      "delay": stats.get("delay", stats.get("runtime")),
                      "adp": stats.get("adp", stats.get("area_delay_product")),
                      "edap": stats.get("edap")}
            if values["adp"] is None and values["area"] is not None and values["delay"] is not None:
                values["adp"] = values["area"] * values["delay"]
            values = {k: v for k, v in values.items() if v is not None}
            measured[design_id] = values
            if not dry_run:
                # spire owns the write (metrics.json + index mirror, schema, reserved-name guard)
                annotate(key, design_id, tech=technology, values=values, raw=stats, force=True,
                         db=db)
            scored += 1
    return {"technology": technology, "scored": scored, "skipped": skipped, "failed": failed,
            "dry_run": dry_run, "measured": measured}

"""Workspace-shim backend for design-DB agent runs: ``eval`` (advisory) and ``insert`` (the gate).

The workspace shims (``./eval``, ``./db-insert``) are thin bash wrappers around
``python -m core.design_db_shims …`` with the slot/db **pinned at provisioning time** — the agent
supplies only its candidate file. The shims *are* the trust boundary: ``eval`` runs the slot's
frozen verification advisorily; ``insert`` is Spire's gate (verify → dedup → metrics → admit).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from spire.design_db import DesignDB, insert_design
from spire.design_db.verify import VerificationError, cec_check
from spire.design_db.verify_sim import run_frozen_tb


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _cmd_eval(args: argparse.Namespace) -> int:
    d = DesignDB.open(args.db, create=False)
    slot = d.slot_dir(args.slot)
    verification = d.read_json(slot / "verification.json", None)
    if verification is None:
        _print({"verdict": "ERROR", "reason": "slot has no frozen verification"})
        return 1
    design = Path(args.design)
    if not design.exists():
        _print({"verdict": "ERROR", "reason": f"design file not found: {design}"})
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="ddb_eval_") as td:
            if verification.get("method") == "cec":
                cec_check(design, slot / "golden.v", Path(td),
                          budget_s=args.budget or verification.get("budget_s", 120.0))
            else:
                run_frozen_tb(args.slot, design, Path(td), db=args.db,
                              budget_s=args.budget or verification.get("sim_budget_s", 300.0))
    except VerificationError as exc:
        _print({"verdict": "FAIL", "method": verification.get("method"),
                "reason": str(exc).splitlines()[0][:300]})
        return 2
    _print({"verdict": "PASS", "method": verification.get("method"),
            "note": "advisory only — ./db-insert runs the authoritative gate and admits"})
    return 0


def _cmd_insert(args: argparse.Namespace) -> int:
    try:
        res = insert_design(args.slot, Path(args.design), source=args.source, db=args.db,
                            budget_s=args.budget)
    except VerificationError as exc:
        _print({"verdict": "REJECTED", "type": type(exc).__name__,
                "reason": str(exc).splitlines()[0][:300]})
        return 2
    _print({"verdict": "ADMITTED", "design_id": res.design_id, "deduped": res.deduped,
            "metrics": res.metrics})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="design_db_shims")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--slot", required=True)
        p.add_argument("--db", default=None)
        p.add_argument("--design", default="design.v")
        p.add_argument("--budget", type=float, default=None)

    p = sub.add_parser("eval");   _common(p); p.set_defaults(func=_cmd_eval)
    p = sub.add_parser("insert"); _common(p)
    p.add_argument("--source", default="agent")
    p.set_defaults(func=_cmd_insert)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

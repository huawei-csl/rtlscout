#!/usr/bin/env python3
"""rtlscout management CLI — orphan sweep / cleanup for orchestrated-mode containers
(handover doc §5.5, layer 3).

This is plain CLI (only depends on the `docker` binary + core.containers), so it works
even after the harness/SDK process is gone — e.g. to clear running orphans left by a
SIGKILLed harness:

    python rtlscout_cli.py cleanup                 # stop+remove ALL rtlscout.managed=true
    python rtlscout_cli.py cleanup --session <id>  # just one campaign
    python rtlscout_cli.py cleanup --kill          # SIGKILL (panic)
    python rtlscout_cli.py list                     # list managed containers (this framework only)

It NEVER touches the VS Code devcontainer: selection is by the rtlscout.managed label
(which the devcontainer doesn't carry), and cleanup additionally refuses anything with a
devcontainer.local_folder label.
"""
import argparse
import json
import sys

from core.containers import LABEL_SESSION, cleanup, list_managed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="rtlscout", description="rtlscout container management")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cleanup", help="stop + remove managed containers (label-scoped)")
    c.add_argument("--session", default=None, help="only this campaign's session id")
    c.add_argument("--kill", action="store_true", help="SIGKILL instead of graceful stop")

    sub.add_parser("list", help="list this framework's managed containers")

    f = sub.add_parser("fill-db", help="fill a design-DB slot via an RTLScout campaign "
                                       "(seeds the original as baseline, admits via Spire's gate)")
    f.add_argument("--slot", required=True, help="spec_key (or unique prefix) of the slot")
    f.add_argument("--model", required=True, help="provider:model, e.g. openrouter:z-ai/glm-5.2")
    f.add_argument("--db", default=None, help="design-DB root (default: resolve)")
    f.add_argument("--objective", default="area")
    f.add_argument("--cost-metric", default=None, help="override the campaign cost metric")
    f.add_argument("--runs", type=int, default=1)
    f.add_argument("--max-steps", type=int, default=12)
    f.add_argument("--language", default="verilog")
    f.add_argument("--module-name", default=None)
    f.add_argument("--keep-runs", action="store_true", help="keep the campaign artifacts")

    s = sub.add_parser("db-score", help="stamp per-technology PPA metrics onto stored designs")
    s.add_argument("--db", default=None)
    s.add_argument("--slot", action="append", default=None, help="limit to slot(s); default all")
    s.add_argument("--technology", default="asap7")
    s.add_argument("--target-delay", type=float, default=500.0)
    s.add_argument("--netlist-sim", action="store_true", help="re-simulate the synthesized netlist")
    s.add_argument("--force", action="store_true", help="re-score even if already stamped")
    s.add_argument("--max-designs", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "fill-db":
        from spire.design_db import DesignDB, DesignDBError
        from core.design_db_fill import fill_slot
        try:
            d = DesignDB.open(args.db, create=False)
            hits = [p.name for p in d.v1.iterdir()
                    if p.is_dir() and p.name.startswith(args.slot)] if d.v1.is_dir() else []
            key = args.slot if (d.v1 / args.slot).is_dir() else (hits[0] if len(hits) == 1 else None)
            if key is None:
                raise DesignDBError(f"unknown or ambiguous slot {args.slot!r}")
            report = fill_slot(key, model=args.model, db=args.db, objective=args.objective,
                               cost_metric=args.cost_metric, module_name=args.module_name,
                               total_runs=args.runs, max_steps=args.max_steps,
                               language=args.language, keep_runs=args.keep_runs)
        except DesignDBError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if (report.admitted or report.deduped or report.seeded) else 1

    if args.cmd == "db-score":
        from core.design_db_fill import score_designs
        report = score_designs(args.slot, db=args.db, technology=args.technology,
                               target_delay=args.target_delay, run_netlist_sim=args.netlist_sim,
                               force=args.force, max_designs=args.max_designs)
        print(json.dumps(report, indent=2))
        return 0 if not report["failed"] else 1

    if args.cmd == "cleanup":
        report = cleanup(session=args.session, kill=args.kill)
        print(json.dumps(report, indent=2))
        if report["errors"]:
            return 1
        return 0

    if args.cmd == "list":
        rows = list_managed()
        if not rows:
            print("(no rtlscout.managed containers)")
            return 0
        for r in rows:
            labels = r.get("Labels", "")
            session = ""
            for kv in labels.split(","):
                if kv.startswith(f"{LABEL_SESSION}="):
                    session = kv.split("=", 1)[1]
            print(f"{r.get('Names',''):40s} {r.get('Status',''):24s} session={session}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

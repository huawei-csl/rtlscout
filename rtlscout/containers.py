"""Label-based management of rtlscout-launched containers (handover doc §5.5).

THE devcontainer-safety contract: managed containers are identified ONLY by the
``rtlscout.managed=true`` label — **never by image**. The VS Code devcontainer shares
``rtlscout:latest`` but carries no ``rtlscout.*`` labels, so every selector here is
guaranteed-disjoint from it by construction. Cleanup additionally refuses to touch any
container carrying ``devcontainer.local_folder`` (belt-and-suspenders).

This module is plain ``docker`` CLI (no new deps, matches the repo's shell-out style) and
is importable both by the harness (``ContainerSandbox``) and by the ``rtlscout`` cleanup
CLI (which must work even after the harness process is gone — handover §5.5 layer 3).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Dict, List, Optional

LABEL_MANAGED = "rtlscout.managed"
LABEL_SESSION = "rtlscout.session"
LABEL_ROLE = "rtlscout.role"
LABEL_RUN = "rtlscout.run"
LABEL_STARTED = "rtlscout.started"
DEVCONTAINER_LABEL = "devcontainer.local_folder"  # set by VS Code Dev Containers; never by us


def _docker(*args: str, check: bool = False, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def managed_filters(session: Optional[str] = None) -> List[str]:
    flt = ["--filter", f"label={LABEL_MANAGED}=true"]
    if session:
        flt += ["--filter", f"label={LABEL_SESSION}={session}"]
    return flt


def list_managed(session: Optional[str] = None, all_states: bool = True) -> List[Dict]:
    """Return the framework's containers (label-scoped). Never matches the devcontainer."""
    args = ["ps"] + (["-a"] if all_states else []) + managed_filters(session) + ["--format", "{{json .}}"]
    out = _docker(*args).stdout
    rows: List[Dict] = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _container_labels(container_id: str) -> Dict[str, str]:
    out = _docker("inspect", "--format", "{{json .Config.Labels}}", container_id).stdout.strip()
    try:
        return json.loads(out) or {}
    except json.JSONDecodeError:
        return {}


def has_devcontainer_label(container_id: str) -> bool:
    return DEVCONTAINER_LABEL in _container_labels(container_id)


def cleanup(session: Optional[str] = None, timeout: int = 10, kill: bool = False) -> Dict[str, List[str]]:
    """Stop + remove all managed containers (optionally one session). Refuses anything
    carrying ``devcontainer.local_folder``. Returns what it touched. Safe to run by hand
    after a SIGKILLed harness (orphan sweep, handover §5.5 layer 3)."""
    report: Dict[str, List[str]] = {"stopped": [], "removed": [], "skipped_devcontainer": [], "errors": []}
    for row in list_managed(session=session, all_states=True):
        cid = row.get("ID") or row.get("Id") or ""
        name = row.get("Names") or row.get("Name") or cid
        if not cid:
            continue
        if has_devcontainer_label(cid):
            report["skipped_devcontainer"].append(name)
            continue
        try:
            if kill:
                _docker("kill", cid)
            else:
                _docker("stop", "-t", str(timeout), cid)
            report["stopped"].append(name)
            _docker("rm", "-f", cid)
            report["removed"].append(name)
        except subprocess.SubprocessError as e:
            report["errors"].append(f"{name}: {e}")
    return report


def main(argv=None) -> int:
    """Management CLI: orphan sweep / cleanup for orchestrated-mode containers (handover doc §5.5, layer 3), plus
    the design-DB commands.

    Plain CLI (only the `docker` binary and this module), so it works even after the harness/SDK process is gone,
    e.g. to clear running orphans left by a SIGKILLed harness:

        python -m rtlscout.containers cleanup                 # stop+remove ALL rtlscout.managed=true
        python -m rtlscout.containers cleanup --session <id>  # just one campaign
        python -m rtlscout.containers cleanup --kill          # SIGKILL (panic)
        python -m rtlscout.containers list                    # list managed containers (this framework only)

    A checkout also has the root wrapper `rtlscout_cli.py`. It NEVER touches the VS Code devcontainer: selection
    is by the rtlscout.managed label (which the devcontainer doesn't carry), and cleanup additionally refuses
    anything with a devcontainer.local_folder label.
    """
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

    s = sub.add_parser("db-score", help="measure per-technology PPA on stored designs and "
                                        "annotate the DB (or --dry-run to just print numbers)")
    s.add_argument("--db", default=None)
    s.add_argument("--slot", action="append", default=None, help="limit to slot(s); default all")
    s.add_argument("--design", action="append", default=None,
                   help="limit to design_id(s) or unique prefixes within the selected slot(s)")
    s.add_argument("--technology", default="asap7")
    s.add_argument("--target-delay", type=float, default=500.0)
    s.add_argument("--netlist-sim", action="store_true", help="re-simulate the synthesized netlist")
    s.add_argument("--force", action="store_true", help="re-score even if already stamped")
    s.add_argument("--max-designs", type=int, default=None)
    s.add_argument("--dry-run", action="store_true",
                   help="measure only: print the values, write nothing to the DB")

    args = parser.parse_args(argv)

    if args.cmd == "fill-db":
        from spire.design_db import DesignDB, DesignDBError
        from rtlscout.design_db_fill import fill_slot
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
        from rtlscout.design_db_score import score_designs
        report = score_designs(args.slot, db=args.db, technology=args.technology,
                               target_delay=args.target_delay, run_netlist_sim=args.netlist_sim,
                               force=args.force, max_designs=args.max_designs,
                               designs=args.design, dry_run=args.dry_run)
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

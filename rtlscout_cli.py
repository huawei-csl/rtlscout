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

    args = parser.parse_args(argv)

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

"""Patchability gate helper (run with the venv python, tech_eval on sys.path):
for each design script, confirm the fpmul sweep's strict AST matcher finds the
main multiplier and adder. Prints one marker-prefixed JSON object per design
("GATE_RESULT {...}") — the import/patch machinery prints its own chatter, so
callers must filter on the marker.
"""
import json
import sys
from pathlib import Path


def main():
    from tech_eval.ppa_extract.sweeps.fpmul.script_to_component import load_component_cls
    for arg in sys.argv[1:]:
        path = Path(arg)
        entry = {"path": str(path), "ok": False, "error": None}
        sys.path.insert(0, str(path.parent))     # design-local imports
        try:
            load_component_cls(str(path))
            entry["ok"] = True
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        finally:
            sys.path.pop(0)
        print("GATE_RESULT " + json.dumps(entry), flush=True)


if __name__ == "__main__":
    main()

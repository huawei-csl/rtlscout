"""Agent machinery for design-DB slot optimization (R2).

Implements the handover protocol of ``metadocuments/DESIGN_DB_AND_SUBAGENTS.md`` §4:

- **agent definitions** — ``rtl-subcircuit`` (optimize one slot) and ``rtl-orchestrator``
  (decompose / dispatch / select), rendered as lean AGENTS.md + opencode.json;
- **workspace provisioning** — the shims ``eval`` / ``db-insert`` (wrapping
  ``core.design_db_shims`` with the slot pinned) and, for orchestrators, ``dispatch``;
- **the dispatch launcher** — the one sanctioned way to start a subcircuit agent
  (``opencode run`` sub-session), with the **depth guard** (`RTLSCOUT_DISPATCH_DEPTH`, cap 2)
  bounding recursion mechanically;
- **the trusted report** — built by tooling from the slot index (before/after diff + selection),
  never taken from the agent's own claims.

The dispatch payload is a *pointer* (`{db, spec_key, objective, budget}`): the golden, the frozen
verification, prior designs, and the starting point are all read from the slot on the shared
filesystem — no design files travel through the agent channel.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from spire.design_db import DesignDB, DesignDBError, pareto_front, select_design

DISPATCH_DEPTH_ENV = "RTLSCOUT_DISPATCH_DEPTH"
DISPATCH_DEPTH_CAP = 2
AGENT_MODEL_ENV = "RTLSCOUT_FILL_MODEL"        # same knob as the campaign filler
_REPO_ROOT = Path(__file__).resolve().parent.parent


# --- rendering ----------------------------------------------------------------------------------


def _ports_table(spec: Dict[str, Any]) -> str:
    return "\n".join(f"  - {p['dir']:6s} {p['name']}  ({p['width']} bit"
                     f"{'s' if p['width'] != 1 else ''}{', signed' if p['signed'] else ''})"
                     for p in spec["ports"])


def render_subcircuit_agents_md(spec: Dict[str, Any], verification: Dict[str, Any],
                                spec_key: str, slot_dir: Path, objective: str,
                                budget_min: float) -> str:
    method = verification.get("method", "cec")
    check = ("formal equivalence (CEC) against `golden.v`" if method == "cec"
             else "the frozen trace testbench (`tb.sv` + `vectors.dat` in the slot)")
    prior = "\n- `designs/` — previously admitted implementations (prior art; read, don't copy blindly)." \
        if (slot_dir / "designs").exists() else ""
    sp = "\n- `starting_point.py` — the current implementation's source (the primary starting point)." \
        if (slot_dir / "starting_point.py").exists() else ""
    return f"""# Task — implement and optimize one design-DB slot

Slot `{spec_key[:12]}…` at `{slot_dir}` — produce Verilog implementations that are **correct**
(verified by {check}) and minimize **{objective}**. You have roughly **{budget_min:g} minutes**;
you will be terminated automatically once the time budget runs out, so use your time wisely.

## The slot (read these files yourself)

- `{slot_dir}/golden.v` — the reference your design must be functionally equivalent to.{sp}{prior}
- `{slot_dir}/spec.json` — the interface. Your module's **ports must match exactly**:

{_ports_table(spec)}

(The module *name* is up to you; only the ports are checked.)

## Workflow

1. Write your implementation to `design.v` in this workspace.
2. `./eval design.v` — the advisory check (the same verification the gate runs). Iterate.
3. `./db-insert design.v` — the authoritative gate: it re-verifies, dedups structurally, stamps
   metrics, and admits. Rejections tell you why. **Only admitted designs count.**
4. Submit several structurally *different* correct designs if you can — the DB keeps them all and
   selection later picks per objective (area/delay Pareto matters, not just one winner).

## Rules

- Never modify anything under `{slot_dir}` — the slot is read-only for you; `./db-insert` is the
  only write path, and it verifies everything.
- Do not fabricate metrics or reports: the final report is computed by tooling from the DB.
- Correctness first, then {objective}.
"""


def render_orchestrator_agents_md(db_root: Path, objective: str, budget_min: float) -> str:
    return f"""# Task — orchestrate design-DB slot optimization

You coordinate; subagents implement. The design DB at `{db_root}` holds *slots* (subcircuits with a
golden reference). Your job: pick the slots worth optimizing, dispatch one subcircuit agent per
slot, and summarize. Budget ≈ **{budget_min:g} minutes** total; you will be terminated
automatically once it runs out.

## Tools

- `spire db ls` / `spire db show <name|key> --pareto` — inspect slots (registered names, designs,
  selection state). The manifest at `{db_root}/v1/manifest.json` is the reverse index.
- `./dispatch <spec_key> [--objective {objective}] [--budget-min N]` — the **only** way to start a
  subcircuit agent. It blocks until that agent finishes and prints the trusted report JSON
  (n_added, best, Pareto). Depth and budget are enforced by the shim, not by you.
- `spire db verify --slot <key> …` — if a slot has no frozen verification, choose one explicitly
  (`--auto` for the sim harness; CEC is the combinational default). Never guess: the command's
  errors list the options.

## Policy

- Prefer slots with no admitted designs beyond `original:*`, or with a weak Pareto front.
- Dispatch sequentially; read each report before deciding the next step.
- You never insert designs yourself and never edit slot files — subagents + the gate do that.
"""


def render_agent_opencode_config(model_spec: str, agent_name: str) -> Dict[str, Any]:
    """opencode.json for a slot-agent session — same permission posture as the `rtl` agent."""
    from core.opencode_backend import _permissions
    perms = _permissions(yolo=False)
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": model_spec,
        "instructions": ["AGENTS.md"],
        "permission": perms,
        "agent": {agent_name: {
            "description": f"design-DB {agent_name} (non-interactive)",
            "mode": "primary",
            "model": model_spec,
            "permission": perms,
            "tools": {"write": True, "edit": True, "bash": True, "read": True},
        }},
    }


# --- provisioning -------------------------------------------------------------------------------


def _write_shim(path: Path, module_args: str) -> None:
    path.write_text("#!/usr/bin/env bash\n"
                    f"PYTHONPATH={shlex.quote(str(_REPO_ROOT))} "
                    f"exec {shlex.quote(sys.executable)} -m {module_args} \"$@\"\n")
    path.chmod(0o755)


def provision_slot_workspace(spec_key: str, workdir: Path, *, db: Optional[Any] = None,
                             objective: str = "area", model_spec: str = "openrouter/model",
                             budget_min: float = 10.0) -> Path:
    """Write AGENTS.md + opencode.json + the eval/db-insert shims for one slot agent."""
    d = DesignDB.open(db, create=False)
    slot = d.slot_dir(spec_key)
    spec = d.read_json(slot / "spec.json", None)
    if spec is None:
        raise DesignDBError(f"unknown slot {spec_key[:12]}…")
    verification = d.read_json(slot / "verification.json", None)
    if verification is None:
        raise DesignDBError("slot has no frozen verification — freeze one first "
                            "(spire db verify --slot <key> …)")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "AGENTS.md").write_text(render_subcircuit_agents_md(
        spec, verification, spec_key, slot, objective, budget_min))
    (workdir / "opencode.json").write_text(
        json.dumps(render_agent_opencode_config(model_spec, "rtl-subcircuit"), indent=2) + "\n")
    base = f"core.design_db_shims {{cmd}} --slot {spec_key} --db {shlex.quote(str(d.root))}"
    _write_shim(workdir / "eval", base.format(cmd="eval") + " --design")
    _write_shim(workdir / "db-insert",
                base.format(cmd="insert") + " --source agent:rtl-subcircuit --design")
    return workdir


def provision_orchestrator_workspace(workdir: Path, *, db: Optional[Any] = None,
                                     objective: str = "area",
                                     model_spec: str = "openrouter/model",
                                     budget_min: float = 30.0) -> Path:
    d = DesignDB.open(db, create=False)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "AGENTS.md").write_text(
        render_orchestrator_agents_md(d.root, objective, budget_min))
    (workdir / "opencode.json").write_text(
        json.dumps(render_agent_opencode_config(model_spec, "rtl-orchestrator"), indent=2) + "\n")
    _write_shim(workdir / "dispatch",
                f"core.design_db_agents dispatch --db {shlex.quote(str(d.root))} --slot")
    return workdir


# --- the trusted report ---------------------------------------------------------------------------


def build_report(spec_key: str, *, db: Optional[Any] = None, objective: str = "area",
                 before_ids: Optional[set] = None) -> Dict[str, Any]:
    """The handover report — computed from the DB, never from agent claims."""
    d = DesignDB.open(db, create=False)
    index = d.read_json(d.slot_dir(spec_key) / "index.json", {})
    added = sorted(set(index) - (before_ids or set()))
    sel = select_design(spec_key, objective=objective, db=db, record=True) if index else None
    report: Dict[str, Any] = {
        "spec_key": spec_key, "objective": objective,
        "n_designs": len(index), "n_added": len(added), "added": added,
        "best": None, "pareto": pareto_front(spec_key, db=db) if index else [],
    }
    if sel is not None:
        report["best"] = {"design_id": sel.design_id, "metric": sel.metric,
                          "metrics": sel.entry.get("metrics", {})}
    return report


# --- dispatch (the one sanctioned launcher) -------------------------------------------------------


def dispatch_subcircuit(spec_key: str, *, db: Optional[Any] = None, objective: str = "area",
                        model: Optional[str] = None, budget_min: float = 10.0,
                        workdir: Optional[Path] = None,
                        opencode_bin: str = "opencode") -> Dict[str, Any]:
    """Launch one ``rtl-subcircuit`` agent on a slot and return the trusted report.

    Depth-guarded (``RTLSCOUT_DISPATCH_DEPTH``, cap 2): a dispatched agent may dispatch further,
    but recursion is bounded by the shim, not by prompt goodwill.
    """
    depth = int(os.environ.get(DISPATCH_DEPTH_ENV, "0"))
    if depth >= DISPATCH_DEPTH_CAP:
        raise DesignDBError(f"dispatch depth cap reached ({depth} ≥ {DISPATCH_DEPTH_CAP}) — "
                            f"refusing to launch another agent")
    model = model or os.environ.get(AGENT_MODEL_ENV)
    if not model:
        raise DesignDBError(f"dispatch needs a model: pass model=... or set ${AGENT_MODEL_ENV}")
    if shutil.which(opencode_bin) is None:
        raise DesignDBError(f"{opencode_bin!r} not found on PATH")
    model_spec = model.replace(":", "/", 1)     # provider:model -> provider/model (opencode form)

    d = DesignDB.open(db, create=False)
    before = set(d.read_json(d.slot_dir(spec_key) / "index.json", {}))

    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ddb_dispatch_"))
    provision_slot_workspace(spec_key, workdir, db=db, objective=objective,
                             model_spec=model_spec, budget_min=budget_min)
    kickoff = (f"Optimize design-DB slot {spec_key}. Read AGENTS.md first; the slot files are on "
               f"disk. Objective: minimize {objective}. Use ./eval to iterate and ./db-insert to "
               f"submit. You will be terminated automatically once the time budget runs out.")
    env = dict(os.environ)
    env[DISPATCH_DEPTH_ENV] = str(depth + 1)
    cmd = f"exec {shlex.quote(opencode_bin)} run --format json -m {shlex.quote(model_spec)} " \
          f"--agent rtl-subcircuit {shlex.quote(kickoff)}"
    started = time.time()
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=str(workdir), env=env,
                              capture_output=True, text=True, timeout=budget_min * 60)
        agent_note = f"agent exited rc={proc.returncode}"
        (workdir / "opencode_session.log").write_text(proc.stdout + "\n--- stderr ---\n"
                                                      + proc.stderr)
    except subprocess.TimeoutExpired:
        agent_note = f"agent terminated at the {budget_min:g}-minute budget"

    report = build_report(spec_key, db=db, objective=objective, before_ids=before)
    report["agent"] = {"model": model, "note": agent_note,
                       "duration_s": round(time.time() - started, 1),
                       "workspace": str(workdir)}
    (workdir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="design_db_agents")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dispatch", help="launch one rtl-subcircuit agent on a slot")
    p.add_argument("--slot", required=True)
    p.add_argument("--db", default=None)
    p.add_argument("--objective", default="area")
    p.add_argument("--model", default=None)
    p.add_argument("--budget-min", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        report = dispatch_subcircuit(args.slot, db=args.db, objective=args.objective,
                                     model=args.model, budget_min=args.budget_min)
    except DesignDBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

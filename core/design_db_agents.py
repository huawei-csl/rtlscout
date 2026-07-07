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

import difflib
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

from spire.design_db import (DesignDB, DesignDBError, pareto_front, seed_original,
                             select_design)
from spire.design_db.store import DB_ENV
from spire.design_db.verify import VerificationError

DISPATCH_DEPTH_ENV = "RTLSCOUT_DISPATCH_DEPTH"
DISPATCH_DEPTH_CAP = 2
AGENT_MODEL_ENV = "RTLSCOUT_FILL_MODEL"        # same knob as the campaign filler
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _agent_env(depth: int, model: str, db_root: Path) -> Dict[str, str]:
    env = dict(os.environ)
    env[DISPATCH_DEPTH_ENV] = str(depth + 1)
    env[AGENT_MODEL_ENV] = model              # nested shim launches inherit the model choice
    env[DB_ENV] = str(db_root)                # `spire db ...` inside the session hits the same DB
    return env


def _run_agent_session(cmd: str, workdir: Path, env: Dict[str, str], budget_min: float) -> str:
    """Run one opencode session; always leave opencode_session.log in the workspace."""
    def _txt(x: Any) -> str:
        # TimeoutExpired carries the captured streams as *bytes* even under text=True
        return x.decode(errors="replace") if isinstance(x, bytes) else (x or "")
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=str(workdir), env=env,
                              capture_output=True, text=True, timeout=budget_min * 60)
        note = f"agent exited rc={proc.returncode}"
        out, err = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        note = f"agent terminated at the {budget_min:g}-minute budget"
        out, err = _txt(exc.stdout), _txt(exc.stderr)
    (workdir / "opencode_session.log").write_text(out + "\n--- stderr ---\n" + err)
    return note


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

1. **Author in spire** (the ecosystem's design language; Verilog is only the intermediate
   representation): write `design.py` in this workspace defining `build() -> Netlist/Component`
   — `starting_point.py` shows the current implementation in exactly that form. The gate
   elaborates it and stores your python source with the design. If you must, authoring
   `design.v` directly is also accepted (no source stored then).
2. `./eval design.py` — the advisory check (the same verification the gate runs). Iterate.
3. `./db-insert design.py` — the authoritative gate: it elaborates, re-verifies, dedups
   structurally, stamps metrics, and admits. Rejections tell you why. **Only admitted designs
   count.**
4. Submit several structurally *different* correct designs if you can — the DB keeps them all and
   selection later picks per objective (area/delay Pareto matters, not just one winner).

## Rules

- Never modify anything under `{slot_dir}` — the slot is read-only for you; `./db-insert` is the
  only write path, and it verifies everything.
- Do not fabricate metrics or reports: the final report is computed by tooling from the DB.
- Correctness first, then {objective}.
"""


def render_dv_prep_agents_md(spec: Dict[str, Any], spec_key: str, slot_dir: Path,
                             budget_min: float) -> str:
    clock = spec.get("clock") or {}
    return f"""# Task — author a stimulus generator for one design-DB slot (dv prep)

Slot `{spec_key[:12]}…` at `{slot_dir}` needs a **simulation verification**: your job is to write
the *stimulus only*. Expected outputs are always produced by tooling simulating the golden — you
never write answers, and you never see or write candidate designs. Budget ≈ **{budget_min:g}
minutes**; you will be terminated automatically once it runs out.

## Understand the interface first (read these)

- `{slot_dir}/golden.v` — the reference implementation (its behavior defines the protocol).
- `{slot_dir}/starting_point.py` / `{slot_dir}/spec.json` — source + interface.
  Data inputs to drive (clock `{clock.get('clk')}` / reset `{clock.get('rst')}` are driven by the
  testbench, not by you):

{_ports_table(spec)}

## Deliverable

Write **`stimulus.py`** in this workspace, defining exactly:

```python
def generate(ports, n_vectors, seed):
    # ports: [{{"name", "width", "signed", "dir"}}] — the data inputs above
    # yield one dict {{input_name: int}} per cycle/vector
    ...
```

Aim for stimulus that *exercises the block*: reset-adjacent behavior, corner values, bursts,
protocol sequences — not just uniform random. The stimulus is frozen afterwards and stays open to
human review; weak stimulus weakens the check for every future design in this slot.

## Workflow

1. Read the golden + source; understand the protocol.
2. Write `stimulus.py`; run `./check-stimulus` to validate it loads and produces vectors. Iterate.
3. Done — tooling simulates the golden with your generator and freezes the verification. You do
   not freeze, insert, or report anything yourself.
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
- `./dv-prep <spec_key> [--budget-min N]` — for an *unfrozen sequential slot*: launches the
  stimulus-authoring agent, then tooling freezes the sim verification. Run it **before**
  dispatching an optimizer at such a slot.
- `spire db set-verification --slot <key> …` — if a slot has no frozen verification, choose one explicitly
  (`--auto` for the sim harness; CEC is the combinational default). Never guess: the command's
  errors list the options.

## Policy

- Read the manifest first: each slot's `class` and whether it is verified (`spire db show <key>`
  — a missing `verification` means unverified).
- **Sequential slot without a frozen verification → `./dv-prep <key>` first**, then dispatch it.
  Combinational slots are CEC-verified by default — dispatch them directly.
- Dispatch each slot **once**, sequentially, with a small sub-budget (`--budget-min 3` unless told
  otherwise). The commands block until the subagent finishes — that is normal; read each JSON
  report before deciding the next step.
- Prefer slots with no admitted designs beyond `original:*`, or with a weak Pareto front.
- You never insert designs yourself and never edit slot files — subagents + the gate do that.
"""


def render_designer_agents_md(db_root: Path, objective: str, budget_min: float) -> str:
    return f"""# Task — improve a full design through the design DB (rtl-designer)

Mission: reduce the **{objective}** (tooling metric: estimated transistors) of the full design in
`design.py` in this workspace, preserving its function exactly. You do it *indirectly*: slot the
design's subcircuits into the design DB at `{db_root}`, have subcircuit agents fill the slots with
verified better implementations, and recompile — the best admitted design splices in
automatically. Budget ≈ **{budget_min:g} minutes** total; you will be terminated automatically
once it runs out.

## Tools

- `./compile` — runs `design.py` (which fires the `@from_design_db` decorators — slots register,
  selections splice — and writes `design.v`), then measures it. Prints JSON: the full-design
  `cost` (+ `cost_metric`) and the `slots` table (name → spec_key, n_designs, selected_id). This
  is the only measurement that counts.
- `./dispatch <spec_key> --objective {objective} --budget-min N` — the only way to start a
  subcircuit agent on a slot. Blocks until that agent finishes; prints the trusted report JSON.
- `./dv-prep <spec_key> --budget-min N --vectors 64` — only needed for a *sequential* slot with
  no frozen verification (combinational slots are CEC-gated automatically).
- `spire db ls` / `spire db show <name|key> --pareto` — inspect the DB.

## Workflow

1. Read `design.py`. Slot candidates are its small pure helper functions computing signals
   (e.g. `def f(a, b): return a * b`) — called from `build()` on spire expressions. (The file
   already writes `design.v` when run — leave that as is.)
2. Decorate each candidate with `@from_design_db(objective="{objective}")` and add the one
   import `from spire.design_db import from_design_db`. **Change nothing else.**
3. `./compile` — registers the slots. First run prints "no admitted design … using the original
   logic" notes: that is normal. Note the baseline `cost` and the slot spec_keys.
4. For each slot, once, sequentially: `./dispatch <spec_key> --objective {objective}
   --budget-min 3`. The command blocks for minutes — wait for its JSON; read it before moving on.
5. `./compile` again — selections splice in. Compare `cost` with step 3.
6. Summarize: per-slot outcome (from the dispatch reports) and full-design `cost`
   before → after (from the two compiles). Use only tooling-printed numbers.

## Rules

- `design.py` edits: the decorators + the one import, nothing else. No logic, port, or `build()`
  changes — your diff is part of the reviewed report.
- Never write into `{db_root}` by hand; inserts happen only through the subagents' gate.
- Dispatch each slot once; if a dispatch fails, note it — do not retry.
- Never invent numbers: `./compile` and the dispatch reports are the ground truth.
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
                            "(spire db set-verification --slot <key> …)")
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
    _write_shim(workdir / "dv-prep",
                f"core.design_db_agents dv-prep --db {shlex.quote(str(d.root))} --slot")
    return workdir


def provision_designer_workspace(design_file: Path, workdir: Path, *, db: Optional[Any] = None,
                                 objective: str = "area", technology: Optional[str] = None,
                                 model_spec: str = "openrouter/model",
                                 budget_min: float = 30.0) -> Path:
    """Copy the design file into the workspace (the agent edits the copy, never the original)
    + AGENTS.md + opencode.json + the compile/dispatch/dv-prep shims."""
    d = DesignDB.open(db, create=True)          # the designer may bootstrap an empty DB
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(design_file, workdir / "design.py")
    (workdir / "AGENTS.md").write_text(render_designer_agents_md(d.root, objective, budget_min))
    (workdir / "opencode.json").write_text(
        json.dumps(render_agent_opencode_config(model_spec, "rtl-designer"), indent=2) + "\n")
    tech_arg = f" --technology {shlex.quote(technology)}" if technology else ""
    _write_shim(workdir / "compile",
                f"core.design_db_agents compile-design --db {shlex.quote(str(d.root))} "
                f"--file {shlex.quote(str(workdir / 'design.py'))}{tech_arg}")
    _write_shim(workdir / "dispatch",
                f"core.design_db_agents dispatch --db {shlex.quote(str(d.root))} --slot")
    _write_shim(workdir / "dv-prep",
                f"core.design_db_agents dv-prep --db {shlex.quote(str(d.root))} --slot")
    return workdir


def provision_dv_prep_workspace(spec_key: str, workdir: Path, *, db: Optional[Any] = None,
                                model_spec: str = "openrouter/model",
                                budget_min: float = 10.0) -> Path:
    """AGENTS.md + opencode.json + the check-stimulus shim for a dv-prep agent."""
    d = DesignDB.open(db, create=False)
    slot = d.slot_dir(spec_key)
    spec = d.read_json(slot / "spec.json", None)
    if spec is None:
        raise DesignDBError(f"unknown slot {spec_key[:12]}…")
    existing = d.read_json(slot / "verification.json", None)
    if existing is not None and int(existing.get("tier", 0)) >= 1:
        raise DesignDBError("slot already has a frozen sim verification (immutable) — "
                            "dv-prep has nothing to do")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "AGENTS.md").write_text(
        render_dv_prep_agents_md(spec, spec_key, slot, budget_min))
    (workdir / "opencode.json").write_text(
        json.dumps(render_agent_opencode_config(model_spec, "rtl-dv-prep"), indent=2) + "\n")
    _write_shim(workdir / "check-stimulus",
                f"core.design_db_shims stimulus-check --slot {spec_key} "
                f"--db {shlex.quote(str(d.root))} --stimulus")
    return workdir


# --- the trusted report ---------------------------------------------------------------------------


def build_report(spec_key: str, *, db: Optional[Any] = None, objective: str = "area",
                 before_ids: Optional[set] = None) -> Dict[str, Any]:
    """The handover report — computed from the DB, never from agent claims."""
    d = DesignDB.open(db, create=False)
    index = d.read_index(spec_key)                  # derived from designs/ (source of truth)
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
                        workdir: Optional[Path] = None, seed_baseline: bool = True,
                        opencode_bin: str = "opencode") -> Dict[str, Any]:
    """Launch one ``rtl-subcircuit`` agent on a slot and return the trusted report.

    Seeds the slot's own golden first (the selection floor — a correct-but-worse agent design can
    never win). Depth-guarded (``RTLSCOUT_DISPATCH_DEPTH``, cap 2): a dispatched agent may
    dispatch further, but recursion is bounded by the shim, not by prompt goodwill.
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
    seeded = None
    if seed_baseline:
        try:
            seeded = seed_original(spec_key, db=db).design_id
        except VerificationError as exc:        # a golden failing its own gate is a slot problem
            seeded = f"seed-failed: {str(exc).splitlines()[0][:120]}"
    before = set(d.derive_index(spec_key))

    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ddb_dispatch_"))
    provision_slot_workspace(spec_key, workdir, db=db, objective=objective,
                             model_spec=model_spec, budget_min=budget_min)
    kickoff = (f"Optimize design-DB slot {spec_key}. Read AGENTS.md first; the slot files are on "
               f"disk. Objective: minimize {objective}. Use ./eval to iterate and ./db-insert to "
               f"submit. You will be terminated automatically once the time budget runs out.")
    env = _agent_env(depth, model, d.root)
    cmd = f"exec {shlex.quote(opencode_bin)} run --format json -m {shlex.quote(model_spec)} " \
          f"--agent rtl-subcircuit {shlex.quote(kickoff)}"
    started = time.time()
    agent_note = _run_agent_session(cmd, workdir, env, budget_min)

    report = build_report(spec_key, db=db, objective=objective, before_ids=before)
    report["seeded"] = seeded
    report["agent"] = {"model": model, "note": agent_note,
                       "duration_s": round(time.time() - started, 1),
                       "workspace": str(workdir)}
    (workdir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def dispatch_dv_prep(spec_key: str, *, db: Optional[Any] = None, model: Optional[str] = None,
                     budget_min: float = 10.0, n_vectors: int = 256, seed: int = 0,
                     workdir: Optional[Path] = None,
                     opencode_bin: str = "opencode") -> Dict[str, Any]:
    """Launch one ``rtl-dv-prep`` agent to author a stimulus generator, then have tooling freeze
    the Tier-2 sim verification (golden-simulated outputs; no coverage gating — human review of
    the frozen stimulus is the quality backstop). The agent authors *stimulus only*."""
    depth = int(os.environ.get(DISPATCH_DEPTH_ENV, "0"))
    if depth >= DISPATCH_DEPTH_CAP:
        raise DesignDBError(f"dispatch depth cap reached ({depth} ≥ {DISPATCH_DEPTH_CAP})")
    model = model or os.environ.get(AGENT_MODEL_ENV)
    if not model:
        raise DesignDBError(f"dv-prep needs a model: pass model=... or set ${AGENT_MODEL_ENV}")
    if shutil.which(opencode_bin) is None:
        raise DesignDBError(f"{opencode_bin!r} not found on PATH")
    model_spec = model.replace(":", "/", 1)

    d = DesignDB.open(db, create=False)
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ddb_dvprep_"))
    provision_dv_prep_workspace(spec_key, workdir, db=db, model_spec=model_spec,
                                budget_min=budget_min)
    kickoff = (f"Author the stimulus generator for design-DB slot {spec_key}. Read AGENTS.md "
               f"first. Deliverable: stimulus.py with generate(ports, n_vectors, seed); validate "
               f"it with ./check-stimulus. You will be terminated automatically once the time "
               f"budget runs out.")
    env = _agent_env(depth, model, d.root)
    cmd = f"exec {shlex.quote(opencode_bin)} run --format json -m {shlex.quote(model_spec)} " \
          f"--agent rtl-dv-prep {shlex.quote(kickoff)}"
    started = time.time()
    agent_note = _run_agent_session(cmd, workdir, env, budget_min)

    report: Dict[str, Any] = {"spec_key": spec_key, "frozen": None,
                              "agent": {"model": model, "note": agent_note,
                                        "duration_s": round(time.time() - started, 1),
                                        "workspace": str(workdir)}}
    stimulus = workdir / "stimulus.py"
    if stimulus.exists():
        from spire.design_db.verify_sim import freeze_sim_verification
        verification = freeze_sim_verification(spec_key, stimulus_file=stimulus,
                                               n_vectors=n_vectors, seed=seed, db=db)
        # Record honest authorship (spire tags stimulus files "human"; this one is agent-authored).
        verification["stimulus_author"] = "agent:rtl-dv-prep"
        d.write_json(d.slot_dir(spec_key) / "verification.json", verification)
        shutil.copyfile(stimulus, d.slot_dir(spec_key) / "stimulus.py")   # review artifact
        report["frozen"] = verification
    else:
        report["error"] = "agent produced no stimulus.py — slot left unverified"
    (workdir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def run_orchestrator(*, db: Optional[Any] = None, objective: str = "area",
                     model: Optional[str] = None, budget_min: float = 30.0,
                     workdir: Optional[Path] = None, kickoff_extra: str = "",
                     opencode_bin: str = "opencode") -> Dict[str, Any]:
    """Launch the ``rtl-orchestrator`` session: it inspects the DB, prepares verifications
    (``./dv-prep``) and dispatches subcircuit agents (``./dispatch``) — all launches go through
    the depth-guarded shims. The report is tooling-derived from the manifest before/after."""
    depth = int(os.environ.get(DISPATCH_DEPTH_ENV, "0"))
    if depth >= DISPATCH_DEPTH_CAP:
        raise DesignDBError(f"dispatch depth cap reached ({depth} ≥ {DISPATCH_DEPTH_CAP})")
    model = model or os.environ.get(AGENT_MODEL_ENV)
    if not model:
        raise DesignDBError(f"orchestrator needs a model: pass model=... or set ${AGENT_MODEL_ENV}")
    if shutil.which(opencode_bin) is None:
        raise DesignDBError(f"{opencode_bin!r} not found on PATH")
    model_spec = model.replace(":", "/", 1)

    d = DesignDB.open(db, create=False)
    before = d.read_json(d.manifest_path, {"slots": {}})
    before_counts = {name: len(d.derive_index(e["spec_key"]))
                     for name, e in before.get("slots", {}).items() if e.get("spec_key")}
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ddb_orch_"))
    provision_orchestrator_workspace(workdir, db=db, objective=objective,
                                     model_spec=model_spec, budget_min=budget_min)
    kickoff = (f"Orchestrate design-DB optimization at {d.root}. Read AGENTS.md first; inspect "
               f"slots with `spire db ls` / the manifest, prepare verifications with ./dv-prep "
               f"where needed, dispatch subcircuit agents with ./dispatch, and summarize. "
               f"Objective: {objective}. You will be terminated automatically once the time "
               f"budget runs out.")
    if kickoff_extra:
        kickoff += " " + kickoff_extra
    env = _agent_env(depth, model, d.root)
    nested = workdir / "nested"           # child dispatch/dv-prep workspaces land here
    nested.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(nested)
    cmd = f"exec {shlex.quote(opencode_bin)} run --format json -m {shlex.quote(model_spec)} " \
          f"--agent rtl-orchestrator {shlex.quote(kickoff)}"
    started = time.time()
    agent_note = _run_agent_session(cmd, workdir, env, budget_min)

    after = d.read_json(d.manifest_path, {"slots": {}})
    slots_report = {}
    for name, entry in sorted(after.get("slots", {}).items()):
        slots_report[name] = {
            "spec_key": entry.get("spec_key"),
            "n_designs": len(d.derive_index(entry["spec_key"])) if entry.get("spec_key") else 0,
            "n_designs_before": before_counts.get(name, 0),
            "selected_id": entry.get("selected_id"),
        }
    report = {"objective": objective, "slots": slots_report,
              "agent": {"model": model, "note": agent_note,
                        "duration_s": round(time.time() - started, 1),
                        "workspace": str(workdir)}}
    (workdir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


# --- the full-design designer role ----------------------------------------------------------------


def compile_design(design_file: Path, *, db: Optional[Any] = None,
                   technology: Optional[str] = None) -> Dict[str, Any]:
    """Compile a spire design file through RTLScout's **native evaluator** and measure it.

    ``evaluate(language="spirehdl", …)`` runs ``design.py`` as a subprocess (which, inheriting
    ``$SPIREHDL_DB_PATH``, fires the ``@from_design_db`` decorators — slots register, selections
    splice — and writes ``design.v`` via ``to_verilog_file``), then measures the result with the
    cost metric. Correctness is **not** checked (``run_rtl_sim=False``, ``run_cec=False``): each
    spliced slot is already verified-equivalent to its golden, and the composed design has no
    benchmark reference. Measures transistors by default (fast); ``technology`` selects the PPA
    (OpenROAD) area flow. Returns the cost + slot snapshot + the generated Verilog."""
    from core.cost import make_cost_metric
    from core.evaluation import SPIREHDL_VERILOG_OUTPUT, evaluate
    design_file = Path(design_file).resolve()
    d = DesignDB.open(db, create=True)
    metric = (make_cost_metric("area", technology=technology, run_netlist_sim=False)
              if technology else make_cost_metric("transistors"))
    old_env = os.environ.get(DB_ENV)
    os.environ[DB_ENV] = str(d.root)            # the design subprocess's decorators resolve here
    try:
        with tempfile.TemporaryDirectory(prefix="ddb_compile_") as td:
            w = Path(td)
            shutil.copyfile(design_file, w / "design.py")
            result = evaluate(w, cost_metric=metric, language="spirehdl",
                              design_file="design.py", run_rtl_sim=False, run_cec=False)
            vpath = w / SPIREHDL_VERILOG_OUTPUT
            verilog = vpath.read_text() if vpath.exists() else ""
            py_out = result.python_run_output or ""
    finally:
        if old_env is None:
            os.environ.pop(DB_ENV, None)
        else:
            os.environ[DB_ENV] = old_env
    if not result.cost.ok:
        raise DesignDBError(f"compile/measure failed: {result.cost.error or py_out[-400:] or 'no design.v produced (design.py must to_verilog_file())'}")
    manifest = d.read_json(d.manifest_path, {"slots": {}})
    slots = {name: {"spec_key": e.get("spec_key"),
                    "n_designs": len(d.derive_index(e["spec_key"])) if e.get("spec_key") else 0,
                    "selected_id": e.get("selected_id")}
             for name, e in sorted(manifest.get("slots", {}).items())}
    notes = [ln for ln in py_out.splitlines() if ln.startswith("[spire.design_db]")]
    return {"design_file": str(design_file), "db": str(d.root),
            "cost": result.cost_value, "cost_metric": result.cost_metric_name,
            "stats": dict(result.cost.stats or {}),
            "slots": slots, "notes": notes, "verilog": verilog}


def run_designer(design_file: Path, *, db: Optional[Any] = None, objective: str = "area",
                 technology: Optional[str] = None, model: Optional[str] = None,
                 budget_min: float = 30.0, workdir: Optional[Path] = None,
                 kickoff_extra: str = "", opencode_bin: str = "opencode") -> Dict[str, Any]:
    """Launch the full-design ``rtl-designer`` session: the agent decorates the subcircuit
    functions in a *copy* of the design file, compiles, fills the slots through the gated
    subagents, recompiles, and summarizes. Trust: slot inserts stay hard-gated; the design-file
    edit is soft-gated — the unified diff is embedded in the report for human review; the
    before/after transistor numbers come from tooling compiles, never from the agent."""
    depth = int(os.environ.get(DISPATCH_DEPTH_ENV, "0"))
    if depth >= DISPATCH_DEPTH_CAP:
        raise DesignDBError(f"dispatch depth cap reached ({depth} ≥ {DISPATCH_DEPTH_CAP})")
    model = model or os.environ.get(AGENT_MODEL_ENV)
    if not model:
        raise DesignDBError(f"designer needs a model: pass model=... or set ${AGENT_MODEL_ENV}")
    if shutil.which(opencode_bin) is None:
        raise DesignDBError(f"{opencode_bin!r} not found on PATH")
    model_spec = model.replace(":", "/", 1)

    design_file = Path(design_file).resolve()
    d = DesignDB.open(db, create=True)
    before_manifest = d.read_json(d.manifest_path, {"slots": {}})
    before_counts = {name: len(d.derive_index(e["spec_key"]))
                     for name, e in before_manifest.get("slots", {}).items()
                     if e.get("spec_key")}
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ddb_designer_"))
    workdir.mkdir(parents=True, exist_ok=True)

    baseline = compile_design(design_file, db=d.root, technology=technology)   # trusted baseline
    (workdir / "baseline.v").write_text(baseline.pop("verilog"))

    provision_designer_workspace(design_file, workdir, db=d.root, objective=objective,
                                 technology=technology, model_spec=model_spec,
                                 budget_min=budget_min)
    kickoff = (f"Improve the full design in design.py of this workspace through the design DB at "
               f"{d.root}. Read AGENTS.md first and follow its workflow: decorate the subcircuit "
               f"helper functions, ./compile, fill each slot with ./dispatch (./dv-prep first "
               f"only if a slot is sequential and unverified), ./compile again, then summarize "
               f"per-slot and full-design results. Objective: {objective}. You will be "
               f"terminated automatically once the time budget runs out.")
    if kickoff_extra:
        kickoff += " " + kickoff_extra
    env = _agent_env(depth, model, d.root)
    nested = workdir / "nested"                 # child dispatch/dv-prep workspaces land here
    nested.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(nested)
    cmd = f"exec {shlex.quote(opencode_bin)} run --format json -m {shlex.quote(model_spec)} " \
          f"--agent rtl-designer {shlex.quote(kickoff)}"
    started = time.time()
    agent_note = _run_agent_session(cmd, workdir, env, budget_min)

    edited = workdir / "design.py"
    final = final_error = None
    try:                                        # the agent may have broken the file — report it
        final = compile_design(edited, db=d.root, technology=technology)
        (workdir / "final.v").write_text(final.pop("verilog"))
    except Exception as exc:
        final_error = f"{type(exc).__name__}: {exc}"
    diff = "".join(difflib.unified_diff(
        design_file.read_text().splitlines(keepends=True),
        edited.read_text().splitlines(keepends=True),
        fromfile="design.py (original)", tofile="design.py (agent)"))

    after_manifest = d.read_json(d.manifest_path, {"slots": {}})
    slots_report = {}
    for name, entry in sorted(after_manifest.get("slots", {}).items()):
        slots_report[name] = {
            "spec_key": entry.get("spec_key"),
            "n_designs": len(d.derive_index(entry["spec_key"])) if entry.get("spec_key") else 0,
            "n_designs_before": before_counts.get(name, 0),
            "selected_id": entry.get("selected_id"),
        }
    b_cost, f_cost = baseline["cost"], (final["cost"] if final else None)
    report = {
        "objective": objective, "design_file": str(design_file),
        "cost_metric": baseline["cost_metric"],
        "baseline_cost": b_cost,
        "final_cost": f_cost,
        "improvement": (b_cost - f_cost) if (b_cost is not None and f_cost is not None) else None,
        "final_compile_error": final_error,
        "slots": slots_report, "design_diff": diff,
        "notes": {"baseline": baseline["notes"], "final": final["notes"] if final else []},
        "agent": {"model": model, "note": agent_note,
                  "duration_s": round(time.time() - started, 1), "workspace": str(workdir)},
    }
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
    p.set_defaults(kind="dispatch")

    p = sub.add_parser("dv-prep", help="launch one rtl-dv-prep agent (stimulus authoring + freeze)")
    p.add_argument("--slot", required=True)
    p.add_argument("--db", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--budget-min", type=float, default=10.0)
    p.add_argument("--vectors", type=int, default=256)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(kind="dv-prep")

    p = sub.add_parser("orchestrate", help="launch the rtl-orchestrator session over the DB")
    p.add_argument("--db", default=None)
    p.add_argument("--objective", default="area")
    p.add_argument("--model", default=None)
    p.add_argument("--budget-min", type=float, default=30.0)
    p.set_defaults(kind="orchestrate")

    p = sub.add_parser("compile-design",
                       help="compile a spire design file (native spirehdl eval) + measure cost")
    p.add_argument("--file", required=True)
    p.add_argument("--db", default=None)
    p.add_argument("--technology", default=None,
                   help="measure PPA area under this technology (default: fast transistors)")
    p.set_defaults(kind="compile-design")

    p = sub.add_parser("designer", help="launch the full-design rtl-designer session")
    p.add_argument("--file", required=True)
    p.add_argument("--db", default=None)
    p.add_argument("--objective", default="area")
    p.add_argument("--technology", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--budget-min", type=float, default=30.0)
    p.set_defaults(kind="designer")

    args = parser.parse_args(argv)
    try:
        if args.kind == "dispatch":
            report = dispatch_subcircuit(args.slot, db=args.db, objective=args.objective,
                                         model=args.model, budget_min=args.budget_min)
        elif args.kind == "orchestrate":
            report = run_orchestrator(db=args.db, objective=args.objective, model=args.model,
                                      budget_min=args.budget_min)
        elif args.kind == "compile-design":
            report = compile_design(args.file, db=args.db, technology=args.technology)
            report.pop("verilog", None)          # keep the shim output lean
        elif args.kind == "designer":
            report = run_designer(args.file, db=args.db, objective=args.objective,
                                  technology=args.technology, model=args.model,
                                  budget_min=args.budget_min)
        else:
            report = dispatch_dv_prep(args.slot, db=args.db, model=args.model,
                                      budget_min=args.budget_min, n_vectors=args.vectors,
                                      seed=args.seed)
    except DesignDBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report.get("error") else 2


if __name__ == "__main__":
    sys.exit(main())

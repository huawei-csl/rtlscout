"""Slot-first OpenCode run: one agent, one design-DB slot — no benchmark folder, no ./evaluate_design.

The agent is handed the slot (golden.v, spec.json, starting_point.py, the frozen oracle, any Lean
spec layers) plus the design-DB skills; `spire db verify` is its only feedback and `spire db insert`
its only write path. When the wall clock ends, every design admitted during the run is re-checked
against the slot's frozen oracle in a fresh gate call (the slot-flow analogue of `reeval`: a shell
agent with a writable DB could bypass the gate, so recorded admissions are audited, never trusted).

Direction note: RTLScout imports Spire (`spire.design_db`); Spire never imports RTLScout back.
"""
from __future__ import annotations

import json
import os
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from spire.design_db import DesignDB, DesignDBError, check_design
from spire.design_db.verify import VerificationError

from core.design_db_skills import provision_design_db_skills
from core.opencode_backend import _PROVIDER_ENV, _permissions, write_remaining_time_wrapper


@dataclass
class SlotRunReport:
    spec_key: str
    name: Optional[str]
    method: Optional[str]
    model: str
    workdir: str
    returncode: int = 0
    timed_out: bool = False
    duration_s: float = 0.0
    admitted: List[str] = field(default_factory=list)          # design ids admitted during the run
    audit: Dict[str, Dict[str, str]] = field(default_factory=dict)  # design id -> {verdict, reason}

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @property
    def ok(self) -> bool:
        return bool(self.admitted) and all(a["verdict"] == "PASS" for a in self.audit.values())


def _slot_info(d: DesignDB, spec_key: str) -> Dict[str, Any]:
    slot = d.slot_dir(spec_key)
    spec = d.read_json(slot / "spec.json", None)
    if spec is None:
        raise DesignDBError(f"unknown slot {spec_key[:12]}…")
    ver = d.read_json(slot / "verification.json", None)
    if ver is None:
        raise DesignDBError("slot has no frozen verification — run `spire db set-verification` first")
    manifest = d.read_json(d.manifest_path, {"slots": {}}).get("slots", {})
    names = [n for n, e in manifest.items() if e.get("spec_key") == spec_key]
    layers = sorted(p.stem for p in (slot / "lean" / "specs").glob("*.json")) if (slot / "lean").is_dir() else []
    return {"slot_dir": slot, "spec": spec, "verification": ver, "name": names[0] if names else None, "layers": layers}


def render_slot_agents_md(info: Dict[str, Any], spec_key: str, *, source: str, db_root: Path) -> str:
    spec, ver = info["spec"], info["verification"]
    slot_ref = info["name"] or spec_key
    ports = "\n".join(f"| `{p['name']}` | {p['dir']} | {p['width']} | {'signed' if p['signed'] else 'unsigned'} |"
                      for p in spec["ports"])
    method = ver.get("method")
    oracle = {"cec": "combinational equivalence against `golden.v` (yosys/abc)",
              "sim": "cycle-accurate trace equality on the frozen `tb.sv` + `vectors.dat`",
              "lean": "a kernel-checked Lean 4 proof that your design equals the golden "
                      f"({'trace equivalence over all input sequences' if spec.get('class') == 'sequential' else 'on every input'})"}.get(method, method)
    lean_block = ""
    if method == "lean":
        layers = ", ".join(f"`{l}`" for l in info["layers"]) or "none yet"
        lean_block = f"""
## This slot is Lean-gated — every insert needs a proof

Load the `design-db-lean-proof` skill before your first submission. In short:

1. `spire db verify <workdir>/design.py --slot {slot_ref} --workspace <workdir>/ws` — with no
   proof yet this exits 2 on purpose: it writes the Lean workspace (frozen `Spec.lean`,
   `Interface.lean`, `GoldenCircuit.lean`, the spec layers, every admitted design's modules, and
   your `D<hash>_Circuit.lean`) and names the proof file to write.
2. Write `<workdir>/ws/D<hash>_Proof.lean` ending in `theorem implements : <statement>` exactly as
   the message says. Proof shapes, in order of preference: through a spec layer
   (`(Layer.equiv _).mp (by …)`), as a delta against an admitted design
   (`fun i => (step i).trans (D<other>_Proof.implements i)`), or by `bv_decide` on the whole
   design for small bitwise/control logic. Sequential slot: a simulation relation and
   `Machine.trace_eq_of_rel`. Available spec layers: {layers}.
3. `cd <workdir>/ws && lake build` until it passes; read Lean's first error each time.
4. `spire db insert <workdir>/design.py --slot {slot_ref} --proof <workdir>/ws/D<hash>_Proof.lean --source {source}`

The gate regenerates the circuit model itself and audits the axioms: no `sorry`, no `axiom`, the
statement unchanged. A proof that does not check is rejected with the Lean log — fix the design or
the proof, never the frozen files. A nicer spec formulation can be added with `add-spec` (skill
`design-db-lean-spec`) — it must be proven equivalent to `Spec.Correct` and helps every later proof.
"""
    return f"""# Optimize design-DB slot `{slot_ref}`

You optimize ONE slot of the Spire design DB — a library of verified implementations of the same
subcircuit. Goal: admit structurally *different*, correct implementations that are cheaper (fewer
transistors / AIG nodes, lower AIG depth) than what the slot holds. Only **admitted** designs count;
selection keeps the whole area/delay Pareto set, so several good candidates beat one.

- spec_key: `{spec_key}`
- slot directory: `{db_root}/v1/{spec_key}/` — `golden.v` (the reference), `spec.json` (port
  contract), `starting_point.py` (the current implementation as spire source, when captured),
  `designs/` (admitted implementations with `metrics.json`)
- circuit class: {spec.get('class')} · oracle: {oracle}
- `$SPIREHDL_DB_PATH` is set; every `spire db …` command finds this DB.

## Interface (must match exactly; the module name is free)

| port | dir | width | signedness |
|---|---|---|---|
{ports}

## Workflow

Author in **spire** (this ecosystem's design language; Verilog is only the intermediate form):
`work/design.py` defining `build() -> Component/Netlist`. Start from `starting_point.py` or from the
best admitted design's `design.py`. Iterate with
`spire db verify work/design.py --slot {slot_ref}` (advisory PASS/FAIL, writes nothing), then submit
with `spire db insert work/design.py --slot {slot_ref} --source {source}`. Inspect results with
`spire db show {slot_ref} --pareto` — judge by what the DB reports, never by your own estimate.
Skills are in `.opencode/skills/` (`design-db-inspect`, `design-db-eval`, `design-db-insert`, …).
{lean_block}
## Rules

- Work only under `work/` (create it). Slot files are read-only. **Never write into the DB
  directory by hand** — `spire db insert` is the only write path, and everything you admit is
  re-verified after the run.
- Do not fabricate metrics; the gate stamps them.
- `./remaining_time` shows the budget left. Do not stop early; when little time remains, the last
  useful act is one final `spire db insert` of your best passing design.
- Finish with one short paragraph: the slot and the design_ids you admitted.
"""


def _dotenv_value(name: str) -> Optional[str]:
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv.exists():
        return None
    for line in dotenv.read_text().splitlines():
        if line.startswith(f"{name}=") and "your-" not in line:
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def render_slot_opencode_config(model_arg: str, yolo: bool) -> Dict[str, Any]:
    perms = _permissions(yolo)
    return {"$schema": "https://opencode.ai/config.json", "model": model_arg, "instructions": ["AGENTS.md"],
            "permission": perms,
            "agent": {"rtl": {"description": "Design-DB slot optimization agent (non-interactive).", "mode": "primary",
                              "model": model_arg, "permission": perms,
                              "tools": {"write": True, "edit": True, "bash": True, "read": True}}}}


def audit_admitted(spec_key: str, since_ts: int, *, db: Optional[Any] = None) -> Dict[str, Dict[str, str]]:
    """Re-run the slot's frozen oracle on every design admitted at or after `since_ts`."""
    d = DesignDB.open(db)
    slot = d.slot_dir(spec_key)
    out: Dict[str, Dict[str, str]] = {}
    for ddir in sorted(p for p in (slot / "designs").iterdir() if p.is_dir()):
        prov = d.read_json(ddir / "provenance.json", None)
        if prov is None or int(prov.get("created", 0)) < since_ts:
            continue
        design = ddir / "design.py" if (ddir / "design.py").exists() else ddir / "design.v"
        proofs = list((ddir / "lean").glob("D*_Proof.lean")) if (ddir / "lean").is_dir() else []
        try:
            check_design(spec_key, design, proof=proofs[0] if proofs else None, db=db)
            out[ddir.name] = {"verdict": "PASS", "reason": ""}
        except (VerificationError, DesignDBError) as exc:
            out[ddir.name] = {"verdict": "FAIL", "reason": str(exc).splitlines()[0][:300]}
    return out


def run_slot_agent(spec_key: str, *, model: str, db: Optional[Any] = None, wall_clock_min: float = 10,
                   source: str = "agent:rtl-slot", work_root: Optional[Path] = None,
                   opencode_bin: str = "opencode", kickoff: Optional[str] = None) -> SlotRunReport:
    """One fresh `opencode run` on one slot (single-container mode), then the post-run audit."""
    from core.agent_backend import RunLimits
    from core.sandbox import LocalSandbox, SandboxSpec

    d = DesignDB.open(db)
    info = _slot_info(d, spec_key)
    db_root = Path(d.root).resolve()
    provider, _, model_name = model.partition(":")
    if not model_name:
        raise DesignDBError("model must be provider:model, e.g. openrouter:z-ai/glm-5.2")
    model_arg = f"{provider}/{model_name}"

    workdir = Path(work_root or Path("runs") / f"slot_{spec_key[:10]}_{time.strftime('%Y%m%d-%H%M%S')}").resolve()
    workspace = workdir / "workspace"
    (workspace / "work").mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text(render_slot_agents_md(info, spec_key, source=source, db_root=db_root))
    yolo = os.environ.get("RTLSCOUT_OPENCODE_YOLO") == "1"
    (workspace / "opencode.json").write_text(json.dumps(render_slot_opencode_config(model_arg, yolo), indent=2))
    provision_design_db_skills(workspace)
    write_remaining_time_wrapper(SimpleNamespace(workdir=workdir, workspace=workspace))

    env: Dict[str, str] = {"SPIREHDL_DB_PATH": str(db_root), "HOME": str((workdir / "_ochome").resolve())}
    Path(env["HOME"]).mkdir(exist_ok=True)
    keyvar = _PROVIDER_ENV.get(provider)
    key = os.environ.get(keyvar) if keyvar else None
    if keyvar and not key:                                   # RTLScout convention: keys live in <repo>/.env
        key = _dotenv_value(keyvar)
    if keyvar and key:
        env[keyvar] = key

    slot_ref = info["name"] or spec_key
    kickoff = kickoff or (f"Optimize design-DB slot {slot_ref} as described in AGENTS.md: read the slot, produce "
                          f"structurally different correct implementations in spire, verify each with `spire db verify`, "
                          f"and submit each through `spire db insert --source {source}`"
                          + (" with its Lean proof" if info["verification"].get("method") == "lean" else "")
                          + ". Keep going until the time budget runs out.")
    skip_perm = " --dangerously-skip-permissions" if yolo else ""
    inner = f'exec {shlex.quote(opencode_bin)} run{skip_perm} --format json -m {model_arg} --agent rtl "$1"'
    wall_s = int(wall_clock_min * 60)
    (workdir / "_deadline_epoch").write_text(str(int(time.time() + wall_s)) if wall_s else "0")
    start = int(time.time()); t0 = time.time()
    res = LocalSandbox().run_command(["bash", "-c", inner, "opencode-rtl-slot", kickoff],
                                     SandboxSpec(workdir=workspace, network="provider", limits=RunLimits(wall_clock_s=wall_s),
                                                 env=env, mounts_rw=(db_root,)))
    (workdir / "opencode_stdout.jsonl").write_text(res.stdout or "")
    (workdir / "opencode_stderr.txt").write_text(res.stderr or "")

    audit = audit_admitted(spec_key, start, db=db)
    report = SlotRunReport(spec_key=spec_key, name=info["name"], method=info["verification"].get("method"), model=model,
                           workdir=str(workdir), returncode=res.returncode, timed_out=res.timed_out,
                           duration_s=round(time.time() - t0, 1), admitted=sorted(audit), audit=audit)
    (workdir / "slot_run_report.json").write_text(json.dumps(report.to_dict(), indent=2))
    return report

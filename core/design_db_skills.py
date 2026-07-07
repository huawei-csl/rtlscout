"""Design-DB skills for the default OpenCode backend — the skill/subagent integration.

Static SKILL.md content lives in ``core/skills/<name>/`` and is copied verbatim into each
provisioned workspace (``.opencode/skills/``), where opencode discovers it. The only generated
artifact is the ``db-score`` wrapper (baked repo/python paths — the same pattern as
``evaluate_design``). The two subagent definitions (``rtl-subcircuit`` / ``rtl-dv-prep``,
``mode: subagent`` with the task tool denied — the structural depth cap) are rendered into the
backend's ``opencode.json`` next to the primary ``rtl`` agent.

Stdlib-only on purpose: no spire imports, so provisioning can never break a spire-less install.
Design: ``metadocuments/DESIGN_DB_SKILLS_APPROACH.md``. The subprocess launchers in
``core/design_db_agents.py`` are the separate legacy variant and are untouched by this module.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any, Dict

SKILLS_SRC = Path(__file__).resolve().parent / "skills"
_REPO_ROOT = Path(__file__).resolve().parent.parent

SKILL_NAMES = ("design-db-inspect", "design-db-insert", "design-db-eval",
               "design-db-dv-prep", "design-db-dispatch", "design-db-score")


def provision_design_db_skills(workspace: Path) -> Path:
    """Copy the skill pack into ``<workspace>/.opencode/skills`` and write the one generated
    wrapper (``design-db-score/scripts/db-score``, baked paths). Idempotent."""
    dest = Path(workspace) / ".opencode" / "skills"
    shutil.copytree(SKILLS_SRC, dest, dirs_exist_ok=True)
    scripts = dest / "design-db-score" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    wrapper = scripts / "db-score"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "# Technology-PPA scoring for stored slot designs (annotates unless --dry-run).\n"
        f'cd "{_REPO_ROOT}" >/dev/null 2>&1\n'
        f'exec "{sys.executable}" rtlscout_cli.py db-score "$@"\n'
    )
    wrapper.chmod(0o755)
    return dest


_SUBCIRCUIT_PROMPT = """\
You optimize ONE design-DB slot, named in the task prompt (a spec key or manifest name). The
task prompt also assigns your WORKDIR (default: work/<spec_key>/) and your SOURCE tag (default:
agent:rtl-subcircuit) — several of you may work the same slot in parallel under different
workdirs/tags, and it may give you a search LENS (e.g. depth-first structures, aggressive
sharing, start-from-Pareto): follow it rather than the generic approach.

Author in spire — this ecosystem's design language (Verilog is only the intermediate
representation): write <workdir>/design.py defining build() -> Netlist/Component. The slot's
starting_point.py (under <db_root>/v1/<spec_key>/) shows the current implementation in exactly
that form — start from it unless your lens says otherwise. Direct Verilog (design.v) is the
fallback, not the norm.

Workflow: read the slot files (golden.v = the reference, spec.json = the port contract,
starting_point.py = the source). Iterate with
`spire db verify <workdir>/design.py --slot <spec_key>` (advisory PASS/FAIL, writes nothing).
When it passes, submit through the gate:
`spire db insert <workdir>/design.py --slot <spec_key> --source <your-source-tag>`
(your python source is stored with the design automatically). Only admitted designs count.
Submit several structurally different correct designs if you can — selection keeps the whole
Pareto set, and a design another agent already admitted simply dedups (no harm).

Rules: work only inside your assigned workdir (create it). Slot files are read-only; never
write into the DB directory by hand — `spire db insert` is the only write path and it verifies
everything. Do not fabricate metrics; the gate stamps them. Check ./remaining_time between
attempts; when little time remains, stop new work — the last useful act is one final
`spire db insert` of your best already-passing design. End with one short paragraph: the slot
key and the admitted design_ids.
"""

_DV_PREP_PROMPT = """\
You author test stimulus for ONE design-DB slot, named in the task prompt. Deliverable: a single
file work/<spec_key>/stimulus.py defining generate(ports, n_vectors, seed) that yields one
{input_name: int} dict per cycle. You write inputs only — expected outputs always come from
tooling simulating the golden — and you never author candidate designs.

Read <db_root>/v1/<spec_key>/golden.v and spec.json to understand the interface (clock/reset are
driven by the testbench, not by you). Aim for stimulus that exercises the block: reset-adjacent
values, corners, wraparound bursts, protocol sequences — not just uniform random; weak stimulus
weakens the check for every future design in this slot. Validate with
`spire db set-verification --slot <spec_key> --stimulus work/<spec_key>/stimulus.py --check`
(a dry run — it writes nothing). Do NOT freeze (never run set-verification without --check):
the delegating agent reviews and freezes. Work only inside work/<spec_key>/. End by stating the
stimulus file path and what it covers.
"""


def design_db_subagent_entries(model_arg: str, perms: Dict[str, str]) -> Dict[str, Any]:
    """The ``opencode.json`` agent entries for the two design-DB subagents.

    ``mode: subagent`` + task tool denied (tools + permission) — recursion is structurally
    impossible, replacing the subprocess variant's env depth guard. The primary agent's perms
    dict is not mutated."""
    sub_perms = {**perms, "task": "deny"}
    tools = {"write": True, "edit": True, "bash": True, "read": True, "task": False}
    def _entry(description: str, prompt: str) -> Dict[str, Any]:
        return {"description": description, "mode": "subagent", "hidden": True,
                "model": model_arg, "permission": sub_perms, "tools": dict(tools),
                "prompt": prompt}
    return {
        "rtl-subcircuit": _entry(
            "Optimize one design-DB slot (dispatched with a spec key; spire-first authoring).",
            _SUBCIRCUIT_PROMPT),
        "rtl-dv-prep": _entry(
            "Author the test stimulus for one design-DB slot (never freezes, never designs).",
            _DV_PREP_PROMPT),
    }


def render_design_db_agents_section() -> str:
    """The short standing AGENTS.md block for the main agent (details live in the skills)."""
    return """## Design DB

A library of verified subcircuit implementations may be available (`$SPIREHDL_DB_PATH`, else a
local `./design_db`). When the task references design-DB slots, or your design has reusable
subcircuits worth optimizing separately, load the `design-db-*` skills: `design-db-inspect`
(slots, designs, Pareto — also how to judge results), `design-db-dispatch` (delegate one slot to
the `rtl-subcircuit` subagent via the task tool), `design-db-dv-prep` (unverified sequential
slots), `design-db-insert` / `design-db-eval` (submit / check candidates yourself, spire-first),
`design-db-score` (technology PPA, on demand). Typical loop: inspect → (dv-prep if needed) →
dispatch per slot → inspect again to see what changed → for spire designs re-run
`./evaluate_design` (it fires the `@from_design_db` decorators, so the score reflects the new
selections) — after each fill, not just at the end. **Delegate slot implementation via
`design-db-dispatch` (the task tool) instead of authoring slot candidates yourself**; if you do
insert something, use your own `--source agent:rtl` (provenance must be honest). Never write
into the DB directory by hand — inserts only through `spire db insert` (the verification gate);
results come from tooling (`spire db show`), never from subagent claims.
"""

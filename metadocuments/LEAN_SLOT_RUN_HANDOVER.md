# Handover: testing the slot-first OpenCode run on a Lean-gated design-DB slot

Written 2026-09-14 (updated after the `fill-slot` rename) for whoever takes over. State: implemented, **not yet executed** beyond syntax
checks. Nothing in this document has been run; treat every expected result as a prediction.

## 1. What exists and where

| Repo / path | Branch / state | Content |
|---|---|---|
| `/scratch/farnold/spire/spire-hdl-autoproof` | `lean-gated-design-db`, committed up to `c85bdc9` | Spire with the design_db Lean tier: `src/spire/design_db/lean/` (bridge, semantics), `verify_lean.py`, CLI (`set-verification --lean`, `add-spec`, `verify/insert --proof`, `--workspace`), tests `testing/design_db/test_lean_*.py`, docs `docs/README_lean_gate.md` |
| `/scratch/farnold/spire/rtlscout` | branch `feat/design-db-lean-slot-fill` @ `de7de29` + uncommitted fill-slot rename | slot-first runner `core/design_db_slot_run.py`, CLI `rtlscout_cli.py fill-slot --agent-backend opencode --flow direct` (formerly `agent-slot`; `fill-db` was renamed to `fill-slot`, no alias), skills `core/skills/design-db-lean-proof`, `design-db-lean-spec`, registry in `core/design_db_skills.py`, test `tests/test_design_db_slot_run.py`, README sections |
| `/scratch/farnold/spire/spire-hdl-autoproof/.venv` | Python 3.12 venv (uv) | spire installed editable, pytest, pypdf. RTLScout core modules import against it (verified) |
| `/scratch/farnold/spire/.elan` | elan + `leanprover/lean4:v4.33.1` | `lake` for the Lean tier |
| `/scratch/farnold/spire/.tools/opencode` | OpenCode 1.17.11 (RTLScout's pinned version) | unpacked release binary; `--version` works |
| `/scratch/farnold/spire/kepler-formal`, `kepler-deps` | built | unrelated (equivalence-checker experiment) |

Design documents: `spire-hdl-autoproof/metadocs/LEAN_GATE_PLAN.md`, `LEAN_GATE_TEST_REPORT.md`,
`spire-hdl-autoproof/docs/README_lean_gate.md` (the flow), and `DESIGN_DB_SKILLS_APPROACH.md` here.

Host facts: no Docker, no Node, no API key on this machine; `sudo` needs a password; 192 cores.

Standard environment for every command below (run from the RTLScout clone):

```bash
cd /scratch/farnold/spire/rtlscout
export PATH=/scratch/farnold/spire/.elan/bin:/scratch/farnold/spire/.tools:/scratch/farnold/spire/spire-hdl-autoproof/.venv/bin:$PATH
export ELAN_HOME=/scratch/farnold/spire/.elan
export PYTHONPATH=/scratch/farnold/spire/spire-hdl-autoproof:/scratch/farnold/spire/rtlscout
PY=/scratch/farnold/spire/spire-hdl-autoproof/.venv/bin/python
```

## 2. Test plan, in order

Stop at the first failing stage; later stages assume the earlier ones.

### Stage 0 — regression of the Lean tier itself (Spire only)

```bash
cd /scratch/farnold/spire/spire-hdl-autoproof && PYTHONPATH=$(pwd) .venv/bin/python -m pytest -q testing/design_db
```

Expected: 88 passed, 8 skipped, about 3 minutes (last run 2026-09-10). A missing `lake` is an ERROR
by design. Files: `test_lean_bridge.py` (12), `test_lean_gate.py` (18), existing CEC/sim tests (55).

### Stage 1 — RTLScout offline: skill pack and slot runner with a stand-in agent

```bash
$PY -m pytest -q tests/test_design_db_skills.py tests/test_design_db_slot_run.py -p no:cacheprovider
```

- `test_design_db_skills.py`: the pack now has 8 skills; `SKILL_NAMES` and the on-disk directories must agree.
- `test_design_db_slot_run.py`: flag validation (`react --flow direct` rejected, `opencode --flow eval` not implemented); `fill_slot(backend="opencode", flow="direct")` maps to the unified `FillReport`; (a) `AGENTS.md` rendered from a Lean slot mentions `spire db verify` /
  `spire db insert`, the Lean section and the `Mmac` layer, and never `evaluate_design`; (b) a stand-in
  `opencode` script that does verify, write proof, insert (exactly what the skill says) is launched by
  `run_slot_agent`, admits `agent:rtl-slot:<hash>`, and the audit passes; (c) a design copied by hand
  into `designs/` with tampered logic fails the audit.
- Likely first-run issues: the stand-in calls `spire db …` through `PATH`, so the venv `bin` must be on
  `PATH` (the test prepends it); `lake` must be on `PATH`; the test imports Spire's test helpers from the
  sibling checkout by path and skips if it is not there.

### Stage 2 — OpenCode CLI contract (no key needed)

```bash
opencode --version
opencode run --help
```

Confirm these flags exist in 1.17.11: `--format json`, `-m <provider/model>`, `--agent <name>`,
`--dangerously-skip-permissions`. The runner composes
`opencode run --format json -m <provider/model> --agent rtl "<kickoff>"`; RTLScout's existing
`OpenCodeBackend` uses the same set, so a mismatch would affect its benchmark runs too.

### Stage 3 — stand-in trial through the CLI (no key)

Create a Lean-gated slot in a fresh DB (matmul tile, `Mmac` layer):

```bash
$PY - <<'PYEOF'
import sys; sys.path.insert(0, "/scratch/farnold/spire/spire-hdl-autoproof/testing/design_db")
from mmac_candidates import CANDIDATES, CONTRACT
from lean_matmul_helper import layer_proof_lean
from spire.design_db import register_slot, freeze_lean_verification, seed_original, add_spec
from spire.design_db.lean.bridge import collect_signed_arith_shapes
db = "/scratch/farnold/spire/trial_db"
key = register_slot(CANDIDATES["BalancedMmac"](), db=db, name="mmac")
freeze_lean_verification(key, db=db); seed_original(key, db=db)
shapes = collect_signed_arith_shapes(CANDIDATES["BalancedMmac"]().to_netlist("g"))
add_spec(key, "Mmac", CONTRACT.spec_lean("Mmac"), layer_proof_lean("Mmac", shapes), author="human", db=db)
print(key)
PYEOF
```

Then write a stand-in `opencode` executable (copy the script body from
`tests/test_design_db_slot_run.py::_fake_opencode` into `/tmp/fakebin/opencode`, `chmod +x`) and run:

```bash
$PY rtlscout_cli.py fill-slot --slot mmac --model openrouter:fake/model --agent-backend opencode \
    --db /scratch/farnold/spire/trial_db --wall-clock-min 5 \
    --opencode /tmp/fakebin/opencode --work-root runs/trial_standin
spire db show mmac --db /scratch/farnold/spire/trial_db
```

Expected: `runs/trial_standin/slot_run_report.json` with one admitted design and `audit: PASS`; the
slot lists `original:…` and `agent:rtl-slot:…`. `runs/` is gitignored.

### Stage 4 — live trial, single-container, OpenRouter

Prerequisite: `/scratch/farnold/spire/rtlscout/.env` containing `OPENROUTER_API_KEY=…` (gitignored;
the runner reads it when the variable is not in the environment).

```bash
$PY rtlscout_cli.py fill-slot --slot mmac --model openrouter:z-ai/glm-5.2 --agent-backend opencode \
    --db /scratch/farnold/spire/trial_db --wall-clock-min 15 --work-root runs/trial_live
```

What to look at afterwards:

- `runs/trial_live/workspace/AGENTS.md`, `opencode.json`, `.opencode/skills/`: what the agent saw.
- `runs/trial_live/opencode_stdout.jsonl` (the session, `--format json`) and `opencode_stderr.txt`.
- `runs/trial_live/workspace/work/`: the agent's `design.py`, its `ws/` Lean project, its proof file.
- `runs/trial_live/slot_run_report.json`: `admitted`, `audit`, `returncode`, `timed_out`.
- `spire db show mmac --db /scratch/farnold/spire/trial_db`: metrics of what was admitted.

Success: at least one `agent:rtl-slot:<hash>` admitted with audit PASS and a smaller
`transistors_heavy` than `original:`. A failed run is still informative: the transcript shows where the
skill text is unclear. A 15-minute GLM-5.2 run is cheap; each Lean build in the agent's workspace takes
3 to 6 seconds. Try a stronger model afterwards (e.g. `openrouter:anthropic/claude-sonnet-4.5`); proof
writing is where model capability should show.

### Stage 5 — Docker / orchestrated mode (needs a Docker host)

Not implemented for the direct flow yet; it always uses `LocalSandbox`. Steps:

1. Image: add elan and the pinned toolchain to `.devcontainer/Dockerfile.opencode` after the OpenCode
   install (download `elan-x86_64-unknown-linux-gnu.tar.gz` from the elan v4.2.4 release, run
   `elan-init -y --no-modify-path --default-toolchain leanprover/lean4:v4.33.1`, put `~/.elan/bin` on
   `PATH`), and pre-warm one `lake build` of a project importing `Std.Tactic` so the first agent build is fast.
2. Spire pin: `deps/spire-hdl` is at `cdd252a`, before the Lean tier. Point the submodule at
   `lean-gated-design-db` (or merge that branch into `main` first).
3. Runner: give `run_slot_agent` a `mode` argument and use `make_agent_sandbox("orchestrated", …)` from
   `core/sandbox.py`; the DB root is already passed as `mounts_rw`, which `ContainerSandbox` honours.
   Apply the YOLO permission rule the way `OpenCodeBackend._is_yolo` does.
4. Audit in a judge container: `audit_admitted` currently runs in-process. For the adversarial
   guarantee run it through `make_judge_sandbox("orchestrated")`, mirroring `reeval`.
5. Rebuild the images (`bash .devcontainer/build_image.sh`, then the `Dockerfile.opencode` build) and
   repeat stage 4 with the new mode flag.

## 3. Known gaps and risks

- The stand-in agent proves the left-deep candidate through the `Mmac` layer. A live agent must
  discover the pattern from the skill text and from the admitted designs' proofs, which are visible in
  the workspace as worked examples.
- `fill-slot --flow direct` exits 1 when nothing was admitted, even if the run was otherwise healthy.
- The audit runs in the same process as the agent did; in single-container mode a hostile agent could
  tamper the Spire installation itself. Orchestrated mode (stage 5) is the answer.
- The trial slot has no `starting_point.py` (registered from a Component, not through the decorator),
  so the agent starts from `golden.v` and the admitted designs' `design.py`.
- Memory slots and latency-tolerant (retimed) specs are not supported; see
  `spire-hdl-autoproof/metadocs/LEAN_GATE_PLAN.md` §5.

## 4. Commit checklist (RTLScout)

After stages 1 to 3 pass:

```bash
git add core/design_db_slot_run.py core/design_db_skills.py core/skills/design-db-lean-proof \
        core/skills/design-db-lean-spec rtlscout_cli.py tests/test_design_db_slot_run.py \
        README.md README_orchestration.md
```

Never commit `.env`, `runs/`, or `metadocuments/` (all gitignored).

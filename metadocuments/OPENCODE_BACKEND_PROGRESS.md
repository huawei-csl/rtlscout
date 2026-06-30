# OpenCode Agent Backend — Implementation Progress

Living log for the work specified in `/scratch/farnold/eda_package/RTLSCOUT_OPENCODE_BACKEND.md`
(the handover doc). This folder (`rtl_scout_opencode`) is a **clone** of `rtl_scout_public`; the
original is never touched and its running devcontainer (`nervous_elbakyan`) keeps running.

Plan file: `~/.claude/plans/use-rtl-scout-public-as-a-cuddly-harp.md`.

## Conventions / environment

- **Branch:** `feat/opencode-backend`, based on the **pristine committed HEAD** of
  `sim_eval_updates` (`75b8211`). **No** WIP is committed: the original's uncommitted working-tree
  changes (modified tracked files + untracked files) are kept in the working tree only, never in
  history. Feature work is committed via **explicit paths** (never `git add -A`). The clearly-junk
  untracked copies (`internal_docs/`, `FINDINGS_dr_rtl_eval.md`, `.vscode/`, stray root `.v`) were
  deleted; the experimental benchmark dirs tests rely on (`benchmarks/matmul/` etc.) are kept on
  disk but listed in `.git/info/exclude` so they can't be committed.
- **Test/run environment:** the host has no EDA toolchain, so all toolchain-dependent runs happen
  inside a persistent, labelled dev container:
  - name `rtlscout-oc-dev`, image `rtlscout:latest`, mount `<this folder> -> /workspaces/rtl_scout`.
  - labels `rtlscout.managed=true`, `rtlscout.session=devtest`, `rtlscout.role=devtest`.
  - uid/gid remapped to host (10126/1200) so files written on the mount stay host-owned.
  - deps installed once via `.devcontainer/post_create.sh` (`uv pip install -e deps/spire-hdl
    -e deps/tech_eval -r requirements.txt`).
  - run things with:
    `docker exec -u vscode -w /workspaces/rtl_scout rtlscout-oc-dev bash -lc '<cmd>'`.
- **Real-LLM model:** `openrouter / GLM 5.2` (fallback 5.1), kept token-minimal.

## Design decisions adopted (handover §10)

O1 all `eval_{i}/` re-scored · O2 advisory-in/authoritative-out (b) · O3 pin OpenCode + GLM ·
O4 key via env not opencode.json · O8 default `single-container`, `orchestrated` opt-in ·
O9 withholding OFF (full benchmark to agent) · O7 react stays default (no retirement).

## Devcontainer-safety baseline

`docker ps` before work: `nervous_elbakyan` (vsc-rtl_scout_public…) **Up**, `clever_murdock`
(vsc-rtl_scout…) **Up**. Invariants for every docker step: no `stop/kill/prune` of those; never
overwrite `rtlscout:latest`; all managed-container selectors are label-based, never image-based.

---

## Status

### Step 0 — Clone + baseline — ✅ DONE
- `rsync -a` clone into `/scratch/farnold/eda_package/rtl_scout_opencode` (147 MB; heavy dirs
  excluded). `.git`, `.env`, `deps/` (submodule + vendored tech_eval) preserved.
- Submodule `deps/spire-hdl` resolves (relative gitdir pointer). Repo is independent.
- Dev container stood up; deps installed.
- **Baseline green:** `pytest -q tests/` → **41 passed** (~119 s); fake smoke
  `run_benchmark.py --benchmark simple_adder --model fake:simple_adder_pass` → `Best: PASS |
  Transistors: 308`.
- Branch `feat/opencode-backend` based on pristine `75b8211`; no WIP committed (see Conventions).

### Phase 0 — AgentBackend seam + provision_workspace — ✅ DONE
- New `core/agent_backend.py`: `RunLimits`, `BackendRequest`, `AgentBackend` Protocol,
  `PythonReactBackend` (wraps `RTLAgent`), `make_backend()`. Import-light (TYPE_CHECKING + lazy
  imports) so no cycle with `core.runner`.
- `core/runner.py`: factored `provision_workspace(benchmark, workdir, language, run_cec) ->
  (workspace, cec_reference)`; `run_agent_on_benchmark` now provisions then dispatches via
  `make_backend(agent_backend)`, new param `agent_backend="react"` (default = unchanged).
- New `tests/test_agent_backend.py` (5 tests).
- **Verified:** fake smoke `Best: PASS | Transistors: 308 | Steps: 3` (identical headline);
  artifacts byte-equivalent vs pre-refactor (best_design/design.sv + _best_meta.json identical;
  result.json differs only in run-dir path + Verilator's nondeterministic walltime — run-to-run
  noise, not refactor-induced); `pytest -q tests/` → **41 passed**; new unit tests → **5 passed**.

### Phase 1 — Eval split + Sandbox seam + post-run re-score — ⬜ TODO

### Phase 2 — OpenCodeBackend (single-container) — ⬜ TODO

### Phase 3 — ContainerSandbox + orchestrated mode + cleanup — ⬜ TODO

---

## Issues & deviations

- **Initial baseline commit included carried-over WIP — corrected.** The first `baseline:` commit
  used `git add -A` and swept in the original's uncommitted WIP (internal_docs, experimental
  benchmarks, editor config). Per user feedback this is not wanted: un-committed (`git reset` to
  `75b8211`), deleted the junk copies, excluded the rest from git. Going forward only explicit
  feature paths are committed.
- **Backends return `AgentResult`, not the doc's `AgentRunResult` (§5.1).** `AgentResult` is a
  superset (adds `messages`/`best_eval`/`all_evals`/`num_steps`) that `chat_log.txt`, `result.json`
  and `make_elite_entry` all require; the slimmer `AgentRunResult` would drop them and break the
  on-disk contract. Returning `AgentResult` is what makes the Phase-0 react path byte-identical.

## Token spend (real-LLM checks)

- *(none yet)*

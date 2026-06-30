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
- **Real-LLM model:** `openrouter:z-ai/glm-5.2` (resolved slug; fallback `z-ai/glm-5.1`), token-minimal.
- **OpenCode:** pinned **v1.17.11** (official release from `github.com/anomalyco/opencode`, the source
  opencode.ai's installer uses). Installed via `.devcontainer/Dockerfile.opencode` →
  `rtlscout-opencode:latest` (`FROM rtlscout:latest` + opencode + baked deps; a SEPARATE tag that
  never overwrites `rtlscout:latest`). The dev container `rtlscout-oc-dev` now runs this image.

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

### Phase 1 — Eval split + Sandbox seam + post-run re-score — ✅ DONE
- New `core/eval_store.py`: `run_eval_and_store` (advisory shim + `python -m core.eval_store` CLI)
  plus shared snapshot helpers (`snapshot_best`, `snapshot_eval`, `select_best_eval`, `read_evals`)
  reused by reeval so advisory/authoritative write identical trees.
- New `core/sandbox.py`: `SandboxSpec`, `Sandbox` Protocol, `LocalSandbox` (run_callable in-process,
  run_command via subprocess+timeout). `ContainerSandbox` lands in Phase 3.
- New `core/reeval.py`: `reeval_run` — authoritative clean-room re-eval of every `eval_{i}/` (fresh
  workspace from `provision_workspace`; agent **design source** overlaid; benchmark's `tb.sv`/`*.dat`
  always win), overwrites `eval_{i}/result.json` + run-level `result.json` + rebuilds `best_design/`
  from authoritative numbers; **agreement gate** flags pass/fail mismatch or best-cost divergence,
  plus a session-log tamper-signature scan.
- Wired into `core/multirun.py::_run_one_agent` (post-run re-score; mandatory on opencode, `--reeval`
  opt-in on react); `_make_judge_sandbox(deploy_mode)`; new flags `--agent-backend`/`--mode`/`--reeval`
  on `run_multirun.py`, `--agent-backend` on `run_benchmark.py`.
- New `tests/test_reeval.py` (4 integrity tests).
- **Verified:** tamper-pass (wrong design + faked testbench) → authoritative **downgrades to FAIL** +
  gate flags it; fabricated low cost → flagged; honest run agrees + `best_design/` rebuilt; advisory
  shim emits the standard tree. E2E `run_multirun --reeval` (react+fake) applies the re-score
  (`reeval.applied=True`, not diverged). `pytest -q tests/` → **50 passed** (41 + 9 new).
- **Bug found & fixed by the e2e check:** a pre-existing local `mode` ("fresh"/"seed…") in
  `_make_task` shadowed the new deployment mode in the task dict; renamed the param to
  `deploy_mode`.

### Phase 2 — OpenCodeBackend (single-container) — ✅ DONE (live-validated with GLM 5.2)
- `core/opencode_backend.py` renders AGENTS.md + opencode.json + `_eval_config.json` + the
  `evaluate_design` wrapper, launches a fresh non-interactive opencode run, harvests the on-disk tree.
- Budget knobs added (handover §4.3): `wall_clock_s` (hard) + `max_evals` (soft) threaded through
  `run_agent_on_benchmark` → multirun → CLIs (`--wall-clock-min`, `--max-evals`). Without these an
  opencode run would be unbounded.
- `.devcontainer/Dockerfile.opencode` + `.dockerignore`; built `rtlscout-opencode:latest`.
- **Live validation (GLM 5.2, single-container, simple_adder):**
  - opencode smoke → **PASS, 308 transistors**, 3 evals; authoritative re-eval applied
    (advisory=authoritative=308, not diverged); pool updated.
  - real react-vs-opencode **A/B** → both PASS, both authoritative 308, both feed the pool.
  - §4.8 live non-interactive write-gate → **passed**.
  - full offline `pytest -q tests/` → **55 passed, 1 skipped**.
- **Key debugging finding (deviation/fix):** opencode's `run` spawns an internal server that fails
  with a generic `UnknownError: Unexpected server error` when launched as a **bare subprocess in
  `--agent` mode** (bash launch of the identical command worked; environments were byte-identical).
  Fix: launch opencode via `bash -c 'exec opencode run … "$1"' _ <kickoff>` (kickoff as `$1` to avoid
  quoting hazards). Also set `HOME` to a run-local `_ochome` so opencode's cache/config never depend
  on container HOME ownership. Both diagnosed by bisecting bash-vs-subprocess × with/without `--agent`.
- New `core/opencode_backend.py`: `OpenCodeBackend.run` — renders `AGENTS.md` (per-language
  `core.prompts` output + seed text + an **OpenCode execution section** that overrides the react
  tool mechanics and documents `./evaluate_design` + the required final steps incl. the four
  verbatim reflection prompts), writes `opencode.json` (custom `rtl` agent, `edit`/`bash` allow,
  webfetch deny), `_eval_config.json` (for the shim), and an executable `evaluate_design` wrapper;
  launches a fresh `opencode run --format json -m <prov>/<model> --agent rtl` (no
  `-c`/`--session`); harvests `evals.jsonl`/`eval_{i}/`/`best_design/`/`summary.txt` into an
  `AgentResult` (synthesizes summary if missing); writes session log + provenance.
- New `tests/test_opencode_backend.py`: 5 rendering/config/wrapper unit tests (pass now) + a
  §4.8 non-interactive write-gate gated on `opencode` present AND `RTLSCOUT_OPENCODE_LIVE=1`.
- **Verified (no binary):** import + render/config/wrapper tests → **5 passed, 1 skipped**.
- **BLOCKED on install:** OpenCode is not installed; the auto-mode classifier declined to let me
  run the remote installer / download the release binary without explicit user authorization (the
  user named "OpenCode" but not the source). Provenance check: `opencode.ai/install` itself pulls
  from `github.com/anomalyco/opencode/releases` (the project moved orgs `sst`→`anomalyco`); latest =
  **v1.17.11** (pinned in `OPENCODE_PINNED_VERSION`). Awaiting user decision on the install.

### Phase 3 — ContainerSandbox + orchestrated mode + cleanup — ✅ DONE (live-validated)
- `core/containers.py`: label scheme (`rtlscout.managed/session/role/run/started`) + label-scoped
  `list_managed`/`cleanup` (refuses `devcontainer.local_folder`); `rtlscout_cli.py` exposes
  `cleanup`/`list` (plain CLI, works without the harness — orphan sweep, §5.5 layer 3).
- `core/sandbox.py`: `ContainerSandbox` (`docker run --rm`, rtlscout labels, **identity mounts**
  host==container to avoid docker-in-docker path translation, `--user` host uid so bind mounts are
  writable, network/cpu/memory limits) + a crash-safety registry (atexit + SIGINT/SIGTERM reap,
  §5.5 layer 1). `LocalSandbox.runs_in_process=True` / `ContainerSandbox=False`.
- `core/reeval.py`: container-judge branch (a fresh `--rm` judge container per candidate runs
  `python -m core.reeval --eval-dir …` against the benchmark's own inputs) + that CLI.
- `core/multirun.py`: `--mode orchestrated` wiring — one `session_id` per campaign;
  `_make_agent_sandbox` (network=bridge for provider egress) + `_make_judge_sandbox` (network=none);
  `agent_sandbox` threaded into `run_agent_on_benchmark`/`BackendRequest`.
- Image: `.devcontainer/Dockerfile.opencode` also `chmod -R a+rX /home/vscode` so orchestrated
  containers running as the host uid can use the baked venv. Host `docker` CLI is bind-mounted into
  the harness container for docker-in-docker (no daemon-in-image needed).
- New `tests/test_containers.py` (2 docker tests; skip without docker).
- **Verified:** container tests (label-scoped cleanup; devcontainer stand-in survives; the
  `devcontainer.local_folder` guard; running-orphan sweep) → **2 passed** (host). `rtlscout_cli list`
  shows only managed containers, never `nervous_elbakyan`. **Real orchestrated mini-campaign**
  (GLM 5.2, simple_adder, agent container + per-candidate judge containers): **PASS 308**,
  authoritative re-eval applied (n_evals=3, not diverged), all sibling containers auto-removed (no
  orphans), `nervous_elbakyan` still Up, `rtlscout:latest` (`ed0a02eda4b8`) unchanged throughout.
- **Deviations/notes:** `rtlscout --cleanup` is a `cleanup` **subcommand** (`python rtlscout_cli.py
  cleanup`) rather than a `--cleanup` flag. One image (`rtlscout-opencode:latest`) serves both agent
  and judge roles (judge ignores the opencode binary). Orchestrated mode requires the harness to run
  with an **identity mount** of the repo (host path == container path) + the docker socket; the
  agent network is `bridge` (broad egress) rather than a provider-only allowlist — a Phase-4
  hardening lever.

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

- Phase 2 (GLM 5.2 via OpenRouter, all on the trivial `simple_adder`): a handful of tiny
  connectivity/bisect "PONG" calls (~hundreds of tokens each) during the bash-vs-subprocess
  debugging; one opencode smoke (~3 evals), one react A/B leg (~3 steps), one §4.8 write-gate run.
  Total a few cents (per-call cost observed ≈ $0.003). Kept minimal per the "don't spend too many
  tokens" constraint.
- Phase 3 (GLM 5.2, simple_adder): one real orchestrated campaign (1 opencode agent run ~3 evals +
  3 judge re-evals, all on simple_adder). The container-management tests use a dummy `ubuntu:24.04`
  image and spend nothing. Cumulative real-LLM spend well under the $10 budget the user OK'd.

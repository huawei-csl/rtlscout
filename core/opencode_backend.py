"""OpenCode agent backend (handover doc §5.4): run the external ``opencode`` agent
once per optimization run, in its own (single-container or orchestrated) sandbox.

Lifecycle:
  1. The workspace is already provisioned (``provision_workspace``) with the full
     benchmark (tb + data + context + reference — O9 keeps nothing withheld).
  2. Render ``AGENTS.md`` (from ``core.prompts`` + the opencode execution section) and
     ``opencode.json`` into the workspace; write ``_eval_config.json`` (for the eval
     shim) into the run root and an ``evaluate_design`` wrapper into the workspace.
  3. Launch a FRESH ``opencode run`` (no ``-c``/``--session``/``--attach`` — one run ==
     one fresh context, §4.2) via the agent sandbox.
  4. Harvest the standard on-disk tree (``agent_evals.jsonl`` / ``eval_{i}/`` / ``best_design/``
     / ``summary.txt``) the eval shim produced, and build an ``AgentResult``. The full native
     session (prompts + responses) is saved via ``opencode export`` to ``opencode_session.json``.

The recorded score is NOT trusted from here — the harness re-derives it with
``core.reeval.reeval_run`` against the benchmark's own inputs (mandatory on this path).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from core.agent import AgentResult
    from core.agent_backend import BackendRequest

# Pinned OpenCode version this backend targets (recorded for provenance; re-verify CLI
# flags / opencode.json schema against this exact version — handover §4.8/§8).
OPENCODE_PINNED_VERSION = "1.17.11"

# Provider -> env var carrying the API key (handover O4: key via env, never opencode.json).
_PROVIDER_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
}

# The four reflection prompts, verbatim from RTLAgent._request_summary (handover §5.2:
# keep them so summary quality doesn't regress).
REFLECTION_PROMPTS = (
    "1. What approaches did you try and what worked best?\n"
    "2. What optimizations had the most impact?\n"
    "3. What didn't work or caused regressions?\n"
    "4. Lessons learned and what you would do differently next time."
)

# Summarizer turn (react parity): after the optimization session ends/is killed, we CONTINUE
# the same opencode session and ask the agent to write summary.txt with full memory of the run
# — mirroring RTLAgent._request_summary. This is NOT part of the wall-clock budget; it gets its
# own short timeout below.
SUMMARY_TURN_TIMEOUT_S = 180

SUMMARY_KICKOFF = (
    "The optimization session is over. Write a file named `summary.txt` in the current "
    "directory — a brief, specific summary covering:\n" + REFLECTION_PROMPTS + "\n\n"
    "Refer to your design files by name where useful. Be concise. Write ONLY summary.txt; do "
    "not modify any design files."
)

# If the agent hands back before the wall-clock budget is used up (its equivalent of the react
# loop's `done`), nudge it to keep going. Bounded by the guards below so it can't run away.
NUDGE_MIN_REMAINING_S = 45   # don't continue if less than this remains
NUDGE_MAX_ROUNDS = 5         # hard cap on continuation rounds
NUDGE_PROMPT = (
    "You still have time left and there is likely more to gain — do NOT stop yet. Try a "
    "genuinely different design, or a further optimization of your best so far, then re-run "
    "./evaluate_design. You'll be terminated automatically when time runs out; keep improving "
    "until then."
)


_SESSION_ID_RE = re.compile(r"ses_[a-zA-Z0-9]+")


def _extract_child_session_ids(transcript_text: str, parent_id: Optional[str]) -> List[str]:
    """Every session ID referenced in the transcript except the parent — with the task tool,
    these are the subagent child sessions."""
    return sorted(set(_SESSION_ID_RE.findall(transcript_text)) - {parent_id})


def _preserve_session_store(oc_home: Path, workdir: Path) -> bool:
    """Copy opencode's SQLite session store (small) out of _ochome before the ~100 MB HOME is
    deleted — the raw store is the last-resort session record (`sqlite3` / future exports)."""
    store = oc_home / ".local" / "share" / "opencode" / "opencode.db"
    if not store.exists():
        return False
    for suffix in ("", "-wal", "-shm"):                # WAL contents merge on next open
        src = Path(str(store) + suffix)
        if src.exists():
            shutil.copyfile(src, workdir / ("opencode_store.db" + suffix))
    return True


def _extract_session_id(stdout: str) -> Optional[str]:
    """Pull the opencode session id out of a `--format json` stream (events carry sessionID)."""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        sid = d.get("sessionID") or (d.get("part") or {}).get("sessionID")
        if sid:
            return sid
    return None

_DESIGN_FILE_BY_LANG = {"spirehdl": "design.py", "amaranth": "design.py", "verilog": "design.sv"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _metric_name(req: "BackendRequest") -> str:
    return req.cost_metric.metric_name if req.cost_metric else "transistors"


def render_agents_md(req: "BackendRequest") -> str:
    """Render AGENTS.md for an OpenCode run via the unified lean renderer
    (``core.agents_md``) — a shell-capable agent gets task + workflow + reference pointers,
    not the react loop's inlined tool mechanics. With ``req.design_db_skills`` the design-DB block
    (skills + subagents) rides along in the execution section."""
    metric_name = _metric_name(req)
    execution_section = _opencode_execution_section(req, metric_name)
    if req.design_db_skills:
        from core.design_db_skills import render_design_db_agents_section
        execution_section += "\n\n" + render_design_db_agents_section()
    from core.agents_md import render_opencode_agents_md
    return render_opencode_agents_md(req, execution_section=execution_section,
                                     metric_name=metric_name, seed_text=req.system_prompt_extra)


def _opencode_execution_section(req: "BackendRequest", metric_name: str) -> str:
    """Render the shared OpenCode workflow block (shell intro, ./evaluate_design,
    ./remaining_time, time budget, finishing-up). Language-agnostic; the per-HDL renderer in
    core.agents_md places it after the objective."""
    design_file = _DESIGN_FILE_BY_LANG.get(req.language, "design.sv")
    secs = req.limits.wall_clock_s
    budget_min = f"~{secs // 60} minutes" if secs else "a fixed wall-clock budget"
    return f"""## How you work here

You are an autonomous coding agent with a **real shell and your own file-editing tools**.
Read, write and edit files directly and run shell commands in your working directory.

**Your design file:** put your design in `{design_file}` in the current directory
(create helper files as needed).

**How to evaluate (get a correctness + cost score):** run

    ./evaluate_design {design_file}

This runs the project's evaluator on your design, prints correctness (lint/sim/CEC) and
the `{metric_name}` cost, and snapshots the result. Use it to iterate: get a correct
design first, then minimize `{metric_name}` cost without breaking correctness.

**Time budget.** You have {budget_min} of wall-clock time and there is **no step/turn limit**.
You do **not** need to stop or wrap up on your own — you will be **terminated automatically**
when the budget runs out, and every design you evaluated is kept (see below). So keep working
the whole time; there is no benefit to finishing early. Check how much is left at any point with:

    ./remaining_time

**Use your time wisely:** spend it making and *evaluating design changes*, not investigating
the harness/evaluator internals. Treat `./evaluate_design` as a black box (design in, score
out) — a quick look at the reference docs/designs listed below is fine, but do **not** burn
your budget reading `core/`, the cost-metric implementation, or the testbench plumbing.

Do **NOT** stop or wind down after one or two evaluations. Keep trying genuinely different
designs / micro-architectures (e.g. different multiplier/adder configurations, pipelining,
sharing) and re-evaluating each with `./evaluate_design`, keeping the best result. If you run
low on ideas, try more variations rather than stopping — you have the full budget to use.

**No wrap-up needed.** Every design you score with `./evaluate_design` is automatically saved
as a candidate, and after the session the harness independently re-scores all candidates and
keeps the best one — so you do **not** need to restore your best design into `{design_file}`,
run a "final" evaluation, or write a summary. Just make sure every version you want considered
has been scored at least once (a design you edit but never evaluate is not a candidate). After
your time is up, the harness also scores `{design_file}` one final time; if your final design
lives in a **different** file, write that filename into `.final_eval_file` (a plain filename in
this directory) so the closing score targets the right file. A short summary is requested from
you separately after you're stopped.
"""


# All opencode permission categories (v1.17.11 schema). The critical fix (handover §4.8):
# in non-interactive `opencode run`, any permission left at the default "ask" is
# AUTO-REJECTED and that aborts the run — which is exactly what killed a run mid-optimization
# when the agent tried to read the Spire package source (an `external_directory` access).
# So we never leave a key at "ask": everything is "allow" or "deny".
_ALL_PERMS = ["read", "edit", "glob", "grep", "list", "bash", "task", "external_directory",
              "todowrite", "question", "webfetch", "websearch", "lsp", "doom_loop", "skill"]


def _permissions(yolo: bool) -> Dict[str, str]:
    """yolo=True → allow everything (safe only in an isolated sandbox). yolo=False → allow
    everything needed to iterate, INCLUDING reading outside the workspace
    (``external_directory``), but deny network (webfetch/websearch). No key is left at
    "ask", so a denied tool simply returns 'denied' and the agent keeps going rather than
    the run being aborted."""
    if yolo:
        return {k: "allow" for k in _ALL_PERMS}
    return {k: ("deny" if k in ("webfetch", "websearch") else "allow") for k in _ALL_PERMS}


def render_opencode_config(req: "BackendRequest", yolo: bool = False) -> Dict:
    """Render opencode.json. The custom 'rtl' agent gets full local tool permissions so
    non-interactive runs apply edits AND can read the Spire package source to explore
    architectures (handover §4.8). The provider key is supplied via env, never here (O4).
    With ``req.design_db_skills`` the design-DB subagents (rtl-subcircuit / rtl-dv-prep, task tool
    denied) are merged in — reachable only via the primary agent's task tool."""
    model_arg = f"{req.provider}/{req.model}"
    perms = _permissions(yolo)
    agents: Dict = {
        "rtl": {
            "description": "Autonomous RTL design-optimization agent (non-interactive).",
            "mode": "primary",
            "model": model_arg,
            "permission": perms,
            "tools": {"write": True, "edit": True, "bash": True, "read": True},
        },
    }
    if req.design_db_skills:
        from core.design_db_skills import design_db_subagent_entries
        agents.update(design_db_subagent_entries(model_arg, perms))
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": model_arg,
        "instructions": ["AGENTS.md"],
        "permission": perms,
        "agent": agents,
    }


def _is_yolo(req: "BackendRequest") -> bool:
    """YOLO (skip all permission prompts) when the agent runs in its OWN isolated container
    (orchestrated ContainerSandbox) — safe because it can't reach the host/judge. Forceable
    anywhere via RTLSCOUT_OPENCODE_YOLO=1 (e.g. when the whole harness runs in a throwaway
    container). Single-container default is NOT yolo (the agent shares the container)."""
    if os.environ.get("RTLSCOUT_OPENCODE_YOLO") == "1":
        return True
    sb = req.agent_sandbox
    return sb is not None and not getattr(sb, "runs_in_process", True)


def write_eval_config(req: "BackendRequest") -> Path:
    """Write _eval_config.json (read by `python -m core.eval_store`) into the run root."""
    cfg = {
        "design_top_module": req.benchmark.module_name,
        "cost_metric": _metric_name(req),
        "target_delay": getattr(req.cost_metric, "target_delay", None),
        "technology": getattr(req.cost_metric, "technology", "asap7"),
        "energy_exp": getattr(req.cost_metric, "energy_exp", 1.0),
        "language": req.language,
        "run_cec": bool(req.run_cec and req.cec_reference is not None),
        "cec_reference": str(req.cec_reference) if req.cec_reference else None,
    }
    path = req.workdir / "_eval_config.json"
    path.write_text(json.dumps(cfg, indent=2))
    return path


def write_eval_wrapper(req: "BackendRequest") -> Path:
    """Write an executable `evaluate_design` wrapper into the workspace so the agent can
    score its design with one command regardless of cwd / PYTHONPATH."""
    repo = _repo_root()
    py = sys.executable
    ws = req.workspace.resolve()
    rr = req.workdir.resolve()
    wrapper = req.workspace / "evaluate_design"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "# Advisory eval + snapshot shim. Usage: ./evaluate_design [design_file]\n"
        "set -e\n"
        f'cd "{repo}" >/dev/null 2>&1\n'
        f'exec "{py}" -m core.eval_store --workspace "{ws}" --run-root "{rr}" "$@"\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def write_remaining_time_wrapper(req: "BackendRequest") -> Path:
    """Write an executable `remaining_time` command into the workspace so the agent can check
    how much wall-clock budget is left. It reads the deadline file the backend stamps at
    launch (an absolute path, so it works from any cwd and in a fresh container)."""
    deadline_file = (req.workdir / "_deadline_epoch").resolve()
    wrapper = req.workspace / "remaining_time"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "# Remaining wall-clock budget for this optimization run.\n"
        f'deadline=$(cat "{deadline_file}" 2>/dev/null || echo 0)\n'
        'if ! [ "$deadline" -gt 0 ] 2>/dev/null; then echo "No wall-clock limit set."; exit 0; fi\n'
        'rem=$(( deadline - $(date +%s) )); [ "$rem" -lt 0 ] && rem=0\n'
        'printf "Remaining wall-clock budget: %dm %02ds (%ds total). Keep optimizing until near '
        'zero; do not stop early.\\n" $((rem/60)) $((rem%60)) "$rem"\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def _synth_summary(all_evals, best) -> str:
    """Synthesize a minimal summary.txt from agent_evals.jsonl when the agent left none."""
    n = len(all_evals)
    if best is not None:
        return (f"(Auto-generated) {n} evaluation(s) recorded. Best passing design: "
                f"cost={best.get('cost_value')} at eval {best.get('eval_index')}.\n"
                f"No agent-written summary.txt was found.\n")
    return (f"(Auto-generated) {n} evaluation(s) recorded; no passing design found.\n"
            f"No agent-written summary.txt was found.\n")


def _parse_token_usage(stdout: str):
    """Best-effort token-usage parse from `opencode run --format json` output. Robust to
    schema drift: returns a zeroed TokenUsage if nothing parses (harvest never depends on
    this — the on-disk eval tree is the source of truth)."""
    from core.llm_client import TokenUsage
    tu = TokenUsage()
    if not stdout:
        return tu
    for blob in (stdout, stdout.strip().splitlines()[-1] if stdout.strip() else ""):
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        usage = None
        if isinstance(data, dict):
            usage = data.get("usage") or data.get("tokens") or (data.get("info") or {}).get("usage")
        if isinstance(usage, dict):
            tu.input_tokens = int(usage.get("input") or usage.get("input_tokens") or 0)
            tu.output_tokens = int(usage.get("output") or usage.get("output_tokens") or 0)
            return tu
    return tu


def _harvest(req: "BackendRequest", stop_reason: str, cmd_result, token_usage) -> "AgentResult":
    from core.agent import AgentResult
    from core.eval_store import read_evals, select_best_eval

    workdir = req.workdir
    all_evals = read_evals(workdir / "agent_evals.jsonl")
    tiebreaker = getattr(type(req.cost_metric), "tiebreaker_key", None) if req.cost_metric else None
    best = select_best_eval(all_evals, tiebreaker)

    # Surface the agent's summary.txt where _read_summary expects it (run root).
    ws_summary = req.workspace / "summary.txt"
    wd_summary = workdir / "summary.txt"
    if ws_summary.exists() and not wd_summary.exists():
        shutil.copy2(ws_summary, wd_summary)
    if not wd_summary.exists():
        wd_summary.write_text(_synth_summary(all_evals, best))

    error = ""
    if stop_reason not in ("completed",):
        tail = (cmd_result.stderr or "")[-500:]
        error = f"opencode stop_reason={stop_reason}: {tail}".strip()

    return AgentResult(
        benchmark_name=req.benchmark.name,
        model=req.model,
        passed=best is not None,
        best_cost=best.get("cost_value") if best else None,
        cost_metric_name=_metric_name(req),
        best_eval=best,
        all_evals=all_evals,
        num_steps=len(all_evals),
        messages=[],
        token_usage=token_usage,
        error=error,
        best_metrics=best.get("metrics") if best else None,
    )


class OpenCodeBackend:
    """Run one optimization run via a fresh, non-interactive ``opencode run``."""
    name = "opencode"

    def run(self, req: "BackendRequest") -> "AgentResult":
        from core.sandbox import LocalSandbox, SandboxSpec

        workspace = req.workspace
        metric_name = _metric_name(req)

        # Render + write the agent's instructions, config, and eval shim. The permission
        # policy is decided + written PER RUN into the (mounted) workspace, so it applies to
        # every freshly-spun orchestrated agent container — no image baking needed.
        yolo = _is_yolo(req)
        (workspace / "AGENTS.md").write_text(render_agents_md(req))
        opencode_cfg = render_opencode_config(req, yolo)
        (workspace / "opencode.json").write_text(json.dumps(opencode_cfg, indent=2))
        write_eval_config(req)
        write_eval_wrapper(req)
        write_remaining_time_wrapper(req)
        if req.design_db_skills:
            from core.design_db_skills import provision_design_db_skills
            provision_design_db_skills(workspace)   # .opencode/skills/** — opencode discovers them

        # Provider key via env (never in opencode.json).
        env: Dict[str, str] = {}
        keyvar = _PROVIDER_ENV.get(req.provider)
        if keyvar:
            val = req.api_key or os.environ.get(keyvar)
            if val:
                env[keyvar] = val

        # Design-DB handover (only with the skills layer on): resolve the DB root — explicit
        # request path (e.g. multirun's campaign DB) → $SPIREHDL_DB_PATH → none (spire's
        # workspace-local ./design_db default) — and forward it. The backend's env dict is
        # fresh, so without this a ContainerSandbox agent could not see it (LocalSandbox merges
        # os.environ anyway). mkdir before the container mount: docker would otherwise create a
        # missing host dir root-owned.
        db_path = None
        if req.design_db_skills:
            db_path = str(req.design_db_path) if req.design_db_path else os.environ.get("SPIREHDL_DB_PATH")
        if db_path:
            Path(db_path).mkdir(parents=True, exist_ok=True)
            env["SPIREHDL_DB_PATH"] = db_path

        # Give opencode a guaranteed-writable HOME under the run dir, so its config/cache
        # never depend on the container's HOME ownership (robust across uid remapping /
        # fresh orchestrated containers). Project-local opencode.json + the env key mean
        # no global config or auth file is needed.
        # MUST be absolute: opencode's cwd is the workspace, so a *relative* HOME would be
        # resolved against the workspace and nest opencode's ~100 MB of cache/node_modules
        # INSIDE it — which then gets copied into every eval_i/ snapshot (huge bloat).
        oc_home = (req.workdir / "_ochome").resolve()
        oc_home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(oc_home)

        model_arg = f"{req.provider}/{req.model}"
        kickoff = (
            "Implement and optimize the RTL design described in AGENTS.md. Start with a simple "
            "correct implementation, run ./evaluate_design to score it, then keep iterating to "
            f"minimize the {metric_name} cost while staying correct. Do not stop or wind down on "
            "your own — you will be terminated automatically when the time budget runs out, and "
            "every design you evaluated is kept. Keep improving the whole time."
        )
        # Fresh session, machine-readable output. NO -c/--session/--attach (handover §4.2).
        # IMPORTANT: opencode's `run` spawns an internal server that fails with a generic
        # "Unexpected server error" when launched as a bare subprocess in --agent mode; running
        # it via a shell (bash -c) reliably fixes it (env is identical either way — it's the
        # process/session context opencode's server-spawn needs). The kickoff is passed as $1 to
        # avoid any shell-quoting hazards; model_arg is a safe provider/model slug.
        # YOLO (isolated sandbox): also auto-approve any not-explicitly-denied permission so a
        # fresh container never stalls on a prompt. This flag is part of the per-run launch
        # command, so it applies in every spawned agent container too.
        skip_perm = " --dangerously-skip-permissions" if yolo else ""
        inner = f'exec opencode run{skip_perm} --format json -m {model_arg} --agent rtl "$1"'
        argv = ["bash", "-c", inner, "opencode-rtl", kickoff]

        sandbox = req.agent_sandbox or LocalSandbox()
        spec = SandboxSpec(workdir=workspace, network="provider", limits=req.limits, env=env,
                           mounts_rw=(Path(db_path),) if db_path else ())

        # Stamp the wall-clock deadline as close to launch as possible so the agent's
        # ./remaining_time reflects the real budget (0 = no limit).
        from core.agent_backend import RunLimits
        from core.eval_store import read_evals
        wall_s = req.limits.wall_clock_s
        deadline = (time.time() + wall_s) if wall_s else None
        (req.workdir / "_deadline_epoch").write_text(str(int(deadline)) if deadline else "0")

        def _n_evals() -> int:
            return len(read_evals(req.workdir / "agent_evals.jsonl"))

        def _continue_session(session_id: str, prompt: str, timeout_s: int):
            """Continue the SAME opencode session with a follow-up prompt (nudge or summary)."""
            inner = (f'exec opencode run --session {shlex.quote(session_id)}{skip_perm} '
                     f'--format json -m {model_arg} --agent rtl "$1"')
            cspec = SandboxSpec(workdir=workspace, network="provider",
                                limits=RunLimits(wall_clock_s=max(1, timeout_s)), env=env)
            return sandbox.run_command(["bash", "-c", inner, "opencode-rtl", prompt], cspec)

        cmd_result = sandbox.run_command(argv, spec)
        session_id = _extract_session_id(cmd_result.stdout)
        transcript = [cmd_result.stdout or ""]

        # Nudge loop: if the agent handed back before the wall-clock ran out (its equivalent of
        # the react `done`), continue the same session and push it to keep improving. Guards:
        # stop if <NUDGE_MIN_REMAINING_S left, a round adds no new evaluation (done/stuck), or
        # after NUDGE_MAX_ROUNDS. Worse attempts are harmless — the harness keeps the best.
        nudges = 0
        while (session_id and deadline is not None and not cmd_result.timed_out
               and nudges < NUDGE_MAX_ROUNDS and (deadline - time.time()) > NUDGE_MIN_REMAINING_S):
            before = _n_evals()
            cmd_result = _continue_session(session_id, NUDGE_PROMPT, int(deadline - time.time()))
            transcript.append(cmd_result.stdout or "")
            nudges += 1
            if not cmd_result.timed_out and _n_evals() == before:
                break  # nudge produced no new evaluation → agent is done/stuck; stop nudging

        # Final framework eval (react parity): the harness — not the agent — guarantees the
        # LAST workspace state is scored, so a parent killed mid-wrap-up loses nothing
        # measurable. Runs the same advisory eval shim the agent uses (same snapshot tree); for
        # spire designs the recompile fires @from_design_db, i.e. this measures the final
        # spliced selection state. NOT counted against the optimization budget.
        final_eval = None
        final_name = _DESIGN_FILE_BY_LANG.get(req.language, "design.sv")
        final_eval_note = None
        override_p = workspace / ".final_eval_file"
        if override_p.exists():
            cand = override_p.read_text().strip()
            # agent-controlled, harness-validated: one plain filename in the workspace
            if cand and "/" not in cand and ".." not in cand and (workspace / cand).is_file():
                final_name = cand
            else:
                final_eval_note = f"ignored invalid .final_eval_file {cand!r}"
        if (workspace / final_name).is_file():
            final_eval = sandbox.run_command(
                ["bash", "-c", f"exec ./evaluate_design {shlex.quote(final_name)}",
                 "opencode-final-eval"],
                SandboxSpec(workdir=workspace, network="none",
                            limits=RunLimits(wall_clock_s=600), env=env))
            transcript.append("=== FINAL FRAMEWORK EVAL ===\n" + (final_eval.stdout or ""))

        # Summarizer turn (react parity, handover §5.2): CONTINUE the same session and ask the
        # agent to write summary.txt with full memory. Its own short timeout, NOT counted against
        # the optimization budget. Falls back to _harvest's _synth_summary if it can't continue.
        summary_result = None
        if session_id:
            summary_result = _continue_session(session_id, SUMMARY_KICKOFF, SUMMARY_TURN_TIMEOUT_S)
            transcript.append("=== SUMMARY TURN ===\n" + (summary_result.stdout or ""))

        # Export the FULL native session as JSON (`opencode export`) BEFORE deleting _ochome
        # (its SQLite DB). Unlike the stdout transcript, this includes the *prompts* (user turns:
        # kickoff, nudges, summary) alongside the assistant/tool events — one self-contained
        # {info, messages} document for the whole run (all rounds share one session). Best-effort:
        # a failed export just leaves the stdout transcript log below as the record.
        export_errors: Dict[str, str] = {}

        def _export_session(sid: str, dest: Path) -> bool:
            # The export is redirected to a FILE inside the sandbox, never captured through a
            # pipe: opencode (Node) writes stdout asynchronously and exits — a pipe truncates
            # at ~8 KB on fast exit (K8 finding: all in-run exports died at char ~8190 while
            # file-redirected exports of the same sessions were complete). File writes are
            # synchronous, so the redirect sidesteps the truncation class entirely.
            # Two attempts: opencode spawns an internal server per invocation and can also fail
            # transiently right after the previous invocation (the summary turn) exits.
            last = ""
            tmp = workspace / f"_export_{sid}.json"
            for attempt in (1, 2):
                try:
                    exp = sandbox.run_command(
                        ["bash", "-c", f"exec opencode export {shlex.quote(sid)} > {shlex.quote(tmp.name)}",
                         "opencode-export"],
                        SandboxSpec(workdir=workspace, network="none",
                                    limits=RunLimits(wall_clock_s=60), env=env))
                    out = tmp.read_text().strip() if tmp.exists() else ""
                    brace = out.find("{")           # tolerate any non-JSON preamble
                    if exp.returncode == 0 and brace != -1:
                        payload = out[brace:]
                        json.loads(payload)         # validate it's real JSON before trusting it
                        dest.write_text(payload)
                        tmp.unlink(missing_ok=True)
                        return True
                    last = (f"rc={exp.returncode} file[:120]={out[:120]!r} "
                            f"stderr[:120]={(exp.stderr or '')[:120]!r}")
                except (json.JSONDecodeError, ValueError, OSError) as exc:
                    last = f"{type(exc).__name__}: {exc}"
                if attempt == 1:
                    time.sleep(2)
            tmp.unlink(missing_ok=True)
            export_errors[sid] = last               # surfaced in provenance, not swallowed
            return False

        session_json_saved = bool(session_id) and _export_session(
            session_id, req.workdir / "opencode_session.json")

        # Subagent (task tool) child sessions: their turn-by-turn transcripts live only in the
        # session store — export each one alongside the parent (best-effort; the children's
        # *products* are durable in the workspace/DB regardless).
        child_ids = _extract_child_session_ids("\n".join(transcript), session_id)
        children_exported = [sid for sid in child_ids
                             if _export_session(sid, req.workdir / f"opencode_child_{sid}.json")]

        # Keep the (small) raw session store as the last-resort record, then drop the ~100 MB
        # HOME (_ochome: cache / node_modules / snapshots). The session was only needed for the
        # nudge + summary turns + the exports above. (_ochome is a sibling of workspace, so it
        # never entered eval snapshots — but it still bloats the run dir if left behind.)
        store_saved = _preserve_session_store(oc_home, req.workdir)
        shutil.rmtree(oc_home, ignore_errors=True)

        # opencode_session.json (above) is the complete record — prompts + responses — whenever
        # the export succeeded, so it supersedes the assembled-from-stdout transcript. Only write
        # the transcript log as a FALLBACK when the export didn't save, so there is always some
        # session record for the agreement-gate tamper scan.
        if not session_json_saved:
            (req.workdir / "opencode_session.log").write_text(
                "\n\n=== ROUND ===\n".join(transcript) + "\n--- STDERR ---\n" + (cmd_result.stderr or ""))
        (req.workdir / "_opencode_provenance.json").write_text(json.dumps({
            "opencode_pinned_version": OPENCODE_PINNED_VERSION,
            "model": model_arg,
            "yolo": yolo,
            "argv": argv[:-1] + ["<kickoff>"],
            "returncode": cmd_result.returncode,
            "timed_out": cmd_result.timed_out,
            "nudge_rounds": nudges,
            "session_json_saved": session_json_saved,
            "child_sessions": {"found": child_ids, "exported": children_exported},
            "session_export_errors": export_errors,
            "session_store_saved": store_saved,
            "final_framework_eval": {"ran": final_eval is not None,
                                     "returncode": getattr(final_eval, "returncode", None),
                                     "design_file": final_name if final_eval is not None else None,
                                     **({"note": final_eval_note} if final_eval_note else {})},
            "summary_turn": {
                "session_id": session_id,
                "ran": summary_result is not None,
                "returncode": getattr(summary_result, "returncode", None),
            },
            "opencode_config": opencode_cfg,
        }, indent=2))

        # stop_reason reflects how the agent phase ended (after any nudges).
        if cmd_result.timed_out:
            stop_reason = "timeout"
        elif cmd_result.returncode == 0:
            stop_reason = "completed"
        else:
            stop_reason = "error"

        token_usage = _parse_token_usage("\n".join(transcript))
        return _harvest(req, stop_reason, cmd_result, token_usage)

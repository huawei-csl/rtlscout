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
  4. Harvest the standard on-disk tree (``evals.jsonl`` / ``eval_{i}/`` / ``best_design/``
     / ``summary.txt``) the eval shim produced, and build an ``AgentResult``.

The recorded score is NOT trusted from here — the harness re-derives it with
``core.reeval.reeval_run`` against the benchmark's own inputs (mandatory on this path).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict

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

_DESIGN_FILE_BY_LANG = {"spirehdl": "design.py", "amaranth": "design.py", "verilog": "design.sv"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _metric_name(req: "BackendRequest") -> str:
    return req.cost_metric.metric_name if req.cost_metric else "transistors"


def render_agents_md(req: "BackendRequest") -> str:
    """Render AGENTS.md: the per-language task/spec prompt from core.prompts, the seed
    text, and an OpenCode execution section that overrides the react tool mechanics."""
    from core.prompts import (build_amaranth_system_prompt, build_spirehdl_system_prompt,
                              build_system_prompt)

    metric_name = _metric_name(req)
    td_settable = bool(req.cost_metric is not None and hasattr(req.cost_metric, "target_delay"))
    budget = req.limits.max_evals or req.limits.max_steps or 20

    if req.language == "spirehdl":
        base = build_spirehdl_system_prompt(
            req.benchmark.description, metric_name, extra="",
            target_delay_is_settable=td_settable, max_steps=budget,
            flowy_optimize=req.flowy_optimize, abc_optimize=req.abc_optimize,
            arith_autoconfig=req.arith_autoconfig, dont_touch_main_arith=req.dont_touch_main_arith,
            fsm_optimize=req.fsm_optimize)
    elif req.language == "amaranth":
        base = build_amaranth_system_prompt(
            req.benchmark.description, metric_name, extra="",
            target_delay_is_settable=td_settable, max_steps=budget)
    else:
        base = build_system_prompt(
            req.benchmark.description, metric_name, extra="",
            target_delay_is_settable=td_settable, max_steps=budget)

    parts = [base]
    if req.system_prompt_extra:
        parts.append("\n## Additional guidance (seed / lessons)\n\n" + req.system_prompt_extra)
    parts.append(_opencode_execution_section(req, metric_name))
    return "\n".join(parts)


def _opencode_execution_section(req: "BackendRequest", metric_name: str) -> str:
    design_file = _DESIGN_FILE_BY_LANG.get(req.language, "design.sv")
    budget_line = (f"You have an evaluation budget of ~{req.limits.max_evals} scored evaluations"
                   if req.limits.max_evals else "Use evaluations judiciously")
    secs = req.limits.wall_clock_s
    budget_min = f"~{secs // 60} minutes" if secs else "a fixed wall-clock budget"
    return f"""
## OpenCode execution environment (AUTHORITATIVE — overrides any tool notes above)

You are running as an autonomous coding agent with a **real shell and your own
file-editing tools**, in your working directory. Ignore any earlier references to
`create_file` / `replace_file` / `apply_diff` / `edit_file` / `run_evaluation` / `done`
tools and to a per-response "always call a tool" rule — those describe a *different*
harness. Here you simply read, write and edit files directly and run shell commands.

**Your design file:** put your design in `{design_file}` in the current directory
(create helper files as needed).

**How to evaluate (get a correctness + cost score):** run

    ./evaluate_design {design_file}

This runs the project's evaluator on your design, prints correctness (lint/sim/CEC) and
the `{metric_name}` cost, and snapshots the result. Use it to iterate: get a correct
design first, then minimize `{metric_name}` cost without breaking correctness. {budget_line}.

**Time budget — keep going until it runs out.** You have {budget_min} of wall-clock time and
there is **no step/turn limit**. Check how much is left at any point by running:

    ./remaining_time

Do **NOT** stop after one or two evaluations. Keep trying genuinely different designs /
micro-architectures (e.g. different multiplier/adder configurations, pipelining, sharing) and
re-evaluating each with `./evaluate_design`, keeping the best result, until `./remaining_time`
is near zero (or you see a `[BUDGET]` message). Only then do the required final steps below.

**REQUIRED final steps before you stop (do these in order):**
1. Make sure your best design is in `{design_file}` and run `./evaluate_design {design_file}`
   one final time so the recorded best reflects it.
2. Write a file named `summary.txt` in the current directory, a brief, specific summary covering:
{REFLECTION_PROMPTS}

Your design files carry over to the next agent, so refer to them by filename where useful.
"""


# All opencode permission categories (v1.17.11 schema). The critical fix (handover §4.8):
# in non-interactive `opencode run`, any permission left at the default "ask" is
# AUTO-REJECTED and that aborts the run — which is exactly what killed a run mid-optimization
# when the agent tried to read the SpireHDL package source (an `external_directory` access).
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
    non-interactive runs apply edits AND can read the SpireHDL package source to explore
    architectures (handover §4.8). The provider key is supplied via env, never here (O4)."""
    model_arg = f"{req.provider}/{req.model}"
    perms = _permissions(yolo)
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": model_arg,
        "instructions": ["AGENTS.md"],
        "permission": perms,
        "agent": {
            "rtl": {
                "description": "Autonomous RTL design-optimization agent (non-interactive).",
                "mode": "primary",
                "model": model_arg,
                "permission": perms,
                "tools": {"write": True, "edit": True, "bash": True, "read": True},
            },
        },
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
        "max_evals": req.limits.max_evals,
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
    """Synthesize a minimal summary.txt from evals.jsonl when the agent left none."""
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
    all_evals = read_evals(workdir / "evals.jsonl")
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

        # Provider key via env (never in opencode.json).
        env: Dict[str, str] = {}
        keyvar = _PROVIDER_ENV.get(req.provider)
        if keyvar:
            val = req.api_key or os.environ.get(keyvar)
            if val:
                env[keyvar] = val

        # Give opencode a guaranteed-writable HOME under the run dir, so its config/cache
        # never depend on the container's HOME ownership (robust across uid remapping /
        # fresh orchestrated containers). Project-local opencode.json + the env key mean
        # no global config or auth file is needed.
        oc_home = req.workdir / "_ochome"
        oc_home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(oc_home)

        model_arg = f"{req.provider}/{req.model}"
        kickoff = (
            "Implement and optimize the RTL design described in AGENTS.md. Start with a simple "
            "correct implementation, run ./evaluate_design to score it, then iterate to minimize "
            f"the {metric_name} cost while staying correct. Follow the REQUIRED final steps in "
            "AGENTS.md before you stop."
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
        spec = SandboxSpec(workdir=workspace, network="provider", limits=req.limits, env=env)

        # Stamp the wall-clock deadline as close to launch as possible so the agent's
        # ./remaining_time reflects the real budget (0 = no limit).
        wall_s = req.limits.wall_clock_s
        (req.workdir / "_deadline_epoch").write_text(
            str(int(time.time()) + wall_s) if wall_s else "0")

        cmd_result = sandbox.run_command(argv, spec)

        # Persist the session for provenance + the agreement-gate tamper scan.
        (req.workdir / "opencode_session.log").write_text(
            (cmd_result.stdout or "") + "\n--- STDERR ---\n" + (cmd_result.stderr or ""))
        (req.workdir / "_opencode_provenance.json").write_text(json.dumps({
            "opencode_pinned_version": OPENCODE_PINNED_VERSION,
            "model": model_arg,
            "yolo": yolo,
            "argv": argv[:-1] + ["<kickoff>"],
            "returncode": cmd_result.returncode,
            "timed_out": cmd_result.timed_out,
            "opencode_config": opencode_cfg,
        }, indent=2))

        if cmd_result.timed_out:
            stop_reason = "timeout"
        elif cmd_result.returncode == 0:
            stop_reason = "completed"
        else:
            stop_reason = "error"

        token_usage = _parse_token_usage(cmd_result.stdout)
        return _harvest(req, stop_reason, cmd_result, token_usage)

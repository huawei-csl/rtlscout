"""Agent-backend seam: pluggable agent implementations behind one interface.

Two backends share this seam (handover doc §3, §4.1, §5.1):

  - ``PythonReactBackend`` — the in-process ReAct loop (``core.agent.RTLAgent``).
    This is the **default** and the only backend that keeps the offline ``fake:``
    smoke test working (OpenCode cannot replay a canned fake).
  - ``OpenCodeBackend`` — external ``opencode run`` with a real shell (added in Phase 2,
    ``core.opencode_backend``).

INVARIANT (handover doc §4.2): **one run == one fresh agent session == one fresh
context window.** A backend MUST NOT carry conversational state between ``run()``
calls. The only cross-run channels are seed *files* staged into the workspace and
seed/lessons *text* in ``system_prompt_extra`` — never session state.

Note on the return type: both backends return the existing rich
``core.agent.AgentResult`` rather than the slimmer ``AgentRunResult`` sketched in
the handover doc §5.1. ``AgentResult`` already carries a superset of those fields
*plus* ``messages`` / ``best_eval`` / ``all_evals`` / ``num_steps`` that
``chat_log.txt``, ``result.json`` and ``core.multirun.make_elite_entry`` all
require — so returning it is what keeps the Phase-0 react path byte-identical.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:  # type-only imports — keeps this module import-light and cycle-proof
    from core.agent import AgentResult
    from core.benchmarks import Benchmark
    from core.cost import CostMetric
    from core.sandbox import Sandbox


@dataclass
class RunLimits:
    """Per-run budget.

    ``max_steps`` is the ReAct turn cap used by the react backend. ``wall_clock_s`` is the
    hard subprocess/container timeout used by the OpenCode backend (which has no turn cap);
    ``0`` means "no wall-clock limit". The two backends use different limiters: react is
    step-bounded, OpenCode is time-bounded.
    """
    wall_clock_s: int = 0
    max_steps: int = 20


@dataclass
class BackendConfig:
    """Backend selection + backend-specific knobs, bundled once at the CLI layer.

    Travels opaquely through ``run_multirun`` → task dict → ``run_agent_on_benchmark``, so
    the shared plumbing never enumerates backend-specific fields — a new knob touches this
    dataclass and the backend that reads it, nothing in between.

    ``name`` selects the backend ('react' | 'opencode'). ``deploy_mode``
    ('single-container' | 'orchestrated') selects the Sandbox implementation for the agent
    and the judge; 'orchestrated' applies to the opencode backend only — the react agent
    has no shell and always runs in-process (its in-process score is already trustworthy),
    so containerizing it — or its judge — buys nothing. ``reeval`` forces the authoritative
    post-run re-score on the react path for apples-to-apples A/B parity (it is always on
    for opencode — see ``wants_reeval``). ``wall_clock_s`` is the opencode hard per-run
    budget (0 = no limit; react is step-bounded and ignores it). ``design_db_skills`` /
    ``design_db_path`` opt the opencode run into the design-DB skills layer (see
    ``BackendRequest``). ``session_id`` labels + scopes a campaign's orchestrated
    containers; ``run_multirun`` stamps it per campaign.
    """
    name: str = "react"
    deploy_mode: str = "single-container"
    reeval: bool = False
    wall_clock_s: int = 0
    design_db_skills: bool = False
    design_db_path: Optional[Path] = None
    session_id: str = ""

    def __post_init__(self):
        if self.deploy_mode == "orchestrated" and self.name != "opencode":
            raise ValueError(
                f"deploy_mode 'orchestrated' applies to the opencode backend only (got "
                f"backend {self.name!r}). The react agent runs in-process; use "
                f"'single-container', or switch to the opencode backend.")

    @property
    def wants_reeval(self) -> bool:
        """Authoritative re-eval is mandatory on the opencode path (its container is
        untrusted); on react it is opt-in via ``reeval`` purely for A/B parity."""
        return self.reeval or self.name == "opencode"


@dataclass
class BackendRequest:
    """Everything a backend needs to run one already-provisioned session.

    The workspace (``workdir/workspace``) has already been provisioned by
    ``core.runner.provision_workspace`` with the benchmark's testbench, data files,
    context and (separately) the resolved golden reference (``cec_reference``).
    """
    benchmark: "Benchmark"
    workdir: Path
    workspace: Path
    model: str
    provider: str
    cost_metric: Optional["CostMetric"]
    language: str
    limits: RunLimits
    system_prompt_extra: str = ""
    api_key: Optional[str] = None
    cec_reference: Optional[Path] = None
    run_cec: bool = True
    save_workspaces: bool = True
    flowy_optimize: bool = False
    abc_optimize: bool = False
    arith_autoconfig: bool = False
    dont_touch_main_arith: bool = False
    fsm_optimize: bool = False
    # Design-DB skills layer (opt-in, opencode backend only): provision the skill pack, merge
    # the rtl-subcircuit/rtl-dv-prep subagents, add the AGENTS.md section, and hand a DB over
    # (design_db_path → $SPIREHDL_DB_PATH → workspace-local ./design_db, spire's default).
    # The DB itself is spire's — this layer is the guidance + handover, not the capability.
    # Off ⇒ the plain opencode run (pre-K3 state). React ignores both.
    design_db_skills: bool = False
    design_db_path: Optional[Path] = None       # explicit DB root (e.g. multirun's campaign DB)
    # The agent-role sandbox (handover §3.1). None ⇒ the backend uses a LocalSandbox
    # (single-container mode). Phase 3 sets this to a ContainerSandbox for orchestrated mode.
    agent_sandbox: Optional["Sandbox"] = None


class AgentBackend(Protocol):
    """One run == one fresh agent session == one fresh context window.

    MUST NOT carry conversational state between calls. Cross-run transfer is ONLY
    via files already in ``req.workspace`` and text already in
    ``req.system_prompt_extra``.
    """
    name: str

    def run(self, req: BackendRequest) -> "AgentResult":
        ...


class PythonReactBackend:
    """Thin adapter over ``core.agent.RTLAgent`` — today's in-process ReAct loop.

    Behaviour is byte-for-byte identical to the pre-seam ``run_agent_on_benchmark``
    flow: build the provider client, construct ``RTLAgent`` with the same arguments,
    set the top module, and run. Each ``run()`` constructs a brand-new ``RTLAgent``
    (fresh ``messages=[system_prompt]``), honouring the one-run-one-context invariant.
    Keeps the ``fake:`` provider path working.
    """
    name = "react"

    def run(self, req: BackendRequest) -> "AgentResult":
        # Lazy imports: avoids any import cycle (core.runner imports this module) and
        # keeps module import light.
        from core.agent import RTLAgent
        from core.runner import build_client

        client = build_client(req.provider, req.model, req.api_key)
        agent = RTLAgent(
            client=client,
            workdir=req.workdir,
            max_steps=req.limits.max_steps,
            cost_metric=req.cost_metric,
            system_prompt_extra=req.system_prompt_extra,
            language=req.language,
            save_workspaces=req.save_workspaces,
            flowy_optimize=req.flowy_optimize,
            abc_optimize=req.abc_optimize,
            arith_autoconfig=req.arith_autoconfig,
            dont_touch_main_arith=req.dont_touch_main_arith,
            fsm_optimize=req.fsm_optimize,
            run_cec=req.run_cec and req.cec_reference is not None,
            cec_reference=req.cec_reference,
        )
        agent.design_top_module = req.benchmark.module_name
        return agent.run(req.benchmark.description, req.benchmark.name)


def make_backend(name: str) -> AgentBackend:
    """Construct the agent backend selected by ``--agent-backend`` (default ``react``)."""
    if name == "react":
        return PythonReactBackend()
    if name == "opencode":
        from core.opencode_backend import OpenCodeBackend  # added in Phase 2
        return OpenCodeBackend()
    raise ValueError(f"Unknown agent backend: {name!r}. Use 'react' or 'opencode'.")

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

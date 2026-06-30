"""The ``Sandbox`` seam (handover doc §3.1, §5.1b): *where* work runs.

Two roles share this abstraction:
  - **Agent role** — runs the backend (for OpenCode, a shell). One per run.
  - **Judge role** — runs ``evaluate()`` on the extracted design + the benchmark's own
    inputs. One per scored candidate. Needed even on the trusted side because
    ``evaluate()`` *executes* the agent-authored ``.py``.

Two implementations, selected by ``--mode``:
  - ``LocalSandbox`` (this module) — run the work in the current process/container
    (``single-container`` mode). No new container.
  - ``ContainerSandbox`` (added in Phase 3) — ``docker run --rm`` a fresh container
    (``orchestrated`` mode).

Assurance is a property of the *mode*, not this code (see §3.1): ``single-container +
opencode`` is the convenience/lower-assurance path; ``orchestrated`` is the
adversarial-agent guarantee.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Protocol, Sequence

if TYPE_CHECKING:
    from core.agent_backend import RunLimits


@dataclass
class SandboxSpec:
    """Where + how a unit of work runs."""
    workdir: Path                                   # dir the work runs in (bind-mounted in container mode)
    mounts_ro: Sequence[Path] = field(default_factory=tuple)  # read-only inputs (repo/deps in container mode)
    network: str = "none"                           # "none" | provider-allowlist | ...
    limits: Optional["RunLimits"] = None
    env: Optional[dict] = None                       # extra env (e.g. provider key) for command runs


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class Sandbox(Protocol):
    name: str

    def run_callable(self, fn: Callable[[], Any], spec: SandboxSpec) -> Any:
        """Run a Python callable (used by the judge: evaluate)."""
        ...

    def run_command(self, argv: List[str], spec: SandboxSpec) -> CommandResult:
        """Run a subprocess (used by OpenCode / the eval shim)."""
        ...


class LocalSandbox:
    """Run the work in the current process/container (single-container mode).

    ``run_callable`` executes ``fn`` in-process. Note (§3.1): with the OpenCode
    backend this shares the container with the agent, so it carries the lower
    assurance caveat — ``reeval`` still rebuilds from the benchmark's own inputs in a
    fresh workdir (defending against accidental tampering / nondeterminism), but it is
    not the adversarial-agent guarantee. For that, use ``ContainerSandbox``.
    """
    name = "local"

    def run_callable(self, fn: Callable[[], Any], spec: SandboxSpec) -> Any:
        return fn()

    def run_command(self, argv: List[str], spec: SandboxSpec) -> CommandResult:
        timeout = None
        if spec.limits is not None and spec.limits.wall_clock_s:
            timeout = spec.limits.wall_clock_s
        env = None
        if spec.env is not None:
            import os
            env = {**os.environ, **spec.env}
        try:
            proc = subprocess.run(
                argv, cwd=str(spec.workdir), env=env,
                capture_output=True, text=True, timeout=timeout,
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr, timed_out=False)
        except subprocess.TimeoutExpired as e:
            return CommandResult(
                returncode=124,
                stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
                timed_out=True,
            )

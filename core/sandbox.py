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

import atexit
import os
import signal
import subprocess
import time
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
    mounts_rw: Sequence[Path] = field(default_factory=tuple)  # extra writable identity mounts
    #   (container mode only; e.g. a shared $SPIREHDL_DB_PATH design DB — LocalSandbox ignores)


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
    runs_in_process = True  # reeval can hand it a Python callable directly

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


# --- Crash-safety registry (handover §5.5 layer 1): stop exactly the containers we
# launched on normal exit / SIGINT / SIGTERM. The label-based `rtlscout --cleanup` orphan
# sweep (layer 3) backstops the uncatchable-SIGKILL gap.
_ACTIVE_CONTAINERS: set = set()
_HANDLERS_INSTALLED = False


def _reap_active_containers(*_a):
    for name in list(_ACTIVE_CONTAINERS):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
        _ACTIVE_CONTAINERS.discard(name)


def _install_crash_handlers():
    global _HANDLERS_INSTALLED
    if _HANDLERS_INSTALLED:
        return
    atexit.register(_reap_active_containers)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            prev = signal.getsignal(sig)

            def _handler(signum, frame, _prev=prev):
                _reap_active_containers()
                if callable(_prev) and _prev not in (signal.SIG_DFL, signal.SIG_IGN):
                    _prev(signum, frame)
                else:
                    raise SystemExit(128 + signum)
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass  # not in main thread (e.g. some pool workers) — atexit still covers normal exit
    _HANDLERS_INSTALLED = True


class ContainerSandbox:
    """Run work in a fresh ``docker run`` container (orchestrated mode, handover §3.1/§5.5).

    Uses **identity mounts** (host path == container path) for the run work-root and the
    repo, so paths in generated wrappers/configs are valid both in the harness and in the
    launched container (the docker-in-docker path-translation trap). Every container is
    stamped with the ``rtlscout.*`` labels and a human-readable name, runs as the host
    uid/gid (so the bind-mounted, host-owned work-root is writable), and is network/cpu/
    memory limited. ``--rm`` reaps on exit; the crash-safety registry + the label sweep
    cover the harness-died-mid-run gaps.
    """
    runs_in_process = False  # work runs via run_command (a CLI), not in-process callables

    def __init__(self, role: str, session_id: str, work_root: Path, host_repo: Path,
                 run_index: int = 0, image: str = "rtlscout-opencode:latest",
                 network: str = "none", cpus: Optional[float] = None,
                 memory: Optional[str] = None, stop_timeout: int = 120):
        self.role = role
        self.session_id = session_id
        self.work_root = Path(work_root).resolve()
        self.host_repo = Path(host_repo).resolve()
        self.run_index = run_index
        self.image = image
        self.network = network
        self.cpus = cpus
        self.memory = memory
        self.stop_timeout = stop_timeout
        self.name = "container"
        self._seq = 0
        _install_crash_handlers()

    def _container_name(self) -> str:
        self._seq += 1
        return f"rtlscout-{self.role}-{self.session_id[:8]}-{self.run_index:03d}-{self._seq:02d}"

    def run_callable(self, fn: Callable[[], Any], spec: SandboxSpec) -> Any:
        raise NotImplementedError(
            "ContainerSandbox runs work via run_command (a CLI), not in-process callables; "
            "reeval uses `python -m core.reeval` inside the judge container.")

    def run_command(self, argv: List[str], spec: SandboxSpec) -> CommandResult:
        name = self._container_name()
        labels = [
            "--label", "rtlscout.managed=true",
            "--label", f"rtlscout.session={self.session_id}",
            "--label", f"rtlscout.role={self.role}",
            "--label", f"rtlscout.run={self.run_index}",
            "--label", f"rtlscout.started={int(time.time())}",
        ]
        docker = [
            "docker", "run", "--rm", "--name", name,
            *labels,
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--network", self.network,
            "--stop-timeout", str(self.stop_timeout),
            # identity mounts: host path == container path (no translation needed)
            "-v", f"{self.work_root}:{self.work_root}",
            "-v", f"{self.host_repo}:{self.host_repo}:ro",
            "-w", str(Path(spec.workdir).resolve()),
        ]
        for extra in spec.mounts_rw:            # e.g. a shared design DB — writable identity mount
            p = Path(extra).resolve()
            docker += ["-v", f"{p}:{p}"]
        if self.cpus:
            docker += ["--cpus", str(self.cpus)]
        if self.memory:
            docker += ["--memory", str(self.memory)]
        for k, v in (spec.env or {}).items():
            docker += ["-e", f"{k}={v}"]
        docker += [self.image, *argv]

        timeout = None
        if spec.limits is not None and spec.limits.wall_clock_s:
            timeout = spec.limits.wall_clock_s + 60  # grace over the in-container budget

        _ACTIVE_CONTAINERS.add(name)
        try:
            proc = subprocess.run(docker, capture_output=True, text=True, timeout=timeout)
            return CommandResult(proc.returncode, proc.stdout, proc.stderr, timed_out=False)
        except subprocess.TimeoutExpired as e:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
            return CommandResult(
                returncode=124,
                stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
                timed_out=True,
            )
        finally:
            _ACTIVE_CONTAINERS.discard(name)

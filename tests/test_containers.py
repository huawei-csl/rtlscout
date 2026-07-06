"""Phase-3 container-management tests (handover §5.5, §9). No API/LLM — just docker.

Validates that label-scoped cleanup removes ONLY this framework's containers
(rtlscout.managed=true), leaves a VS Code devcontainer stand-in untouched, honours the
belt-and-suspenders devcontainer.local_folder guard, and sweeps running orphans (the
SIGKILLed-harness case). Skips when docker isn't usable (e.g. inside a socket-less
container); run on a docker-capable host.
"""
import shutil
import subprocess
import uuid

import pytest

from core.containers import cleanup, list_managed


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


requires_docker = pytest.mark.skipif(not _docker_ok(), reason="docker not usable here")

# A tiny, ubiquitous image so the test doesn't depend on rtlscout:latest being present.
TEST_IMAGE = "ubuntu:24.04"


def _run(name, labels, test_tag):
    args = ["docker", "run", "-d", "--rm", "--name", name, "--label", f"rtlscout.test={test_tag}"]
    for k, v in labels.items():
        args += ["--label", f"{k}={v}"]
    args += [TEST_IMAGE, "sleep", "300"]
    subprocess.run(args, capture_output=True, text=True, check=True)


def _exists(name) -> bool:
    out = subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{name}$"],
                         capture_output=True, text=True).stdout.strip()
    return bool(out)


@requires_docker
def test_cleanup_is_label_scoped_and_devcontainer_safe():
    sid = "pytest-" + uuid.uuid4().hex[:8]
    tag = uuid.uuid4().hex[:8]
    mg = f"rtlscout-test-mg-{tag}"          # managed -> must be removed
    standin = f"rtlscout-test-ide-{tag}"    # devcontainer stand-in (no managed) -> must survive
    guard = f"rtlscout-test-guard-{tag}"    # managed BUT devcontainer-labelled -> must be skipped
    try:
        _run(mg, {"rtlscout.managed": "true", "rtlscout.session": sid, "rtlscout.role": "agent"}, tag)
        _run(standin, {"devcontainer.local_folder": "/home/dev/proj"}, tag)
        _run(guard, {"rtlscout.managed": "true", "rtlscout.session": sid,
                     "devcontainer.local_folder": "/home/dev/proj"}, tag)

        # list_managed (scoped) sees the two managed ones, never the pure stand-in.
        names = {r.get("Names") for r in list_managed(session=sid)}
        assert mg in names and guard in names
        assert standin not in names

        report = cleanup(session=sid)

        assert mg in report["removed"]
        assert guard in report["skipped_devcontainer"]
        assert not _exists(mg), "managed container must be removed"
        assert _exists(standin), "devcontainer stand-in must survive (not rtlscout.managed)"
        assert _exists(guard), "devcontainer-labelled container must be skipped even if managed"
    finally:
        subprocess.run("docker ps -aq --filter label=rtlscout.test=" + tag
                       + " | xargs -r docker rm -f", shell=True, capture_output=True)


@requires_docker
def test_orphan_sweep_removes_running_managed():
    """The SIGKILLed-harness case: a still-running managed container is swept by cleanup."""
    sid = "pytest-" + uuid.uuid4().hex[:8]
    tag = uuid.uuid4().hex[:8]
    orphan = f"rtlscout-test-orphan-{tag}"
    try:
        _run(orphan, {"rtlscout.managed": "true", "rtlscout.session": sid, "rtlscout.role": "judge"}, tag)
        assert _exists(orphan)
        report = cleanup(session=sid)
        assert orphan in report["removed"]
        assert not _exists(orphan)
    finally:
        subprocess.run("docker ps -aq --filter label=rtlscout.test=" + tag
                       + " | xargs -r docker rm -f", shell=True, capture_output=True)

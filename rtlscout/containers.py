"""Label-based management of rtlscout-launched containers (handover doc §5.5).

THE devcontainer-safety contract: managed containers are identified ONLY by the
``rtlscout.managed=true`` label — **never by image**. The VS Code devcontainer shares
``rtlscout:latest`` but carries no ``rtlscout.*`` labels, so every selector here is
guaranteed-disjoint from it by construction. Cleanup additionally refuses to touch any
container carrying ``devcontainer.local_folder`` (belt-and-suspenders).

This module is plain ``docker`` CLI (no new deps, matches the repo's shell-out style) and
is importable both by the harness (``ContainerSandbox``) and by the ``rtlscout`` cleanup
CLI (which must work even after the harness process is gone — handover §5.5 layer 3).
"""
from __future__ import annotations

import json
import subprocess
from typing import Dict, List, Optional

LABEL_MANAGED = "rtlscout.managed"
LABEL_SESSION = "rtlscout.session"
LABEL_ROLE = "rtlscout.role"
LABEL_RUN = "rtlscout.run"
LABEL_STARTED = "rtlscout.started"
DEVCONTAINER_LABEL = "devcontainer.local_folder"  # set by VS Code Dev Containers; never by us


def _docker(*args: str, check: bool = False, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def managed_filters(session: Optional[str] = None) -> List[str]:
    flt = ["--filter", f"label={LABEL_MANAGED}=true"]
    if session:
        flt += ["--filter", f"label={LABEL_SESSION}={session}"]
    return flt


def list_managed(session: Optional[str] = None, all_states: bool = True) -> List[Dict]:
    """Return the framework's containers (label-scoped). Never matches the devcontainer."""
    args = ["ps"] + (["-a"] if all_states else []) + managed_filters(session) + ["--format", "{{json .}}"]
    out = _docker(*args).stdout
    rows: List[Dict] = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _container_labels(container_id: str) -> Dict[str, str]:
    out = _docker("inspect", "--format", "{{json .Config.Labels}}", container_id).stdout.strip()
    try:
        return json.loads(out) or {}
    except json.JSONDecodeError:
        return {}


def has_devcontainer_label(container_id: str) -> bool:
    return DEVCONTAINER_LABEL in _container_labels(container_id)


def cleanup(session: Optional[str] = None, timeout: int = 10, kill: bool = False) -> Dict[str, List[str]]:
    """Stop + remove all managed containers (optionally one session). Refuses anything
    carrying ``devcontainer.local_folder``. Returns what it touched. Safe to run by hand
    after a SIGKILLed harness (orphan sweep, handover §5.5 layer 3)."""
    report: Dict[str, List[str]] = {"stopped": [], "removed": [], "skipped_devcontainer": [], "errors": []}
    for row in list_managed(session=session, all_states=True):
        cid = row.get("ID") or row.get("Id") or ""
        name = row.get("Names") or row.get("Name") or cid
        if not cid:
            continue
        if has_devcontainer_label(cid):
            report["skipped_devcontainer"].append(name)
            continue
        try:
            if kill:
                _docker("kill", cid)
            else:
                _docker("stop", "-t", str(timeout), cid)
            report["stopped"].append(name)
            _docker("rm", "-f", cid)
            report["removed"].append(name)
        except subprocess.SubprocessError as e:
            report["errors"].append(f"{name}: {e}")
    return report

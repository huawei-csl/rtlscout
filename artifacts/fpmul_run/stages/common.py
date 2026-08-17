"""Shared helpers: subprocess wrapper, manifest, stage state markers."""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rerun_config as cfg

if str(cfg.REPO) not in sys.path:      # for in-process imports of core.*
    sys.path.insert(0, str(cfg.REPO))


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def sh(cmd, log_name: str, cwd: Path = cfg.REPO, timeout: int | None = None,
       env_extra: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, teeing stdout+stderr to logs/<log_name>.log."""
    cfg.LOGS.mkdir(parents=True, exist_ok=True)
    log_file = cfg.LOGS / f"{log_name}.log"
    cmd = [str(c) for c in cmd]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cfg.REPO) + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    log(f"run: {' '.join(cmd)}  (log: {log_file.relative_to(cfg.REPO)})")
    with open(log_file, "a") as lf:
        lf.write(f"\n===== [{_now()}] {' '.join(cmd)}\n")
        lf.flush()
        proc = subprocess.run(cmd, cwd=str(cwd), stdout=lf, stderr=subprocess.STDOUT,
                              env=env, timeout=timeout)
    if check and proc.returncode != 0:
        tail = "".join(log_file.read_text().splitlines(keepends=True)[-40:])
        raise RuntimeError(
            f"command failed (rc={proc.returncode}): {' '.join(cmd)}\n"
            f"--- last lines of {log_file} ---\n{tail}")
    return proc


def py(script, *args) -> list:
    return [str(cfg.VENV_PYTHON), str(script), *[str(a) for a in args]]


# ------------------------------------------------------------------ manifest
def record(stage: str, path: Path, note: str) -> None:
    """Register a generated file/dir in the manifest (drives REPORT.md)."""
    entries = []
    if cfg.MANIFEST.exists():
        entries = json.loads(cfg.MANIFEST.read_text())
    p = str(path)
    entries = [e for e in entries if e["path"] != p]        # dedupe on re-run
    entries.append({"stage": stage, "path": p, "note": note, "time": _now()})
    cfg.MANIFEST.write_text(json.dumps(entries, indent=2))


def save_state(name: str, data: dict) -> None:
    cfg.STATE.mkdir(parents=True, exist_ok=True)
    (cfg.STATE / f"{name}.json").write_text(json.dumps(data, indent=2))


def load_state(name: str) -> dict | None:
    p = cfg.STATE / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def stage_done(name: str) -> bool:
    return (cfg.STATE / f"{name}.done").exists()


def mark_done(name: str) -> None:
    cfg.STATE.mkdir(parents=True, exist_ok=True)
    (cfg.STATE / f"{name}.done").write_text(_now() + "\n")


def front_design_scripts(front_dir: Path) -> list:
    """The design .py script of each design dir in a front, resolved via
    pareto_front.json's extracted_file (dirs may also contain dependency .py
    files, so globbing alone picks wrong files)."""
    front_dir = Path(front_dir)
    by_dir = {}
    manifest = front_dir / "pareto_front.json"
    if manifest.exists():
        for e in json.loads(manifest.read_text()):
            ef = e.get("extracted_file", "")
            if ef:
                by_dir[ef.split("/")[0]] = front_dir / ef
    scripts = []
    for d in sorted(x for x in front_dir.glob("design_*") if x.is_dir()):
        p = by_dir.get(d.name)
        if p is None or not p.exists() or p.suffix != ".py":
            p = next((c for c in [d / "design.py"] + sorted(d.glob("*.py"))
                      if c.exists()), None)
        if p is not None:
            scripts.append(p)
        else:
            log(f"front_design_scripts: no .py design in {d}")
    return scripts


def ensure_fresh(path: Path) -> None:
    """Refuse to write into a pre-existing non-empty dir we did not create
    (handover decision 3: never overwrite existing runs/pareto content)."""
    if path.exists() and any(path.iterdir()) and not (path / ".fpmul_rerun_owned").exists():
        raise RuntimeError(
            f"{path} already exists and is not owned by this rerun — refusing to "
            f"overwrite. Pick a new name in rerun_config.py or remove it manually.")
    path.mkdir(parents=True, exist_ok=True)
    (path / ".fpmul_rerun_owned").touch()

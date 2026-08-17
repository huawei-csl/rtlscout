"""Shared helpers (trimmed from the fpmul rerun suite): logged subprocess
runner, manifest, stage markers."""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rr_config as cfg

if str(cfg.REPO) not in sys.path:
    sys.path.insert(0, str(cfg.REPO))


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def sh(cmd, log_name: str, cwd: Path = cfg.REPO, check: bool = True,
       env_extra: dict | None = None) -> subprocess.CompletedProcess:
    cfg.LOGS.mkdir(parents=True, exist_ok=True)
    log_file = cfg.LOGS / f"{log_name}.log"
    cmd = [str(c) for c in cmd]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{cfg.REPO}:{cfg.REPO}/deps/tech_eval/src:" + env.get("PYTHONPATH", "")
    env["MPLBACKEND"] = "Agg"
    if env_extra:
        env.update(env_extra)
    log(f"run: {' '.join(cmd)}  (log: {log_file})")
    with open(log_file, "a") as lf:
        lf.write(f"\n===== [{_now()}] {' '.join(cmd)}\n")
        lf.flush()
        proc = subprocess.run(cmd, cwd=str(cwd), stdout=lf,
                              stderr=subprocess.STDOUT, env=env)
    if check and proc.returncode != 0:
        tail = "".join(log_file.read_text(errors="replace").splitlines(keepends=True)[-30:])
        raise RuntimeError(f"command failed (rc={proc.returncode}): {' '.join(cmd)}\n"
                           f"--- last lines of {log_file} ---\n{tail}")
    return proc


def py(script, *args) -> list:
    return [str(cfg.VENV_PYTHON), str(script), *[str(a) for a in args]]


def record(stage: str, path: Path, note: str) -> None:
    entries = json.loads(cfg.MANIFEST.read_text()) if cfg.MANIFEST.exists() else []
    entries = [e for e in entries if e["path"] != str(path)]
    entries.append({"stage": stage, "path": str(path), "note": note, "time": _now()})
    cfg.MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    cfg.MANIFEST.write_text(json.dumps(entries, indent=2))


def stage_done(name: str) -> bool:
    return (cfg.STATE / f"{name}.done").exists()


def mark_done(name: str) -> None:
    cfg.STATE.mkdir(parents=True, exist_ok=True)
    (cfg.STATE / f"{name}.done").write_text(_now() + "\n")

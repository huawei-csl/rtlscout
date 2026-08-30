"""Smoke tests — exercise every part of the pipeline cheaply before the real
campaigns. Includes the mandatory positive control: the verification harness
must FLAG the known-buggy old design_005, or the harness itself is broken.

Steps (each recorded in state/smoke.json):
  0. stage 0 in full (golden, directed vectors, baseline eval)
  1. Stage V controls: old-repo golden vs new golden (must PASS),
     buggy old design_005 vs golden (must FAIL)
  2. one short agent run (1 run x SMOKE_MAX_STEPS, Opus 5)
  3. extract_pareto on the smoke run
  4. patchability gate on the smoke-front designs (spire-era converter)
  5. batch_deepsyn --smoke from the golden + batch_eval on its outputs
"""
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg
import stage0_setup
import stage1_agent
import stagev_verify

SMOKE = cfg.DATA / "smoke"


def _control_front(name: str, design_v: Path) -> Path:
    front = SMOKE / name
    d = front / "design_000"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(design_v, d / "design.v")
    return front


def step_stage0(results: dict) -> None:
    stage0_setup.run()
    results["stage0"] = {"ok": True, "baseline": common.load_state("baseline")}


def step_verify_controls(results: dict) -> None:
    good = stagev_verify.verify_front(
        _control_front("control_golden", cfg.OLD_GOLDEN), "smoke_control_golden",
        exclude=False)
    ok_good = good["passed"] == good["total"] == 1
    bad = stagev_verify.verify_front(
        _control_front("control_buggy", cfg.BUGGY_CONTROL), "smoke_control_buggy",
        exclude=False)
    bd = bad["designs"][0]
    ok_bad = (bad["passed"] == 0
              and not bd["regression"]["passed"]
              and bd["exhaustive"]["mismatches"] > 0)
    results["verify_controls"] = {
        "ok": ok_good and ok_bad,
        "old_golden_equivalent_to_new": ok_good,
        "buggy_design_flagged": ok_bad,
        "buggy_mismatch_count": bd.get("exhaustive", {}).get("mismatches"),
    }
    if not ok_good:
        raise RuntimeError("SMOKE FAIL: old-repo golden vs regenerated golden mismatch")
    if not ok_bad:
        raise RuntimeError("SMOKE FAIL: harness did NOT flag the known-buggy design_005")


def step_agent(results: dict) -> None:
    stage1_agent.run_campaign("smoke", cfg.RUNS_SMOKE, "area", 1, 1, 1, None,
                              max_steps=cfg.SMOKE_MAX_STEPS)
    evals = list(Path(cfg.RUNS_SMOKE).rglob("eval_*/result.json"))
    chats = (list(Path(cfg.RUNS_SMOKE).rglob("*chat*")) +
             list(Path(cfg.RUNS_SMOKE).rglob("*.jsonl")))
    results["agent_smoke"] = {"ok": len(evals) > 0, "num_evals": len(evals),
                              "chat_logs": len(chats)}
    if not evals:
        raise RuntimeError(f"SMOKE FAIL: agent run produced no evals in {cfg.RUNS_SMOKE}")


def step_extract(results: dict) -> None:
    front = SMOKE / "front"
    common.sh(common.py(cfg.REPO / "extract_pareto.py", cfg.RUNS_SMOKE,
                        "-o", front, "--separate-dirs"), "smoke_extract")
    designs = sorted(d for d in front.glob("design_*") if d.is_dir())
    results["extract"] = {"ok": len(designs) > 0, "designs": len(designs)}
    if not designs:
        raise RuntimeError("SMOKE FAIL: extract_pareto produced no designs")


def step_patch_gate(results: dict) -> None:
    import os
    targets = common.front_design_scripts(SMOKE / "front")
    env = {**os.environ,
           "PYTHONPATH": f"{cfg.REPO}/deps/tech_eval/src:{cfg.REPO}"}
    proc = subprocess.run(common.py(Path(__file__).parent / "patch_gate.py", *targets),
                          capture_output=True, text=True, cwd=cfg.REPO, env=env)
    gate = [json.loads(l[len("GATE_RESULT "):]) for l in proc.stdout.splitlines()
            if l.startswith("GATE_RESULT ")]
    # The machinery must work and at least one design must convert cleanly.
    # Not-ok entries are tolerated here (a degenerate 1-run smoke front can
    # contain the unmodified starting point, which real campaign fronts never
    # should — the real gate in stage 3 hard-stops on any failure).
    results["patch_gate"] = {"ok": (proc.returncode == 0 and len(gate) == len(targets)
                                    and any(g["ok"] for g in gate)),
                             "results": gate, "stderr": proc.stderr[-500:]}
    if not results["patch_gate"]["ok"]:
        raise RuntimeError(f"SMOKE FAIL: patch gate broken:\n{proc.stderr}")


def step_deepsyn(results: dict) -> None:
    out = SMOKE / "deepsyn"
    common.sh(common.py(cfg.ARTIFACTS / "ported" / "batch_deepsyn.py",
                        "--benchmark", cfg.BENCHMARK, "--top", cfg.TOP_MODULE,
                        "--initial-design", cfg.GOLDEN, "--smoke",
                        "--time-budget", 60, "--workers", 4, "-o", out),
              "smoke_deepsyn")
    ev = out / "eval_results.json"
    common.sh(common.py(cfg.REPO / "batch_eval.py", out,
                        "--benchmark", cfg.BENCHMARK,
                        "--target-delay", cfg.EVAL_TARGET_DELAYS[0],
                        "--workers", 4, "-o", ev), "smoke_deepsyn_eval")
    entries = json.loads(ev.read_text())
    passed = [e for e in entries if e.get("passed")]
    results["deepsyn"] = {"ok": len(passed) > 0,
                          "configs": len(entries), "passed": len(passed)}
    if not passed:
        raise RuntimeError("SMOKE FAIL: no deepsyn smoke design passed batch_eval")


def run() -> None:
    results: dict = {"passed": False,
                     "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    steps = [step_stage0, step_verify_controls, step_agent, step_extract,
             step_patch_gate, step_deepsyn]
    try:
        for step in steps:
            common.log(f"--- smoke: {step.__name__}")
            step(results)
            common.save_state("smoke", results)
        results["passed"] = True
    finally:
        common.save_state("smoke", results)
    common.log(f"SMOKE {'PASS' if results['passed'] else 'FAIL'}")


if __name__ == "__main__":
    run()

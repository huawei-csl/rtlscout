"""Stage 1 — multi-run agent campaigns, no decorators (paper Phase 1).
Stage 2 reuses run_campaign() with --abc-optimize and --seed-from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg


def run_campaign(name, runs_root, cost_metric, total_runs, max_concurrent,
                 fresh_first, seed_from, fresh_base=None, fresh_min=None,
                 abc_optimize=False, max_steps=cfg.MAX_STEPS) -> None:
    marker = f"campaign_{name}"
    if common.stage_done(marker):
        common.log(f"campaign {name} already done, skipping")
        return
    common.ensure_fresh(Path(runs_root))
    cmd = common.py(
        cfg.REPO / "run_multirun.py",
        "--benchmark", "fpmul_f16",
        "--model", cfg.MODEL,
        "--total-runs", total_runs,
        "--max-concurrent", max_concurrent,
        "--max-steps", max_steps,
        "--cost-metric", cost_metric,
        "--target-delay", cfg.AGENT_TARGET_DELAY,
        "--language", cfg.LANGUAGE,
        "--dont-touch-main-arith",          # keeps main arith patchable for stage 3
        "--elite-size", cfg.ELITE_SIZE,
        "--skip-cec",                       # CEC off in-run (handover decision 2)
        "--runs-root", runs_root,
    )
    if fresh_first:
        cmd += ["--fresh-first", str(fresh_first)]
    if fresh_base is not None:      # 0/0 => every run improves an elite seed
        cmd += ["--fresh-base", str(fresh_base)]
    if fresh_min is not None:
        cmd += ["--fresh-min", str(fresh_min)]
    if abc_optimize:
        cmd += ["--abc-optimize"]
    if seed_from:
        cmd += ["--seed-from", str(seed_from)]
    common.sh(cmd, marker)
    common.record("stage2" if abc_optimize else "stage1", Path(runs_root),
                  f"{name}: {total_runs} runs x {max_steps} steps, {cost_metric}-opt, "
                  f"model {cfg.MODEL}" + (", @abc_optimized" if abc_optimize else ""))
    common.mark_done(marker)


def run() -> None:
    for name, root, metric, n, conc, fresh, seed, fb, fm in cfg.CAMPAIGNS_P1:
        run_campaign(name, root, metric, n, conc, fresh, seed, fb, fm)
    common.mark_done("stage1")


if __name__ == "__main__":
    run()

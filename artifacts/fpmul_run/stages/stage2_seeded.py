"""Stage 2 — seeded agent + @abc_optimized campaigns (paper Phase 2), then
Pareto extraction and the mandatory Stage-V gate on both fronts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg
import stage1_agent
import stagev_verify


def extract_fronts() -> None:
    cfg.FRONTS.mkdir(parents=True, exist_ok=True)
    # ADP campaigns are optional per profile; when present their designs are
    # pooled into the fronts too (the glm52 run predates this and pooled
    # only area/delay — its paper states so explicitly).
    p1_adp = [cfg.RUNS_P1_ADP] if cfg.RUNS_P1_ADP else []
    p2_adp = [cfg.RUNS_P2_ADP] if cfg.RUNS_P2_ADP else []
    common.ensure_fresh(cfg.FRONT_ABC)
    common.sh(common.py(cfg.REPO / "extract_pareto.py",
                        cfg.RUNS_P1_AREA, cfg.RUNS_P1_DELAY, *p1_adp,
                        cfg.RUNS_P2_AREA, cfg.RUNS_P2_DELAY, *p2_adp,
                        "-o", cfg.FRONT_ABC, "--separate-dirs"),
              "stage2_extract_abc")
    common.record("stage2", cfg.FRONT_ABC, "Phase 1+2 Pareto front (with @abc_optimized)")
    common.ensure_fresh(cfg.FRONT_NO_ABC)
    common.sh(common.py(cfg.REPO / "extract_pareto.py",
                        cfg.RUNS_P1_AREA, cfg.RUNS_P1_DELAY, *p1_adp,
                        "-o", cfg.FRONT_NO_ABC, "--separate-dirs"),
              "stage2_extract_no_abc")
    common.record("stage2", cfg.FRONT_NO_ABC, "Phase-1-only ablation front (agent only)")


def run() -> None:
    for name, root, metric, n, conc, fresh, seed, fb, fm in cfg.CAMPAIGNS_P2:
        stage1_agent.run_campaign(name, root, metric, n, conc, fresh, seed, fb, fm,
                                  abc_optimize=True)
    extract_fronts()
    # Verification gate before Phase 3: tainted designs are removed HERE.
    s1 = stagev_verify.verify_front(cfg.FRONT_ABC, "front_abc")
    s2 = stagev_verify.verify_front(cfg.FRONT_NO_ABC, "front_no_abc")
    if s1["passed"] == 0 and s2["passed"] == 0:
        raise RuntimeError("stage 2: every front design failed verification — "
                           "harness or extraction defect, not a QoR outcome")
    common.mark_done("stage2")


if __name__ == "__main__":
    run()

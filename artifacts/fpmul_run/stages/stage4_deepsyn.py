"""Stage 4 — high-effort ABC &deepsyn refinement (paper Phase 4) plus the
equal-compute deepsyn-from-scratch baseline, evaluated at 900/1800 ps."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg
import stagev_verify

BATCH_DEEPSYN = cfg.ARTIFACTS / "ported" / "batch_deepsyn.py"


def _batch_deepsyn(initial_v: Path, out_dir: Path, num_runs: int | None,
                   log_name: str, smoke: bool = False) -> None:
    cmd = common.py(BATCH_DEEPSYN,
                    "--benchmark", cfg.BENCHMARK, "--top", cfg.TOP_MODULE,
                    "--initial-design", initial_v,
                    "--time-budget", cfg.DEEPSYN_TIME_BUDGET,
                    "--workers", cfg.DEEPSYN_WORKERS,
                    "-o", out_dir)
    if smoke:
        cmd += ["--smoke"]
    elif num_runs:
        cmd += ["--num-runs", str(num_runs)]
    common.sh(cmd, log_name)


def _batch_eval(design_root: Path, log_name: str) -> Path:
    out = design_root / "eval_results.json"
    common.sh(common.py(cfg.REPO / "batch_eval.py", design_root,
                        "--benchmark", cfg.BENCHMARK,
                        "--target-delay", *cfg.EVAL_TARGET_DELAYS,
                        "--workers", cfg.EVAL_WORKERS, "-o", out),
              log_name)
    return out


def refine() -> None:
    sources = sorted(d for d in cfg.FRONT_SWEEP_DEDUP.glob("design_*") if d.is_dir())
    if not sources:
        raise RuntimeError(f"no designs in {cfg.FRONT_SWEEP_DEDUP} — run stage 3 first")
    common.ensure_fresh(cfg.FRONT_DEEPSYN_REFINE)
    merged = []
    for src in sources:
        vs = sorted(src.glob("*.v"))
        if not vs:
            common.log(f"refine: {src} has no .v, skipping")
            continue
        out = cfg.FRONT_DEEPSYN_REFINE / src.name
        _batch_deepsyn(vs[0], out, cfg.DEEPSYN_REFINE_RUNS, f"stage4_refine_{src.name}")
        # batch_eval only scans one level of design_* dirs, so evaluate each
        # source's refinement set separately and merge.
        eval_json = _batch_eval(out, f"stage4_eval_{src.name}")
        for e in json.loads(eval_json.read_text()):
            e["source_design"] = src.name
            merged.append(e)
    out = cfg.FRONT_DEEPSYN_REFINE / "eval_results.json"
    out.write_text(json.dumps(merged, indent=2))
    common.record("stage4", out, f"deepsyn refinement evals at "
                  f"{cfg.EVAL_TARGET_DELAYS} ps ({len(merged)} entries)")


def equal_compute() -> None:
    common.ensure_fresh(cfg.FRONT_INITIAL_DEEPSYN)
    n_runs = cfg.EQUAL_COMPUTE_RUNS
    if n_runs is None:
        # Matched compute by construction (user decision 2026-07-29): the
        # from-scratch arm gets exactly as many deepsyn trajectories as the
        # refinement arm ran in total (N front designs x refine runs), at the
        # same per-trajectory budget.
        n_designs = len([d for d in cfg.FRONT_SWEEP_DEDUP.glob("design_*")
                         if d.is_dir()])
        n_runs = n_designs * cfg.DEEPSYN_REFINE_RUNS
        common.log(f"equal-compute matched: {n_designs} designs x "
                   f"{cfg.DEEPSYN_REFINE_RUNS} runs = {n_runs} trajectories")
    _batch_deepsyn(cfg.GOLDEN, cfg.FRONT_INITIAL_DEEPSYN, n_runs,
                   "stage4_equal_compute")
    out = _batch_eval(cfg.FRONT_INITIAL_DEEPSYN, "stage4_eval_equal_compute")
    common.record("stage4", out, "equal-compute deepsyn-from-scratch evals")
    # Initial-design reference points at the paper's two operating points.
    for td in cfg.EVAL_TARGET_DELAYS:
        save = cfg.STATE / f"baseline_td{int(td)}"
        common.sh(common.py(cfg.REPO / "run_eval.py", cfg.GOLDEN,
                            "--benchmark", cfg.BENCHMARK, "--language", "verilog",
                            "--cost-metric", "area", "--target-delay", td,
                            "--save-to", save),
                  f"stage4_baseline_td{int(td)}")
        common.record("stage4", save / "result.json", f"initial-design eval at {int(td)} ps")


def equal_compute_2x() -> None:
    """Optional DOUBLE-EFFORT from-scratch arm: same trajectory count as the
    matched arm but 2x the per-trajectory time budget. Comparison baseline
    only (not RTLScout method cost); shown as an extra front in the arrows
    plot, following the original paper."""
    common.ensure_fresh(cfg.FRONT_INITIAL_DEEPSYN_2X)
    n_designs = len([d for d in cfg.FRONT_SWEEP_DEDUP.glob("design_*")
                     if d.is_dir()])
    n_runs = n_designs * cfg.DEEPSYN_REFINE_RUNS
    common.log(f"double-effort arm: {n_runs} trajectories x "
               f"{2 * cfg.DEEPSYN_TIME_BUDGET} s")
    cmd = common.py(BATCH_DEEPSYN,
                    "--benchmark", cfg.BENCHMARK, "--top", cfg.TOP_MODULE,
                    "--initial-design", cfg.GOLDEN,
                    "--time-budget", 2 * cfg.DEEPSYN_TIME_BUDGET,
                    "--workers", cfg.DEEPSYN_WORKERS,
                    "--num-runs", str(n_runs),
                    "-o", cfg.FRONT_INITIAL_DEEPSYN_2X)
    common.sh(cmd, "stage4_equal_compute_2x")
    out = _batch_eval(cfg.FRONT_INITIAL_DEEPSYN_2X, "stage4_eval_equal_compute_2x")
    common.record("stage4", out, "double-effort from-scratch evals (baseline)")


def _pareto_of(ok: list[dict]) -> list[dict]:
    """Non-dominated entries of an already-filtered (passed/area/delay) list."""
    return [e for e in ok
            if not any(o["area"] <= e["area"] and o["delay"] <= e["delay"]
                       and (o["area"] < e["area"] or o["delay"] < e["delay"])
                       for o in ok)]


def _ok_entries(eval_json: Path) -> list[dict]:
    entries = json.loads(eval_json.read_text())
    return [e for e in entries if e.get("passed") and e.get("area") and e.get("delay")]


def _pareto_entries(eval_json: Path) -> list[dict]:
    """Entries on the area/delay Pareto front of a batch_eval results file."""
    return _pareto_of(_ok_entries(eval_json))


def _sweep_to_eval(e: dict) -> dict:
    """Adapt a sweep pareto_front.json record to the batch_eval entry shape."""
    return {"design": e["design"],
            "design_file": Path(e.get("extracted_file", "design.v")).name,
            "area": e["area"], "delay": e["delay"],
            "target_delay": e.get("target_delay"),
            "metrics": e.get("metrics"), "power": e.get("power"),
            "passed": float(e.get("pass_rate", 0)) >= 1.0,
            "status": "ok", "source_phase": "phase3"}


def final_front() -> None:
    """Reported RTLScout front: Pareto(Phase-4 output u the Phase-3 seed front).
    A seed design deepsyn never beat is still a result the pipeline delivered."""
    if common.stage_done("final_front"):
        common.log("final front already built — skipping")
        return
    refine_ok = _ok_entries(cfg.FRONT_DEEPSYN_REFINE / "eval_results.json")
    for e in refine_ok:
        e["source_phase"] = "phase4"
    seed_json = cfg.FRONT_SWEEP_DEDUP / "pareto_front.json"
    seed_ok = [x for x in (_sweep_to_eval(e) for e in json.loads(seed_json.read_text()))
               if x["passed"] and x["area"] and x["delay"]] if seed_json.exists() else []
    front = _pareto_of(refine_ok + seed_ok)

    common.ensure_fresh(cfg.FRONT_FINAL)
    for e in front:
        if e["source_phase"] == "phase3":
            src = cfg.FRONT_SWEEP_DEDUP / e["design"]
            name = f"design_p3_{e['design'].split('_')[-1]}"
        else:
            src = (cfg.FRONT_DEEPSYN_REFINE / e["source_design"] / e["design"]
                   if "source_design" in e else cfg.FRONT_DEEPSYN_REFINE / e["design"])
            suffix = (f"{e['source_design'].split('_')[-1]}_{e['design'].split('_')[-1]}"
                      if "source_design" in e else e["design"].split("_")[-1])
            name = f"design_p4_{suffix}"
        link = cfg.FRONT_FINAL / name
        if not link.exists():
            link.symlink_to(src)
    (cfg.FRONT_FINAL / "eval_results.json").write_text(json.dumps(front, indent=2))
    n3 = sum(1 for e in front if e["source_phase"] == "phase3")
    common.log(f"final front: {len(front)} points ({len(front) - n3} Phase 4, {n3} Phase 3), "
               f"best area {min(e['area'] for e in front):.1f}, "
               f"best delay {min(e['delay'] for e in front):.1f}")
    common.record("stage4", cfg.FRONT_FINAL / "eval_results.json",
                  "reported RTLScout front (Phase 4 u Phase-3 seeds)")
    common.mark_done("final_front")


def verify_reported() -> None:
    """Stage V on every design that lands on a reported Phase-4 front —
    the refinement front AND the equal-compute baseline front. Designs are
    collected (symlinked) into flat dirs so verify_front applies."""
    fronts = [(cfg.FRONT_DEEPSYN_REFINE, "deepsyn_refine_front"),
              (cfg.FRONT_INITIAL_DEEPSYN, "initial_deepsyn_front")]
    if (cfg.FRONT_INITIAL_DEEPSYN_2X / "eval_results.json").exists():
        fronts.append((cfg.FRONT_INITIAL_DEEPSYN_2X, "initial_deepsyn_2x_front"))
    for root, label in fronts:
        reported = root / "reported_front"
        reported.mkdir(parents=True, exist_ok=True)
        for e in _pareto_entries(root / "eval_results.json"):
            d = (root / e["source_design"] / e["design"] if "source_design" in e
                 else root / e["design"])
            suffix = (f"{d.parent.name.split('_')[-1]}_{d.name.split('_')[-1]}"
                      if "source_design" in e else d.name.split("_")[-1])
            link = reported / f"design_{suffix}"
            if not link.exists():
                link.symlink_to(d)
        stagev_verify.verify_front(reported, label)
    # One authoritative manifest over exactly the reported (cumulative) front.
    if (cfg.FRONT_FINAL / "eval_results.json").exists():
        stagev_verify.verify_front(cfg.FRONT_FINAL, "final_front")


def run() -> None:
    refine()
    equal_compute()
    if cfg.DEEPSYN_DOUBLE_EFFORT:
        equal_compute_2x()
    final_front()
    verify_reported()
    common.mark_done("stage4")


if __name__ == "__main__":
    run()

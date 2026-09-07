#!/usr/bin/env python3
"""Helper: run the OPTIONAL double-effort from-scratch Deepsyn arm for an
already-completed run and refresh everything downstream, so the arm lands in
the equal-compute table and the Phase-4 arrows figure.

    _run_double_effort.py --profile full_glm          # dry run: print the plan
    _run_double_effort.py --profile full_glm --yes    # actually launch

Steps (all inside the run dir resolved from the profile):
  1. stage4_deepsyn.equal_compute_2x() — N front designs x refine_runs
     trajectories at 2x time budget -> fronts/initial_deepsyn_2x/
     (+ batch eval -> eval_results.json)
  2. Stage-V gate-level verification of that front's Pareto designs
     (same symlink + verify_front flow as stage4.verify_reported)
  3. stage5_figures.equal_compute_table() + arrows_plot() — the table
     generator sees eval_results.json and appends the "2x effort" row;
     the arrows plot gains the double-effort staircase

Afterwards rerun paper/.../generate_paper.py: it probes the same
eval_results.json (ec2_exists) and switches captions/prose automatically.

Deliberately does NOT touch state/*.done: clearing stage4.done would re-run
the expensive refine + matched-compute arms (no internal skip guards).
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "stages"))

# --profile must be resolved BEFORE rerun_config is imported (run_all.py
# pattern); exported so stages and subprocesses agree.
_PROFILES = sorted(p.stem for p in (HERE / "profiles").glob("*.yaml"))
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--profile", choices=_PROFILES,
                  default=os.environ.get("RTLSCOUT_RERUN_PROFILE", "full"))
_pre_args = _pre.parse_known_args()[0]
os.environ["RTLSCOUT_RERUN_PROFILE"] = _pre_args.profile
os.environ.setdefault("SPIREHDL_TIMEOUT", "600")   # match run_all.py

import rerun_config as cfg

if Path(sys.executable).resolve() != cfg.VENV_PYTHON.resolve():
    os.execv(str(cfg.VENV_PYTHON), [str(cfg.VENV_PYTHON), __file__] + sys.argv[1:])

import yaml                    # noqa: E402  (venv guaranteed from here on)
import stage4_deepsyn          # noqa: E402
import stage5_figures          # noqa: E402
import stagev_verify           # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, parents=[_pre])
    ap.add_argument("--yes", action="store_true",
                    help="actually run (default: print the plan and exit)")
    args = ap.parse_args()

    n_designs = len([d for d in cfg.FRONT_SWEEP_DEDUP.glob("design_*")
                     if d.is_dir()])
    n_runs = n_designs * cfg.DEEPSYN_REFINE_RUNS
    budget = 2 * cfg.DEEPSYN_TIME_BUDGET
    eta_h = n_runs * budget / cfg.DEEPSYN_WORKERS / 3600
    print(f"run dir : {cfg.DATA}")
    print(f"target  : {cfg.FRONT_INITIAL_DEEPSYN_2X}")
    print(f"plan    : {n_runs} trajectories ({n_designs} designs x "
          f"{cfg.DEEPSYN_REFINE_RUNS}) x {budget // 60} min, "
          f"{cfg.DEEPSYN_WORKERS} workers  (~{eta_h:.1f} h wall + batch eval)")
    if (cfg.FRONT_INITIAL_DEEPSYN_2X / "eval_results.json").exists():
        raise SystemExit("already done: eval_results.json exists — nothing to do.")
    prof = yaml.safe_load(
        (HERE / "profiles" / f"{_pre_args.profile}.yaml").read_text())
    if not prof.get("deepsyn", {}).get("double_effort"):
        print("NOTE: the profile does not set deepsyn.double_effort: true — "
              "set it so a from-scratch rerun keeps this arm.")
    if not args.yes:
        print("dry run only — re-invoke with --yes to launch.")
        return

    # 1. the arm itself
    stage4_deepsyn.equal_compute_2x()

    # 2. Stage-V verification of the new front's Pareto designs
    root = cfg.FRONT_INITIAL_DEEPSYN_2X
    reported = root / "reported_front"
    reported.mkdir(parents=True, exist_ok=True)
    for e in stage4_deepsyn._pareto_entries(root / "eval_results.json"):
        d = (root / e["source_design"] / e["design"] if "source_design" in e
             else root / e["design"])
        suffix = (f"{d.parent.name.split('_')[-1]}_{d.name.split('_')[-1]}"
                  if "source_design" in e else d.name.split("_")[-1])
        link = reported / f"design_{suffix}"
        if not link.exists():
            link.symlink_to(d)
    stagev_verify.verify_front(reported, "initial_deepsyn_2x_front")

    # 3. downstream consumers: equal-compute table + arrows figure
    stage5_figures.equal_compute_table()
    stage5_figures.arrows_plot()

    print("\ndone. now rerun generate_paper.py "
          "(paper/rtlscout/neurips-ai-for-chip-design/) — ec2_exists flips "
          "on the new eval_results.json and the table/captions follow.")


if __name__ == "__main__":
    main()

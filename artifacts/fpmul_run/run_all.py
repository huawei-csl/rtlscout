#!/usr/bin/env python3
"""fpmul_f16 rerun (ABC / Opus 5) — main entry point.

    run_all.py --smoke          # cheap end-to-end smoke of every moving part
    run_all.py                  # full pipeline, stages 0..5 in order
    run_all.py --stages 3,4,5   # subset (completed stages are skipped anyway)
    run_all.py --report-only    # just regenerate REPORT.md

Every stage is resumable: completed stages/campaigns leave .done markers in
state/ and are skipped on re-invocation. REPORT.md is regenerated after every
stage. Run me with any python; I re-exec into the pyenv_eda venv."""
import argparse
import datetime
import importlib
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "stages"))

# --profile must be resolved BEFORE rerun_config is imported (it configures
# the whole namespace); it is exported so stages and subprocesses agree.
_PROFILES = sorted(p.stem for p in (HERE / "profiles").glob("*.yaml"))
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--profile", choices=_PROFILES,
                  default=os.environ.get("RTLSCOUT_RERUN_PROFILE", "full"))
_pre.add_argument("--new-run", action="store_true")
_pre_args = _pre.parse_known_args()[0]
_profile = _pre_args.profile
os.environ["RTLSCOUT_RERUN_PROFILE"] = _profile
if _pre_args.new_run:
    os.environ["RTLSCOUT_RERUN_NEW"] = "1"   # rerun_config mints + pins the run

# Spire compile budget (core/evaluation.py defaults to 60 s). A design using
# @abc_optimized runs a full ABC recipe inside this window, and the recipes are
# sized to ~120 s (&deepsyn -T 120/110), so 60 s kills them mid-optimization and
# the harness records a correctness failure rather than a timeout. Matches
# pdpu_run/common.py. setdefault: an explicit env var still wins.
os.environ.setdefault("SPIREHDL_TIMEOUT", "600")

import rerun_config as cfg

if Path(sys.executable).resolve() != cfg.VENV_PYTHON.resolve():
    os.execv(str(cfg.VENV_PYTHON), [str(cfg.VENV_PYTHON), __file__] + sys.argv[1:])

import common       # noqa: E402  (venv guaranteed from here on)
import report       # noqa: E402

STAGE_MODULES = {
    "0": "stage0_setup",
    "1": "stage1_agent",
    "2": "stage2_seeded",
    "3": "stage3_sweep",
    "4": "stage4_deepsyn",
    "5": "stage5_figures",
}


def _snapshot_profile() -> None:
    """Archive the profile yaml actually used into the run dir (first
    snapshot is authoritative; later edits land as timestamped copies)."""
    cfg.DATA.mkdir(parents=True, exist_ok=True)
    cur = cfg.PROFILE_FILE.read_text()
    snap = cfg.DATA / f"profile_{cfg.PROFILE}.yaml"
    if not snap.exists():
        snap.write_text(cur)
        common.log(f"profile snapshot -> {snap}")
    elif snap.read_text() != cur:
        alt = (cfg.DATA / f"profile_{cfg.PROFILE}"
               f".{datetime.datetime.now():%Y%m%d_%H%M%S}.yaml")
        alt.write_text(cur)
        common.log(f"profile changed since first snapshot -> {alt}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=_PROFILES, default=_profile,
                    help="scale profile from profiles/<name>.yaml (default: full); "
                         "each profile has its own output namespace and state")
    ap.add_argument("--new-run", action="store_true",
                    help="start a fresh data/<tag>_<datetime> run dir (and point "
                         "future invocations at it); without this flag, "
                         "invocations RESUME the latest run of the profile")
    ap.add_argument("--stages", default="0,1,2,3,4,5",
                    help="comma-separated stage numbers to run (default: all)")
    ap.add_argument("--smoke", action="store_true",
                    help="run the smoke-test suite instead of the pipeline")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-run stages even if their .done marker exists")
    args = ap.parse_args()
    common.log(f"profile: {cfg.PROFILE} (run {cfg.RUN_NAME}, model {cfg.MODEL}) "
               f"-> {cfg.DATA}")

    if args.report_only:
        report.main()
        return
    _snapshot_profile()
    if args.smoke:
        smoke = importlib.import_module("smoke")
        try:
            smoke.run()
        finally:
            report.main()
        return

    for s in args.stages.split(","):
        s = s.strip()
        name = STAGE_MODULES[s]
        if common.stage_done(f"stage{s}") and not args.force:
            common.log(f"stage {s} already done — skipping")
            continue
        common.log(f"===== stage {s} ({name}) =====")
        importlib.import_module(name).run()
        report.main()
    common.log("pipeline complete")


if __name__ == "__main__":
    main()

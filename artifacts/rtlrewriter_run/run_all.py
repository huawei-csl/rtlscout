#!/usr/bin/env python3
"""RTLRewriter rerun (Opus 4.8, ABC-only phase 2, post-hoc CEC).

    run_all.py --profile reduced --new-run   # fresh rehearsal (cases 7+9)
    run_all.py --new-run                     # fresh full run (all 14, n=1)
    run_all.py                               # RESUME the latest run
    run_all.py --report-only

Setup (preconditions + >=10k golden-simulated stimuli per case) always runs
first and self-skips once done. Then the selected campaigns — cells and/or
transistors (each: runner, tables, plots, post-hoc CEC evidence) — per the
profile's enabled: flags or an explicit --campaigns, then report. Deviations from the handover are recorded in STATUS.md — notably:
NO in-run CEC gating (Stage 0a deliberately not applied; evidence is post-hoc
via the bundled three-method cec_engine, following
artifacts/rtlrewriter_benchmark_results/README_cec_results.md)."""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Choices come from the profiles dir so a new <name>.yaml works without edits.
_PROFILES = sorted(p.stem for p in (HERE / "profiles").glob("*.yaml"))

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--profile", choices=_PROFILES,
                  default=os.environ.get("RTLSCOUT_RRRERUN_PROFILE", "full"))
_pre.add_argument("--new-run", action="store_true")
_a = _pre.parse_known_args()[0]
os.environ["RTLSCOUT_RRRERUN_PROFILE"] = _a.profile
if _a.new_run:
    os.environ["RTLSCOUT_RRRERUN_NEW"] = "1"

import rr_config as cfg          # noqa: E402

if Path(sys.executable).resolve() != cfg.VENV_PYTHON.resolve():
    os.execv(str(cfg.VENV_PYTHON), [str(cfg.VENV_PYTHON), __file__] + sys.argv[1:])

import augment_vectors           # noqa: E402
import common                    # noqa: E402


# ---------------------------------------------------------------- stage 0
def stage0() -> None:
    if common.stage_done("stage0"):
        common.log("stage 0 already done — skipping")
        return
    # Preconditions (handover): uniform read_file cap present; no flowy;
    # phase-2 recipe patched to ABC-only; benchmarks exist.
    agent_src = (cfg.REPO / "core" / "agent.py").read_text()
    assert "READ_FILE_DEFAULT_MAX_CHARS = 5_000" in agent_src, "read_file fix missing"
    mr = (cfg.REPO / "experiments" / "rtl_rewriter_multirun.py").read_text()
    assert '"flowy_optimize": True' not in mr, "phase-2 flags still advertise flowy"
    for tree, (root, _) in cfg.BENCH_TREES.items():
        for c in cfg.CASES:
            assert (root / f"case{c}").exists(), f"missing {root}/case{c}"
    # No in-run CEC: benchmarks must NOT declare a golden_reference.
    for tree, (root, _) in cfg.BENCH_TREES.items():
        for meta in root.glob("case*/metadata.json"):
            assert "golden_reference" not in json.loads(meta.read_text()), \
                f"{meta}: golden_reference set — in-run CEC gating is deliberately OFF"
    common.log("preconditions ok; augmenting stimuli (all cases, both trees)")
    augment_vectors.run()        # idempotent; validates every golden afterwards
    common.record("stage0", cfg.BENCH_TREES["verilog"][0],
                  f">=~{cfg.VEC_TARGET} golden-simulated stimuli per case (both trees)")
    common.mark_done("stage0")


# ---------------------------------------------------------------- campaigns
def _merge_stats(runs: list) -> dict:
    """Same shape as rtl_rewriter_multirun._phase_stats."""
    out = {}
    for metric in ("wires", "cells", "transistors"):
        vals = [r[f"best_{metric}"] for r in runs
                if r.get("passed") and r.get(f"best_{metric}") is not None]
        out[metric] = ({"min": min(vals), "max": max(vals),
                        "mean": round(sum(vals) / len(vals), 2),
                        "count": len(vals)}
                       if vals else
                       {"min": None, "max": None, "mean": None, "count": 0})
    return out


def merge_reps(rep_paths: list, out_path: Path) -> None:
    """Merge N independent single-run-per-phase rep summaries into one
    summary shaped like a total_runs=N summary: per (case, lang, phase) the
    runs lists concatenate (tables get mean±std across reps) and
    global_best_* comes from the best rep (CEC verifies that design)."""
    reps = [json.loads(p.read_text()) for p in rep_paths]
    merged = dict(reps[0])
    merged["repetitions"] = len(reps)
    merged["total_runs_per_phase"] = len(reps)   # as seen by table consumers
    merged["merged_from"] = [str(p) for p in rep_paths]
    merged["total_duration_s"] = round(
        sum(r.get("total_duration_s") or 0 for r in reps), 2)
    results = {}
    for case_id, per_lang in reps[0]["results"].items():
        results[case_id] = {}
        for lang, rec0 in per_lang.items():
            rec = {k: v for k, v in rec0.items()
                   if k not in ("phase1", "phase2")}
            recs = [r["results"].get(case_id, {}).get(lang) for r in reps]
            for phase in ("phase1", "phase2"):
                phs = [rr[phase] for rr in recs if rr and rr.get(phase)]
                if not phs:
                    continue
                runs = [run for p in phs for run in (p.get("runs") or [])]
                ok = [p for p in phs if p.get("status") == "ok"
                      and p.get("global_best_cost") is not None]
                best = (min(ok, key=lambda p: p["global_best_cost"])
                        if ok else None)
                m = dict(phs[0])
                m["runs"] = runs
                m["stats"] = _merge_stats(runs)
                m["total_runs"] = len(runs)
                m["global_best_cost"] = best["global_best_cost"] if best else None
                m["global_best_workdir"] = (best["global_best_workdir"]
                                            if best else None)
                m["total_duration_s"] = round(
                    sum(p.get("total_duration_s") or 0 for p in phs), 2)
                m["status"] = ("ok" if any(p.get("status") == "ok" for p in phs)
                               else phs[0].get("status"))
                m["rep_statuses"] = [p.get("status") for p in phs]
                rec[phase] = m
            results[case_id][lang] = rec
    merged["results"] = results
    out_path.write_text(json.dumps(merged, indent=2) + "\n")


def _check_readfile(runs_root: Path) -> None:
    """The rerun's raison d'etre: case9's verilog agent must see the WHOLE
    reference (old repo truncated it at 2000 chars)."""
    chats = list(runs_root.glob("rep*/phase1/verilog/case9/**/chat_log.txt"))
    if not chats:
        return
    t = chats[0].read_text(errors="replace")
    m = re.search(r"read_file\(filename='starting_point\.v'\)([\s\S]{0,4000})", t)
    if not m:
        common.log("WARNING: case9 verilog chat has no read_file(starting_point.v)")
        return
    seg = m.group(1)
    assert "showing lines" not in seg and "truncated" not in seg, \
        "case9 starting_point.v read was truncated — read_file fix not effective!"
    common.log("read_file completeness check ok (case9 verilog, full reference)")


def campaign(name: str) -> None:
    if common.stage_done(name):
        common.log(f"campaign {name} already done — skipping")
        return
    scfg = cfg.CAMPAIGNS[name]
    runs_root = cfg.DATA / f"runs_{name}"
    # N INDEPENDENT repetitions: each invocation starts a fresh elite pool
    # (phase 2 seeds from its OWN rep's phase 1). A completed rep (summary
    # on disk) is skipped, so a crashed campaign resumes at the failed rep.
    rep_summaries = []
    for i in range(1, cfg.REPETITIONS + 1):
        rep_root = runs_root / f"rep{i}"
        rep_summary = rep_root / "summary.json"
        rep_summaries.append(rep_summary)
        if rep_summary.exists():
            common.log(f"{name} rep{i}/{cfg.REPETITIONS} already done — skipping")
            continue
        cmd = common.py(cfg.REPO / "experiments" / "rtl_rewriter_multirun.py",
                        "--model", cfg.MODEL,
                        "--cost-metric", scfg["cost_metric"],
                        "--total-runs", cfg.TOTAL_RUNS,
                        "--max-steps", scfg["max_steps"],
                        "--phases", cfg.PHASES,
                        "--workers", cfg.WORKERS,
                        "--max-concurrent", cfg.MAX_CONCURRENT,
                        "--elite-size", cfg.ELITE_SIZE,
                        "--runs-root", rep_root,
                        "--cases", *cfg.CASES)
        if scfg.get("fsm_optimize"):
            cmd += ["--fsm-optimize"]  # Appendix B: state-encoding API access
        common.sh(cmd, f"{name}_runner_rep{i}")
    summary = runs_root / "summary.json"
    merge_reps(rep_summaries, summary)
    common.record(name, summary, f"{name} merged summary "
                  f"(n={cfg.REPETITIONS} independent reps x {cfg.TOTAL_RUNS} "
                  f"run/phase, {scfg['max_steps']} steps, {cfg.MODEL})")
    _check_readfile(runs_root)

    common.sh(common.py(cfg.REPO / "experiments" / "table_rtl_rewriter_multirun.py",
                        summary), f"{name}_tables")
    common.sh(common.py(cfg.REPO / "experiments" / "plot_rtl_rewriter_multirun.py",
                        "--input", summary), f"{name}_plots", check=False)
    common.record(name, runs_root / "table.md", f"{name} comparison table (+ .tex)")

    # Post-hoc CEC evidence: three-method engine (equiv / tempinduct /
    # 1M-vector sim for --sim-cases); nonzero exit on any NOT_EQUIVALENT.
    cec_cmd = common.py(cfg.CEC_ENGINE, summary,
                        "--workers", cfg.CEC_WORKERS,
                        "--sim-cases", *cfg.CEC_SIM_CASES,
                        "--sim-vectors", cfg.CEC_SIM_VECTORS,
                        "--out", runs_root / "cec_results.md",
                        "--json-out", runs_root / "cec_results.json")
    if cfg.CASES != list(range(1, 15)):
        cec_cmd += ["--cases", *cfg.CASES]
    # CEC_REPO_ROOT: the bundled engine's default root is its own package dir.
    common.sh(cec_cmd, f"{name}_cec", env_extra={"CEC_REPO_ROOT": str(cfg.REPO)})
    # The engine exits nonzero only on NOT_EQUIVALENT; ERROR rows must also
    # fail the stage (handover: every table-backing row must be equivalent).
    rows = json.loads((runs_root / "cec_results.json").read_text())
    bad = [r for r in rows if r.get("status") not in ("EQUIVALENT", "IDENTITY")]
    if bad:
        raise RuntimeError(
            f"{name}: {len(bad)} table-backing design(s) lack an EQUIVALENT "
            f"verdict:\n" + "\n".join(
                f"  {r.get('case')} {r.get('language')}: {r.get('status')} "
                f"({r.get('method', '')}) {str(r.get('detail', ''))[:100]}"
                for r in bad)
            + f"\nSee {runs_root / 'cec_results.md'}; diagnose and rerun.")
    common.record(name, runs_root / "cec_results.md",
                  f"{name} post-hoc equivalence evidence (per-row method)")
    common.mark_done(name)


# ---------------------------------------------------------------- traceability
def _snapshot_profile() -> None:
    """Archive the profile yaml actually used into the run dir. The first
    snapshot is authoritative; if the profile is edited between resumes
    (e.g. flipping a campaign's enabled:), the changed content is saved as
    an additional timestamped copy so the evolution stays traceable."""
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


# ---------------------------------------------------------------- report
def report() -> None:
    lines = [f"# RTLRewriter rerun — profile `{cfg.PROFILE}` (run {cfg.RUN_NAME})",
             "", f"Model `{cfg.MODEL}` · cases {cfg.CASES} · "
             f"n={cfg.REPETITIONS} independent reps × {cfg.TOTAL_RUNS} run/phase · "
             f"post-hoc CEC (sim fallback for cases {cfg.CEC_SIM_CASES})", ""]
    for s in ["stage0"] + list(cfg.CAMPAIGNS):
        lines.append(f"- [{'x' if common.stage_done(s) else ' '}] {s}")
    # cost: run-level result.json carry token_usage; eval snapshots carry duration_s
    tok = {"input_tokens": 0, "output_tokens": 0,
           "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    runs = 0
    eval_s = 0.0
    for rj in cfg.DATA.glob("runs_*/**/result.json"):
        try:
            r = json.loads(rj.read_text())
        except Exception:
            continue
        if r.get("token_usage"):
            runs += 1
            for k in tok:
                tok[k] += r["token_usage"].get(k, 0)
        elif r.get("duration_s") and "eval" in rj.parent.name:
            eval_s += r["duration_s"]
    usd = (tok["input_tokens"] * cfg.PRICING["input"]
           + tok["output_tokens"] * cfg.PRICING["output"]
           + tok["cache_creation_input_tokens"] * cfg.PRICING["cache_write"]
           + tok["cache_read_input_tokens"] * cfg.PRICING["cache_read"]) / 1e6
    lines += ["", f"LLM: {runs} agent runs, "
              f"{(tok['input_tokens']+tok['cache_creation_input_tokens']+tok['cache_read_input_tokens'])/1e6:.1f}M "
              f"in / {tok['output_tokens']/1e6:.2f}M out tokens ≈ **${usd:.2f}** · "
              f"eval compute {eval_s/3600:.1f} core-h (measured, 1 core/eval)"]
    if cfg.MANIFEST.exists():
        lines += ["", "## Generated files", ""]
        for e in json.loads(cfg.MANIFEST.read_text()):
            lines.append(f"- `{e['path']}` — {e['note']}")
    lines += ["", f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"]
    cfg.REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    cfg.REPORT_MD.write_text("\n".join(lines) + "\n")
    common.log(f"wrote {cfg.REPORT_MD}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=_PROFILES, default=cfg.PROFILE)
    ap.add_argument("--new-run", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    enabled = [c for c in cfg.CAMPAIGNS if cfg.CAMPAIGNS[c].get("enabled", True)]
    ap.add_argument("--campaigns", default=",".join(enabled),
                    help="comma-separated subset of: cells,transistors "
                         "(default: campaigns with enabled:true in the "
                         "profile; passing this flag overrides enabled:). "
                         "Setup always runs first and self-skips when done.")
    args = ap.parse_args()
    common.log(f"profile: {cfg.PROFILE} (run {cfg.RUN_NAME}, model {cfg.MODEL}) "
               f"-> {cfg.DATA} | campaigns: {args.campaigns or '(none)'}")
    if args.report_only:
        report()
        return
    _snapshot_profile()
    stage0()
    report()
    for c in args.campaigns.split(","):
        if c.strip():
            campaign(c.strip())
            report()
    common.log("pipeline complete")


if __name__ == "__main__":
    main()

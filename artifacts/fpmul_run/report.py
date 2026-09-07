"""Auto-generate REPORT.md: stage status, key numbers, and every generated
file with its location (from manifest.json + verification results)."""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "stages"))
import common
import rerun_config as cfg

STAGES = [
    ("stage0", "Stage 0 — setup (golden, vectors, baseline)"),
    ("stage1", "Stage 1 — agent campaigns, no decorators (Phase 1)"),
    ("stage2", "Stage 2 — seeded + @abc_optimized (Phase 2) + fronts + Stage V"),
    ("stage3", "Stage 3 — architecture sweep (Phase 3) + Stage V"),
    ("stage4", "Stage 4 — &deepsyn refinement + equal-compute (Phase 4) + Stage V"),
    ("stage5", "Stage 5 — figures and tables"),
]


def _size(p: Path) -> str:
    if not p.exists():
        return "MISSING"
    if p.is_dir():
        n = sum(1 for _ in p.rglob("*") if _.is_file())
        return f"dir, {n} files"
    return f"{p.stat().st_size:,} B"


def _fmt(v, nd=1):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "—"


def build() -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# fpmul_f16 rerun — ABC / Opus 5 — profile `{cfg.PROFILE}` "
             f"(run {cfg.RUN_NAME})",
             "",
             f"Generated {now} by `report.py`. Scale: `profiles/{cfg.PROFILE}.yaml` "
             f"(model `{cfg.MODEL}`, eval targets {cfg.EVAL_TARGET_DELAYS} ps, "
             f"deepsyn {cfg.DEEPSYN_REFINE_RUNS} runs/design at {cfg.DEEPSYN_TIME_BUDGET}s). "
             f"Handover: `metadocuments/reruns/inputs/HANDOVER_fpmul_rerun.md`.",
             "", "## Stage status", ""]
    for key, title in STAGES:
        done = common.stage_done(key)
        mark = "x" if done else " "
        when = ""
        if done:
            when = " (done " + (cfg.STATE / f"{key}.done").read_text().strip() + ")"
        lines.append(f"- [{mark}] {title}{when}")
    smoke = common.load_state("smoke")
    if smoke:
        lines += ["", f"Smoke test: {'PASS' if smoke.get('passed') else 'FAIL'} "
                      f"({smoke.get('time', '?')}) — details in STATUS.md"]

    baseline = common.load_state("baseline")
    if baseline:
        lines += ["", "## Baseline (starting point, target 500 ps)", "",
                  f"- area **{_fmt(baseline.get('area'))} µm²**, "
                  f"delay **{_fmt(baseline.get('delay'))} ps** "
                  f"(old environment: ≈84 µm², 1458 ps). All improvement "
                  f"percentages reference this baseline."]

    # Best numbers per front, where extraction summaries exist.
    _p2 = "abc" if cfg.P2_ABC_OPTIMIZE else "no decorator, ABLATION"
    fronts = [(f"Phases 1+2 ({_p2})", cfg.FRONT_ABC),
              ("Phase 1 only (ablation)", cfg.FRONT_NO_ABC),
              ("post-sweep (dedup)", cfg.FRONT_SWEEP_DEDUP)]
    rows = []
    for label, front in fronts:
        pf = front / "pareto_front.json"
        if not pf.exists():
            continue
        try:
            entries = json.loads(pf.read_text())
            areas = [e["area"] for e in entries if e.get("area")]
            delays = [e["delay"] for e in entries if e.get("delay")]
            # Which campaigns the front members come from — min-area/min-delay
            # alone can hide a phase's mid-front contribution entirely.
            phases = sorted({m.group(1) for e in entries
                             for m in [re.search(r"_(p\d)_", e.get("original_result_json", ""))]
                             if m})
            comp = "+".join(f"{sum(1 for e in entries if f'_{p}_' in e.get('original_result_json',''))}×{p}"
                            for p in phases) or "—"
            rows.append((label, len(entries), min(areas), min(delays), comp))
        except Exception:
            continue
    for label, front in (("deepsyn refinement (Phase 4)", cfg.FRONT_DEEPSYN_REFINE),
                         ("reported front (Phase 4 + Phase-3 seeds)", cfg.FRONT_FINAL)):
        ev = front / "eval_results.json"
        if not ev.exists():
            continue
        ok = [e for e in json.loads(ev.read_text()) if e.get("passed") and e.get("area")]
        if ok:
            rows.append((label, len(ok),
                         min(e["area"] for e in ok), min(e["delay"] for e in ok), "—"))
    if rows:
        lines += ["", "## Best results per phase", "",
                  "| front | designs | best area (µm²) | best delay (ps) | members |",
                  "|---|---|---|---|---|"]
        for label, n, a, d, comp in rows:
            lines.append(f"| {label} | {n} | {_fmt(a)} | {_fmt(d)} | {comp} |")
        lines += ["", "Paper reference (backed by the buggy lineage, expect "
                      "differences): 81 µm² / 955 ps Phases 1–3, 79 µm² / 891 ps Phase 4."]

    # Verification summaries.
    vlines = []
    for front in (cfg.FRONT_ABC, cfg.FRONT_NO_ABC, cfg.FRONT_SWEEP_DEDUP,
                  cfg.FRONT_DEEPSYN_REFINE / "reported_front",
                  cfg.FRONT_INITIAL_DEEPSYN / "reported_front"):
        vr = front / "verification_results.json"
        if vr.exists():
            s = json.loads(vr.read_text())
            excl = f", excluded: {', '.join(s['excluded'])}" if s["excluded"] else ""
            vlines.append(f"- `{vr}`: {s['passed']}/{s['total']} passed{excl}")
    if vlines:
        lines += ["", "## Verification (Stage V)", "",
                  "Regression pre-check + exhaustive simulation over all 2^32 "
                  "input pairs vs the golden (complete functional verification "
                  "for this combinational design; no CEC, per user decision):",
                  ""] + vlines

    # Generated files from the manifest.
    if cfg.MANIFEST.exists():
        entries = json.loads(cfg.MANIFEST.read_text())
        lines += ["", "## Generated files", "",
                  "| stage | path | what | size |", "|---|---|---|---|"]
        for e in sorted(entries, key=lambda x: (x["stage"], x["path"])):
            p = Path(e["path"])
            try:
                rel = p.relative_to(cfg.REPO)
            except ValueError:
                rel = p
            lines.append(f"| {e['stage']} | `{rel}` | {e['note']} | {_size(p)} |")

    # Cost breakdown (reviewer request): regenerated best-effort each cycle.
    try:
        import cost_report
        costs = cost_report.write_all()
        if costs["rows"]:
            lines += ["", "## Cost breakdown (LLM + compute)", ""]
            lines += cost_report.markdown_table(costs)
            lines += ["", f"LaTeX variants: `{cfg.FIGURES}/table_cost_breakdown_v{{1,2,3}}.tex`"]
    except Exception as e:
        lines += ["", f"(cost breakdown unavailable: {e})"]

    failures = (common.load_state("figure_failures") or {}).get("failed", [])
    if failures:
        lines += ["", f"**Failed figures (stage 5):** {', '.join(failures)} — "
                      f"see `logs/`."]
    lines += ["", "## Key decisions in effect", "",
              f"- Model: `{cfg.MODEL}` for **all** campaigns (user request; the "
              f"handover/paper used Sonnet for Phase-1 area).",
              "- ABC `@abc_optimized` / `&deepsyn` replace Mockturtle/flowy "
              "(handover decision 1; no flowy in this container).",
              "- In-run CEC off (`--skip-cec`); verification is directed vectors "
              "+ exhaustive simulation (complete for 2×16-bit inputs).",
              f"- Phase-4 operating points {cfg.EVAL_TARGET_DELAYS} ps — 800/1800 "
              f"(user decision 2026-07-28, overriding the handover's 900/1800): a "
              f"tight 800 ps target may pull delays below 900; below 800 is not "
              f"expected.",
              f"- Deepsyn refinement budget: first {cfg.DEEPSYN_REFINE_RUNS} of "
              f"the 650 configs per design (`--num-runs`, added when porting); "
              f"equal-compute baseline uses the full 650.",
              ""]
    return "\n".join(lines)


def main() -> None:
    cfg.REPORT_MD.write_text(build())
    print(f"wrote {cfg.REPORT_MD}")


if __name__ == "__main__":
    main()

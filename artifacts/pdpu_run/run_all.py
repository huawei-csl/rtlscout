#!/usr/bin/env python3
"""PDPU library-core experiment: Verilog vs Spire, on the fpmul pipeline shape.

    run_all.py --new-run                 # fresh run (profile: reduced)
    run_all.py                           # RESUME the latest run
    run_all.py --report-only

Stages, per language:
  0  baselines           starting design evaluated at every eval.target_delay
  1  agent phase 1       one campaign per objective (area, delay)
  2  agent phase 2       same, seeded from the matching P1 campaign
  F  fronts              per-phase Pareto fronts (fronts/, fpmul layout),
                         each evaluated at eval.target_delays
  4  deepsyn             refine every point of the agent front, plus
                         from-scratch baselines at matched and 2x compute

Every table number comes from batch_eval at eval.target_delays, so rows stay
comparable regardless of the target an agent picked for itself. Pareto
*selection* still uses the agent's own measurements."""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--profile", default=os.environ.get("RTLSCOUT_PDPU_PROFILE", "reduced"))
_pre.add_argument("--new-run", action="store_true")
_a = _pre.parse_known_args()[0]
os.environ["RTLSCOUT_PDPU_PROFILE"] = _a.profile
if _a.new_run:
    os.environ["RTLSCOUT_PDPU_NEW"] = "1"

import pdpu_config as cfg        # noqa: E402

if Path(sys.executable).resolve() != cfg.VENV_PYTHON.resolve():
    os.execv(str(cfg.VENV_PYTHON), [str(cfg.VENV_PYTHON), __file__] + sys.argv[1:])

import common                    # noqa: E402

# Languages come from the profile's `benchmarks:` map, so a profile can run
# a single language (e.g. spire-only) without touching the code.
LANGS = [l for l in ("verilog", "spirehdl") if l in cfg.BENCHMARKS]


def _snapshot_profile() -> None:
    cfg.DATA.mkdir(parents=True, exist_ok=True)
    snap = cfg.DATA / f"profile_{cfg.PROFILE}.yaml"
    cur = cfg.PROFILE_FILE.read_text()
    if not snap.exists():
        snap.write_text(cur)
    elif snap.read_text() != cur:
        (cfg.DATA / f"profile_{cfg.PROFILE}"
         f".{datetime.datetime.now():%Y%m%d_%H%M%S}.yaml").write_text(cur)


def _bench_dir(lang: str) -> Path:
    """Resolve a benchmark against BENCH_ROOTS — public benchmarks/ as well as
    internal/benchmarks/ (fpadd_f16 lives in the former)."""
    name = cfg.BENCHMARKS[lang]
    for root in cfg.BENCH_ROOTS:
        d = Path(root) / name
        if d.is_dir():
            return d
    raise RuntimeError(f"benchmark {name!r} not found under {cfg.BENCH_ROOTS}")


def _starting_point(lang: str) -> Path:
    d = _bench_dir(lang) / "context"
    return d / ("starting_point.py" if lang == "spirehdl" else "starting_point.v")


def _campaign_dir(lang: str, ph: int, name: str) -> Path:
    return cfg.DATA / "runs" / f"p{ph}_{lang}_{name}"


# ---------------------------------------------------------------- stage 0
def stage0() -> None:
    """Starting-design baseline at every reporting operating point.

    Guarded per (language, target delay), not by the stage marker alone: adding
    a language to a finished run must still produce ITS baselines, otherwise the
    table's Starting-design row for that language is silently empty."""
    for lang in LANGS:
        for td in cfg.EVAL_TARGET_DELAYS:
            save = cfg.STATE / f"baseline_{lang}_td{int(td)}"
            if (save / "result.json").exists():
                continue
            common.sh(common.py(cfg.REPO / "run_eval.py", _starting_point(lang),
                                "--benchmark", _bench_dir(lang),
                                "--language", lang,
                                "--cost-metric", "area",
                                "--target-delay", td,
                                "--skip-cec", "--save-to", save),
                      f"stage0_baseline_{lang}_td{int(td)}")
            common.record("stage0", save / "result.json",
                          f"{lang} baseline eval @ {int(td)} ps")
    common.mark_done("stage0")


# ---------------------------------------------------------------- campaigns
def campaign(lang: str, ph: int, camp: dict) -> None:
    """One agent campaign: a (phase, language, objective) triple."""
    name = f"p{ph}_{lang}_{camp['name']}"
    if common.stage_done(name):
        common.log(f"{name} already done — skipping")
        return
    runs_root = _campaign_dir(lang, ph, camp["name"])
    cmd = common.py(cfg.REPO / "run_multirun.py",
                    "--benchmark", cfg.BENCHMARKS[lang],
                    "--benchmarks-root", *cfg.BENCH_ROOTS,
                    "--model", cfg.MODEL,
                    "--language", lang,
                    "--cost-metric", camp["metric"],
                    "--target-delay", cfg.TARGET_DELAY,
                    "--total-runs", camp["runs"],
                    "--max-concurrent", camp["concurrent"],
                    "--max-steps", cfg.MAX_STEPS,
                    "--elite-size", cfg.ELITE_SIZE,
                    "--skip-cec",
                    "--runs-root", runs_root,
                    *cfg.PHASE_FLAGS[lang][ph])
    # fresh_first / fresh_base / fresh_min come from the campaign entry; unset
    # ones fall through to run_multirun's defaults (0 / 0.5 / 0.1).
    for key, flag in (("fresh_first", "--fresh-first"),
                      ("fresh_base", "--fresh-base"),
                      ("fresh_min", "--fresh-min")):
        if camp.get(key) is not None:
            cmd += [flag, str(camp[key])]
    if camp.get("seed_from"):
        seed = _campaign_dir(lang, ph - 1, camp["seed_from"]) / "multirun_summary.json"
        cmd += ["--seed-from", seed]
    common.sh(cmd, name)
    common.record(name, runs_root / "multirun_summary.json",
                  f"{name}: {camp['runs']} runs x {cfg.MAX_STEPS} steps "
                  f"({camp['metric']})")
    common.mark_done(name)


def agent_phases(lang: str) -> None:
    """Every agent campaign for one language, plus its per-phase fronts.

    Phase 2 seeds from the matching phase-1 campaign, so phases stay ordered
    within a language; the two languages are independent until phase 4."""
    for ph in sorted(cfg.CAMPAIGNS):
        for camp in cfg.CAMPAIGNS[ph]:
            campaign(lang, ph, camp)
        front_phase(lang, ph)
        report()


# ---------------------------------------------------------------- fronts
def _emit_netlists(front_dir: Path, lang: str) -> None:
    """Ensure every design_NNN/ holds an evaluable netlist.

    Spire designs are Python and only become a netlist when executed (their
    `to_verilog_file` tail), so run them once. Verilog agents write .v or .sv
    and need nothing — batch_eval and batch_deepsyn both read either."""
    if lang != "spirehdl":
        return
    for d in sorted(front_dir.glob("design_*")):
        if next(d.glob("*.v"), None):
            continue
        pys = [p for p in sorted(d.glob("*.py")) if p.name != "__init__.py"]
        if not pys:
            common.log(f"emit: {d} has no .py, skipping")
            continue
        common.sh(common.py(pys[0]), f"emit_{front_dir.name}_{d.name}",
                  cwd=d, check=False)
        if not (d / "design.v").exists():
            common.log(f"emit: {pys[0].name} produced no design.v")


def _extract_front(out: Path, run_dirs: list, log_name: str,
                   n_points=None) -> Path:
    """Pareto front (area vs delay) over one or more campaign roots."""
    cmd = common.py(cfg.REPO / "extract_pareto.py", *run_dirs,
                    "-o", out, "--separate-dirs", "--dims", "area,delay")
    if n_points:
        cmd += ["-n", str(n_points)]
    common.sh(cmd, log_name)
    return out


def _dedup_front(src: Path, dst: Path) -> int:
    """Drop content-identical designs.

    Agents may evaluate one design at several target delays; each evaluation
    is a distinct (area, delay) point and can be Pareto-optimal, so the same
    RTL shows up more than once. That is fine for reporting, but refinement
    would then run twice on a byte-identical AIG (batch_deepsyn's prep has no
    timing target), so the phase-4 seed set is deduplicated by content —
    fpmul's sweep_dedup / sweep_full split, for the same reason."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    seen, kept, total = {}, 0, 0
    for d in sorted(src.glob("design_*")):
        total += 1
        files = sorted(p for p in d.iterdir()
                       if p.suffix in (".py", ".v", ".sv"))
        if not files:
            continue
        h = hashlib.sha256(b"".join(p.read_bytes() for p in files)).hexdigest()
        if h in seen:
            common.log(f"dedup: {d.name} == {seen[h]} (same content) — dropped")
            continue
        seen[h] = d.name
        shutil.copytree(d, dst / f"design_{kept:03d}")
        kept += 1
    common.log(f"dedup: {kept} of {total} designs kept")
    return kept


def _batch_eval(design_root: Path, lang: str, log_name: str,
                workers: int | None = None) -> Path:
    out = design_root / "eval_results.json"
    common.sh(common.py(cfg.REPO / "batch_eval.py", design_root,
                        "--benchmark", _bench_dir(lang),
                        "--target-delay", *cfg.EVAL_TARGET_DELAYS,
                        "--workers", workers or cfg.EVAL_WORKERS,
                        "-o", out), log_name)
    return out


def front_phase(lang: str, ph: int) -> None:
    """Per-phase front: Pareto over that phase's campaigns, then evaluated."""
    name = f"front_p{ph}_{lang}"
    if common.stage_done(name):
        common.log(f"{name} already done — skipping")
        return
    roots = [_campaign_dir(lang, ph, c["name"]) for c in cfg.CAMPAIGNS[ph]]
    out = cfg.FRONTS / f"p{ph}_{lang}"
    _extract_front(out, [r for r in roots if r.exists()], f"{name}_extract")
    _emit_netlists(out, lang)
    _batch_eval(out, lang, f"{name}_eval")
    common.record(name, out / "eval_results.json",
                  f"phase-{ph} {lang} Pareto front @ {cfg.EVAL_TARGET_DELAYS}")
    common.mark_done(name)


def front_agent(lang: str) -> Path:
    """Combined P1+P2 front — the phase-4 seed set (deduplicated).

    fpmul seeds phase 4 from the post-sweep front; PDPU has no phase 3, so the
    agent front takes that role. P1 is included because P2 seeds from P1's
    elite and does not necessarily dominate it."""
    name = f"front_agent_{lang}"
    full = cfg.FRONTS / f"agent_{lang}"
    dedup = cfg.FRONTS / f"agent_{lang}_dedup"
    if common.stage_done(name):
        common.log(f"{name} already done — skipping")
        return dedup
    roots = [_campaign_dir(lang, ph, c["name"])
             for ph in sorted(cfg.CAMPAIGNS) for c in cfg.CAMPAIGNS[ph]]
    _extract_front(full, [r for r in roots if r.exists()], f"{name}_extract",
                   n_points=cfg.FRONT_N_POINTS)
    _emit_netlists(full, lang)
    _dedup_front(full, dedup)
    common.record(name, dedup, f"agent front feeding phase 4 ({lang})")
    common.mark_done(name)
    return dedup


# ---------------------------------------------------------------- phase 4
def _design_v(d: Path):
    vs = sorted(d.glob("*.v")) or sorted(d.glob("*.sv"))
    return vs[0] if vs else None


def _scratch_design_v(lang: str) -> Path:
    """The starting design as Verilog (spire's starting point self-emits)."""
    if lang == "verilog":
        return _starting_point(lang)
    d = cfg.FRONTS / f"scratch_src_{lang}"
    v = d / "design.v"
    if not v.exists():
        d.mkdir(parents=True, exist_ok=True)
        common.sh(common.py(_starting_point(lang)), f"emit_scratch_{lang}", cwd=d)
    return v


def _deepsyn(initial_v: Path, out: Path, num_runs: int, budget: int,
             lang: str, log_name: str, workers: int | None = None,
             config_offset: int = 0) -> None:
    common.sh(common.py(cfg.REPO / "artifacts" / "fpmul_run" / "ported" / "batch_deepsyn.py",
                        "--benchmark", _bench_dir(lang),
                        "--top", cfg.TOP_MODULE,
                        # widths only — the emitted wrapper's PI/PO order comes
                        # from yosys `write_aiger -map`, not from this order.
                        "--inputs", cfg.DEEPSYN_INPUTS,
                        "--outputs", cfg.DEEPSYN_OUTPUTS,
                        "--initial-design", initial_v,
                        "--time-budget", budget,
                        "--workers", workers or cfg.DEEPSYN_WORKERS,
                        "--num-runs", num_runs,
                        "--config-offset", config_offset,
                        "-o", out), log_name)


def refine(lang: str, seeds: Path) -> int:
    """Refine every point of the agent front; returns the seed count."""
    name = f"p4_{lang}_refine"
    sources = sorted(d for d in seeds.glob("design_*") if d.is_dir())
    if common.stage_done(name):
        common.log(f"{name} already done — skipping")
        return len(sources)
    if not sources:
        raise RuntimeError(f"no designs in {seeds} — run the agent phases first")
    root = cfg.FRONTS / f"deepsyn_refine_{lang}"
    # One batch_deepsyn per front point would leave most of the pool idle
    # (refine_runs trajectories on DEEPSYN_WORKERS cores), so run several
    # points at once: each keeps refine_runs workers and the arm fills the
    # same budget as the single-batch from-scratch arm.
    per_point = min(cfg.DEEPSYN_REFINE_RUNS, cfg.DEEPSYN_WORKERS)
    n_conc = max(1, cfg.DEEPSYN_WORKERS // per_point)
    ev_workers = max(1, cfg.EVAL_WORKERS // n_conc)
    common.log(f"{name}: {len(sources)} points, {n_conc} at a time x "
               f"{per_point} workers (eval {ev_workers} each)")

    def one(item) -> list:
        idx, src = item
        v = _design_v(src)
        if v is None:
            common.log(f"refine: {src.name} has no .v — skipping")
            return []
        out = root / src.name
        # Disjoint config slice per seed: seed i takes configs
        # [i*refine_runs : (i+1)*refine_runs]. Their union is exactly what the
        # from-scratch arm (n_points x refine_runs runs from offset 0) searches,
        # so the two arms cover the SAME configs and only the starting design
        # differs. Without this every seed would re-run configs 0..N-1.
        _deepsyn(v, out, cfg.DEEPSYN_REFINE_RUNS, cfg.DEEPSYN_T, lang,
                 f"{name}_{src.name}", workers=per_point,
                 config_offset=idx * cfg.DEEPSYN_REFINE_RUNS)
        # batch_eval only scans one level of design_* dirs, so evaluate each
        # source's refinement set separately and merge.
        ev = _batch_eval(out, lang, f"{name}_eval_{src.name}",
                         workers=ev_workers)
        es = json.loads(ev.read_text())
        for e in es:
            e["source_design"] = src.name
        return es

    with ThreadPoolExecutor(max_workers=n_conc) as ex:
        merged = [e for batch in ex.map(one, enumerate(sources)) for e in batch]
    (root / "eval_results.json").write_text(json.dumps(merged, indent=2))
    common.record(name, root / "eval_results.json",
                  f"{name}: {len(sources)} points x {cfg.DEEPSYN_REFINE_RUNS} runs "
                  f"x {cfg.DEEPSYN_T}s")
    common.mark_done(name)
    return len(sources)


def from_scratch(lang: str, n_points: int, double: bool) -> None:
    """Deepsyn on the starting design at compute matched to the refine arm."""
    arm = "scratch2x" if double else "scratch"
    name = f"p4_{lang}_{arm}"
    if common.stage_done(name):
        common.log(f"{name} already done — skipping")
        return
    budget = cfg.DEEPSYN_T * (2 if double else 1)
    n_runs = n_points * cfg.DEEPSYN_REFINE_RUNS      # matched by construction
    out = cfg.FRONTS / (f"initial_deepsyn_2x_{lang}" if double
                        else f"initial_deepsyn_{lang}")
    src = _scratch_design_v(lang)
    common.log(f"{name}: {n_runs} trajectories x {budget}s from {src}")
    _deepsyn(src, out, n_runs, budget, lang, f"{name}_deepsyn")
    _batch_eval(out, lang, f"{name}_eval")
    common.record(name, out / "eval_results.json",
                  f"{name}: {n_runs} x {budget}s from the starting design")
    common.mark_done(name)


def phase4(lang: str) -> None:
    seeds = front_agent(lang)
    n = refine(lang, seeds)
    from_scratch(lang, n, double=False)
    if cfg.DEEPSYN_DOUBLE_EFFORT:
        from_scratch(lang, n, double=True)


# ---------------------------------------------------------------- table
def _points(path: Path) -> list:
    """(area, delay) pairs from a batch_eval results file."""
    if not path or not path.exists():
        return []
    return [(e["area"], e["delay"]) for e in json.loads(path.read_text())
            if e.get("passed") and e.get("area") and e.get("delay")]


def _metrics(points: list) -> dict:
    """Best area, best delay and best ADP over a point set.

    Area and delay are independent extremes (they may come from different
    points), matching the fpmul ablation table; ADP is min(area x delay)."""
    if not points:
        return {}
    return {"area": min(a for a, _ in points),
            "delay": min(d for _, d in points),
            "adp": min(a * d for a, d in points),
            "n": len(points)}


def _final_front(lang: str) -> Path:
    """Reported front: Pareto(Phase-4 output u the P1/P2 front that seeded it).
    A seed design deepsyn never beat is still a result the pipeline delivered."""
    out = cfg.FRONTS / f"final_{lang}" / "eval_results.json"
    # Only meaningful once phase 4 has run: without the refine front this would
    # be the AGENT front rewritten under a "deepsyn refine" label, plotting
    # exactly on top of the phase-2 row and reading as if deepsyn did nothing.
    if not (cfg.FRONTS / f"deepsyn_refine_{lang}" / "eval_results.json").exists():
        return out
    ok = []
    for name in (f"deepsyn_refine_{lang}", f"p1_{lang}", f"p2_{lang}"):
        p = cfg.FRONTS / name / "eval_results.json"
        if p.exists():
            ok += [e for e in json.loads(p.read_text())
                   if e.get("passed") and e.get("area") and e.get("delay")]
    if not ok:
        return out
    front = [e for e in ok
             if not any(o["area"] <= e["area"] and o["delay"] <= e["delay"]
                        and (o["area"] < e["area"] or o["delay"] < e["delay"])
                        for o in ok)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(front, indent=2))
    return out


def _row_sources(lang: str) -> list:
    """(row label, eval_results.json) per table row; None = stage-0 baseline."""
    return [
        ("Starting design", None),
        ("Phase 1 (agent)", cfg.FRONTS / f"p1_{lang}" / "eval_results.json"),
        ("Phase 2 (+decorators)", cfg.FRONTS / f"p2_{lang}" / "eval_results.json"),
        # Cumulative: Phase-4 output plus the seed designs it never beat.
        ("Phase 4 (deepsyn refine)",
         cfg.FRONTS / f"final_{lang}" / "eval_results.json"),
        ("From scratch, equal compute",
         cfg.FRONTS / f"initial_deepsyn_{lang}" / "eval_results.json"),
        ("From scratch, 2x effort",
         cfg.FRONTS / f"initial_deepsyn_2x_{lang}" / "eval_results.json"),
    ]


def _baseline_points(lang: str) -> list:
    pts = []
    for td in cfg.EVAL_TARGET_DELAYS:
        rj = cfg.STATE / f"baseline_{lang}_td{int(td)}" / "result.json"
        if not rj.exists():
            continue
        m = json.loads(rj.read_text()).get("metrics") or {}
        if m.get("area") and m.get("delay"):
            pts.append((m["area"], m["delay"]))
    return pts


def table() -> None:
    rows = {}
    for lang in LANGS:
        rows[lang] = {}
        _final_front(lang)
        for label, path in _row_sources(lang):
            pts = _baseline_points(lang) if path is None else _points(path)
            rows[lang][label] = _metrics(pts)

    def cells(m):
        if not m:
            return ["--", "--", "--"]
        return [f"{m['area']:.1f}", f"{m['delay']:.0f}", f"{m['adp'] / 1e3:.1f}"]

    labels = [l for l, _ in _row_sources(LANGS[0])]
    head = "| phase | " + " | ".join(
        f"{l} area (µm²) | {l} delay (ps) | {l} ADP (10³ µm²·ps)"
        for l in LANGS) + " |"
    md = [head, "|" + "---|" * (1 + 3 * len(LANGS))]
    for label in labels:
        md.append("| " + label + " | " + " | ".join(
            " | ".join(cells(rows[l][label])) for l in LANGS) + " |")

    tex = [r"\begin{tabular}{@{}l" + "ccc" * len(LANGS) + r"@{}}", r"\toprule",
           "Phase & " + " & ".join("Area & Delay & ADP" for _ in LANGS) + r" \\",
           r"\midrule"]
    for label in labels:
        tex.append(label.replace("2x", r"2$\times$") + " & " + " & ".join(
            " & ".join(cells(rows[l][label])) for l in LANGS) + r" \\")
    tex += [r"\bottomrule", r"\end{tabular}"]

    (cfg.DATA / "table.md").write_text("\n".join(md) + "\n")
    (cfg.DATA / "table.tex").write_text("\n".join(tex) + "\n")
    (cfg.DATA / "table.json").write_text(json.dumps(rows, indent=2))
    common.log("table:\n" + "\n".join(md))
    common.record("table", cfg.DATA / "table.md",
                  f"phase comparison @ {cfg.EVAL_TARGET_DELAYS} ps")


# ---------------------------------------------------------------- figures
# Shared with the fpmul suite rather than duplicated; it reads the same
# batch_eval entry shape (original_area/original_delay for the refine arm).
ARROWS_SCRIPT = cfg.REPO / "artifacts" / "fpmul_run" / "ported" / "plot_deepsyn_arrows.py"


def _star_args(lang: str) -> list:
    """--starting-point plot args (NOT the benchmark's starting_point.v — that is
    _starting_point above; this name used to shadow it). The baseline at the
    median target delay; NOT the table's 'Starting design' row, whose area and
    delay are independent extremes."""
    pts = sorted(_baseline_points(lang))
    return [] if not pts else ["--starting-point", *pts[len(pts) // 2]]


def _campaign_figures(lang: str) -> None:
    """Per-campaign Pareto/cost-evolution plots + combined multi-front plots."""
    out = cfg.DATA / "figures" / f"phase12_{lang}"
    star = _star_args(lang)
    roots = {}
    for ph in sorted(cfg.CAMPAIGNS):
        for camp in cfg.CAMPAIGNS[ph]:
            root = _campaign_dir(lang, ph, camp["name"])
            if not root.exists():
                continue
            roots[(ph, camp["name"])] = root
            common.sh(common.py(cfg.REPO / "plot_pareto_paper.py", root,
                                "-o", out / f"p{ph}_{camp['name']}", *star),
                      f"fig_{lang}_p{ph}_{camp['name']}")

    def combined(name, a, b, c, label):
        if not (a and b):
            return
        third = [] if not c else ["--roots-c", *c, "--label-c", f"{label} adp-opt"]
        common.sh(common.py(cfg.REPO / "plot_pareto_paper.py",
                            "--roots-a", *a, "--roots-b", *b,
                            "--label-a", f"{label} area-opt",
                            "--label-b", f"{label} delay-opt",
                            *third, "-o", out / name, *star),
                  f"fig_{lang}_{name}")

    for ph in sorted(cfg.CAMPAIGNS):
        combined(f"p{ph}_combined", *[[roots[(ph, m)]] if (ph, m) in roots else None
                                      for m in ("area", "delay", "adp")], f"p{ph}")
    both = {m: [roots[(ph, m)] for ph in sorted(cfg.CAMPAIGNS) if (ph, m) in roots]
            for m in ("area", "delay", "adp")}
    combined("p12_combined", both["area"], both["delay"], both["adp"], "P1+P2")


def _arrows_figure(lang: str) -> None:
    """Refine vs from-scratch movement (the fpmul-style arrows plot)."""
    refine = cfg.FRONTS / f"deepsyn_refine_{lang}" / "eval_results.json"
    if not refine.exists():
        return
    out = cfg.DATA / "figures" / f"deepsyn_{lang}"
    cmd = common.py(ARROWS_SCRIPT, "--data",
                    "RTLScout: Phases 1-2 + Deepsyn refinement", refine, "-o", out)
    # Seed PPA lives only in the agent front manifest; refine evals carry no origins.
    originals = cfg.FRONTS / f"agent_{lang}" / "pareto_front.json"
    if originals.exists():
        cmd += ["--originals", str(originals),
                "--originals-label", "Pareto Phases 1–2"]   # no phase 3 here
    scratch = cfg.FRONTS / f"initial_deepsyn_{lang}" / "eval_results.json"
    pts = sorted(_baseline_points(lang))
    if scratch.exists() and pts:
        oa, od = pts[len(pts) // 2]
        n = len({e.get("design") for e in json.loads(scratch.read_text())})
        cmd += ["--standalone",
                f"Deepsyn from scratch ({n}x{cfg.DEEPSYN_T // 60} min)",
                str(scratch), str(oa), str(od)]
    common.sh(cmd, f"fig_arrows_{lang}")


def figures() -> None:
    """All fronts (every phase, both languages) in one area/delay plot, plus
    per-campaign and refine-vs-scratch plots per language."""
    out = cfg.DATA / "figures" / "fronts_area_delay"
    try:
        import plot_fronts
        common.log(f"figure: {plot_fronts.plot(out)}")
        common.record("figures", out.with_suffix(".pdf"),
                      "area/delay fronts by phase and language")
    except Exception as e:                    # a missing arm must not kill the run
        common.log(f"FIGURE FAILED fronts_area_delay: {e}")
    for lang in LANGS:
        for name, fn in (("campaign", _campaign_figures), ("arrows", _arrows_figure)):
            try:
                fn(lang)
            except Exception as e:
                common.log(f"FIGURE FAILED {name}_{lang}: {e}")
    common.record("figures", cfg.DATA / "figures",
                  "per-campaign Pareto plots and refinement arrows")


# ---------------------------------------------------------------- report
def _stages() -> list:
    s = ["stage0"]
    for lang in LANGS:
        for ph in sorted(cfg.CAMPAIGNS):
            s += [f"p{ph}_{lang}_{c['name']}" for c in cfg.CAMPAIGNS[ph]]
            s.append(f"front_p{ph}_{lang}")
        s.append(f"front_agent_{lang}")
        s += [f"p4_{lang}_refine", f"p4_{lang}_scratch"]
        if cfg.DEEPSYN_DOUBLE_EFFORT:
            s.append(f"p4_{lang}_scratch2x")
    return s


_REPORT_LOCK = threading.Lock()      # both language threads call report()


def report() -> None:
  with _REPORT_LOCK:
      n_camp = sum(len(v) for v in cfg.CAMPAIGNS.values())
      lines = [f"# PDPU experiment — profile `{cfg.PROFILE}` (run {cfg.RUN_NAME})",
               "", f"Model `{cfg.MODEL}` · {n_camp} campaigns per language "
               f"({cfg.MAX_STEPS} steps each) · agent target "
               f"{cfg.TARGET_DELAY:.0f} ps · reported at "
               f"{[int(t) for t in cfg.EVAL_TARGET_DELAYS]} ps · deepsyn "
               f"{cfg.DEEPSYN_REFINE_RUNS} runs/point x {cfg.DEEPSYN_T}s", ""]
      for s in _stages():
          lines.append(f"- [{'x' if common.stage_done(s) else ' '}] {s}")
      t = cfg.DATA / "table.md"
      if t.exists():
          lines += ["", t.read_text()]
      fig = cfg.DATA / "figures" / "fronts_area_delay.pdf"
      if fig.exists():
          lines += ["", f"Fronts figure: `{fig}`"]
      tok = {"input_tokens": 0, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
      nruns = 0
      for rj in cfg.DATA.glob("runs/*/run_*/**/result.json"):
          try:
              r = json.loads(rj.read_text())
          except Exception:
              continue
          if r.get("token_usage"):
              nruns += 1
              for k in tok:
                  tok[k] += r["token_usage"].get(k, 0)
      usd = sum(tok[k] * cfg.PRICING[p] for k, p in
                [("input_tokens", "input"), ("output_tokens", "output"),
                 ("cache_creation_input_tokens", "cache_write"),
                 ("cache_read_input_tokens", "cache_read")]) / 1e6
      lines += ["", f"LLM: {nruns} agent runs ≈ **${usd:.2f}**",
                "", f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"]
      cfg.REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
      cfg.REPORT_MD.write_text("\n".join(lines) + "\n")
      common.log(f"wrote {cfg.REPORT_MD}")


def _parallel(fn, tag: str) -> None:
    """Run fn(lang) for both languages concurrently and re-raise any failure."""
    errors = {}

    def wrap(lang):
        try:
            fn(lang)
        except BaseException as e:                 # noqa: BLE001 — re-raised below
            errors[lang] = e
            common.log(f"{tag}_{lang} FAILED: {e}")

    threads = [threading.Thread(target=wrap, args=(l,), name=f"{tag}_{l}")
               for l in LANGS]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    if errors:
        raise RuntimeError(f"{tag} failed for {sorted(errors)}: "
                           f"{'; '.join(str(e) for e in errors.values())}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default=cfg.PROFILE)
    ap.add_argument("--new-run", action="store_true")
    ap.add_argument("--stop-after-agents", action="store_true",
                    help="run stage 0 + the agent phases and their per-phase "
                         "fronts, then stop before phase 4 (deepsyn). Resume "
                         "later without the flag to continue in place.")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    common.log(f"profile: {cfg.PROFILE} (run {cfg.RUN_NAME}, model {cfg.MODEL}) "
               f"-> {cfg.DATA}")
    if args.report_only:
        table()
        figures()
        report()
        return
    _snapshot_profile()
    stage0()
    _parallel(agent_phases, "agent")
    if args.stop_after_agents:
        table()
        figures()
        report()
        common.log("stopped after agent phases (--stop-after-agents); "
                   "resume without the flag to run phase 4")
        return
    # Deepsyn arms: DEEPSYN_WORKERS cores per language, sequential within a
    # language, so peak use is 2 x workers.
    _parallel(phase4, "p4")
    table()
    figures()
    report()
    common.log("pipeline complete")


if __name__ == "__main__":
    main()

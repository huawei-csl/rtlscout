"""Stage 5 — figures and tables. Each figure is attempted independently and
failures are recorded (not fatal): figure plumbing can only be fully exercised
once real campaign data exists."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg

PLOT_FPMUL_PARETO = (cfg.REPO / "deps" / "tech_eval" / "src" / "tech_eval" /
                     "ppa_extract" / "sweeps" / "fpmul" / "plot_fpmul_pareto.py")


def _attempt(name: str, fn) -> None:
    try:
        fn()
        common.log(f"figure ok: {name}")
    except Exception as e:
        common.log(f"FIGURE FAILED {name}: {e}")
        failures = common.load_state("figure_failures") or {"failed": []}
        failures["failed"] = sorted(set(failures["failed"] + [name]))
        common.save_state("figure_failures", failures)


def phase12_plots() -> None:
    baseline = common.load_state("baseline") or {}
    star = ([] if not baseline.get("area") else
            ["--starting-point", baseline["area"], baseline["delay"]])
    out = cfg.FIGURES / "phase12"
    # adp is optional: only profiles defining an area_delay_product campaign have it.
    singles = [("p1_area", cfg.RUNS_P1_AREA), ("p2_area", cfg.RUNS_P2_AREA),
               ("p1_delay", cfg.RUNS_P1_DELAY), ("p2_delay", cfg.RUNS_P2_DELAY)]
    singles += [(n, r) for n, r in (("p1_adp", cfg.RUNS_P1_ADP),
                                    ("p2_adp", cfg.RUNS_P2_ADP)) if r]
    for name, root in singles:
        common.sh(common.py(cfg.REPO / "plot_pareto_paper.py", root,
                            "-o", out / name, *star), f"stage5_{name}")
        # half-width twin (paper subfigure); full-size output is kept
        common.sh(common.py(cfg.REPO / "plot_pareto_paper.py", root,
                            "-o", out / name, *star, "--narrow"),
                  f"stage5_{name}_narrow")
    # Two-phase cost evolution (paper Fig. 4a): Phase-2 runs continue the
    # run index and seed arrows cross the phase boundary.
    pairs = [("p12_area", cfg.RUNS_P1_AREA, cfg.RUNS_P2_AREA),
             ("p12_delay", cfg.RUNS_P1_DELAY, cfg.RUNS_P2_DELAY)]
    if cfg.RUNS_P1_ADP and cfg.RUNS_P2_ADP:
        pairs.append(("p12_adp", cfg.RUNS_P1_ADP, cfg.RUNS_P2_ADP))
    # starting design as a star at run index -1 (seed arrows to the fresh runs)
    start_cost = {"p12_area": baseline.get("area"), "p12_delay": baseline.get("delay"),
                  "p12_adp": (baseline["area"] * baseline["delay"]
                              if baseline.get("area") else None)}
    for name, p1, p2 in pairs:
        sc = ([] if start_cost.get(name) is None else
              ["--start-cost", start_cost[name]])
        for extra, tag in (([], ""), (["--narrow"], "_narrow")):
            common.sh(common.py(cfg.REPO / "plot_pareto_paper.py", p1,
                                "--phase2", p2, "-o", out / name, *sc, *extra),
                      f"stage5_{name}{tag}")
    for name, a, b, c in (("p1", cfg.RUNS_P1_AREA, cfg.RUNS_P1_DELAY, cfg.RUNS_P1_ADP),
                          ("p2", cfg.RUNS_P2_AREA, cfg.RUNS_P2_DELAY, cfg.RUNS_P2_ADP)):
        third = [] if not c else ["--roots-c", c, "--label-c", f"{name} adp-opt"]
        common.sh(common.py(cfg.REPO / "plot_pareto_paper.py",
                            "--roots-a", a, "--roots-b", b,
                            "--label-a", f"{name} area-opt", "--label-b", f"{name} delay-opt",
                            *third,
                            "-o", out / f"{name}_combined", *star),
                  f"stage5_{name}_combined")
    # Third front only if the profile defines an area_delay_product campaign.
    adp = ([] if not (cfg.RUNS_P1_ADP or cfg.RUNS_P2_ADP) else
           ["--roots-c", *[r for r in (cfg.RUNS_P1_ADP, cfg.RUNS_P2_ADP) if r],
            "--label-c", "adp-targeted (P1+P2)"])
    common.sh(common.py(cfg.REPO / "plot_pareto_paper.py",
                        "--roots-a", cfg.RUNS_P1_AREA, cfg.RUNS_P2_AREA,
                        "--roots-b", cfg.RUNS_P1_DELAY, cfg.RUNS_P2_DELAY,
                        "--label-a", "area-targeted (P1+P2)",
                        "--label-b", "delay-targeted (P1+P2)",
                        *adp,
                        "-o", out / "p12_combined", *star),
              "stage5_p12_combined")
    common.sh(common.py(cfg.REPO / "plot_pareto_paper.py",
                        "--roots-a", cfg.RUNS_P1_AREA, cfg.RUNS_P2_AREA,
                        "--roots-b", cfg.RUNS_P1_DELAY, cfg.RUNS_P2_DELAY,
                        "--label-a", "area-targeted (P1+P2)",
                        "--label-b", "delay-targeted (P1+P2)",
                        *adp,
                        "-o", out / "p12_combined", *star, "--narrow"),
              "stage5_p12_combined_narrow")
    # Phase-1 front drawn separately from the Phases-1+2 front, per objective.
    camps = [("area-targeted", cfg.RUNS_P1_AREA, cfg.RUNS_P2_AREA),
             ("delay-targeted", cfg.RUNS_P1_DELAY, cfg.RUNS_P2_DELAY)]
    if cfg.RUNS_P1_ADP and cfg.RUNS_P2_ADP:
        camps.append(("adp-targeted", cfg.RUNS_P1_ADP, cfg.RUNS_P2_ADP))
    pf_args = []
    for lbl, p1, p2 in camps:
        pf_args += ["--campaign", lbl, str(p1), str(p2)]
    for extra, name in (([], "stage5_phase_fronts"),
                        (["--narrow"], "stage5_phase_fronts_narrow")):
        common.sh(common.py(cfg.ARTIFACTS / "ported" / "plot_phase_fronts.py",
                            *pf_args, "-o", out / "phase_fronts", *star, *extra),
                  name)
    common.record("stage5", out, "Phase 1/2 cost-evolution + Pareto plots")


def sweep_plot() -> None:
    out = cfg.FIGURES / "sweep"
    out.mkdir(parents=True, exist_ok=True)
    common.sh(common.py(PLOT_FPMUL_PARETO, cfg.SWEEP_RESULTS, "-o", out,
                        "--show-operator"),          # paper fig: ..._with_op2
              "stage5_sweep_pareto")
    # Half-width twin for the paper's paired figure; the full-size one stays.
    common.sh(common.py(PLOT_FPMUL_PARETO, cfg.SWEEP_RESULTS, "-o", out,
                        "--show-operator", "--narrow"),
              "stage5_sweep_pareto_narrow")
    common.record("stage5", out, "full-pipeline Pareto (sweep results)")


def arrows_plot() -> None:
    out = cfg.FIGURES / "deepsyn"
    manifest = None
    for cand in ("pareto_front.json", "manifest.json"):
        p = cfg.FRONT_SWEEP_DEDUP / cand
        if p.exists():
            manifest = p
            break
    cmd = common.py(cfg.ARTIFACTS / "ported" / "plot_deepsyn_arrows.py",
                    "--data", "RTLScout: Phases 1-4",
                    cfg.FRONT_DEEPSYN_REFINE / "eval_results.json",
                    "--commercial",                  # Larsson-Edefors reference
                    "-o", out)
    if manifest:
        cmd += ["--originals", str(manifest)]
    # Deepsyn-from-scratch arrows (analog of the old "Starting design + MT"
    # datasets): shared origin = the stage-0 baseline point, one arrow per run.
    baseline = common.load_state("baseline") or {}
    ec_eval = cfg.FRONT_INITIAL_DEEPSYN / "eval_results.json"
    if ec_eval.exists() and baseline.get("area"):
        n = len({e.get("design") for e in json.loads(ec_eval.read_text())})
        cmd += ["--standalone",
                f"Deepsyn only ({n}x{cfg.DEEPSYN_TIME_BUDGET // 60} min)",
                str(ec_eval), str(baseline["area"]), str(baseline["delay"])]
        # Optional double-effort arm: staircase only (no second arrow fan).
        ec2 = cfg.FRONT_INITIAL_DEEPSYN_2X / "eval_results.json"
        if ec2.exists():
            n2 = len({e.get("design") for e in json.loads(ec2.read_text())})
            label2 = (f"Deepsyn only "
                      f"({n2}x{2 * cfg.DEEPSYN_TIME_BUDGET // 60} min)")
            cmd += ["--standalone", label2, str(ec2),
                    str(baseline["area"]), str(baseline["delay"]),
                    "--front-only", label2]
    common.sh(cmd, "stage5_arrows")
    common.sh(cmd + ["--narrow"], "stage5_arrows_narrow")
    common.record("stage5", out, "refinement arrows plot")


def equal_compute_table() -> None:
    baseline_tds = [cfg.STATE / f"baseline_td{int(td)}" / "result.json"
                    for td in cfg.EVAL_TARGET_DELAYS]
    tex = cfg.FIGURES / "table_equal_compute.tex"
    n_src = len([d for d in cfg.FRONT_SWEEP_DEDUP.glob("design_*") if d.is_dir()])
    cmd = common.py(cfg.ARTIFACTS / "ported" / "plot_equal_compute_table.py",
                    "--refine-eval", cfg.FRONT_DEEPSYN_REFINE / "eval_results.json",
                    # Counts stay deepsyn-only; only area/delay use the final front.
                    "--refine-front", cfg.FRONT_FINAL / "eval_results.json",
                    "--initial-eval", cfg.FRONT_INITIAL_DEEPSYN / "eval_results.json",
                    "--baseline-evals", *baseline_tds,
                    "--budget-min", cfg.DEEPSYN_TIME_BUDGET // 60,
                    "--refine-desc",
                    f"Deepsyn {n_src}$\\times${cfg.DEEPSYN_REFINE_RUNS}"
                    f"$\\times${cfg.DEEPSYN_TIME_BUDGET // 60}\\,min",
                    "-o", tex)
    ec2 = cfg.FRONT_INITIAL_DEEPSYN_2X / "eval_results.json"
    if ec2.exists():
        cmd += ["--initial-2x-eval", ec2]
    common.sh(cmd, "stage5_equal_compute")
    common.record("stage5", tex, "equal-compute (same-optimizer) table")


def _extremes(points) -> tuple:
    """(best area, best delay) — independent extremes, like the paper table."""
    pts = [(a, d) for a, d in points if a is not None and d is not None]
    return (min(a for a, _ in pts), min(d for _, d in pts)) if pts else (None, None)


def ablation_table() -> None:
    """Submission Tab. 'Ablation: Extremes across phase combinations',
    MT -> Deepsyn, filled from this run's artifacts."""
    sweep = json.loads(cfg.SWEEP_RESULTS.read_text())["case_results"]

    def sweep_pts(prefixes, op_only=False):
        out = []
        for key, entries in sweep.items():
            if not any(key.startswith(p) for p in prefixes):
                continue
            for e in entries:
                # the sweep stringifies these flags: 'False' is truthy, so
                # compare against the literal (matches plot_fpmul_pareto.py)
                if op_only and not (e.get("mult_use_operator") == "True"
                                    and e.get("add_use_operator") == "True"):
                    continue
                out.append((e.get("area"), e.get("delay")))
        return out

    def eval_pts(path):
        return [(e.get("area"), e.get("delay"))
                for e in json.loads(path.read_text()) if e.get("passed")]

    start_pts = []
    b = common.load_state("baseline") or {}
    if b.get("area"):
        start_pts.append((b["area"], b["delay"]))
    for td_dir in cfg.STATE.glob("baseline_td*"):
        r = json.loads((td_dir / "result.json").read_text())
        m = r.get("metrics") or {}
        start_pts.append((m.get("area"), m.get("delay")))

    agent_fronts = ["pareto_fpmul_no_abc/", "pareto_fpmul_abc/"]
    rows = [
        ("Starting design", *_extremes(start_pts)),
        (r"Phase~4 only (start+Deepsyn)",
         *_extremes(eval_pts(cfg.FRONT_INITIAL_DEEPSYN / "eval_results.json"))),
        (r"Phase~3 only (start+arch.\ sweep)",
         *_extremes(sweep_pts(["pareto_front_init/"]))),
        (r"Phases~1,3 (no ABC agent)",
         *_extremes(sweep_pts(["pareto_fpmul_no_abc/"]))),
        (r"Phases~1,2 (no arch.\ sweep)",
         *_extremes(sweep_pts(agent_fronts, op_only=True))),
        (r"Phases~1--3", *_extremes(sweep_pts(agent_fronts))),
    ]
    final = _extremes(eval_pts(cfg.FRONT_FINAL / "eval_results.json"))

    def num(x, bold=False):
        s = "--" if x is None else f"{x:.0f}"
        return r"\textbf{" + s + "}" if bold and x is not None else s

    tex = [r"\begin{table}[t]", r"    \centering",
           r"    \caption{Ablation: Extremes across phase combinations on "
           r"fpmul\_f16.}",
           r"    \label{tab:ablation}",
           r"    \begin{tabular}{@{}lcc@{}}", r"        \toprule",
           r"        Configuration & Best area (\textmu m$^2$) & Best delay (ps) \\",
           r"        \midrule"]
    for label, a, d in rows:
        tex.append(f"        {label:<40} & {num(a)} & {num(d)} \\\\")
    tex += [r"        \midrule",
            f"        RTLScout: Phases~1--4                    "
            f"& {num(final[0], bold=True)} & {num(final[1], bold=True)} \\\\",
            r"        \bottomrule", r"    \end{tabular}",
            r"    \vspace{-10pt}", r"\end{table}"]
    out = cfg.FIGURES / "table_ablation.tex"
    out.write_text("\n".join(tex) + "\n")
    common.record("stage5", out, "ablation table (extremes per phase combination)")


def run() -> None:
    cfg.FIGURES.mkdir(parents=True, exist_ok=True)
    _attempt("ablation_table", ablation_table)
    _attempt("phase12_plots", phase12_plots)
    _attempt("sweep_plot", sweep_plot)
    _attempt("arrows_plot", arrows_plot)
    _attempt("equal_compute_table", equal_compute_table)
    failures = (common.load_state("figure_failures") or {}).get("failed", [])
    if failures:
        common.log(f"stage 5 finished with failed figures: {failures}")
    else:
        common.mark_done("stage5")


if __name__ == "__main__":
    run()

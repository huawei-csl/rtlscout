#!/usr/bin/env python3
"""CLI: full Phases 1-2 optimization pipeline for a single benchmark.

This is the recommended *general* workflow. It chains several `run_multirun.py`
campaigns and combines their results into one Pareto front via `extract_pareto.py`:

  Phase 1  Structural exploration — one multirun campaign per cost metric
           (area, delay, ...), no synthesis decorators. Half explore / half
           exploit (core.multirun's default fresh schedule).
  Phase 2  Synthesis-aware polish — one campaign per cost metric, each *seeded*
           from the matching Phase-1 elite pool and run as pure exploitation
           (fresh=0). For SpireHDL the agent additionally gets @arithmetic_optimized
           (replace_arithmetic_ops) and @abc_optimized.
  Pareto   The Pareto-optimal designs over every campaign, extracted into
           pareto_fronts/<benchmark>/.

Running one campaign per metric (area AND delay) and combining them yields the
area-vs-delay Pareto front — the "area + speed" workflow. For a single objective
pass `--metrics area` (or transistors, sky130_adp, ...).

For the FP-specialized 4-phase workflow (arithmetic-architecture + Mockturtle
high-effort refinement) see README_fpmul.md. For the full set of per-campaign
knobs see README_multirun.md.

Example:
  python run_pipeline.py \
      --benchmark fpmul_f16 \
      --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
      --metrics area,delay --total-runs 8 --max-concurrent 4 --max-steps 20

Requires an LLM provider token in .env (see README, "Running benchmarks").
"""

import argparse
from pathlib import Path


def _phase_flags(language: str, phase: int, fsm_optimize: bool) -> dict:
    """Per-phase SpireHDL agent-prompt flags.

    Mirrors experiments/rtl_rewriter_multirun.py's `_phase_flags`, minus
    @flowy_optimized (Mockturtle/flowy is not installed in this repo). Phase 1 is
    decorator-free structural exploration; Phase 2 layers the decorators as polish.
    All decorator flags are SpireHDL-only — Verilog/Amaranth campaigns ignore them.
    """
    flags: dict = {}
    if language == "spirehdl" and phase == 2:
        flags["arith_autoconfig"] = True   # @arithmetic_optimized / replace_arithmetic_ops()
        flags["abc_optimize"] = True        # @abc_optimized
    if fsm_optimize and language == "spirehdl":
        flags["fsm_optimize"] = True        # optimized_fsm / optimized_encoding context
    return flags


# Map run_multirun() kwarg -> run_multirun.py CLI flag, for --dry-run rendering.
_FLAG_CLI = {"arith_autoconfig": "--arith-autoconfig", "abc_optimize": "--abc-optimize",
             "fsm_optimize": "--fsm-optimize"}


def _build_plan(benchmark: str, metrics: list, language: str, base: Path,
                no_phase2: bool, fsm_optimize: bool) -> list:
    """Resolve the ordered list of multirun campaigns (Phase 1 then Phase 2)."""
    plan = []
    for m in metrics:
        plan.append({
            "phase": 1, "metric": m,
            "runs_root": base / f"{benchmark}_p1_{m}",
            "seed_from": None, "fresh": None,            # default 0.5 -> 0.1 schedule
            "flags": _phase_flags(language, 1, fsm_optimize),
        })
    if not no_phase2:
        for m in metrics:
            plan.append({
                "phase": 2, "metric": m,
                "runs_root": base / f"{benchmark}_p2_{m}",
                "seed_from": str(base / f"{benchmark}_p1_{m}"),
                "fresh": (0.0, 0.0, 0),                  # pure exploitation: seed every agent
                "flags": _phase_flags(language, 2, fsm_optimize),
            })
    return plan


def _print_dry_run(plan: list, args, pareto_dims: tuple, out: Path) -> None:
    dim_x, dim_y = pareto_dims
    print("# Phases 1-2 pipeline plan (dry run — nothing executed)\n")
    for c in plan:
        cmd = [
            "python run_multirun.py",
            f"--benchmark {args.benchmark}",
            f"--model {args.model}",
            f"--language {args.language}",
            f"--cost-metric {c['metric']}",
            f"--total-runs {args.total_runs}",
            f"--max-concurrent {args.max_concurrent}",
            f"--max-steps {args.max_steps}",
            f"--elite-size {args.elite_size}",
            f"--target-delay {args.target_delay}",
            f"--technology {args.technology}",
            f"--runs-root {c['runs_root']}",
        ]
        if c["seed_from"]:
            cmd.append(f"--seed-from {c['seed_from']}")
        if c["fresh"]:
            fb, fm, ff = c["fresh"]
            cmd += [f"--fresh-base {fb}", f"--fresh-min {fm}", f"--fresh-first {ff}"]
        for k in c["flags"]:
            cmd.append(_FLAG_CLI[k])
        if args.dont_touch_main_arith:
            cmd.append("--dont-touch-main-arith")
        print(f"# Phase {c['phase']} — cost metric '{c['metric']}'")
        print("  " + " \\\n      ".join(cmd) + "\n")
    all_dirs = " ".join(str(c["runs_root"]) for c in plan)
    print(f"# Combined {dim_x}-vs-{dim_y} Pareto front over all campaigns")
    print(f"  python extract_pareto.py {all_dirs} --dims {dim_x},{dim_y} "
          f"--separate-dirs -o {out}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Full Phases 1-2 optimization pipeline (multirun campaigns + combined Pareto)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--benchmark", required=True, help="Benchmark name under benchmarks/")
    parser.add_argument("--model", required=True,
                        help="Model spec with provider prefix (e.g. 'deepinfra:MiniMaxAI/MiniMax-M2.5'). "
                             "Providers: deepinfra, anthropic, openrouter, fake")
    parser.add_argument("--metrics", default="area,delay",
                        help="Comma-separated cost metrics — one multirun campaign each, per phase "
                             "(default: area,delay, i.e. the area+speed workflow). For a single "
                             "objective pass e.g. --metrics area")
    parser.add_argument("--language", default="verilog", choices=["verilog", "spirehdl", "amaranth"],
                        help="Source language (default: verilog)")
    parser.add_argument("--total-runs", type=int, default=10,
                        help="Agent runs per campaign (default: 10)")
    parser.add_argument("--max-concurrent", type=int, default=4,
                        help="Max parallel agents per campaign (default: 4)")
    parser.add_argument("--max-steps", type=int, default=30,
                        help="Max steps per agent (default: 30)")
    parser.add_argument("--elite-size", type=int, default=5,
                        help="Max designs in each campaign's elite pool (default: 5)")
    parser.add_argument("--target-delay", type=float, default=500.0,
                        help="Target delay in ps for PPA metrics (default: 500)")
    parser.add_argument("--technology", default="asap7",
                        help="Process technology for PPA metrics: asap7, nangate45, freepdk45 (default: asap7)")
    parser.add_argument("--pareto-dims", default="area,delay",
                        help="Pareto dimension pair for the final extract (default: area,delay). "
                             "Both must be present in each eval's metrics dict.")
    parser.add_argument("--max-points", type=int, default=None,
                        help="Cap the number of extracted designs (Pareto-optimal first). "
                             "Default: the full Pareto front")
    parser.add_argument("--no-phase2", action="store_true",
                        help="Stop after Phase 1 (skip the synthesis-aware seeded phase)")
    parser.add_argument("--fsm-optimize", action="store_true",
                        help="Enable FSM / state-encoding guidance (optimized_fsm / optimized_encoding) "
                             "in both phases (SpireHDL only)")
    parser.add_argument("--dont-touch-main-arith", action="store_true",
                        help="Tell the agent not to modify core multiplier/adder configs "
                             "(MultiplierConfig / AdderConfig)")
    parser.add_argument("--benchmarks-root", default=None, help="Benchmarks directory")
    parser.add_argument("--runs-root", default="runs",
                        help="Base directory for campaign outputs (default: runs/)")
    parser.add_argument("--out", default=None,
                        help="Output directory for the combined Pareto front "
                             "(default: pareto_fronts/<benchmark>)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the run_multirun + extract_pareto steps without executing them")
    args = parser.parse_args()

    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
    if not metrics:
        parser.error("--metrics needs at least one cost metric")
    dims = [d.strip() for d in args.pareto_dims.split(",") if d.strip()]
    if len(dims) != 2:
        parser.error(f"--pareto-dims must be two comma-separated keys, got {args.pareto_dims!r}")
    dim_x, dim_y = dims

    base = Path(args.runs_root)
    out = Path(args.out) if args.out else Path("pareto_fronts") / args.benchmark
    plan = _build_plan(args.benchmark, metrics, args.language, base,
                       args.no_phase2, args.fsm_optimize)

    if args.dry_run:
        _print_dry_run(plan, args, (dim_x, dim_y), out)
        return

    # Lazy imports — keeps --help / --dry-run usable without the EDA deps installed.
    from core.multirun import run_multirun
    from core.runner import DEFAULT_BENCHMARKS_ROOT
    from extract_pareto import extract

    benchmarks_root = Path(args.benchmarks_root) if args.benchmarks_root else DEFAULT_BENCHMARKS_ROOT

    for c in plan:
        print(f"\n{'='*70}\n=== Phase {c['phase']} — cost metric '{c['metric']}' → {c['runs_root']}\n{'='*70}")
        kwargs = dict(
            benchmark_name=args.benchmark,
            model=args.model,
            total_runs=args.total_runs,
            max_concurrent=args.max_concurrent,
            max_steps=args.max_steps,
            elite_size=args.elite_size,
            cost_metric=c["metric"],
            target_delay=args.target_delay,
            technology=args.technology,
            language=args.language,
            benchmarks_root=benchmarks_root,
            runs_root=c["runs_root"],
            seed_from=c["seed_from"],
            dont_touch_main_arith=args.dont_touch_main_arith,
            **c["flags"],
        )
        if c["fresh"]:
            kwargs["fresh_base"], kwargs["fresh_min"], kwargs["fresh_first"] = c["fresh"]
        run_multirun(**kwargs)

    print(f"\n{'='*70}\n=== Combined {dim_x}-vs-{dim_y} Pareto front → {out}\n{'='*70}")
    extract([c["runs_root"] for c in plan], out, separate_dirs=True,
            max_points=args.max_points, dim_x=dim_x, dim_y=dim_y)
    plot_dirs = " ".join(str(c["runs_root"]) for c in plan)
    print(f"\nPlot the Pareto front with:\n  python plot_pareto_paper.py {plot_dirs} -o plots/{args.benchmark}/")


if __name__ == "__main__":
    main()

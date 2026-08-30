#!/usr/bin/env python3
"""Equal-compute (same-optimizer) LaTeX table: ABC &deepsyn from scratch vs
&deepsyn on the agent/sweep Pareto designs, plus the initial-design reference.

Adapted from the old repo's plot_flowy_equal_compute_table.py: the Flowy
configurations are gone (no flowy in this container); both rows now use
&deepsyn, turning the table into a clean same-optimizer ablation
(handover decision 1).

Usage:
    plot_equal_compute_table.py --refine-eval refine/eval_results.json \
        --initial-eval initial_deepsyn/eval_results.json \
        --baseline-evals baseline_td900.json baseline_td1800.json \
        -o table_equal_compute.tex
"""
import argparse
import json
from pathlib import Path


def _load_eval(path: Path):
    """(best_area, best_delay, n_evals, n_passed) over passing entries."""
    data = json.loads(path.read_text())
    ok = [e for e in data if e.get("passed") and e.get("area") and e.get("delay")]
    if not ok:
        return None, None, len(data), 0
    return (min(e["area"] for e in ok), min(e["delay"] for e in ok),
            len(data), len(ok))


def _fmt(v):
    return f"{v:.1f}" if isinstance(v, (int, float)) else "--"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refine-eval", type=Path, required=True,
                    help="merged eval_results.json of deepsyn-on-Pareto-designs")
    ap.add_argument("--initial-eval", type=Path, required=True,
                    help="eval_results.json of deepsyn-from-scratch (650 runs)")
    ap.add_argument("--baseline-evals", type=Path, nargs="+", default=[],
                    help="run_eval --json outputs for the initial design")
    ap.add_argument("--initial-2x-eval", type=Path, default=None,
                    help="optional double-effort from-scratch eval_results.json")
    ap.add_argument("--refine-front", type=Path, default=None,
                    help="cumulative reported front; supplies best area/delay only")
    ap.add_argument("--budget-min", type=int, default=20,
                    help="per-trajectory deepsyn budget in minutes")
    ap.add_argument("--refine-desc", default=None,
                    help="pipeline row label detail, e.g. '16$\\times$50'")
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    rows = []
    for base in args.baseline_evals:
        r = json.loads(base.read_text())
        m = r.get("metrics", r)
        td = base.parent.name.split("td")[-1]
        rows.append((f"Initial design ({td}\\,ps)",
                     "--", m.get("area"), m.get("delay"), 1, 1))
    def _n_designs(path: Path) -> int:
        return len({e.get("design") for e in json.loads(path.read_text())})

    n_scratch = _n_designs(args.initial_eval)
    specials = [(f"Deepsyn from scratch {n_scratch}$\\times${args.budget_min}\\,min*",
                 args.initial_eval, False)]
    if args.initial_2x_eval and args.initial_2x_eval.exists():
        n2 = _n_designs(args.initial_2x_eval)
        specials.append((f"Deepsyn from scratch {n2}$\\times${2 * args.budget_min}"
                         f"\\,min (2$\\times$ effort)", args.initial_2x_eval, False))
    refine_desc = args.refine_desc or "Deepsyn refine"
    specials.append((f"RTLScout: Phases 1--3 + {refine_desc}*",
                     args.refine_eval, True))
    body = []
    for label, path, bold in specials:
        a, d, n, ok = _load_eval(path)
        # Best area/delay come from the cumulative reported front when given;
        # trajectory/eval counts stay deepsyn-only.
        if bold and args.refine_front and args.refine_front.exists():
            a, d, _, _ = _load_eval(args.refine_front)
        aa = f"\\textbf{{{_fmt(a)}}}" if bold else _fmt(a)
        dd = f"\\textbf{{{_fmt(d)}}}" if bold else _fmt(d)
        body.append((label, n, aa, dd, f"{ok}/{n}"))

    lines = [
        r"\begin{table}[t]",
        r"    \centering",
        r"    \caption{Equal-compute comparison: ABC \texttt{\&deepsyn} applied"
        r" directly to the starting design vs.\ the full RTLScout pipeline."
        r" *matched compute}",
        r"    \label{tab:equal_compute}",
        r"    \setlength{\tabcolsep}{4pt}",
        r"    \resizebox{\linewidth}{!}{",
        r"    \begin{tabular}{@{}lrccc@{}}",
        r"        \toprule",
        r"        Configuration & Traj. & Evals (pass) & Best area & Best delay \\",
        r"        & & & ($\mathrm{\mu m^2}$) & (ps) \\",
        r"        \midrule",
    ]
    for label, _dash, a, d, _n, _ok in rows:
        lines.append(f"        {label} & -- & 1/1 & {_fmt(a)} & {_fmt(d)} \\\\")
    lines.append(r"        \midrule")
    for label, n, aa, dd, passed in body:
        lines.append(f"        {label} & {n} & {passed} & {aa} & {dd} \\\\")
    lines += [r"        \bottomrule", r"    \end{tabular}", r"    }",
              r"\end{table}", ""]
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

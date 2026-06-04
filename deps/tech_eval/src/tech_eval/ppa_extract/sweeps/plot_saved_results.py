import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")

from tech_eval.ppa_extract.sweeps.plotting2 import plot_delay_vs_area, plot_power_vs_area, plot_power_vs_delay, plot_switch_count_vs_area, plot_switch_count_vs_delay, plot_transistor_count_vs_area


def _parse_cases(values):
    cases = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                cases.append(part)
    return cases


def _load_results(path):
    with open(path, "r") as f:
        data = json.load(f)
    if "case_results" not in data:
        raise ValueError("Results file missing 'case_results' key")
    return data


def _select_cases(case_results, selected_cases):
    if not selected_cases:
        return case_results
    missing = [case for case in selected_cases if case not in case_results]
    if missing:
        available = ", ".join(case_results.keys())
        raise ValueError(
            f"Unknown case labels: {', '.join(missing)}. Available: {available}"
        )
    return {case: case_results[case] for case in selected_cases}

def _filter_cases_by_delay(case_results, delay_threshold):
    if delay_threshold is None:
        return case_results
    filtered_results = {}
    for case_label, results in case_results.items():
        filtered = [res for res in results if res.get("delay") is not None and res["delay"] <= delay_threshold]
        if filtered:
            filtered_results[case_label] = filtered
    return filtered_results


def _filter_cases_by_area(case_results, area_threshold):
    if area_threshold is None:
        return case_results
    filtered_results = {}
    for case_label, results in case_results.items():
        filtered = [res for res in results if res.get("area") is not None and res["area"] <= area_threshold]
        if filtered:
            filtered_results[case_label] = filtered
    return filtered_results


def _regroup_by_field(case_results, field):
    regrouped = {}
    for entries in case_results.values():
        for entry in entries:
            key = entry.get(field)
            label = str(key) if key is not None else "None"
            regrouped.setdefault(label, []).append(entry)
    return regrouped


def _filter_cases_by_power(case_results, power_threshold):
    if power_threshold is None:
        return case_results
    filtered_results = {}
    for case_label, results in case_results.items():
        filtered = [res for res in results if res.get("power") is not None and res["power"] <= power_threshold]
        if filtered:
            filtered_results[case_label] = filtered
    return filtered_results


def main():
    parser = argparse.ArgumentParser(
        description="Plot delay/power vs area from saved PPA results."
    )
    parser.add_argument(
        "--results",
        default=" ",
        help="Path to a saved results JSON file.",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        default=[],
        help="Case labels to plot (space or comma-separated).",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List available case labels and exit.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for plots (defaults to results file directory).",
    )
    parser.add_argument(
        "--n-bits",
        type=int,
        default=None,
        help="Override bit width if not present in results metadata.",
    )
    parser.add_argument(
        "--design-prefix",
        default=None,
        help="Override design prefix in plot filenames.",
    )
    parser.add_argument(
        "--title-label",
        default=None,
        help="Override plot title label.",
    )

    parser.add_argument(
        "--group-by",
        default=None,
        help="Group results by a field name (e.g. ppa_cls_name, fsa_cls_name, target_delay). Omit to keep original case grouping.",
    )
    parser.add_argument(
        "--no-legend",
        action="store_true",
        help="Disable legend in plots.",
    )
    
    # Delay threshold; slower results get filtered out.
    parser.add_argument(
        "--delay-threshold",
        type=float,
        default=None,
        help="Delay threshold to filter out results slower than this value (in ns).",
    )
    parser.add_argument(
        "--area-threshold",
        type=float,
        default=None,
        help="Area threshold to filter out results larger than this value.",
    )
    parser.add_argument(
        "--power-threshold",
        type=float,
        default=None,
        help="Power threshold to filter out results higher than this value.",
    )

    args = parser.parse_args()

    data = _load_results(args.results)
    case_results = data["case_results"]

    if args.list_cases:
        for case_label in case_results.keys():
            print(case_label)
        return

    selected_cases = _parse_cases(args.cases)
    case_results = _select_cases(case_results, selected_cases)
    case_results = _filter_cases_by_delay(case_results, args.delay_threshold)
    case_results = _filter_cases_by_area(case_results, args.area_threshold)
    case_results = _filter_cases_by_power(case_results, args.power_threshold)
    if not case_results:
        raise SystemExit("No case results to plot after filtering.")

    group_by = args.group_by
    if group_by is not None:
        case_results = _regroup_by_field(case_results, group_by)
        if not case_results:
            raise SystemExit(f"No results after regrouping by field '{group_by}'.")

    meta = data.get("meta", {})
    n_bits = args.n_bits if args.n_bits is not None else meta.get("c_width")
    if n_bits is None:
        raise SystemExit("Missing bit width: provide --n-bits or include meta.c_width.")

    design_prefix = args.design_prefix or meta.get("design_prefix", "MMAC")
    title_label = args.title_label or meta.get("title_label", "MMAC Core")
    suffix = f"by_{group_by}" if group_by is not None else "by_case"
    out_dir = args.out_dir or meta.get("out_dir") or os.path.dirname(os.path.abspath(args.results))

    os.makedirs(out_dir, exist_ok=True)
    add_legend = not args.no_legend

    plot_kwargs = dict(
        results_payload=data,
        groups=case_results,
        out_dir=out_dir,
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )
    for plotter in (
        plot_delay_vs_area,
        plot_power_vs_area,
        plot_switch_count_vs_area,
        plot_transistor_count_vs_area,
        plot_power_vs_delay,
        plot_switch_count_vs_delay,
    ):
        plotter(**plot_kwargs)


if __name__ == "__main__":
    main()
import os
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from matplotlib import pyplot as plt


def _pareto_front(points: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = sorted(points, key=lambda x: (x[0], x[1]))
    front: List[Tuple[float, float]] = []
    best_y = float("inf")
    for x_val, y_val in pts:
        if y_val <= best_y:
            front.append((x_val, y_val))
            best_y = y_val
    return front


def _stepify(front: List[Tuple[float, float]]) -> Tuple[List[float], List[float]]:
    if not front:
        return [], []
    xs = [front[0][0]]
    ys = [front[0][1]]
    for (x_next, y_next), (_, y_prev) in zip(front[1:], front[:-1]):
        xs.extend([x_next, x_next])
        ys.extend([y_prev, y_next])
    return xs, ys


# get_ppa splits power by path: `power_total` (VCD, rebased to fmax) or
# `power_probabilistic_fixed_clock` (fallback); pre-split runs wrote flat `power`.
_METRIC_ALIASES = {"power": ("power", "power_total", "power_probabilistic_fixed_clock")}


def _resolve_metric_key(groups: Dict[str, List[dict]], metric_key: str) -> Optional[str]:
    """First alias of metric_key actually present in the rows, else None."""
    for alias in _METRIC_ALIASES.get(metric_key, (metric_key,)):
        if any(alias in e for entries in groups.values() for e in entries):
            return alias
    return None


def _plot_metric_vs_area(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    metric_key: str,
    metric_label: str,
    x_metric_key: str = "area",
    x_metric_label: str = "Area (um^2)",
    suffix: str,
    design_prefix: str,
    title_label: str,
    add_legend: bool,
) -> None:
    # A missing optional metric must not kill the sweep after the results are saved.
    data_key = _resolve_metric_key(groups, metric_key)
    if data_key is None:
        print(f"[plotting2] no '{metric_key}' field in results — skipping that plot")
        return
    out_path = os.path.join(
        out_dir,
        f"{design_prefix}_m{results_payload['meta']['dim_m']}_a{results_payload['meta']['a_width']}_{suffix}_{x_metric_key}_vs_{metric_key}.png",
    )
    plt.figure(figsize=(8 if add_legend else 5, 4))
    colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])

    for idx, (group_label, entries) in enumerate(groups.items()):
        if not entries:
            continue
        pairs = [(e[x_metric_key], e[data_key]) for e in entries if data_key in e]
        if not pairs:
            continue
        x_values = [p[0] for p in pairs]
        metrics = [p[1] for p in pairs]
        color = colors[idx % len(colors)] if colors else None
        plt.scatter(
            x_values,
            metrics,
            color=color,
            s=20,
            alpha=0.1,
            label=f"{group_label} results",
        )

        front = _pareto_front(zip(x_values, metrics))
        if front:
            xs, ys = _stepify(front)
            plt.plot(xs, ys, color=color, linewidth=1.6, label=f"{group_label} pareto")

    size_info = f"MxKxN: {results_payload['meta']['dim_m']}x{results_payload['meta']['dim_k']}x{results_payload['meta']['dim_n']}, A,B,C bitwidth:{results_payload['meta']['a_width']}b, {results_payload['meta']['b_width']}b, {results_payload['meta']['c_width']}b"
    technology = results_payload['meta'].get('technology', 'unknown technology')
    plt.title(f"{title_label} - {size_info} - {metric_label} vs {x_metric_label} - {technology}", fontsize=7)
    plt.xlabel(x_metric_label)
    plt.ylabel(metric_label)
    plt.grid(True, linestyle="--", alpha=0.5)
    if add_legend:
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=7)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"Saved plot to {out_path}")


def plot_delay_vs_area(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    suffix: str = "by_case",
    design_prefix: str = "Mul",
    title_label: str = "Mult",
    add_legend: bool = False,
) -> None:
    _plot_metric_vs_area(
        results_payload,
        groups,
        out_dir,
        metric_key="delay",
        metric_label=f"Delay ({results_payload['meta'].get('ppa_report_time_unit', 'ns')})",
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )


def plot_power_vs_area(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    suffix: str = "by_case",
    design_prefix: str = "Mul",
    title_label: str = "Mult",
    add_legend: bool = False,
) -> None:
    _plot_metric_vs_area(
        results_payload,
        groups,
        out_dir,
        metric_key="power",
        metric_label="Power",
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )


def plot_switch_count_vs_area(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    suffix: str = "by_case",
    design_prefix: str = "Mul",
    title_label: str = "Mult",
    add_legend: bool = False,
) -> None:
    _plot_metric_vs_area(
        results_payload,
        groups,
        out_dir,
        metric_key="switch_count",
        metric_label="Switch Count",
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )


def plot_transistor_count_vs_area(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    suffix: str = "by_case",
    design_prefix: str = "Mul",
    title_label: str = "Mult",
    add_legend: bool = False,
) -> None:
    _plot_metric_vs_area(
        results_payload,
        groups,
        out_dir,
        metric_key="estimated_num_transistors",
        metric_label="Estimated Number of Transistors",
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )


def plot_power_vs_delay(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    suffix: str = "by_case",
    design_prefix: str = "Mul",
    title_label: str = "Mult",
    add_legend: bool = False,
) -> None:
    _plot_metric_vs_area(
        results_payload,
        groups,
        out_dir,
        metric_key="power",
        metric_label="Power",
        x_metric_key="delay",
        x_metric_label=f"Delay ({results_payload['meta'].get('ppa_report_time_unit', 'ns')})",
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )


def plot_switch_count_vs_delay(
    results_payload: Dict,
    groups: Dict[str, List[dict]],
    out_dir: str,
    *,
    suffix: str = "by_case",
    design_prefix: str = "Mul",
    title_label: str = "Mult",
    add_legend: bool = False,
) -> None:
    _plot_metric_vs_area(
        results_payload,
        groups,
        out_dir,
        metric_key="switch_count",
        metric_label="Switch Count",
        x_metric_key="delay",
        x_metric_label=f"Delay ({results_payload['meta'].get('ppa_report_time_unit', 'ns')})",
        suffix=suffix,
        design_prefix=design_prefix,
        title_label=title_label,
        add_legend=add_legend,
    )


# ---------------------------------------------------------------------------
# -- Regrouping helpers
# ---------------------------------------------------------------------------

def _regroup_by(
    groups: Dict[str, List[dict]],
    key_fn: Callable[[dict], Optional[str]],
) -> Dict[str, List[dict]]:
    """Flatten all entries across groups and re-group by a new key.

    ``key_fn`` returns a string label for each entry, or ``None`` to skip
    that entry (useful when the grouping field is absent, e.g. adder results
    when grouping by PPA tree).
    """
    regrouped: Dict[str, List[dict]] = {}
    for entries in groups.values():
        for entry in entries:
            key = key_fn(entry)
            if key is not None:
                regrouped.setdefault(key, []).append(entry)
    return regrouped


def regroup_by_target_delay(groups: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Group all results by the target delay constraint used during synthesis."""
    return _regroup_by(
        groups,
        lambda e: f"td_{e['target_delay']}" if "target_delay" in e else None,
    )


def regroup_by_ppa(groups: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Group all results by PPA reduction tree type (requires ppa_cls_name field)."""
    return _regroup_by(groups, lambda e: e.get("ppa_cls_name"))


def regroup_by_fsa(groups: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Group all results by final-stage adder type (requires fsa_cls_name field)."""
    return _regroup_by(groups, lambda e: e.get("fsa_cls_name"))


# ---------------------------------------------------------------------------
# -- Backward-compatible aliases (kept for restored/ and other legacy callers)
# ---------------------------------------------------------------------------

def plot_delay_vs_area_by_case(results_payload, case_results, out_dir, *, suffix="by_case", design_prefix="Mul", title_label="Mult", add_legend=False):
    return plot_delay_vs_area(results_payload, case_results, out_dir, suffix=suffix, design_prefix=design_prefix, title_label=title_label, add_legend=add_legend)

def plot_power_vs_area_by_case(results_payload, case_results, out_dir, *, suffix="by_case", design_prefix="Mul", title_label="Mult", add_legend=False):
    return plot_power_vs_area(results_payload, case_results, out_dir, suffix=suffix, design_prefix=design_prefix, title_label=title_label, add_legend=add_legend)

def plot_switch_count_vs_area_by_case(results_payload, case_results, out_dir, *, suffix="by_case", design_prefix="Mul", title_label="Mult", add_legend=False):
    return plot_switch_count_vs_area(results_payload, case_results, out_dir, suffix=suffix, design_prefix=design_prefix, title_label=title_label, add_legend=add_legend)

def plot_transistor_count_vs_area_by_case(results_payload, case_results, out_dir, *, suffix="by_case", design_prefix="Mul", title_label="Mult", add_legend=False):
    return plot_transistor_count_vs_area(results_payload, case_results, out_dir, suffix=suffix, design_prefix=design_prefix, title_label=title_label, add_legend=add_legend)

def plot_power_vs_delay_by_case(results_payload, case_results, out_dir, *, suffix="by_case", design_prefix="Mul", title_label="Mult", add_legend=False):
    return plot_power_vs_delay(results_payload, case_results, out_dir, suffix=suffix, design_prefix=design_prefix, title_label=title_label, add_legend=add_legend)

def plot_switch_count_vs_delay_by_case(results_payload, case_results, out_dir, *, suffix="by_case", design_prefix="Mul", title_label="Mult", add_legend=False):
    return plot_switch_count_vs_delay(results_payload, case_results, out_dir, suffix=suffix, design_prefix=design_prefix, title_label=title_label, add_legend=add_legend)

"""Shared utilities for PPA sweep scripts."""

import os
from typing import Dict, List


def prepare_out_dir() -> str:
    out_dir = os.path.join("results", "ppa")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def sanitize_json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


_SERIALIZE_SKIP_KEYS = {"config", "worst_timing_path"}


def serialize_case_results(case_results: Dict[str, List[dict]]) -> dict:
    serializable = {}
    for case_label, entries in case_results.items():
        cleaned_entries = []
        for entry in entries:
            cleaned_entries.append(
                {k: sanitize_json_value(v) for k, v in entry.items() if k not in _SERIALIZE_SKIP_KEYS}
            )
        serializable[case_label] = cleaned_entries
    return serializable


def case_key(case_label: str, encoding) -> str:
    return f"{case_label}_{encoding.value}"


def report_sweep_counts(results: list, target_delays: list, total_configs: int) -> None:
    print(
        f"Length of configs: "
        f"{total_configs}, target delays: {len(target_delays)}, "
        f"expected length of results: {total_configs * len(target_delays)}, "
        f"length of results: {len(results)}"
    )

#!/usr/bin/env python3
"""Extract Pareto-optimal designs from a tech_eval sweep results JSON.

Reads a *_results.json file (from fpmul_sweep_mp.py or similar), computes the
area-vs-delay Pareto front across all cases, and writes the standard
pareto_front.json + design_NNN/ directory structure.

Usage:
    python extract_sweep_pareto.py \
        /workspaces/rtlagent/deps/tech_eval/results/ppa/FpMul_e5f10_results.json \
        -o pareto_fronts/fpmul_sweep --separate-dirs -n 50
"""

import argparse
import json
import shutil
from pathlib import Path

from extract_pareto import pareto_front, _normalized_score


def _load_sweep_entries(json_path: Path) -> list[dict]:
    """Load all entries with area + delay from a sweep results JSON."""
    data = json.loads(json_path.read_text())
    entries = []
    for case_name, case_entries in data.get("case_results", {}).items():
        for e in case_entries:
            area = e.get("area")
            delay = e.get("delay")
            if area is None or delay is None:
                continue
            entries.append({
                "area": float(area),
                "delay": float(delay),
                "power": float(e["power"]) if e.get("power") is not None else None,
                "cost_value": float(area),
                "cost_metric": "area",
                "metrics": {
                    "area": float(area),
                    "delay": float(delay),
                    "power": float(e["power"]) if e.get("power") is not None else None,
                },
                "target_delay": e.get("target_delay"),
                "pass_rate": 1.0,
                "case_name": case_name,
                "design": e.get("design"),
                "gen_source": e.get("gen_source"),
                "verilog_path": e.get("verilog_path"),
                "worker_path": e.get("worker_path"),
                # Sweep config fields
                "mult_ppa_cls_name": e.get("mult_ppa_cls_name"),
                "mult_fsa_cls_name": e.get("mult_fsa_cls_name"),
                "mult_optim_type": e.get("mult_optim_type"),
                "add_fsa_cls_name": e.get("add_fsa_cls_name"),
            })
    return entries


def _select_top_n(entries: list[dict], front: list[dict], n: int) -> list[dict]:
    """Select up to n designs: all Pareto points first, then best-scored non-Pareto."""
    if n >= len(entries):
        return list(entries)
    if n <= len(front):
        if n <= 0:
            return []
        min_area_idx = min(range(len(front)), key=lambda i: front[i]["area"])
        min_delay_idx = min(range(len(front)), key=lambda i: front[i]["delay"])
        pinned = {min_area_idx, min_delay_idx}
        scores = _normalized_score(front)
        candidates = sorted(
            ((scores[i], i) for i in range(len(front)) if i not in pinned),
            key=lambda x: x[0],
        )
        remaining = n - len(pinned)
        chosen = pinned | {i for _, i in candidates[:max(0, remaining)]}
        return [front[i] for i in sorted(chosen)]

    selected = list(front)
    front_set = {id(e) for e in front}
    non_front = [e for e in entries if id(e) not in front_set]
    scores = _normalized_score(non_front)
    ranked = sorted(zip(scores, non_front), key=lambda x: x[0])
    remaining = n - len(selected)
    selected.extend(e for _, e in ranked[:remaining])
    return selected


def _design_key(e: dict) -> str:
    """Create a key that identifies the unique circuit (independent of target_delay).

    Same design at different target delays produces the same Verilog but
    different PPA results. The circuit identity is: case + config fields.
    """
    parts = [
        e.get("case_name", ""),
        str(e.get("mult_ppa_cls_name", "")),
        str(e.get("mult_fsa_cls_name", "")),
        str(e.get("mult_optim_type", "")),
        str(e.get("add_fsa_cls_name", "")),
    ]
    return "|".join(parts)


def _deduplicate_by_design(entries: list[dict]) -> list[dict]:
    """Keep only the best entry (lowest normalized score) per unique circuit.

    The same circuit evaluated at different target delays produces different PPA.
    We keep the one with the best area-delay trade-off.
    """
    by_key: dict[str, list[dict]] = {}
    for e in entries:
        key = _design_key(e)
        by_key.setdefault(key, []).append(e)

    deduped = []
    for key, group in by_key.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            scores = _normalized_score(group)
            best_idx = min(range(len(group)), key=lambda i: scores[i])
            deduped.append(group[best_idx])
    return deduped


def extract_sweep_pareto(
    json_path: Path,
    output_dir: Path,
    separate_dirs: bool = False,
    max_points: int | None = None,
    deduplicate: bool = True,
) -> None:
    entries = _load_sweep_entries(json_path)
    if not entries:
        print("No entries with area + delay found.")
        return

    if deduplicate:
        n_before = len(entries)
        entries = _deduplicate_by_design(entries)
        print(f"Deduplicated: {n_before} → {len(entries)} unique designs")

    front = pareto_front(entries)

    if max_points is not None:
        selected = _select_top_n(entries, front, max_points)
    else:
        selected = front

    selected.sort(key=lambda e: e["area"])

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    used_names: dict[str, int] = {}

    for idx, entry in enumerate(selected):
        verilog_src = entry.get("verilog_path")
        if verilog_src and Path(verilog_src).exists():
            src_path = Path(verilog_src)
        else:
            # Try worker_path/design.v
            wp = entry.get("worker_path", "")
            candidate = Path(wp) / "design.v" if wp else None
            if candidate and candidate.exists():
                src_path = candidate
            else:
                print(f"  [{idx}] SKIP: no Verilog file found (worker_path={wp})")
                continue

        out_name = src_path.name
        if out_name in used_names:
            used_names[out_name] += 1
            stem, suffix = src_path.stem, src_path.suffix
            out_name = f"{stem}_{used_names[out_name]}{suffix}"
        else:
            used_names[out_name] = 0

        if separate_dirs:
            dest_dir = output_dir / f"design_{idx:03d}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_dir / out_name)
            entry["extracted_file"] = f"design_{idx:03d}/{out_name}"
        else:
            shutil.copy2(src_path, output_dir / out_name)
            entry["extracted_file"] = out_name

        # Clean up internal fields
        clean_entry = {k: v for k, v in entry.items()
                       if k not in ("_design_path",)}
        manifest.append(clean_entry)

    manifest_path = output_dir / "pareto_front.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    n_pareto = sum(1 for e in manifest if any(
        e["area"] == f["area"] and e["delay"] == f["delay"] for f in front
    ))
    extra = f" ({n_pareto} Pareto + {len(manifest) - n_pareto} non-Pareto)" if len(manifest) > n_pareto else ""
    print(f"Extracted: {len(manifest)} designs{extra} (from {len(entries)} sweep entries)")
    print(f"Extracted to {output_dir}/")
    for i, e in enumerate(manifest, 1):
        print(f"  {i}. {e.get('extracted_file', '?'):40s}  area={e['area']:<6.0f}  delay={e['delay']:.0f}")
    print(f"Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract Pareto designs from a tech_eval sweep results JSON")
    parser.add_argument("json_file", type=Path,
                        help="Sweep results JSON (e.g. FpMul_e5f10_results.json)")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="Output directory")
    parser.add_argument("--separate-dirs", action="store_true",
                        help="Put each design in its own design_NNN/ subdirectory")
    parser.add_argument("-n", "--max-points", type=int, default=None,
                        help="Maximum designs to extract (Pareto first, then best-scored)")
    parser.add_argument("--no-deduplicate", action="store_true",
                        help="Keep all entries including duplicates at different target delays")
    args = parser.parse_args()

    extract_sweep_pareto(args.json_file, args.output,
                         separate_dirs=args.separate_dirs,
                         max_points=args.max_points,
                         deduplicate=not args.no_deduplicate)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Re-measure transistor counts in a rtl_rewriter_multirun summary.

Why this exists
---------------
The transistor side-stat in ``core/cost.py`` used to read the per-module
``estimated_num_transistors`` straight from ``stat -tech cmos -json``. For a
design shipped as a module *hierarchy* (top module instantiates submodules)
that field is 0 (or undercounted) on the top module -- the gates live inside
the submodule instances. Wires and cells were never affected (they come from
the text ``stat`` ``=== design hierarchy ===`` roll-up, which recurses). See
``TRANSISTOR_STAT_MODE`` in ``core/cost.py`` for the fix.

Summaries produced before the fix therefore carry stale transistor numbers for
any hierarchical design. This script re-measures, with the *current* (fixed)
``core/cost.py``, every design that feeds the best-per-phase table and writes a
corrected summary. The original summary is left untouched.

Scope
-----
* **Verilog** -- both the baseline and every phase's best agent design are
  re-measured. The baseline comes from the immutable benchmark directory
  (``benchmarks/rtl_rewriter/caseN/context/starting_point.v``); the agent
  design from ``best_design/<design_file>``, where ``design_file`` is named by
  ``best_design/_best_meta.json`` (the run workspace is *not* used -- agents
  scribble on the files there).
* **SpireHDL** -- skipped. SpireHDL compiles to a single flat Verilog module
  (verified: every emitted ``design.v`` has exactly one ``module``), so the
  hierarchy bug cannot affect it and its transistor counts are already correct.

Each re-measured design's wires/cells are cross-checked against the stored
summary; a mismatch is reported and that entry's transistor value is left
unchanged (a mismatch means the wrong file was measured, so the re-measured
transistor count cannot be trusted either).

Usage::

    python experiments/recount_rtl_rewriter_transistors.py runs/<run>/summary.json
    # writes runs/<run>/summary_transistors_fixed.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.cost import YosysCellsCost  # noqa: E402  (after sys.path tweak)


def _case_sort_key(case_id: str) -> int:
    return int(case_id.replace("case", ""))


def _measure(design_file: Path, top_module: Optional[str]) -> Optional[Dict]:
    """Run the (fixed) Yosys stat cost on a single design file.

    Returns ``None`` (rather than raising) on a measurement failure so one bad
    file does not abort the whole recount; the caller logs it and keeps the
    stored value.
    """
    cost = YosysCellsCost(timeout=180)
    try:
        res = cost.evaluate(design_file.parent, top_module=top_module,
                            design_file=design_file)
    except Exception as e:  # noqa: BLE001 - report and continue
        print(f"  ! measure error for {design_file}: {e}", file=sys.stderr)
        return None
    if not res.ok:
        print(f"  ! measure failed for {design_file}: {res.error[:160]}",
              file=sys.stderr)
        return None
    return res.stats


def _best_design_file(best_design_dir: Path) -> Optional[Path]:
    """The authoritative best design file, via ``best_design/_best_meta.json``.

    ``_best_meta.json`` records ``design_file`` -- the name of the winning
    design among the many variants the agent leaves in ``best_design/``.
    """
    meta_path = best_design_dir / "_best_meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:  # noqa: BLE001
        return None
    name = meta.get("design_file")
    if not name:
        return None
    f = best_design_dir / name
    return f if f.is_file() else None


def recount(summary_path: Path) -> Tuple[Dict, List[str], List[str]]:
    """Return (corrected_summary, change_log, wires_cells_mismatches)."""
    summary = json.loads(summary_path.read_text())
    run_root = summary_path.parent
    results = summary.get("results", {})
    phases = ("phase1", "phase2") if summary.get("phases", 2) >= 2 else ("phase1",)

    changes: List[str] = []
    mismatches: List[str] = []

    for case_id in sorted(results, key=_case_sort_key):
        rec = results[case_id].get("verilog")
        if not rec:
            continue
        top = rec.get("module_name")

        # --- baseline: the immutable benchmark starting point ----------------
        bench = rec.get("benchmark_path")
        if bench:
            bf = REPO_ROOT / bench / "context" / "starting_point.v"
            st = _measure(bf, top) if bf.is_file() else None
            if st is not None:
                if st["cells"] != rec.get("baseline_cells") or \
                   st["wires"] != rec.get("baseline_wires"):
                    mismatches.append(
                        f"{case_id}/verilog baseline: wires/cells drift "
                        f"summary=({rec.get('baseline_wires')},{rec.get('baseline_cells')}) "
                        f"remeasured=({st['wires']},{st['cells']}) -- transistor left as-is")
                else:
                    old = rec.get("baseline_transistors")
                    new = st["transistors"]
                    if old != new:
                        changes.append(
                            f"{case_id}/verilog baseline_transistors: {old} -> {new}")
                    rec["baseline_transistors"] = new

        # --- per-phase best agent design -------------------------------------
        for phase in phases:
            prec = rec.get(phase)
            if not prec:
                continue
            best_dir = run_root / phase / "verilog" / case_id / "best_design"
            df = _best_design_file(best_dir)
            if df is None:
                print(f"  ! no best design file for {case_id}/verilog/{phase}",
                      file=sys.stderr)
                continue
            st = _measure(df, top)
            if st is None:
                continue

            tstats = prec.setdefault("stats", {})
            stored_cells = (tstats.get("cells", {}) or {}).get("min")
            stored_wires = (tstats.get("wires", {}) or {}).get("min")
            if st["cells"] != stored_cells or st["wires"] != stored_wires:
                mismatches.append(
                    f"{case_id}/verilog/{phase}: wires/cells drift "
                    f"summary=({stored_wires},{stored_cells}) "
                    f"remeasured=({st['wires']},{st['cells']}) -- transistor left as-is")
                continue

            old = (tstats.get("transistors", {}) or {}).get("min")
            new = st["transistors"]
            if old != new:
                changes.append(
                    f"{case_id}/verilog/{phase} transistors: {old} -> {new}")
            # 1 run/phase -> min == max == mean.
            tr = tstats.setdefault("transistors", {})
            tr["min"] = tr["max"] = tr["mean"] = new
            # Keep the per-run records self-consistent with the patched stats.
            for run in prec.get("runs", []) or []:
                bm = run.get("best_metrics")
                if isinstance(bm, dict) and "transistors" in bm:
                    bm["transistors"] = new
                be = run.get("best_eval")
                if isinstance(be, dict) and isinstance(be.get("metrics"), dict) \
                        and "transistors" in be["metrics"]:
                    be["metrics"]["transistors"] = new

    return summary, changes, mismatches


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("summary_json", type=Path)
    ap.add_argument("--out", type=Path, default=None,
                    help="output path (default: <name>_transistors_fixed.json)")
    args = ap.parse_args()

    summary, changes, mismatches = recount(args.summary_json)

    print(f"\nRe-measured Verilog transistor counts "
          f"({len(changes)} value(s) changed; SpireHDL is flat -> already correct):",
          file=sys.stderr)
    for c in changes:
        print(f"  {c}", file=sys.stderr)
    if not changes:
        print("  (none -- all designs were already correct)", file=sys.stderr)
    if mismatches:
        print("\nWARNING: wires/cells drift (fix should never touch them):",
              file=sys.stderr)
        for m in mismatches:
            print(f"  {m}", file=sys.stderr)

    out = args.out or args.summary_json.with_name(
        args.summary_json.stem + "_transistors_fixed.json")
    out.write_text(json.dumps(summary, indent=1))
    print(f"\nWrote corrected summary: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()

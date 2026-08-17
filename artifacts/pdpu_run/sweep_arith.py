#!/usr/bin/env python3
"""Phase-3-style arithmetic sweep for the PDPU spire design.

Sweeps the StageBased adder/multiplier options that `replace_arithmetic_ops`
can install — final-stage adder (used by every `+`/`-` AND by the multiplier's
final stage), partial-product generation, and partial-product accumulation —
then evaluates every config at the reporting target delays and reports the
area/delay Pareto front. The fpmul suite gets its Phase-3 front from an
architectural sweep of the multiplier/adder grid; this is the PDPU analogue.

    sweep_arith.py --out <dir> [--workers N] [--targets 2000 3500 5000]
"""
import argparse
import itertools
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/workspaces/rtl_scout")
PY = Path.home() / "pyenv_eda" / "bin" / "python"
BENCH = REPO / "internal/benchmarks/pdpu_dot4_spire"
START = BENCH / "context/starting_point.py"

# Final-stage adder: drives every +/- in the design (the 18-bit accumulate
# chain and the exponent adds) and the multiplier's final stage.
FSA = ["RIPPLE_CARRY", "PREFIX_KOGGE_STONE", "PREFIX_BRENT_KUNG",
       "PREFIX_SKLANSKY", "PREFIX_LADNER_FISCHER", "PREFIX_HAN_CARLSON",
       "PREFIX_SPARSE_KOGGE_STONE_2", "PLUS_OPERATOR"]
# Multiplier partial-product accumulation (the 4x4 mantissa products).
PPA = ["CARRY_SAVE_TREE", "WALLACE_TREE", "DADDA_TREE",
       "FOUR_TWO_COMPRESSOR", "ACCUMULATOR_TREE"]
# Partial-product generation.
PPG = ["AND", "BOOTH_OPTIMISED"]


def emit_design(d: Path, fsa: str, ppa: str, ppg: str) -> None:
    src = START.read_text()
    body = src[:src.rindex("PdpuDot4()")]           # drop the emission tail
    d.mkdir(parents=True, exist_ok=True)
    (d / "design.py").write_text(body + f'''
from spire.arithmetic.int_arithmetic_config import (
    ArithmeticConfig, replace_arithmetic_ops, FSAOption, PPAOption, PPGOption)

pdpu = PdpuDot4()
replace_arithmetic_ops(pdpu, ArithmeticConfig(
    fsa_opt=FSAOption.{fsa},
    ppa_opt=PPAOption.{ppa},
    ppg_opt=PPGOption.{ppg},
))
pdpu.to_verilog_file("design.v", name="pdpu_top")
''')


def emit_baseline(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "design.py").write_text(START.read_text())   # plain operators, no replacement


def build(out: Path) -> list:
    """Generate every config; returns the manifest."""
    manifest = []
    emit_baseline(out / "design_000")
    manifest.append({"design": "design_000", "fsa": "(none)", "ppa": "(none)",
                     "ppg": "(none)", "note": "baseline: plain operators"})
    for i, (fsa, ppa, ppg) in enumerate(itertools.product(FSA, PPA, PPG), start=1):
        name = f"design_{i:03d}"
        emit_design(out / name, fsa, ppa, ppg)
        manifest.append({"design": name, "fsa": fsa, "ppa": ppa, "ppg": ppg})
    (out / "sweep_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def elaborate(out: Path, manifest: list, workers: int) -> list:
    """Run each design.py to emit design.v; drop configs that fail to build."""
    def one(m):
        d = out / m["design"]
        p = subprocess.run([str(PY), "design.py"], cwd=d, capture_output=True,
                           text=True, timeout=900)
        ok = (d / "design.v").exists()
        if not ok:
            m["build_error"] = (p.stderr or p.stdout)[-300:]
        return ok
    with ThreadPoolExecutor(max_workers=workers) as ex:
        oks = list(ex.map(one, manifest))
    good = [m for m, ok in zip(manifest, oks) if ok]
    print(f"elaborated {len(good)}/{len(manifest)} configs", flush=True)
    for m in manifest:
        if "build_error" in m:
            print(f"  BUILD FAIL {m['design']} "
                  f"({m['fsa']}/{m['ppa']}/{m['ppg']}): "
                  f"{m['build_error'].splitlines()[-1][:90]}")
    return good


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--targets", type=float, nargs="+",
                    default=[2000.0, 3500.0, 5000.0])
    a = ap.parse_args()
    a.out = a.out.resolve()   # batch_eval runs with cwd=REPO

    manifest = build(a.out)
    print(f"generated {len(manifest)} configs "
          f"({len(FSA)} FSA x {len(PPA)} PPA x {len(PPG)} PPG + baseline)")
    good = elaborate(a.out, manifest, a.workers)

    ev = a.out / "eval_results.json"
    subprocess.run([str(PY), str(REPO / "batch_eval.py"), str(a.out),
                    "--benchmark", str(BENCH),
                    "--target-delay", *[str(t) for t in a.targets],
                    "--workers", str(a.workers), "-o", str(ev)],
                   cwd=str(REPO), check=False)
    print(f"\nwrote {ev}")


if __name__ == "__main__":
    main()

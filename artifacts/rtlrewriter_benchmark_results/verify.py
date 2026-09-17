#!/usr/bin/env python3
"""Standalone re-verifier for the CEC evidence package.

Walks ``designs/<run>/<case>/<language>/`` and, for each design, re-runs the
*same* equivalence check on the bundled ``starting_point.*`` (reference) vs
``best.*`` (optimized) and compares the result to the verdict recorded in
``INFO.json``. Needs only ``yosys`` and (for the multiplier cases) ``verilator``
on ``PATH`` — no repository checkout required.

  python verify.py                 # verify everything
  python verify.py --only case3    # just the case3 folders
  python verify.py --sim-vectors 100000   # faster simulation pass for case2/12

Exits non-zero if any design fails to reproduce its recorded verdict.
"""

import argparse
import concurrent.futures
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

PKG = Path(__file__).resolve().parent

# The check engine sits next to this script (cec_one / sim_equiv). It's bundled
# as `cec_engine.py` in the published package; in the source repo it's
# `cec_rtl_rewriter.py` — accept either.
_engine = next((PKG / n for n in ("cec_engine.py", "cec_rtl_rewriter.py")
                if (PKG / n).exists()), None)
if _engine is None:
    sys.exit("check engine (cec_engine.py) must sit next to verify.py")
_spec = importlib.util.spec_from_file_location("cec_engine", _engine)
cec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cec)

_PASS = {"EQUIVALENT", "IDENTITY"}
_MARK = {"EQUIVALENT": "✅", "IDENTITY": "✅", "NOT_EQUIVALENT": "❌",
         "INCONCLUSIVE": "⚠️", "ERROR": "🛑"}


def _check(folder: Path, info: Dict[str, Any], yosys: str, verilator: str,
           sim_vectors: int) -> Dict[str, Any]:
    files = info.get("files", {})
    gold = folder / files.get("starting_point", "")
    gate = folder / files.get("best_netlist", "")
    top = info.get("top_module")
    seq = info.get("type") == "sequential"
    method = info.get("cec_method") or ""
    if not gold.exists() or not gate.exists():
        return {"status": "ERROR", "detail": "missing starting_point/best file"}
    if "sim" in method:
        return cec.sim_equiv(yosys, verilator, gold, gate, top, sim_vectors)
    # A gate-only reset port (Spire-emitted rst) is tied to its inactive level
    # before checking, mirroring the campaign pipeline's _prepare_row.
    if hasattr(cec, "_tie_gate_only_reset"):
        gate, note = cec._tie_gate_only_reset(gold, gate, top)
    rp, ra = cec._reset_port(gold) if seq else (None, 1)
    res = cec.cec_one(yosys, gold, gate, top, seq, rp, ra)
    if hasattr(cec, "_tie_gate_only_reset") and note:
        res["detail"] = (res.get("detail", "") + " · " + note).strip(" ·")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=PKG,
                    help="package root containing designs/ (default: next to this script)")
    ap.add_argument("--only", default=None,
                    help="substring filter on '<run>/<case>/<language>'")
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--verilator", default="verilator")
    ap.add_argument("--sim-vectors", type=int, default=1_000_000)
    ap.add_argument("--workers", type=int, default=8,
                    help="designs to check concurrently")
    args = ap.parse_args()

    infos = sorted((args.root / "designs").rglob("INFO.json"),
                   key=lambda p: str(p.parent))
    if not infos:
        sys.exit(f"no designs/**/INFO.json under {args.root}")

    jobs = []
    for ip in infos:
        rel = ip.parent.relative_to(args.root / "designs").as_posix()
        if args.only and args.only not in rel:
            continue
        jobs.append((rel, ip))

    def work(job):
        rel, ip = job
        info = json.loads(ip.read_text())
        recorded = info.get("cec_status")
        res = _check(ip.parent, info, args.yosys, args.verilator, args.sim_vectors)
        repro = res.get("status")
        match = (recorded in _PASS and repro in _PASS) or (recorded == repro)
        return (rel, recorded, repro, match, res.get("detail", ""))

    print(f"{'design':52s} {'recorded':16s} {'reproduced':16s} match")
    print("-" * 96)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        for r in ex.map(work, jobs):
            rows.append(r)
            print(f"{r[0]:52s} {str(r[1]):16s} {_MARK.get(r[2],'')} {str(r[2]):14s} "
                  f"{'OK' if r[3] else 'MISMATCH'}")
    rows.sort(key=lambda r: r[0])

    n = len(rows)
    ok = sum(1 for r in rows if r[3])
    real_equiv = sum(1 for r in rows if r[2] in _PASS)
    print("-" * 96)
    print(f"{ok}/{n} reproduce the recorded verdict; {real_equiv}/{n} verify EQUIVALENT.")
    if ok != n:
        print("\nMismatches:")
        for rel, rec, rep, m, det in rows:
            if not m:
                print(f"  {rel}: recorded={rec} reproduced={rep} — {det}")
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())

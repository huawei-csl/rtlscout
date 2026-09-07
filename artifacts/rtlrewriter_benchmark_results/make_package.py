#!/usr/bin/env python3
"""Build the shipped benchmark package from a finished RTLRewriter campaign.

For every (case, language) it copies the benchmark base (starting_point.*,
tb.sv, vectors.dat), the table-backing best design named by the campaign's
cec_results.json (the exact file the CEC verdict was produced for), and writes
INFO.json in the published schema. The campaign's cec_results.{json,md} are
copied into cec_results/<label>.{json,md}.

  python make_package.py <runs_root> cells_run        # e.g. .../runs_cells
  python make_package.py <runs_root> transistor_run

Re-populates designs/<label>/ from scratch (--keep to skip the wipe). Run
verify.py afterwards; its stdout is the recheck evidence
(tee it to cec_results/recheck_<metric>.md).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent.parent
sys.path.insert(0, str(PKG))
import cec_engine as ce  # noqa: E402  (bundled check engine, shared helpers)


def _bench_root(case: str, language: str) -> Path:
    tree = "rtl_rewriter_spirehdl" if language == "spirehdl" else "rtl_rewriter"
    return REPO / "benchmarks" / tree / case


def _copy(src: Path, dst: Path) -> None:
    if not src.exists():
        raise SystemExit(f"missing source file: {src}")
    shutil.copy2(src, dst)


def package_one(row: dict, out_root: Path) -> str:
    case, lang = row["case"], row["language"]
    bench = _bench_root(case, lang)
    meta = json.loads((bench / "metadata.json").read_text())
    dst = out_root / case / lang
    dst.mkdir(parents=True, exist_ok=True)

    # Benchmark base: reference + testbench + stimuli.
    _copy(bench / "tb.sv", dst / "tb.sv")
    _copy(bench / "vectors.dat", dst / "vectors.dat")
    files = {"starting_point": "starting_point.v"}
    if lang == "spirehdl":
        _copy(bench / "context" / "design.v", dst / "starting_point.v")
        _copy(bench / "context" / "starting_point.py", dst / "starting_point.py")
        files["starting_point_source"] = "starting_point.py"
    else:
        _copy(bench / "context" / "starting_point.v", dst / "starting_point.v")
    files["tb.sv"] = "tb.sv"
    files["vectors.dat"] = "vectors.dat"

    # Best design: the exact netlist the CEC verdict was produced for. A
    # *.cec_rst_tied.v gate points back to its original sibling (the tie is
    # re-derived by the bundled engine, so the original is what ships).
    gate = Path(row["gate"])
    if gate.name.endswith(".cec_rst_tied.v"):
        gate = gate.with_name(gate.name.replace(".cec_rst_tied", ""))
    if row["status"] == "IDENTITY":
        gate = ce._reference_file(lang, f"benchmarks/{_bench_root(case, lang).parent.name}/{case}")
    if lang == "spirehdl":
        _copy(gate, dst / "best.v")
        best_meta = gate.parent / "_best_meta.json"
        src_name = (json.loads(best_meta.read_text()).get("design_file")
                    if best_meta.exists() else None)
        if src_name and (gate.parent / src_name).exists():
            _copy(gate.parent / src_name, dst / "best.py")
            files["design_source"] = "best.py"
        files["best_netlist"] = "best.v"
    else:
        _copy(gate, dst / "best.sv")
        files["best_netlist"] = "best.sv"

    value = row.get("value")
    info = {
        "case": case,
        "module": row.get("module") or case,
        "language": lang,
        "top_module": row.get("top") or meta.get("module_name"),
        "type": "sequential" if row.get("seq") else "combinational",
        "metric": row.get("metric"),
        "best_phase": row.get("phase"),
        "metric_value": int(value) if value == int(value) else value,
        "cec_status": row.get("status"),
        "cec_method": row.get("method"),
        "cec_detail": row.get("detail"),
        "files": files,
    }
    (dst / "INFO.json").write_text(json.dumps(info, indent=2) + "\n")
    return f"{case}/{lang}: {row.get('phase')} {info['metric_value']} {row.get('status')}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs_root", type=Path, help="campaign dir with summary.json + cec_results.json")
    ap.add_argument("label", choices=["cells_run", "transistor_run"])
    ap.add_argument("--keep", action="store_true", help="do not wipe designs/<label> first")
    args = ap.parse_args()

    rows = json.loads((args.runs_root / "cec_results.json").read_text())
    rows = rows if isinstance(rows, list) else rows.get("results", rows.get("entries"))
    metric = rows[0]["metric"]

    out_root = PKG / "designs" / args.label
    if out_root.exists() and not args.keep:
        shutil.rmtree(out_root)
    for row in sorted(rows, key=lambda r: (ce._case_sort_key(r["case"]), r["language"])):
        print(package_one(row, out_root))

    # The rendered table this package backs, bundled next to the designs.
    tbl = {"cells_run": "table_rtl_rewriter.tex",
           "transistor_run": "table_rtl_rewriter_transistors.tex"}[args.label]
    _copy(args.runs_root / "table.tex", out_root / tbl)

    cr = PKG / "cec_results"
    cr.mkdir(exist_ok=True)
    for ext in ("json", "md"):
        _copy(args.runs_root / f"cec_results.{ext}", cr / f"{metric}.{ext}")
    print(f"packaged {len(rows)} designs -> {out_root}; evidence -> cec_results/{metric}.{{json,md}}")


if __name__ == "__main__":
    main()

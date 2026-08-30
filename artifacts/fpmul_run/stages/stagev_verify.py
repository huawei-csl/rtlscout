"""Stage V — functional verification of Pareto-front designs.

Per design, in order:
  1. regression pre-check: the 3 known subnormal-boundary inputs vs constants
  2. exhaustive equivalence by simulation vs the golden over ALL 2^32 input
     pairs, sharded across cores (authoritative; complete for this design)

(The handover's optional step 3, a post-hoc CEC attempt, was dropped on user
decision 2026-07-27: exhaustive simulation is already complete for this
combinational design, and CEC of restructured multipliers mostly burns its
timeout to end INCONCLUSIVE.)

A design passes iff both steps pass. Failing designs are renamed to
excluded_design_NNN inside their front dir so nothing downstream picks them
up. Verdicts land in <front>/verification_results.{json,md}.

Usage: stagev_verify.py <front_dir> [--label X] [--no-exclude]
"""
import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg

GOLD_MODULE = "fp_mul_gold"

_MAIN_CPP = r"""
#include "Vharness.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

// regression table: {a, b, expected_y}
static const unsigned REGRESSION[3][3] = {
    {0x0003, 0x6801, 0x0E02},
    {0x8003, 0x6479, 0x8AB6},
    {0x7521, 0x0003, 0x1BB2},
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vharness top;
    if (argc >= 2 && !strcmp(argv[1], "--regression")) {
        int errors = 0;
        for (auto& v : REGRESSION) {
            top.a = v[0]; top.b = v[1]; top.eval();
            if (top.y_dut != v[2]) {
                printf("REGRESSION_FAIL a=%04x b=%04x dut=%04x expected=%04x\n",
                       v[0], v[1], (unsigned)top.y_dut, v[2]);
                errors++;
            }
            if (top.y_gold != v[2]) {
                printf("GOLDEN_BROKEN a=%04x b=%04x gold=%04x expected=%04x\n",
                       v[0], v[1], (unsigned)top.y_gold, v[2]);
                errors++;
            }
        }
        printf(errors ? "REGRESSION_RESULT FAIL\n" : "REGRESSION_RESULT PASS\n");
        return errors ? 1 : 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "--shard")) {
        const unsigned long shard = strtoul(argv[2], nullptr, 0);
        const unsigned long nshards = strtoul(argv[3], nullptr, 0);
        const unsigned long span = 0x10000UL / nshards;   // nshards divides 65536
        const unsigned long a_lo = shard * span, a_hi = a_lo + span;
        unsigned long mism = 0, shown = 0;
        for (unsigned long a = a_lo; a < a_hi; a++) {
            top.a = a;
            for (unsigned long b = 0; b < 0x10000UL; b++) {
                top.b = b; top.eval();
                if (top.y_dut != top.y_gold) {
                    mism++;
                    if (shown < 10) {
                        printf("MISMATCH a=%04lx b=%04lx dut=%04x gold=%04x\n",
                               a, b, (unsigned)top.y_dut, (unsigned)top.y_gold);
                        shown++;
                    }
                }
            }
        }
        printf("SHARD %lu/%lu checked=%lu mismatches=%lu %s\n", shard, nshards,
               span * 0x10000UL, mism, mism ? "FAIL" : "OK");
        return mism ? 1 : 0;
    }
    fprintf(stderr, "usage: harness --regression | --shard I N\n");
    return 2;
}
"""

_WRAPPER_SV = """
module harness(input [15:0] a, input [15:0] b,
               output [15:0] y_dut, output [15:0] y_gold);
  fp_mul_e5f10 dut (.a(a), .b(b), .y(y_dut));
  {gold_module} gold (.a(a), .b(b), .y(y_gold));
endmodule
"""


def _workspace_verilog(design_dir: Path) -> Path | None:
    """The design.v the original eval actually produced and tested — resolved
    via the front's pareto_front.json (original_workspace). The most faithful
    verification target, and the only option for scripts with undetected
    file dependencies (e.g. self-modifying design5.py-style scripts)."""
    manifest = design_dir.parent / "pareto_front.json"
    if not manifest.exists():
        return None
    for e in json.loads(manifest.read_text()):
        if e.get("extracted_file", "").split("/")[0] == design_dir.name:
            ws = Path(e.get("original_workspace", ""))
            if (ws / "design.v").exists():
                dst = design_dir / "design.v"
                shutil.copy2(ws / "design.v", dst)
                return dst
    return None


def design_verilog(design_dir: Path) -> Path:
    """Return the design's Verilog: as-extracted, from the original eval
    workspace, or by elaborating the design script."""
    v = design_dir / "design.v"
    if v.exists():
        return v
    vs = [f for f in sorted(design_dir.glob("*.v")) if not f.name.startswith("tb")]
    if vs:
        return vs[0]        # extract_sweep_pareto numbers files: design_1.v, ...
    ws_v = _workspace_verilog(design_dir)
    if ws_v is not None:
        return ws_v
    py_files = sorted(design_dir.glob("*.py"))
    if not py_files:
        raise RuntimeError(f"{design_dir}: neither design.v nor a .py design found")
    common.sh(common.py(py_files[0]), f"stagev_elab_{design_dir.name}", cwd=design_dir)
    if not v.exists():
        # spire scripts write the file named in to_verilog_file(); find any new .v
        vs = sorted(design_dir.glob("*.v"))
        if not vs:
            raise RuntimeError(f"{design_dir}: running {py_files[0].name} produced no .v")
        v = vs[0]
    return v


def build_harness(design_v: Path, work: Path) -> Path:
    """Verilate dut + module-renamed golden into one binary; return its path."""
    work.mkdir(parents=True, exist_ok=True)
    dut_text = design_v.read_text()
    if re.search(rf"\bmodule\s+{GOLD_MODULE}\b", dut_text):
        raise RuntimeError(f"{design_v} defines {GOLD_MODULE} — rename collision")
    if not re.search(rf"\bmodule\s+{cfg.TOP_MODULE}\b", dut_text):
        raise RuntimeError(f"{design_v} has no module {cfg.TOP_MODULE}")
    gold_text = cfg.GOLDEN.read_text()
    if gold_text.count("\nmodule ") + gold_text.startswith("module ") != 1:
        raise RuntimeError(f"golden {cfg.GOLDEN} is not single-module; rename unsafe")
    (work / "dut.v").write_text(dut_text)
    (work / "gold.v").write_text(
        re.sub(rf"\b{cfg.TOP_MODULE}\b", GOLD_MODULE, gold_text))
    (work / "wrapper.sv").write_text(_WRAPPER_SV.format(gold_module=GOLD_MODULE))
    (work / "main.cpp").write_text(_MAIN_CPP)
    cmd = ["verilator", "-cc", "--exe", "--build", "-j", "8", "-O3", "-Wno-fatal",
           "--top-module", "harness", "-o", "harness_bin", "--Mdir", str(work / "obj"),
           str(work / "wrapper.sv"), str(work / "dut.v"), str(work / "gold.v"),
           str(work / "main.cpp")]
    common.sh(cmd, f"stagev_build_{work.name}", cwd=work)
    return work / "obj" / "harness_bin"


def run_regression(binary: Path) -> dict:
    proc = subprocess.run([str(binary), "--regression"], capture_output=True, text=True)
    return {"passed": proc.returncode == 0, "output": proc.stdout.strip()}


def run_exhaustive(binary: Path, nshards: int = cfg.EXHAUSTIVE_SHARDS,
                   jobs: int = cfg.VERIFY_JOBS) -> dict:
    assert 0x10000 % nshards == 0, "shard count must divide 65536"
    mismatches, examples, failed_shards = 0, [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(subprocess.run, [str(binary), "--shard", str(i), str(nshards)],
                          capture_output=True, text=True): i for i in range(nshards)}
        for fut in concurrent.futures.as_completed(futs):
            proc, i = fut.result(), futs[fut]
            m = re.search(r"mismatches=(\d+)", proc.stdout)
            if m is None:
                raise RuntimeError(f"shard {i} produced no summary:\n{proc.stdout}\n{proc.stderr}")
            n = int(m.group(1))
            if n:
                mismatches += n
                failed_shards.append(i)
                examples += re.findall(r"MISMATCH .*", proc.stdout)[:10]
    return {"passed": mismatches == 0, "total_vectors": 2**32,
            "mismatches": mismatches, "failed_shards": sorted(failed_shards),
            "example_mismatches": examples[:20]}


def verify_design(design_dir: Path, work_root: Path) -> dict:
    work = work_root / design_dir.name
    entry = {"design": design_dir.name, "path": str(design_dir)}
    try:
        dv = design_verilog(design_dir)
        entry["verilog"] = str(dv)
        binary = build_harness(dv, work)
        entry["regression"] = run_regression(binary)
        entry["exhaustive"] = run_exhaustive(binary)
        entry["passed"] = entry["regression"]["passed"] and entry["exhaustive"]["passed"]
    except RuntimeError as e:
        entry["passed"] = False
        entry["error"] = str(e)
    return entry


def verify_front(front_dir: Path, label: str, exclude: bool = True) -> dict:
    front_dir = Path(front_dir)
    designs = sorted(d for d in front_dir.glob("design_*") if d.is_dir())
    if not designs:
        raise RuntimeError(f"no design_* dirs in {front_dir}")
    import time
    t0 = time.monotonic()
    work_root = cfg.VERIFY_WORK / label
    common.log(f"stage V on {front_dir} ({len(designs)} designs)")
    results = [verify_design(d, work_root) for d in designs]

    for entry in results:
        if not entry["passed"] and exclude:
            src = front_dir / entry["design"]
            dst = front_dir / f"excluded_{entry['design']}"
            if src.exists():
                shutil.move(str(src), str(dst))
            entry["excluded_to"] = str(dst)
            common.log(f"EXCLUDED {entry['design']} (see verification_results.md)")

    summary = {"front": str(front_dir), "label": label,
               "duration_s": round(time.monotonic() - t0, 1),   # for cost_report
               "total": len(results), "passed": sum(r["passed"] for r in results),
               "excluded": [r["design"] for r in results if not r["passed"]],
               "designs": results}
    (front_dir / "verification_results.json").write_text(json.dumps(summary, indent=2))
    lines = [f"# Verification — {label}", "",
             f"Golden: `{cfg.GOLDEN}` · regression pre-check + exhaustive "
             f"simulation over all 2^32 input pairs (complete for this design)",
             "",
             "| design | regression | exhaustive (mismatches) | verdict |",
             "|---|---|---|---|"]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['design']} | — | — | ERROR: {r['error']} |")
            continue
        lines.append("| {} | {} | {} ({}) | {} |".format(
            r["design"],
            "pass" if r["regression"]["passed"] else "FAIL",
            "pass" if r["exhaustive"]["passed"] else "FAIL",
            r["exhaustive"]["mismatches"],
            "OK" if r["passed"] else "**EXCLUDED**"))
    (front_dir / "verification_results.md").write_text("\n".join(lines) + "\n")
    common.record("stageV", front_dir / "verification_results.md",
                  f"{label}: {summary['passed']}/{summary['total']} passed"
                  + (f", excluded {summary['excluded']}" if summary["excluded"] else ""))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("front_dir", type=Path)
    ap.add_argument("--label", default=None)
    ap.add_argument("--no-exclude", action="store_true")
    args = ap.parse_args()
    s = verify_front(args.front_dir, args.label or args.front_dir.name,
                     exclude=not args.no_exclude)
    print(json.dumps({k: s[k] for k in ("total", "passed", "excluded")}, indent=2))
    sys.exit(0 if s["passed"] == s["total"] else 1)


if __name__ == "__main__":
    main()

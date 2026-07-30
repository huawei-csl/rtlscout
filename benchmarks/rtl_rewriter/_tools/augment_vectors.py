"""Augment every rtl_rewriter benchmark to >=VEC_TARGET stimuli, with
expected outputs produced by SIMULATING THE GOLDEN.

Maintains BOTH trees (benchmarks/rtl_rewriter and benchmarks/rtl_rewriter_spirehdl);
the per-case seed is tree-independent, so each caseN/vectors.dat pair is
byte-identical — regenerating also cross-checks that the two goldens agree.

Works off the uniform machine-generated tb.sv shape:
    rc = $sscanf(line_buf, "%d ...", in1, ..., expected_out1, ...);
    <drive/timing>            (#1 combinational | @(posedge clk) sequential)
    if (out !== expected_out || ...) begin ... total_errors++ ... end

Method per benchmark dir:
  1. parse tb.sv -> ordered input/output columns, widths, top module name
  2. generate targeted+random input rows (corner cross-samples, exhaustive
     sweeps when the total input space is small — which also gives FSM
     alphabet coverage on sequential cases — then seeded random fill)
  3. build a PRINT-TB (textual transform: sscanf reads inputs only, the
     compare block becomes a $display of inputs + ACTUAL golden outputs),
     verilate it with the tree's own golden, run on the new inputs
  4. append the emitted rows to vectors.dat under an idempotent marker
  5. VALIDATE: run the original tb.sv + golden on the augmented vectors —
     must PASS (catches any transform misalignment before it can poison
     the benchmark)

Usage: python augment_vectors.py [case-number ...]     (default: all 14)
The spirehdl golden compile runs starting_point.py with this interpreter
(override via RTLSCOUT_PYTHON), so run under an env with spire installed.
"""
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BENCH_TREES = {                          # language -> (benchmarks root, golden file)
    "verilog": (REPO / "benchmarks" / "rtl_rewriter", "context/starting_point.v"),
    "spirehdl": (REPO / "benchmarks" / "rtl_rewriter_spirehdl", "context/starting_point.py"),
}
VEC_TARGET = 10000
VEC_SEED = 20260729
VEC_MARKER = "# augmented golden-simulated vectors (rtlrewriter_run)"
PYTHON = os.environ.get("RTLSCOUT_PYTHON", sys.executable)

_VL_FLAGS = ["-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-WIDTHEXPAND",
             "-Wno-UNUSEDSIGNAL", "--Wno-EOFNEWLINE", "-Wno-BLKSEQ",
             "--timescale", "1ns/1ps"]


def _sh(cmd, cwd: Path):
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed (rc={proc.returncode}): "
                           f"{' '.join(str(c) for c in cmd)}\n"
                           + (proc.stdout + proc.stderr)[-2000:])
    return proc


def parse_tb(tb_text: str):
    m = re.search(r'\$sscanf\(line_buf,\s*"([^"]+)",\s*([^;]+)\);', tb_text)
    if not m:
        raise RuntimeError("tb.sv: no sscanf found")
    args = [a.strip() for a in m.group(2).split(",")]
    ins = [a for a in args if not a.startswith("expected_")]
    outs = [a[len("expected_"):] for a in args if a.startswith("expected_")]
    widths = {}
    for name in ins:
        dm = re.search(rf"logic\s*(?:\[(\d+):0\])?\s+{name}\s*;", tb_text)
        if not dm:
            raise RuntimeError(f"tb.sv: no decl for input {name}")
        widths[name] = int(dm.group(1)) + 1 if dm.group(1) else 1
    tm = re.search(r"^\s*(\w+)\s+dut\s*\(", tb_text, re.M)
    if not tm:
        raise RuntimeError("tb.sv: no dut instantiation")
    return ins, outs, widths, tm.group(1)


def gen_inputs(ins, widths, n_rows, seed):
    rng = random.Random(seed)
    corner = {n: sorted({0, 1, 2, (1 << w) - 1, (1 << w) - 2, 1 << (w - 1),
                         (1 << w) // 3, 0x5555555555 & ((1 << w) - 1),
                         0xAAAAAAAAAA & ((1 << w) - 1)})
              for n, w in widths.items()}
    rows = []
    total_bits = sum(widths.values())
    if total_bits <= 12:                       # exhaustive sweeps (also FSM alphabet)
        space = []
        def rec(i, acc):
            if i == len(ins):
                space.append(list(acc)); return
            for v in range(1 << widths[ins[i]]):
                acc.append(v); rec(i + 1, acc); acc.pop()
        rec(0, [])
        while len(rows) < min(n_rows // 2, 4 * len(space)):
            order = space[:] if len(rows) % 2 == 0 else rng.sample(space, len(space))
            for r in order:
                rows.append(r)
                if len(rows) >= n_rows:
                    break
    while len(rows) < n_rows:
        if rng.random() < 0.3:                 # corner cross-sample
            rows.append([rng.choice(corner[n]) for n in ins])
        else:
            rows.append([rng.getrandbits(widths[n]) for n in ins])
        if rng.random() < 0.15:                # hold-run (sequential coverage)
            for _ in range(rng.randint(1, 4)):
                if len(rows) < n_rows:
                    rows.append(list(rows[-1]))
    return rows[:n_rows]


def build_print_tb(tb_text: str, ins, outs) -> str:
    fmt_in = " ".join(["%d"] * len(ins))
    t = re.sub(r'rc = \$sscanf\(line_buf,\s*"[^"]+",\s*[^;]+\);',
               f'rc = $sscanf(line_buf, "{fmt_in}", {", ".join(ins)});', tb_text)
    t = re.sub(r"if \(rc != \d+\) continue;", f"if (rc != {len(ins)}) continue;", t)
    disp_fmt = " ".join(["%0d"] * (len(ins) + len(outs)))
    disp_args = ", ".join(ins + outs)          # ACTUAL dut outputs, original order
    t, n = re.subn(r"if \([^;]*?!==[\s\S]*?total_errors = total_errors \+ 1;\s*\n\s*end",
                   f'$display("VEC {disp_fmt}", {disp_args});', t, count=1)
    if n != 1:
        raise RuntimeError("tb.sv: compare block not found for print transform")
    return t


def golden_verilog(bench_dir: Path, tree: str, work: Path) -> Path:
    root, golden_rel = BENCH_TREES[tree]
    src = bench_dir / golden_rel
    if tree == "verilog":
        dst = work / "golden.v"
        shutil.copy2(src, dst)
        return dst
    ctx = work / "ctx"
    shutil.copytree(bench_dir / "context", ctx)
    _sh([PYTHON, ctx / "starting_point.py"], cwd=ctx)
    vs = sorted(ctx.glob("*.v"))
    if not vs:
        raise RuntimeError(f"{src}: produced no .v")
    return vs[0]


def _simulate(tb_file: Path, design: Path, vectors: Path, work: Path, tag: str) -> str:
    obj = work / f"obj_{tag}"
    cmd = ["verilator", "--binary", "--sv", "--top-module", "tb", "-o", "simv",
           "--Mdir", str(obj)] + _VL_FLAGS + [str(tb_file), str(design)]
    _sh(cmd, cwd=work)
    shutil.copy2(vectors, work / "vectors.dat")
    proc = subprocess.run([str(obj / "simv")], cwd=str(work),
                          capture_output=True, text=True, timeout=600)
    return proc.stdout


def augment_dir(bench_dir: Path, tree: str) -> str:
    vec = bench_dir / "vectors.dat"
    text = vec.read_text()
    if VEC_MARKER in text:
        return f"{bench_dir.name}/{tree}: already augmented"
    tb_text = (bench_dir / "tb.sv").read_text()
    ins, outs, widths, top = parse_tb(tb_text)
    existing = sum(1 for l in text.splitlines() if l.strip() and not l.startswith("#"))
    n_new = max(0, VEC_TARGET - existing)
    # Seed must not depend on the tree (both trees must draw identical rows so
    # the .dat pairs stay byte-identical) nor on salted hash() (not stable across runs).
    seed = VEC_SEED + zlib.crc32(bench_dir.name.encode()) % 10000
    rows = gen_inputs(ins, widths, n_new, seed)

    # Sequential designs make expected outputs depend on the FULL input
    # history — so the print-tb must process the ORIGINAL rows first (same
    # streaming context the validation/eval tb will see), then our new rows.
    orig_rows = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    orig_inputs = [" ".join(l.split()[:len(ins)]) for l in orig_rows]

    work = Path(tempfile.mkdtemp(prefix=f"aug_{bench_dir.name}_{tree}_"))
    try:
        golden = golden_verilog(bench_dir, tree, work)
        ptb = work / "print_tb.sv"
        ptb.write_text(build_print_tb(tb_text, ins, outs))
        newin = work / "new_inputs.dat"
        newin.write_text("\n".join(orig_inputs) + "\n" +
                         "\n".join(" ".join(str(v) for v in r) for r in rows) + "\n")
        out = _simulate(ptb, golden, newin, work, f"{bench_dir.parent.name}_{bench_dir.name}_gen")
        emitted = [l[4:] for l in out.splitlines() if l.startswith("VEC ")]
        if len(emitted) != len(orig_rows) + len(rows):
            raise RuntimeError(f"{bench_dir}: print-tb emitted {len(emitted)} rows "
                               f"for {len(orig_rows) + len(rows)} inputs")
        # The regenerated prefix must reproduce the shipped vectors exactly —
        # otherwise the golden and the original vectors disagree: stop.
        for i, (a, b) in enumerate(zip(emitted[: len(orig_rows)], orig_rows)):
            if [int(x) for x in a.split()] != [int(x) for x in b.split()]:
                raise RuntimeError(
                    f"{bench_dir}/{tree}: golden disagrees with shipped vectors "
                    f"at row {i + 1}: got '{a}', file has '{b}'")
        with open(vec, "a") as f:
            f.write(VEC_MARKER + "\n"
                    + "\n".join(emitted[len(orig_rows):]) + "\n")
        # validation pass: original tb + golden must PASS on the augmented file
        vwork = work / "val"
        vwork.mkdir()
        vtb = vwork / "tb.sv"
        vtb.write_text(tb_text)
        out = _simulate(vtb, golden, vec, vwork,
                        f"{bench_dir.parent.name}_{bench_dir.name}_val")
        if "PASS" not in out:
            # roll back the append — never leave a poisoned benchmark behind
            vec.write_text(text)
            raise RuntimeError(f"{bench_dir}/{tree}: golden FAILED the augmented "
                               f"tb — transform misalignment, rolled back:\n"
                               + out[-500:])
        n_app = len(emitted) - len(orig_rows)
        return (f"{bench_dir.name}/{tree}: +{n_app} rows "
                f"(total {existing + n_app}), golden validated")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def materialize_spirehdl_baselines(cases=None) -> None:
    """Compile each spirehdl starting_point.py once into context/design.v —
    the compiled-baseline CEC reference the evidence engine expects. Safe:
    core.runner skips a context design.v for non-verilog workspaces, so
    agents never see it."""
    root, _ = BENCH_TREES["spirehdl"]
    for c in (cases or range(1, 15)):
        d = root / f"case{c}"
        dst = d / "context" / "design.v"
        if not d.exists() or dst.exists():
            continue
        work = Path(tempfile.mkdtemp(prefix=f"base_{d.name}_"))
        try:
            v = golden_verilog(d, "spirehdl", work)
            shutil.copy2(v, dst)
            print(f"materialized {dst}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


def run(cases=None) -> None:
    materialize_spirehdl_baselines(cases)
    jobs = []
    for tree, (root, _g) in BENCH_TREES.items():
        for c in (cases or range(1, 15)):
            d = root / f"case{c}"
            if d.exists():
                jobs.append((d, tree))
    with ThreadPoolExecutor(max_workers=8) as ex:
        for msg in ex.map(lambda j: augment_dir(*j), jobs):
            print(msg)


if __name__ == "__main__":
    run([int(a) for a in sys.argv[1:]] or None)

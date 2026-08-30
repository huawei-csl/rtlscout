"""Stage 0 — golden reference, directed subnormal vectors, baseline eval."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import rerun_config as cfg


def generate_golden() -> None:
    """metadata.json declares context/design.v as golden but the file is not
    checked in — generate it once from starting_point.py (handover stage 0.1)."""
    if cfg.GOLDEN.exists():
        common.log(f"golden already present: {cfg.GOLDEN}")
    else:
        common.sh(common.py(cfg.STARTING_POINT), "stage0_golden", cwd=cfg.CONTEXT)
    text = cfg.GOLDEN.read_text()
    if f"module {cfg.TOP_MODULE}" not in text:
        raise RuntimeError(f"golden {cfg.GOLDEN} lacks top module {cfg.TOP_MODULE}")
    for port in ("a", "b", "y"):
        if f"[15:0] {port}" not in text:
            raise RuntimeError(f"golden {cfg.GOLDEN} lacks 16-bit port {port}")
    identical = (cfg.OLD_GOLDEN.exists()
                 and cfg.OLD_GOLDEN.read_text() == text)
    common.log(f"golden ok ({len(text)} bytes); byte-identical to old-repo golden: {identical}")
    common.save_state("golden", {"path": str(cfg.GOLDEN), "bytes": len(text),
                                 "identical_to_old_golden": identical})
    common.record("stage0", cfg.GOLDEN, "golden reference (generated from starting_point.py)")


def _directed_vector_block() -> str:
    """3 regression pairs + directed cases per DIRECTED_CLASS_COUNTS, expected
    outputs via numpy float16 (RNE ground truth). Handover stage 0.3, extended:
    both operand orders, subnormal x subnormal, products at the
    subnormal/normal boundary (the original bug class), mantissa edges,
    zero/inf specials, and broad random pairs. NaN-result cases are skipped."""
    import numpy as np

    def f16_mul(a: int, b: int) -> int | None:
        av = np.uint16(a).view(np.float16)
        bv = np.uint16(b).view(np.float16)
        y = np.float16(av * bv)
        return None if np.isnan(y) else int(y.view(np.uint16))

    rng = np.random.default_rng(cfg.DIRECTED_VECTOR_SEED)

    def sign():
        return int(rng.integers(0, 2)) << 15

    def subnormal():
        return sign() | int(rng.integers(1, 1 << 10))

    def normal(lo=1, hi=31):
        return sign() | (int(rng.integers(lo, hi)) << 10) | int(rng.integers(0, 1 << 10))

    def boundary_pair():
        # subnormal a (value m * 2^-24) x normal b with exponent chosen so the
        # product lands within a few octaves of the 2^-14 boundary
        m = int(rng.integers(1, 1 << 10))
        e_b = 24 - int(np.log2(m)) - 14 + int(rng.integers(-2, 3)) + 15  # biased
        return sign() | m, sign() | (max(1, min(30, e_b)) << 10) | int(rng.integers(0, 1 << 10))

    def special_pair():
        kind = int(rng.integers(0, 3))
        if kind == 0:                                   # +-0 x anything
            return sign(), int(rng.integers(0, 1 << 16))
        if kind == 1:                                   # +-inf x nonzero normal
            return sign() | 0x7C00, normal()
        return sign() | 0x7BFF, normal(24, 31)          # max finite x big -> overflow

    generators = {
        "subnormal_x_normal": lambda: (subnormal(), normal()),
        "normal_x_subnormal": lambda: (normal(), subnormal()),
        "subnormal_x_subnormal": lambda: (subnormal(), subnormal()),
        "boundary_product": boundary_pair,
        "mantissa_edge": lambda: (sign() | (int(rng.integers(1, 31)) << 10)
                                  | [0, 1, 0x3FF][int(rng.integers(0, 3))], normal()),
        "specials": special_pair,
        "random_normal": lambda: (normal(), normal()),
    }

    lines = [cfg.VECTOR_MARKER]
    for a, b, y in cfg.REGRESSION_VECTORS:
        got = f16_mul(a, b)
        if got != y:
            raise RuntimeError(
                f"numpy disagrees with handover regression table for "
                f"({a:#06x},{b:#06x}): numpy {got:#06x} vs table {y:#06x}")
        lines.append(f"{a} {b} {y}")
    for cls, count in cfg.DIRECTED_CLASS_COUNTS.items():
        gen, kept = generators[cls], 0
        for _ in range(count):
            a, b = gen()
            y = f16_mul(a, b)
            if y is None:
                continue
            lines.append(f"{a} {b} {y}")
            kept += 1
        common.log(f"vectors: {cls} {kept}/{count}")
    return "\n".join(lines) + "\n"


_TB_TEMPLATE = r"""`timescale 1ns/10ps
@MARKER@
// Golden-referenced directed testbench: compares the DUT against the embedded
// golden reference (fp_mul_e5f10_ref, generated from context/starting_point.py)
// over ~18.9M enumerated vectors — no stimuli file. Structure:
//   1. the 3 known subnormal-boundary regression pairs (+ golden self-checks)
//   2. every subnormal/zero a (2^11 sign+mantissa patterns) x 4096 structured b
//   3. 4096 structured a x every subnormal/zero b
//   4. 2^21 LFSR-driven broad pairs
// Structured operands: both signs x all 32 exponents x 64 mantissas
// (8 corners + 56 LFSR-derived). The retired file-driven testbench is kept at
// tb_vectors.sv (+ vectors.dat) for cross-checking; it is not compiled.
module tb;
  logic [15:0] a, b, y, y_ref;
  int errors;
  longint total;

  fp_mul_e5f10 dut (.a(a), .b(b), .y(y));
  fp_mul_e5f10_ref refm (.a(a), .b(b), .y(y_ref));

  function automatic [15:0] lfsr_next(input [15:0] s);
    lfsr_next = (s >> 1) ^ (s[0] ? 16'hB400 : 16'h0000);
  endfunction

  logic [15:0] structured [0:4095];
  localparam logic [9:0] MANT_CORNERS [0:7] =
      '{10'h000, 10'h001, 10'h002, 10'h003, 10'h3FF, 10'h3FE, 10'h2AA, 10'h155};

  task automatic check();
    #1;
    total = total + 1;
    if (y !== y_ref) begin
      if (errors < 10)
        $display("TB_ERROR a=%0d b=%0d expected_y=%0d actual_y=%0d", a, b, y_ref, y);
      errors = errors + 1;
    end
  endtask

  logic [15:0] lfsr, ra, rb;
  logic [9:0] mant;
  int idx;

  initial begin
    errors = 0; total = 0;

    lfsr = 16'hACE1;
    idx = 0;
    for (int s = 0; s < 2; s++)
      for (int e = 0; e < 32; e++)
        for (int m = 0; m < 64; m++) begin
          if (m < 8) mant = MANT_CORNERS[m];
          else begin lfsr = lfsr_next(lfsr); mant = lfsr[9:0]; end
          structured[idx] = {s[0], e[4:0], mant};
          idx = idx + 1;
        end

    a = 16'h0003; b = 16'h6801; check();
    if (y_ref !== 16'h0E02) begin errors++; $display("TB_ERROR golden self-check 1"); end
    a = 16'h8003; b = 16'h6479; check();
    if (y_ref !== 16'h8AB6) begin errors++; $display("TB_ERROR golden self-check 2"); end
    a = 16'h7521; b = 16'h0003; check();
    if (y_ref !== 16'h1BB2) begin errors++; $display("TB_ERROR golden self-check 3"); end

    for (int sa = 0; sa < 2048; sa++) begin
      a = {sa[10], 5'b00000, sa[9:0]};
      for (int i = 0; i < 4096; i++) begin b = structured[i]; check(); end
    end
    for (int i = 0; i < 4096; i++) begin
      a = structured[i];
      for (int sb = 0; sb < 2048; sb++) begin b = {sb[10], 5'b00000, sb[9:0]}; check(); end
    end
    ra = 16'h0001; rb = 16'hBEEF;
    for (int k = 0; k < (1 << 21); k++) begin
      ra = lfsr_next(ra); rb = lfsr_next(lfsr_next(rb));
      a = ra; b = rb; check();
    end

    $display("TB_SUMMARY total=%0d errors=%0d", total, errors);
    if (errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule

// ---- embedded golden reference (module renamed fp_mul_e5f10_ref) ----
@GOLDEN@"""


def install_exhaustive_tb() -> None:
    """Replace the file-driven testbench with the golden-referenced directed
    one (user decision 2026-07-27); park the old tb at tb_vectors.sv."""
    import re
    gold_text = cfg.GOLDEN.read_text()
    tb_new = (_TB_TEMPLATE
              .replace("@MARKER@", cfg.TB_MARKER)
              .replace("@GOLDEN@", re.sub(rf"\b{cfg.TOP_MODULE}\b",
                                          f"{cfg.TOP_MODULE}_ref", gold_text)))
    for tb in (cfg.BENCHMARK / "tb.sv", cfg.CONTEXT / "tb.sv"):
        if not tb.exists() or cfg.TB_MARKER in tb.read_text():
            continue
        if tb.parent == cfg.BENCHMARK and not cfg.TB_BACKUP.exists():
            cfg.TB_BACKUP.write_text(tb.read_text())
            common.record("stage0", cfg.TB_BACKUP,
                          "retired file-driven testbench (cross-check only)")
        tb.write_text(tb_new)
        common.log(f"installed exhaustive-directed tb: {tb}")
        common.record("stage0", tb, "golden-referenced directed tb (~18.9M vectors)")


def augment_vectors() -> None:
    block = _directed_vector_block()
    n = len(block.splitlines()) - 1          # minus the marker line
    # Both copies: the benchmark-root file backs the eval testbench, the
    # context copy is what agent workspaces start from.
    for vec in (cfg.BENCHMARK / "vectors.dat", cfg.CONTEXT / "vectors.dat"):
        if not vec.exists():
            continue
        if cfg.VECTOR_MARKER in vec.read_text():
            common.log(f"vectors already augmented: {vec}")
            continue
        with open(vec, "a") as f:
            f.write(block)
        common.log(f"appended {n} directed vectors to {vec}")
        common.record("stage0", vec, f"+{n} directed subnormal vectors (seed {cfg.DIRECTED_VECTOR_SEED})")


def baseline_eval() -> dict:
    """Baseline PPA of the starting point; all improvement %s reference this."""
    out_dir = cfg.STATE / "baseline_eval"
    common.sh(common.py(cfg.REPO / "run_eval.py", cfg.STARTING_POINT,
                        "--benchmark", cfg.BENCHMARK, "--language", cfg.LANGUAGE,
                        "--cost-metric", "area", "--target-delay", cfg.AGENT_TARGET_DELAY,
                        "--save-to", out_dir),
              "stage0_baseline")
    out = out_dir / "result.json"
    result = json.loads(out.read_text())
    metrics = result.get("metrics", result)
    baseline = {"area": metrics.get("area"), "delay": metrics.get("delay"),
                "passed": result.get("passed"), "raw": str(out)}
    common.save_state("baseline", baseline)
    common.record("stage0", out, f"baseline eval (area={baseline['area']}, delay={baseline['delay']})")
    common.log(f"baseline: area={baseline['area']} delay={baseline['delay']} passed={baseline['passed']}")
    if baseline["passed"] is False:
        raise RuntimeError("baseline starting point failed its own eval — eval stack broken")
    return baseline


def run() -> None:
    generate_golden()
    install_exhaustive_tb()
    augment_vectors()
    baseline_eval()
    common.mark_done("stage0")


if __name__ == "__main__":
    run()

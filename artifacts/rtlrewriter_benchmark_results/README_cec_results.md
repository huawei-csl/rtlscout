# CEC evidence — RTLRewriter best designs

Every best-per-case design behind the two RTLScout tables, packaged with the
benchmark base (`starting_point.*`) it was equivalence-checked against. The verdicts in
`cec_results/` were produced by the bundled check engine `cec_engine.py` using Yosys:

- **combinational** designs → `equiv` (`equiv_make`+`equiv_simple`+`equiv_induct`),
  or a `miter`+SAT fallback; definitive `EQUIVALENT` / `NOT_EQUIVALENT`.
- **sequential** designs (FSMs / pipelines) → reset-anchored temporal induction
  (`sat -tempinduct`) — complete unbounded proofs, incl. re-encoded FSMs.
- **case2 / case12** (32-bit multipliers, miter SAT-intractable) → 1,000,000
  random-vector simulation (Verilator), 0 mismatches.

`IDENTITY` = the table's best for that cell was the shipped baseline, so the
design *is* the reference.

`best.v` / `best.sv` is the authoritative netlist — the exact file that was
synthesised for the table count and equivalence-checked. For SpireHDL,
re-running `best.py` regenerates it via the `@flowy/@abc` passes (re-synthesising
with ABC/Flowy); `@arithmetic_optimized` designs regenerate bit-identically.

**Re-verify the whole package** with `python verify.py` (bundled; needs only
`yosys` + `verilator`) — it re-runs every check on the local files and
compares to these verdicts. See `README.md` for details.

## Layout

```
designs/<run>/<case>/<language>/
  starting_point.v       benchmark base / spec (verilog: the original RTL;
                         spirehdl: the compiled baseline) — CEC reference
  starting_point.py      SpireHDL base source (spirehdl only)
  best.sv | best.v       the optimized netlist that was measured + CEC'd
  best.py                SpireHDL optimized source (spirehdl only)
  tb.sv, vectors.dat     testbench for run_eval.py (see README_benchmarks.md)
  INFO.json              module, metric value, phase, CEC verdict
```

See **README.md** for the package description and how to re-evaluate any design with `run_eval.py`.

**Provenance:** cells from campaign `rrglm_20260813_130031` (runs_cells), transistors from `rrglm_20260830_221657` (runs_transistors) — GLM 5.2, n=3 repetitions x 30 steps, table-backing bests after the campaign's post-CEC exclusions (see the run's EXCLUSIONS.md). Package rebuilt 2026-09-07 by make_package.py.

## cells_run

| Case | Module | Lang | Phase | Metric | Value | CEC |
|:---|:---|:---|:---|:---|---:|:---|
| case1 | `add3` | verilog | phase1 | cells | 10 | ✅ EQUIVALENT |
| case1 | `add3` | spirehdl | phase1 | cells | 10 | ✅ EQUIVALENT |
| case2 | `commutativity_subexpression` | verilog | phase2 | cells | 11262 | ✅ EQUIVALENT |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | cells | 8499 | ✅ EQUIVALENT |
| case3 | `multi_constant_multiplication` | verilog | phase2 | cells | 653 | ✅ EQUIVALENT |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | cells | 426 | ✅ EQUIVALENT |
| case4 | `multi_constant_multiplication2` | verilog | phase1 | cells | 823 | ✅ EQUIVALENT |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | cells | 556 | ✅ EQUIVALENT |
| case5 | `adder_bit_width` | verilog | phase2 | cells | 23 | ✅ EQUIVALENT |
| case5 | `adder_bit_width` | spirehdl | phase1 | cells | 37 | ✅ EQUIVALENT |
| case6 | `adder_subexpression` | verilog | phase1 | cells | 115 | ✅ EQUIVALENT |
| case6 | `adder_subexpression` | spirehdl | phase2 | cells | 114 | ✅ EQUIVALENT |
| case7 | `alu_subexpression` | verilog | phase2 | cells | 255 | ✅ EQUIVALENT |
| case7 | `alu_subexpression` | spirehdl | phase2 | cells | 240 | ✅ EQUIVALENT |
| case8 | `multiplier_bitwidth` | verilog | phase1 | cells | 370 | ✅ EQUIVALENT |
| case8 | `multiplier_bitwidth` | spirehdl | phase2 | cells | 337 | ✅ EQUIVALENT |
| case9 | `example1` | verilog | phase2 | cells | 39 | ✅ EQUIVALENT |
| case9 | `example1` | spirehdl | phase2 | cells | 15 | ✅ EQUIVALENT |
| case10 | `example3` | verilog | phase2 | cells | 36 | ✅ EQUIVALENT |
| case10 | `example3` | spirehdl | phase2 | cells | 6 | ✅ EQUIVALENT |
| case11 | `mux_dead_code` | verilog | phase1 | cells | 24 | ✅ EQUIVALENT |
| case11 | `mux_dead_code` | spirehdl | phase1 | cells | 24 | ✅ EQUIVALENT |
| case12 | `communtativity_subpexpression2` | verilog | phase1 | cells | 14454 | ✅ EQUIVALENT |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | cells | 10861 | ✅ EQUIVALENT |
| case13 | `mux_type3` | verilog | phase1 | cells | 1 | ✅ EQUIVALENT |
| case13 | `mux_type3` | spirehdl | phase1 | cells | 1 | ✅ EQUIVALENT |
| case14 | `mux_type4` | verilog | phase1 | cells | 2 | ✅ EQUIVALENT |
| case14 | `mux_type4` | spirehdl | phase1 | cells | 2 | ✅ EQUIVALENT |

## transistor_run

| Case | Module | Lang | Phase | Metric | Value | CEC |
|:---|:---|:---|:---|:---|---:|:---|
| case1 | `add3` | verilog | phase1 | transistors | 128 | ✅ EQUIVALENT |
| case1 | `add3` | spirehdl | phase1 | transistors | 96 | ✅ EQUIVALENT |
| case2 | `commutativity_subexpression` | verilog | phase1 | transistors | 75418 | ✅ EQUIVALENT |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | transistors | 60330 | ✅ EQUIVALENT |
| case3 | `multi_constant_multiplication` | verilog | phase1 | transistors | 3192 | ✅ EQUIVALENT |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | transistors | 3092 | ✅ EQUIVALENT |
| case4 | `multi_constant_multiplication2` | verilog | phase2 | transistors | 4326 | ✅ EQUIVALENT |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | transistors | 4168 | ✅ EQUIVALENT |
| case5 | `adder_bit_width` | verilog | phase2 | transistors | 256 | ✅ EQUIVALENT |
| case5 | `adder_bit_width` | spirehdl | phase2 | transistors | 262 | ✅ EQUIVALENT |
| case6 | `adder_subexpression` | verilog | phase2 | transistors | 844 | ✅ EQUIVALENT |
| case6 | `adder_subexpression` | spirehdl | phase2 | transistors | 828 | ✅ EQUIVALENT |
| case7 | `alu_subexpression` | verilog | phase1 | transistors | 1684 | ✅ EQUIVALENT |
| case7 | `alu_subexpression` | spirehdl | phase2 | transistors | 1836 | ✅ EQUIVALENT |
| case8 | `multiplier_bitwidth` | verilog | phase2 | transistors | 2462 | ✅ EQUIVALENT |
| case8 | `multiplier_bitwidth` | spirehdl | phase2 | transistors | 2392 | ✅ EQUIVALENT |
| case9 | `example1` | verilog | phase2 | transistors | 74 | ✅ EQUIVALENT |
| case9 | `example1` | spirehdl | phase2 | transistors | 74 | ✅ EQUIVALENT |
| case10 | `example3` | verilog | phase1 | transistors | 54 | ✅ EQUIVALENT |
| case10 | `example3` | spirehdl | phase1 | transistors | 26 | ✅ EQUIVALENT |
| case11 | `mux_dead_code` | verilog | phase1 | transistors | 160 | ✅ EQUIVALENT |
| case11 | `mux_dead_code` | spirehdl | phase1 | transistors | 160 | ✅ EQUIVALENT |
| case12 | `communtativity_subpexpression2` | verilog | phase2 | transistors | 97720 | ✅ EQUIVALENT |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | transistors | 77248 | ✅ EQUIVALENT |
| case13 | `mux_type3` | verilog | phase1 | transistors | 6 | ✅ EQUIVALENT |
| case13 | `mux_type3` | spirehdl | phase1 | transistors | 6 | ✅ EQUIVALENT |
| case14 | `mux_type4` | verilog | phase1 | transistors | 24 | ✅ EQUIVALENT |
| case14 | `mux_type4` | spirehdl | phase1 | transistors | 24 | ✅ EQUIVALENT |

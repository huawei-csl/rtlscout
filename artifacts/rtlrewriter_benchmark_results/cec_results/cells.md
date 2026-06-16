## CEC results — Cells table (table_rtl_rewriter.tex) (metric: cells)

| Case | Module | Lang | Best phase | cells | Type | CEC result | Method · detail |
|:---|:---|:---|:---|---:|:---:|:---|:---|
| case1 | `add3` | verilog | phase1 | 10 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case1 | `add3` | spirehdl | phase1 | 10 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case2 | `commutativity_subexpression` | verilog | phase1 | 11272 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | 8702 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case3 | `multi_constant_multiplication` | verilog | phase2 | 655 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | 438 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case4 | `multi_constant_multiplication2` | verilog | phase2 | 827 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | 558 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case5 | `adder_bit_width` | verilog | phase2 | 37 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case5 | `adder_bit_width` | spirehdl | phase1 | 37 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case6 | `adder_subexpression` | verilog | phase2 | 128 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 10 $equiv cells proven |
| case6 | `adder_subexpression` | spirehdl | phase2 | 117 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 10 $equiv cells proven |
| case7 | `alu_subexpression` | verilog | phase2 | 272 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case7 | `alu_subexpression` | spirehdl | phase2 | 249 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case8 | `multiplier_bitwidth` | verilog | phase1 | 370 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 16 $equiv cells proven |
| case8 | `multiplier_bitwidth` | spirehdl | phase1 | 343 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 16 $equiv cells proven |
| case9 | `example1` | verilog | phase1 | 40 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 7 $equiv cells proven |
| case9 | `example1` | spirehdl | phase1 | 25 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case10 | `example3` | verilog | phase1 | 6 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case10 | `example3` | spirehdl | phase2 | 10 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case11 | `mux_dead_code` | verilog | phase1 | 24 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 8 $equiv cells proven |
| case11 | `mux_dead_code` | spirehdl | phase1 | 24 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 24 $equiv cells proven |
| case12 | `communtativity_subpexpression2` | verilog | phase1 | 14448 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | 11032 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case13 | `mux_type3` | verilog | phase1 | 1 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case13 | `mux_type3` | spirehdl | phase1 | 1 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case14 | `mux_type4` | verilog | phase1 | 2 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case14 | `mux_type4` | spirehdl | phase1 | 2 | comb | ✅ EQUIVALENT | `miter+SAT` · miter+SAT UNSAT — no input distinguishes the designs |

**Summary:** EQUIVALENT: 28  (total 28)


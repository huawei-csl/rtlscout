## CEC results — Transistors v2 table (table_rtl_rewriter_transistors_v2.tex) (metric: transistors)

| Case | Module | Lang | Best phase | transistors | Type | CEC result | Method · detail |
|:---|:---|:---|:---|---:|:---:|:---|:---|
| case1 | `add3` | verilog | phase1 | 128 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case1 | `add3` | spirehdl | phase1 | 128 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case2 | `commutativity_subexpression` | verilog | phase1 | 84386 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | 68690 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case3 | `multi_constant_multiplication` | verilog | phase2 | 3782 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | 3564 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case4 | `multi_constant_multiplication2` | verilog | phase2 | 4648 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | 4642 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case5 | `adder_bit_width` | verilog | phase1 | 290 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case5 | `adder_bit_width` | spirehdl | phase2 | 290 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case6 | `adder_subexpression` | verilog | phase2 | 908 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 10 $equiv cells proven |
| case6 | `adder_subexpression` | spirehdl | phase2 | 936 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 10 $equiv cells proven |
| case7 | `alu_subexpression` | verilog | phase1 | 2072 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case7 | `alu_subexpression` | spirehdl | phase2 | 1892 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case8 | `multiplier_bitwidth` | verilog | phase1 | 2880 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 16 $equiv cells proven |
| case8 | `multiplier_bitwidth` | spirehdl | phase2 | 2696 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 16 $equiv cells proven |
| case9 | `example1` | verilog | base | 196 | seq | ✅ IDENTITY | best = shipped baseline (identical to the reference) |
| case9 | `example1` | spirehdl | phase2 | 124 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case10 | `example3` | verilog | phase2 | 38 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case10 | `example3` | spirehdl | phase1 | 26 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case11 | `mux_dead_code` | verilog | phase1 | 178 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 8 $equiv cells proven |
| case11 | `mux_dead_code` | spirehdl | phase2 | 178 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 8 $equiv cells proven |
| case12 | `communtativity_subpexpression2` | verilog | phase2 | 108390 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | 88282 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case13 | `mux_type3` | verilog | phase1 | 6 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case13 | `mux_type3` | spirehdl | phase1 | 6 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case14 | `mux_type4` | verilog | phase1 | 24 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case14 | `mux_type4` | spirehdl | phase1 | 24 | comb | ✅ EQUIVALENT | `miter+SAT` · miter+SAT UNSAT — no input distinguishes the designs |

**Summary:** EQUIVALENT: 27, IDENTITY: 1  (total 28)


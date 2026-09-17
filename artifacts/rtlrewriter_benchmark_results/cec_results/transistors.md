## CEC results — runs_transistors (metric: transistors)

| Case | Module | Lang | Best phase | transistors | Type | CEC result | Method · detail |
|:---|:---|:---|:---|---:|:---:|:---|:---|
| case1 | `add3` | verilog | phase1 | 128 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case1 | `add3` | spirehdl | phase1 | 96 | seq | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven · gate-only reset `rst' tied to 1'b0 for CEC |
| case2 | `commutativity_subexpression` | verilog | phase1 | 75418 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | 60330 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case3 | `multi_constant_multiplication` | verilog | phase1 | 3192 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | 3092 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case4 | `multi_constant_multiplication2` | verilog | phase2 | 4326 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | 4168 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 96 $equiv cells proven |
| case5 | `adder_bit_width` | verilog | phase2 | 256 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case5 | `adder_bit_width` | spirehdl | phase2 | 262 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case6 | `adder_subexpression` | verilog | phase2 | 844 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 10 $equiv cells proven |
| case6 | `adder_subexpression` | spirehdl | phase2 | 828 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 10 $equiv cells proven |
| case7 | `alu_subexpression` | verilog | phase1 | 1684 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 9 $equiv cells proven |
| case7 | `alu_subexpression` | spirehdl | phase2 | 1836 | comb | ✅ EQUIVALENT | `miter+SAT` · miter+SAT UNSAT — no input distinguishes the designs |
| case8 | `multiplier_bitwidth` | verilog | phase2 | 2462 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 16 $equiv cells proven |
| case8 | `multiplier_bitwidth` | spirehdl | phase2 | 2392 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 16 $equiv cells proven |
| case9 | `example1` | verilog | phase2 | 74 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case9 | `example1` | spirehdl | phase2 | 74 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case10 | `example3` | verilog | phase1 | 54 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case10 | `example3` | spirehdl | phase1 | 26 | seq | ✅ EQUIVALENT | `tempinduct` · reset-anchored temporal induction — complete proof |
| case11 | `mux_dead_code` | verilog | phase1 | 160 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 8 $equiv cells proven |
| case11 | `mux_dead_code` | spirehdl | phase1 | 160 | comb | ✅ EQUIVALENT | `miter+SAT` · miter+SAT UNSAT — no input distinguishes the designs |
| case12 | `communtativity_subpexpression2` | verilog | phase2 | 97720 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | 77248 | comb | ✅ EQUIVALENT | `sim-1M` · 1,000,000 random vectors, 0 mismatches (simulation; formal CEC intractable — 32-bit multipliers) |
| case13 | `mux_type3` | verilog | phase1 | 6 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case13 | `mux_type3` | spirehdl | phase1 | 6 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case14 | `mux_type4` | verilog | phase1 | 24 | comb | ✅ EQUIVALENT | `equiv_induct` · equiv flow: all 1 $equiv cells proven |
| case14 | `mux_type4` | spirehdl | phase1 | 24 | comb | ✅ EQUIVALENT | `miter+SAT` · miter+SAT UNSAT — no input distinguishes the designs |

**Summary:** EQUIVALENT: 28  (total 28)


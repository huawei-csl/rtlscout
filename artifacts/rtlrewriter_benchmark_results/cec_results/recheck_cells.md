## Number re-check — Cells table (table_rtl_rewriter.tex) (metric: cells)

Re-measured with `core.cost.make_cost_metric` (the eval's own `synth; clean -purge; stat` pipeline) on each best-design netlist.

| Case | Module | Lang | Phase | Table cells | Re-measured | Match |
|:---|:---|:---|:---|---:|---:|:---:|
| case1 | `add3` | verilog | phase1 | 10 | 10 | ✅ |
| case1 | `add3` | spirehdl | phase1 | 10 | 10 | ✅ |
| case2 | `commutativity_subexpression` | verilog | phase1 | 11272 | 11272 | ✅ |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | 8702 | 8702 | ✅ |
| case3 | `multi_constant_multiplication` | verilog | phase2 | 655 | 655 | ✅ |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | 438 | 438 | ✅ |
| case4 | `multi_constant_multiplication2` | verilog | phase2 | 827 | 827 | ✅ |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | 558 | 558 | ✅ |
| case5 | `adder_bit_width` | verilog | phase2 | 37 | 37 | ✅ |
| case5 | `adder_bit_width` | spirehdl | phase1 | 37 | 37 | ✅ |
| case6 | `adder_subexpression` | verilog | phase2 | 128 | 128 | ✅ |
| case6 | `adder_subexpression` | spirehdl | phase2 | 117 | 117 | ✅ |
| case7 | `alu_subexpression` | verilog | phase2 | 272 | 272 | ✅ |
| case7 | `alu_subexpression` | spirehdl | phase2 | 249 | 249 | ✅ |
| case8 | `multiplier_bitwidth` | verilog | phase1 | 370 | 370 | ✅ |
| case8 | `multiplier_bitwidth` | spirehdl | phase1 | 343 | 343 | ✅ |
| case9 | `example1` | verilog | phase1 | 40 | 40 | ✅ |
| case9 | `example1` | spirehdl | phase1 | 25 | 25 | ✅ |
| case10 | `example3` | verilog | phase1 | 6 | 6 | ✅ |
| case10 | `example3` | spirehdl | phase2 | 10 | 10 | ✅ |
| case11 | `mux_dead_code` | verilog | phase1 | 24 | 24 | ✅ |
| case11 | `mux_dead_code` | spirehdl | phase1 | 24 | 24 | ✅ |
| case12 | `communtativity_subpexpression2` | verilog | phase1 | 14448 | 14448 | ✅ |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | 11032 | 11032 | ✅ |
| case13 | `mux_type3` | verilog | phase1 | 1 | 1 | ✅ |
| case13 | `mux_type3` | spirehdl | phase1 | 1 | 1 | ✅ |
| case14 | `mux_type4` | verilog | phase1 | 2 | 2 | ✅ |
| case14 | `mux_type4` | spirehdl | phase1 | 2 | 2 | ✅ |

**28/28 reported values reproduce exactly.**


## Number re-check — Transistors v2 table (table_rtl_rewriter_transistors_v2.tex) (metric: transistors)

Re-measured with `core.cost.make_cost_metric` (the eval's own `synth; clean -purge; stat` pipeline) on each best-design netlist.

| Case | Module | Lang | Phase | Table transistors | Re-measured | Match |
|:---|:---|:---|:---|---:|---:|:---:|
| case1 | `add3` | verilog | phase1 | 128 | 128 | ✅ |
| case1 | `add3` | spirehdl | phase1 | 128 | 128 | ✅ |
| case2 | `commutativity_subexpression` | verilog | phase1 | 84386 | 84386 | ✅ |
| case2 | `commutativity_subexpression` | spirehdl | phase2 | 68690 | 68690 | ✅ |
| case3 | `multi_constant_multiplication` | verilog | phase2 | 3782 | 3782 | ✅ |
| case3 | `multi_constant_multiplication` | spirehdl | phase2 | 3564 | 3564 | ✅ |
| case4 | `multi_constant_multiplication2` | verilog | phase2 | 4648 | 4648 | ✅ |
| case4 | `multi_constant_multiplication2` | spirehdl | phase2 | 4642 | 4642 | ✅ |
| case5 | `adder_bit_width` | verilog | phase1 | 290 | 290 | ✅ |
| case5 | `adder_bit_width` | spirehdl | phase2 | 290 | 290 | ✅ |
| case6 | `adder_subexpression` | verilog | phase2 | 908 | 908 | ✅ |
| case6 | `adder_subexpression` | spirehdl | phase2 | 936 | 936 | ✅ |
| case7 | `alu_subexpression` | verilog | phase1 | 2072 | 2072 | ✅ |
| case7 | `alu_subexpression` | spirehdl | phase2 | 1892 | 1892 | ✅ |
| case8 | `multiplier_bitwidth` | verilog | phase1 | 2880 | 2880 | ✅ |
| case8 | `multiplier_bitwidth` | spirehdl | phase2 | 2696 | 2696 | ✅ |
| case9 | `example1` | verilog | base | 196 | 196 | ✅ |
| case9 | `example1` | spirehdl | phase2 | 124 | 124 | ✅ |
| case10 | `example3` | verilog | phase2 | 38 | 38 | ✅ |
| case10 | `example3` | spirehdl | phase1 | 26 | 26 | ✅ |
| case11 | `mux_dead_code` | verilog | phase1 | 178 | 178 | ✅ |
| case11 | `mux_dead_code` | spirehdl | phase2 | 178 | 178 | ✅ |
| case12 | `communtativity_subpexpression2` | verilog | phase2 | 108390 | 108390 | ✅ |
| case12 | `communtativity_subpexpression2` | spirehdl | phase2 | 88282 | 88282 | ✅ |
| case13 | `mux_type3` | verilog | phase1 | 6 | 6 | ✅ |
| case13 | `mux_type3` | spirehdl | phase1 | 6 | 6 | ✅ |
| case14 | `mux_type4` | verilog | phase1 | 24 | 24 | ✅ |
| case14 | `mux_type4` | spirehdl | phase1 | 24 | 24 | ✅ |

**28/28 reported values reproduce exactly.**


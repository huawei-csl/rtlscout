"""SpireHDL starting point for case11 — `example` (mux_dead_code).

Mirrors the golden's nested `if (x) ... else if (x) ...` structure with the
unreachable inner else branch. The adder/subtractor/alu submodules are
expressed inline (and are dead under the always-false `if (x)` inside the
outer `else`); yosys synth prunes them in both flows. Only the
`and_bitwise` and `or_bitwise` operands actually reach the output.

Notable detail: we write the nested mux as a single pure expression rather than
storing the inner mux results in named Wire intermediates. The post-construction
``apply_simplify`` pass (analogous to yosys's ``opt_muxtree`` / ``opt_expr``)
treats user-named Wires as opaque boundaries but transparently sees through
auto-shared wires, so writing the design as one expression lets the pass apply
guard substitution: ``mux(x, mux(x|sel, and, or), mux(x, sum+diff+alu, or))``
reduces to ``mux(x, and, or)`` because the outer ``x`` guard collapses both
inner muxes' guards through constant propagation in a second iteration.
"""
from spirehdl.spirehdl import UInt, Wire, mux
from spirehdl.spirehdl_module import Module

m = Module("example", with_clock=False, with_reset=False)
x      = m.input(UInt(1), "x")
sel    = m.input(UInt(1), "sel")
a      = m.input(UInt(8), "a")
b      = m.input(UInt(8), "b")
result = m.output(UInt(8), "result")

and_result = Wire(UInt(8), name="and_result");  and_result  <<= a & b
or_result  = Wire(UInt(8), name="or_result");   or_result   <<= a | b
sum_result = Wire(UInt(8), name="sum_result");  sum_result  <<= a + b
diff_result = Wire(UInt(8), name="diff_result"); diff_result <<= a - b
alu_result = Wire(UInt(8), name="alu_result");  alu_result  <<= a + b + (a - b)

# Golden:
#   if (x)
#       if (x | sel) result = and_result;  // x is 1 here, so always true
#       else         result = or_result;   // unreachable
#   else
#       if (x) ... else result = or_result;  // outer else ⇒ x=0, inner if(x) dead
#
# Written as a single nested mux so apply_simplify can see the structure and
# substitute guards across the two layers (no user-named Wire barriers).
result <<= mux(x,
               mux(x | sel, and_result, or_result),
               mux(x, sum_result + diff_result + alu_result, or_result))

m.to_verilog_file("design.v")

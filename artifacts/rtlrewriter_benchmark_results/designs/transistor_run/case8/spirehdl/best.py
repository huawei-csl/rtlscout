"""SpireHDL optimized — stacked abc + arithmetic."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, mux
from spirehdl.optimize import arithmetic_optimized, abc_optimized

@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 10; &put")
@arithmetic_optimized(objective="area")
def opt_mult(a, b):
    return a * b

m = Module("inefficient_multiplier", with_clock=False, with_reset=False)
multiplicandA = m.input(UInt(8), "multiplicandA")
multiplierB   = m.input(UInt(8), "multiplierB")
multiplicandC = m.input(UInt(8), "multiplicandC")
multiplierD   = m.input(UInt(8), "multiplierD")
sel           = m.input(UInt(1), "sel")
product       = m.output(UInt(16), "product")

op1 = mux(sel, multiplicandA, multiplicandC)
op2 = mux(sel, multiplierB, multiplierD)
product <<= opt_mult(op1, op2)

m.to_verilog_file("design.v")

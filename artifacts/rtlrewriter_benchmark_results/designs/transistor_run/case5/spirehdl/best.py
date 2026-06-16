from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.optimize import arithmetic_optimized

@arithmetic_optimized(objective="area")
def opt_add(a, b):
    return a + b

m = Module("example", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
sum_out = m.output(UInt(9), "sum")

sum_out <<= opt_add(a, b)

m.to_verilog_file("design.v")

"""Use @arithmetic_optimized to detect 4-input add chain."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.optimize import arithmetic_optimized

@arithmetic_optimized(objective="area")
def add4(a, b, c, d):
    return a + b + c + d

m = Module("example", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
c = m.input(UInt(8), "c")
d = m.input(UInt(8), "d")
sum_out = m.output(UInt(10), "sum")

sum_out <<= add4(a, b, c, d)

m.to_verilog_file("design.v")

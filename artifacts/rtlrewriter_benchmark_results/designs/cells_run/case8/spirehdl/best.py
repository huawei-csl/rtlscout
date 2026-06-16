"""Optimized: use arithmetic_optimized for the 8x8 multiplier."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, mux
from spirehdl.optimize import arithmetic_optimized

@arithmetic_optimized(objective="area")
def mul8(a, b):
    return a * b

m = Module("inefficient_multiplier", with_clock=False, with_reset=False)
A = m.input(UInt(8), "multiplicandA")
B = m.input(UInt(8), "multiplierB")
C = m.input(UInt(8), "multiplicandC")
D = m.input(UInt(8), "multiplierD")
sel = m.input(UInt(1), "sel")
product = m.output(UInt(16), "product")

a = mux(sel, A, C)
b = mux(sel, B, D)
product <<= mul8(a, b)

m.to_verilog_file("design.v")

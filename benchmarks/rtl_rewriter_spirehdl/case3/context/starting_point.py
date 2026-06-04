"""SpireHDL starting point for case3 — `example` (three const-mul over 32-bit x).

Mirrors the golden: `y = 9*x`, `z = 23*x`, `w = 81*x`. All outputs are 32-bit.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt

m = Module("example", with_clock=False, with_reset=False)
x = m.input(UInt(32), "x")
y = m.output(UInt(32), "y")
z = m.output(UInt(32), "z")
w = m.output(UInt(32), "w")

y <<= 9 * x
z <<= 23 * x
w <<= 81 * x

m.to_verilog_file("design.v")

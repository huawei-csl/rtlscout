from spirehdl.spirehdl import UInt, mux
from spirehdl.spirehdl_module import Module

m = Module("example", with_clock=False, with_reset=False)
x      = m.input(UInt(1), "x")
sel    = m.input(UInt(1), "sel")
a      = m.input(UInt(8), "a")
b      = m.input(UInt(8), "b")
result = m.output(UInt(8), "result")

result <<= mux(x, a & b, a | b)

m.to_verilog_file("design.v")

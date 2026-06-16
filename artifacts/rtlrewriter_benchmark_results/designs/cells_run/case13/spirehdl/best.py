from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt

m = Module("mux_tree", with_clock=False, with_reset=False)
sel = m.input(UInt(1), "sel")
a = m.input(UInt(1), "a")
y = m.output(UInt(1), "y")

y <<= sel | a

m.to_verilog_file("design.v")

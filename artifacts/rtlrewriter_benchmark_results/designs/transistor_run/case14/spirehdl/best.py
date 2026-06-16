"""Optimized mux_tree — redundancy elimination: 3 muxes -> 2 muxes."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, mux

m = Module("mux_tree", with_clock=False, with_reset=False)
sel = m.input(UInt(1), "sel")
a   = m.input(UInt(1), "a")
b   = m.input(UInt(1), "b")
c   = m.input(UInt(1), "c")
d   = m.input(UInt(1), "d")
y   = m.output(UInt(1), "y")

# Combine control signals: s = sel ? d : c
s = mux(sel, d, c)
# Final output: y = s ? b : a
y <<= mux(s, b, a)

m.to_verilog_file("design.v")

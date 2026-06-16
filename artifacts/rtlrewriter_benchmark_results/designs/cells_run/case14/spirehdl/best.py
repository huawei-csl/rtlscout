"""Minimal mux_tree: collapse redundancy.

Both intermediate muxes choose between a and b, so the effective control
bit is (sel ? d : c), and y = ((sel ? d : c) ? b : a).
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, mux

m = Module("mux_tree", with_clock=False, with_reset=False)
sel = m.input(UInt(1), "sel")
a   = m.input(UInt(1), "a")
b   = m.input(UInt(1), "b")
c   = m.input(UInt(1), "c")
d   = m.input(UInt(1), "d")
y   = m.output(UInt(1), "y")

ctrl = mux(sel, d, c)
y <<= mux(ctrl, b, a)

m.to_verilog_file("design.v")

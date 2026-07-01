"""SpireHDL starting point for case14 — `mux_tree` (4-input mux tree, redundant).

Golden is two modules (`mux_tree` instantiating three `mux2to1`). We emit a
single flat module with the same top name and port list; yosys `synth`
flattens the golden's hierarchy anyway, so this is equivalent.

Structure:
  x0 = mux2to1(in0=a, in1=b, sel=c)
  x1 = mux2to1(in0=a, in1=b, sel=d)
  y  = mux2to1(in0=x0, in1=x1, sel=sel)
Both intermediate muxes select from the same {a, b} pair — the redundancy
this case targets.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, mux

m = Module("mux_tree", with_clock=False, with_reset=False)
sel = m.input(UInt(1), "sel")
a   = m.input(UInt(1), "a")
b   = m.input(UInt(1), "b")
c   = m.input(UInt(1), "c")
d   = m.input(UInt(1), "d")
y   = m.output(UInt(1), "y")

x0 = Wire(UInt(1), name="x0"); x0 <<= mux(c, b, a)
x1 = Wire(UInt(1), name="x1"); x1 <<= mux(d, b, a)
y <<= mux(sel, x1, x0)

m.to_verilog_file("design.v")

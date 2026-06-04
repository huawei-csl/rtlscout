"""SpireHDL starting point for case13 — `mux_tree` (2:1 mux with in1 tied to 1).

Golden is two modules (mux_tree wraps mux2to1). We emit a single flat module
with the same top name `mux_tree` and the same port list; yosys `synth`
flattens the golden's hierarchy anyway, so this is equivalent.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, mux

m = Module("mux_tree", with_clock=False, with_reset=False)
sel = m.input(UInt(1), "sel")
a   = m.input(UInt(1), "a")
y   = m.output(UInt(1), "y")

# mux2to1(in0=a, in1=1, sel=sel) ⇒ sel ? 1 : a
y <<= mux(sel, 1, a)

m.to_verilog_file("design.v")

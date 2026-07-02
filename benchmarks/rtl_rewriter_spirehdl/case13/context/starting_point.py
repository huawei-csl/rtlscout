"""Spire starting point for case13 — `mux_tree` (2:1 mux with in1 tied to 1).

Golden is two modules (mux_tree wraps mux2to1). We emit a single flat module
with the same top name `mux_tree` and the same port list; yosys `synth`
flattens the golden's hierarchy anyway, so this is equivalent.
"""
from spire import Component, IORecord, Input, Output, UInt
from spire.expr import mux


class MuxTree(Component):
    def __init__(self):
        self.io = IORecord(
            sel=Input(UInt(1)),
            a=Input(UInt(1)),
            y=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        sel = self.io.sel
        a   = self.io.a
        y   = self.io.y

        # mux2to1(in0=a, in1=1, sel=sel) ⇒ sel ? 1 : a
        y <<= mux(sel, 1, a)


MuxTree().to_verilog_file("design.v", name="mux_tree")

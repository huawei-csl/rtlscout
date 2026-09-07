"""Spire starting point for case14 — `mux_tree` (4-input mux tree, redundant).

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
from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.expr import mux


class MuxTree(Component):
    def __init__(self):
        self.io = IORecord(
            sel=Input(UInt(1)),
            a=Input(UInt(1)),
            b=Input(UInt(1)),
            c=Input(UInt(1)),
            d=Input(UInt(1)),
            y=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        sel = self.io.sel
        a   = self.io.a
        b   = self.io.b
        c   = self.io.c
        d   = self.io.d
        y   = self.io.y

        x0 = Wire(UInt(1), name="x0"); x0 <<= mux(c, b, a)
        x1 = Wire(UInt(1), name="x1"); x1 <<= mux(d, b, a)
        y <<= mux(sel, x1, x0)


MuxTree().to_verilog_file("design.v", name="mux_tree")

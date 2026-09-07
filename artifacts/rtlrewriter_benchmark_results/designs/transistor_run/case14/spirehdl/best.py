"""Optimized mux_tree — redundancy eliminated.

Original: 3 muxes (two redundant intermediates both choosing {a,b}).
Key insight: y = mux(sel, mux(d,b,a), mux(c,b,a)) = mux(mux(sel,d,c), b, a)
This collapses to 2 muxes: one selects the effective control (c or d via sel),
the other selects the output (a or b via that control).
"""
from spire import Component, IORecord, Input, Output, UInt
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

        # Effective control: sel ? d : c
        ctrl = mux(sel, d, c)
        # Output: ctrl ? b : a
        y <<= mux(ctrl, b, a)


MuxTree().to_verilog_file("design.v", name="mux_tree")

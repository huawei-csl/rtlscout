"""mux_tree — optimized: eliminate redundant intermediate muxes.

Since both x0 = mux(c, b, a) and x1 = mux(d, b, a) select from {a, b},
mux(sel, x1, x0) = mux(sel, mux(d,b,a), mux(c,b,a)).
We collapse this to a single 2-to-1 mux selecting between a and b,
with the select being a function of sel, c, d.

Truth table (sel c d -> which intermediate -> pick a or b):
  sel=0 -> x0 = mux(c, b, a) -> a if c==0, b if c==1
  sel=1 -> x1 = mux(d, b, a) -> a if d==0, b if d==1

So:
  y = a when (sel==0 & c==0) | (sel==1 & d==0)
  y = b otherwise
  i.e. y = mux(sel ? d : c, b, a)  => y = mux(sel, d, c) selects, then mux(that, b, a)

That's just 2 muxes. But we can do even better: y = mux((sel & d) | (~sel & c), b, a)
which is 1 mux + a small AND-OR. Let's try the 2-mux form first.
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

        # Inner select: sel ? d : c
        inner_sel = mux(sel, d, c)
        # Output: mux(inner_sel, b, a)  => a if inner_sel==0, b if inner_sel==1
        y <<= mux(inner_sel, b, a)


MuxTree().to_verilog_file("design.v", name="mux_tree")

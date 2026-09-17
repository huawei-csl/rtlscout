"""Variant 15: abc_optimized area seed 15 on the multiply."""
from spire import Component, IORecord, Input, Output, UInt
from spire.expr import mux
from spire.optimize import abc_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 120 -S 15; &put")
def opt_mul(a, b):
    return a * b


class InefficientMultiplier(Component):
    def __init__(self):
        self.io = IORecord(
            multiplicandA=Input(UInt(8)),
            multiplierB=Input(UInt(8)),
            multiplicandC=Input(UInt(8)),
            multiplierD=Input(UInt(8)),
            sel=Input(UInt(1)),
            product=Output(UInt(16)),
        )
        self.elaborate()

    def elaborate(self):
        io = self.io
        multiplicand = mux(io.sel, io.multiplicandA, io.multiplicandC)
        multiplier   = mux(io.sel, io.multiplierB,   io.multiplierD)
        io.product <<= opt_mul(multiplicand, multiplier)


InefficientMultiplier().to_verilog_file("design.v", name="inefficient_multiplier")

from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.expr import mux
from spire.optimize import arithmetic_optimized, abc_optimized, ABC_RECIPES


@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@arithmetic_optimized(objective="area")
def datapath(a, b, c, d, sel):
    op1 = mux(sel, a, c)
    op2 = mux(sel, b, d)
    prod = op1 * op2
    return prod[0:16]


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
        self.io.product <<= datapath(
            self.io.multiplicandA,
            self.io.multiplierB,
            self.io.multiplicandC,
            self.io.multiplierD,
            self.io.sel,
        )


InefficientMultiplier().to_verilog_file("design.v", name="inefficient_multiplier")
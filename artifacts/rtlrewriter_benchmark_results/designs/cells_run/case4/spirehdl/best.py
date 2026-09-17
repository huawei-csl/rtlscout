"""Variant: try different abc scripts stacked on arithmetic_optimized(area).
"""
from spire import Component, IORecord, Input, Output, UInt
from spire.optimize import arithmetic_optimized, abc_optimized, ABC_RECIPES


@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@arithmetic_optimized(objective="area")
def const_mul_datapath(x):
    s = (x << 3) + x   # 9x
    y = (x << 2) + s   # 13x
    z = (x << 4) + s   # 25x
    w = (x << 6) - x   # 63x
    return y, z, w


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            x=Input(UInt(32)),
            y=Output(UInt(32)),
            z=Output(UInt(32)),
            w=Output(UInt(32)),
        )
        self.elaborate()

    def elaborate(self):
        x = self.io.x
        y, z, w = const_mul_datapath(x)
        self.io.y <<= y[0:32]
        self.io.z <<= z[0:32]
        self.io.w <<= w[0:32]


Example().to_verilog_file("design.v", name="example")
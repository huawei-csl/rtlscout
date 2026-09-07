"""Variant: arithmetic_optimized + abc_optimized area."""
from spire import Component, IORecord, Input, Output, UInt
from spire.expr import Wire
from spire.optimize import abc_optimized, arithmetic_optimized, ABC_RECIPES


@abc_optimized(abc_script=ABC_RECIPES["area"])
@arithmetic_optimized(objective="area")
def datapath(x):
    y = ((x << 3) + x)[0:32]
    z = ((x << 5) - y)[0:32]
    w = ((y << 3) + y)[0:32]
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
        y, z, w = datapath(x)
        self.io.y <<= y
        self.io.z <<= z
        self.io.w <<= w


Example().to_verilog_file("design.v", name="example")
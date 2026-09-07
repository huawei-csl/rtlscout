"""Arithmetic-optimized with balanced tree pairing (a+b)+(c+d)."""
from spire import Component, IORecord, Input, Output, UInt
from spire.optimize import arithmetic_optimized


@arithmetic_optimized(objective="area")
def chain_sum(a, b, c, d):
    return (a + b) + (c + d)


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            a=Input(UInt(8)),
            b=Input(UInt(8)),
            c=Input(UInt(8)),
            d=Input(UInt(8)),
            sum=Output(UInt(10)),
        )
        self.elaborate()

    def elaborate(self):
        self.io.sum <<= chain_sum(self.io.a, self.io.b, self.io.c, self.io.d)


Example().to_verilog_file("design.v", name="example")

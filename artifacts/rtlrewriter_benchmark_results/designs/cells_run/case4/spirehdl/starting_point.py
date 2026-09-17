"""Spire starting point for case4 — `example` (three const-mul over 32-bit x).

Mirrors the golden: `y = 13*x`, `z = 25*x`, `w = 63*x`. All outputs are 32-bit.
"""
from spire import Component, IORecord, Input, Output, UInt


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
        y = self.io.y
        z = self.io.z
        w = self.io.w

        y <<= 13 * x
        z <<= 25 * x
        w <<= 63 * x


Example().to_verilog_file("design.v", name="example")

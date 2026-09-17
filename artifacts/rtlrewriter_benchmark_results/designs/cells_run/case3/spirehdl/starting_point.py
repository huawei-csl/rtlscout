"""Spire starting point for case3 — `example` (three const-mul over 32-bit x).

Mirrors the golden: `y = 9*x`, `z = 23*x`, `w = 81*x`. All outputs are 32-bit.
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

        y <<= 9 * x
        z <<= 23 * x
        w <<= 81 * x


Example().to_verilog_file("design.v", name="example")

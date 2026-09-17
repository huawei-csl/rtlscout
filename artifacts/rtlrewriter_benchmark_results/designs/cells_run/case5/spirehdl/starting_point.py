"""Spire starting point for case5 — `example` (8-bit adder, bit-width).

Mirrors the golden: store the 9-bit sum through a 128-bit internal register
then truncate to 9 bits at the output. The 128-bit width has no functional
effect (yosys prunes the unused upper bits), but is preserved so the
starting point matches the verilog baseline's structure.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            a=Input(UInt(8)),
            b=Input(UInt(8)),
            sum=Output(UInt(9)),
        )
        self.elaborate()

    def elaborate(self):
        a   = self.io.a
        b   = self.io.b
        sum_out = self.io.sum

        internal_sum = Wire(UInt(128), name="internal_sum")
        internal_sum <<= a + b
        sum_out <<= internal_sum[0:9]


Example().to_verilog_file("design.v", name="example")

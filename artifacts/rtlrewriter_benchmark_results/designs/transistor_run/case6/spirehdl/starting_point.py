"""Spire starting point for case6 — `example` (4-input 8-bit chain sum).

Mirrors the golden one Wire per `assign <w> = <expr>;`: sum_ab (9b),
sum_abc (10b), sum_abcd (11b), and the 10-bit output `sum`.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire


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
        a = self.io.a
        b = self.io.b
        c = self.io.c
        d = self.io.d
        sum_out = self.io.sum

        sum_ab   = Wire(UInt(9),  name="sum_ab");   sum_ab   <<= a + b
        sum_abc  = Wire(UInt(10), name="sum_abc");  sum_abc  <<= sum_ab + c
        sum_abcd = Wire(UInt(11), name="sum_abcd"); sum_abcd <<= sum_abc + d

        sum_out <<= sum_abcd


Example().to_verilog_file("design.v", name="example")

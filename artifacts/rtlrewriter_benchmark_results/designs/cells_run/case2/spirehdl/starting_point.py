"""Spire starting point for case2 — `arithmetic_operations`.

Six 32-bit output expressions over eight 32-bit inputs A..H. Mirrors each
`assign resultN = <expr>;` from the golden directly on the output port; no
intermediate Wire is declared in the golden either.
"""
from spire import Component, IORecord, Input, Output, UInt


class ArithmeticOperations(Component):
    def __init__(self):
        self.io = IORecord(
            A=Input(UInt(32)),
            B=Input(UInt(32)),
            C=Input(UInt(32)),
            D=Input(UInt(32)),
            E=Input(UInt(32)),
            F=Input(UInt(32)),
            G=Input(UInt(32)),
            H=Input(UInt(32)),
            result1=Output(UInt(32)),
            result2=Output(UInt(32)),
            result3=Output(UInt(32)),
            result4=Output(UInt(32)),
            result5=Output(UInt(32)),
            result6=Output(UInt(32)),
        )
        self.elaborate()

    def elaborate(self):
        A = self.io.A
        B = self.io.B
        C = self.io.C
        D = self.io.D
        E = self.io.E
        F = self.io.F
        G = self.io.G
        H = self.io.H
        result1 = self.io.result1
        result2 = self.io.result2
        result3 = self.io.result3
        result4 = self.io.result4
        result5 = self.io.result5
        result6 = self.io.result6

        result1 <<= (A + B) + (C * D)
        result2 <<= (D * C) + (E - F)
        result3 <<= (B + G + A) + H
        result4 <<= (D * C + E) * (B + A)
        result5 <<= (C * D + B) - (F + B + A)
        result6 <<= (A + C + B) * (E - F)


ArithmeticOperations().to_verilog_file("design.v", name="arithmetic_operations")

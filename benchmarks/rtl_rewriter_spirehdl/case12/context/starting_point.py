"""Spire starting point for case12 — `example` (commutativity / sharing).

Six 32-bit output expressions over eight 32-bit inputs X..T. Mirrors each
`assign outputN = <expr>;` from the golden verbatim — no intermediate
Wire is declared in the golden, so none here either.
"""
from spire import Component, IORecord, Input, Output, UInt


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            X=Input(UInt(32)),
            Y=Input(UInt(32)),
            Z=Input(UInt(32)),
            P=Input(UInt(32)),
            Q=Input(UInt(32)),
            R=Input(UInt(32)),
            S=Input(UInt(32)),
            T=Input(UInt(32)),
            output1=Output(UInt(32)),
            output2=Output(UInt(32)),
            output3=Output(UInt(32)),
            output4=Output(UInt(32)),
            output5=Output(UInt(32)),
            output6=Output(UInt(32)),
        )
        self.elaborate()

    def elaborate(self):
        X = self.io.X
        Y = self.io.Y
        Z = self.io.Z
        P = self.io.P
        Q = self.io.Q
        R = self.io.R
        S = self.io.S
        T = self.io.T
        output1 = self.io.output1
        output2 = self.io.output2
        output3 = self.io.output3
        output4 = self.io.output4
        output5 = self.io.output5
        output6 = self.io.output6

        output1 <<= (X * Y) + (Z + P)
        output2 <<= (P + Z) * (Q - R)
        output3 <<= (Y + S + X) + T
        output4 <<= (Y * X + Q) * (P + X)
        output5 <<= (X * Y + P) - (R + P + X)
        output6 <<= (X + Y + P) * (Q - R)


Example().to_verilog_file("design.v", name="example")

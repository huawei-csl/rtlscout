"""Optimized example — CSE sharing + @arithmetic_optimized(area) for multipliers only.

The 4 multipliers dominate cost. Use @arithmetic_optimized(area) on each mul,
and @abc_optimized(area) on the add/sub helpers with seed sweep.
"""
from spire import Component, IORecord, Input, Output, UInt
from spire.expr import Wire
from spire.optimize import arithmetic_optimized, abc_optimized, ABC_RECIPES


@arithmetic_optimized(objective="area")
def opt_mul32(a, b):
    return a * b


@arithmetic_optimized(objective="area")
def opt_mac(a, b, c):
    return a * b + c


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

        xy = Wire(UInt(32))
        xy <<= opt_mul32(X, Y)

        pz = Wire(UInt(32))
        pz <<= P + Z

        qr = Wire(UInt(32))
        qr <<= Q - R

        xyadd = Wire(UInt(32))
        xyadd <<= X + Y

        self.io.output1 <<= xy + pz
        self.io.output2 <<= opt_mul32(pz, qr)
        self.io.output3 <<= xyadd + S + T
        self.io.output4 <<= opt_mul32(xy + Q, P + X)
        self.io.output5 <<= xy - R - X
        self.io.output6 <<= opt_mul32(xyadd + P, qr)


Example().to_verilog_file("design.v", name="example")

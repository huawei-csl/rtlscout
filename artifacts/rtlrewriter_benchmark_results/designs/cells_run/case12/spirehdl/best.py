"""Try @arithmetic_optimized (area) + ABC: simple resyn2 as 3rd pass after balanced+resyn2."""
from spire import Component, IORecord, Input, Output, UInt
from spire.optimize import abc_optimized, arithmetic_optimized, ABC_RECIPES


@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@abc_optimized(abc_script=ABC_RECIPES["balanced"])
@arithmetic_optimized(objective="area")
def datapath(X, Y, Z, P, Q, R, S, T):
    xy = X * Y
    pz = P + Z
    qr = Q - R
    xpy = X + Y

    o1 = xy + pz
    o2 = pz * qr
    o3 = xpy + S + T
    o4 = (xy + Q) * (P + X)
    o5 = xy - R - X
    o6 = (xpy + P) * qr

    return o1, o2, o3, o4, o5, o6


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
        o1, o2, o3, o4, o5, o6 = datapath(
            self.io.X, self.io.Y, self.io.Z, self.io.P,
            self.io.Q, self.io.R, self.io.S, self.io.T,
        )
        self.io.output1 <<= o1
        self.io.output2 <<= o2
        self.io.output3 <<= o3
        self.io.output4 <<= o4
        self.io.output5 <<= o5
        self.io.output6 <<= o6


Example().to_verilog_file("design.v", name="example")

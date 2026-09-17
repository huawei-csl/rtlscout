from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.optimize import abc_optimized, ABC_RECIPES, arithmetic_optimized


@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@abc_optimized(abc_script=ABC_RECIPES["balanced"])
@arithmetic_optimized(objective="area")
def datapath(A, B, C, D, E, F, G, H):
    CD = Wire(UInt(64))
    CD <<= C * D

    AB = Wire(UInt(33))
    AB <<= A + B

    EF = Wire(UInt(33))
    EF <<= E - F

    r1 = (AB + CD)[0:32]
    r2 = (CD + EF)[0:32]
    r3 = (AB + G + H)[0:32]
    r4 = ((CD + E) * AB)[0:32]
    r5 = (CD - (A + F))[0:32]
    r6 = ((AB + C) * EF)[0:32]
    return r1, r2, r3, r4, r5, r6


class ArithmeticOperations(Component):
    def __init__(self):
        self.io = IORecord(
            A=Input(UInt(32)), B=Input(UInt(32)), C=Input(UInt(32)), D=Input(UInt(32)),
            E=Input(UInt(32)), F=Input(UInt(32)), G=Input(UInt(32)), H=Input(UInt(32)),
            result1=Output(UInt(32)), result2=Output(UInt(32)), result3=Output(UInt(32)),
            result4=Output(UInt(32)), result5=Output(UInt(32)), result6=Output(UInt(32)),
        )
        self.elaborate()

    def elaborate(self):
        r1, r2, r3, r4, r5, r6 = datapath(
            self.io.A, self.io.B, self.io.C, self.io.D,
            self.io.E, self.io.F, self.io.G, self.io.H
        )
        self.io.result1 <<= r1
        self.io.result2 <<= r2
        self.io.result3 <<= r3
        self.io.result4 <<= r4
        self.io.result5 <<= r5
        self.io.result6 <<= r6


ArithmeticOperations().to_verilog_file("design.v", name="arithmetic_operations")

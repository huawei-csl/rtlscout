"""Spire design for case3 — `example` (three const-mul over 32-bit x).

arithmetic_optimized(area) + light abc (resyn2) on individual functions.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.optimize import arithmetic_optimized, abc_optimized


@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@arithmetic_optimized(objective="area")
def compute_y(x):
    return x + (x << 3)

@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@arithmetic_optimized(objective="area")
def compute_z(x, y9):
    return (x << 5) - y9

@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
@arithmetic_optimized(objective="area")
def compute_w(y9):
    return y9 + (y9 << 3)


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

        y9 = Wire(UInt(32))
        y9 <<= compute_y(x)

        self.io.z <<= compute_z(x, y9)
        self.io.w <<= compute_w(y9)
        self.io.y <<= y9


Example().to_verilog_file("design.v", name="example")

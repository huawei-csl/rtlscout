"""abc_optimized with resyn2 (best for adder per benchmarks)."""
from spire import Component, IORecord, Input, Output, UInt
from spire.optimize import abc_optimized, ABC_RECIPES


@abc_optimized(abc_script="strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance")
def add9(a, b):
    return a + b


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            a=Input(UInt(8)),
            b=Input(UInt(8)),
            sum=Output(UInt(9)),
        )
        self.elaborate()

    def elaborate(self):
        self.io.sum <<= add9(self.io.a, self.io.b)


Example().to_verilog_file("design.v", name="example")

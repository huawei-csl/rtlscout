"""4-operand 8-bit chain sum with explicit narrow wires + abc area."""
from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.expr import Const
from spire.optimize import abc_optimized, ABC_RECIPES


@abc_optimized(abc_script=ABC_RECIPES["area"])
def chain_sum(a, b, c, d):
    # Narrow intermediates: a+b is 9-bit, c+d is 9-bit, final is 10-bit
    ab = Wire(UInt(9))
    ab <<= a + b
    cd = Wire(UInt(9))
    cd <<= c + d
    return ab + cd


class example(Component):
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
        self.io.sum <<= chain_sum(a, b, c, d)


example().to_verilog_file("design.v", name="example")

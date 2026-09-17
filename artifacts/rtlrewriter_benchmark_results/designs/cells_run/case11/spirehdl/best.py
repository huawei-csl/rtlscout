from spire import Component, IORecord, Input, Output, UInt
from spire.expr import mux


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            x=Input(UInt(1)),
            sel=Input(UInt(1)),
            a=Input(UInt(8)),
            b=Input(UInt(8)),
            result=Output(UInt(8)),
        )
        self.elaborate()

    def elaborate(self):
        x = self.io.x
        a = self.io.a
        b = self.io.b
        # The nested if(x) ... else if(x) ... structure means:
        #   when x=1: mux(x|sel, a&b, a|b) -> a&b (x|sel always 1 when x=1)
        #   when x=0: mux(x, <dead>, a|b) -> a|b (inner if(x) dead when x=0)
        self.io.result <<= mux(x, a & b, a | b)


Example().to_verilog_file("design.v", name="example")
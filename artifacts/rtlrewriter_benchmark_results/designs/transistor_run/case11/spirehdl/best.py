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
        # x=1 → a & b; x=0 → a | b. Dead branches (add/sub/alu) never execute.
        self.io.result <<= mux(x, a & b, a | b)


Example().to_verilog_file("design.v", name="example")

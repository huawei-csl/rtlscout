from spire import Component, IORecord, Input, Output, UInt, Bool, Wire
from spire.expr import cat, Const, flat_emit


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            a=Input(UInt(8)),
            b=Input(UInt(8)),
            sum=Output(UInt(9)),
        )
        self.elaborate()

    def elaborate(self):
        a = self.io.a
        b = self.io.b

        carries = [Const(0, Bool())]
        sums = []
        for i in range(8):
            g = a[i] & b[i]
            p = a[i] ^ b[i]
            c = g | (p & carries[i])
            carries.append(c)
            sums.append(p ^ carries[i])

        self.io.sum <<= cat(cat(*sums), carries[8])


with flat_emit(True):
    Example().to_verilog_file("design.v", name="example")

"""Optimized: 2-register pipeline with reset."""
from spire import Component, IORecord, Input, Output, UInt, Register


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            **{f"in_{nm}": Input(UInt(1)) for nm in "abcdefghi"},
            sum=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        inputs = [getattr(self.io, f"in_{nm}") for nm in "abcdefghi"]

        xor_val = inputs[0]
        for inp in inputs[1:]:
            xor_val = xor_val ^ inp

        stage1 = Register(UInt(1), name="stage1", init=0)
        stage1 <<= xor_val

        stage2 = Register(UInt(1), name="stage2", init=0)
        stage2 <<= stage1

        self.io.sum <<= stage2


Example().to_verilog_file("design.v", name="example", with_clock=True, with_reset=True)

"""Spire starting point for adder_4bit — registered 4-bit adder (+ cout hash).

Mirrors the reference Verilog one-for-one. Uses `Register(typ, name=...)` for
each `reg` in the golden and `Wire(typ, name=...)` for each `assign`. The
module has no reset (only `clk`), so `with_reset=False`.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire, Register


class Adder4Bit(Component):
    def __init__(self):
        self.io = IORecord(
            a=Input(UInt(4)),
            b=Input(UInt(4)),
            cin=Input(UInt(1)),
            sum=Output(UInt(4)),
            cout=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        # alias every port so the original body is unchanged
        a = self.io.a
        b = self.io.b
        cin = self.io.cin
        sum_out = self.io.sum
        cout = self.io.cout

        # reg [3:0] sum_reg;  always @(posedge clk) sum_reg <= (b + cin) + a;
        sum_reg = Register(UInt(4), name="sum_reg")
        sum_reg <<= (b + cin) + a

        # reg cout_reg;       always @(posedge clk) cout_reg <= (cin & a[3]) | (b[3] & (cin | a[3]));
        cout_reg = Register(UInt(1), name="cout_reg")
        cout_reg <<= (cin & a[3]) | (b[3] & (cin | a[3]))

        # assign sum = sum_reg;
        # assign cout = cout_reg;
        sum_out <<= sum_reg
        cout <<= cout_reg


Adder4Bit().to_verilog_file("design.v", name="adder_4bit", with_clock=True)

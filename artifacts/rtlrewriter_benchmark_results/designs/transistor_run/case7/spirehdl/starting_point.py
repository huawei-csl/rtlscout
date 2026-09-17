"""Spire starting point for case7 — `example` (8-bit ALU with opcode mux).

Mirrors the golden's `case (opcode)` block as a nested `mux(...)` chain.
Opcode patterns are 3-bit constants compared against a 4-bit opcode port,
which — like the verilog — means any opcode with the MSB set (except the
ADDReverse pattern 3'b111 zero-extended to 4'b0111) falls through to the
default 8'b0.
"""
from spire import Component, IORecord, Input, Output, UInt
from spire.expr import mux

ADD        = 0b000
ADDReverse = 0b111
SUB        = 0b001
AND_OP     = 0b010
OR_OP      = 0b011
XOR_OP     = 0b100
NOT_OP     = 0b101
SEL_SUM    = 0b110


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            input_a=Input(UInt(8)),
            input_b=Input(UInt(8)),
            input_c=Input(UInt(8)),
            input_d=Input(UInt(8)),
            opcode=Input(UInt(4)),
            sel=Input(UInt(1)),
            result=Output(UInt(8)),
            zero_flag=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        input_a = self.io.input_a
        input_b = self.io.input_b
        input_c = self.io.input_c
        input_d = self.io.input_d
        opcode  = self.io.opcode
        sel     = self.io.sel
        result    = self.io.result
        zero_flag = self.io.zero_flag

        sum_add     = input_a + input_b + input_c + input_d          # grows past 8 bits, truncates on output.
        sum_reverse = input_d + input_c + input_b + input_a
        sel_sum_val = mux(sel, input_a + input_c, input_b + input_d)

        result <<= mux(opcode == ADD,        sum_add,
                   mux(opcode == ADDReverse, sum_reverse,
                   mux(opcode == SUB,        input_a - input_b,
                   mux(opcode == AND_OP,     input_a & input_b,
                   mux(opcode == OR_OP,      input_a | input_b,
                   mux(opcode == XOR_OP,     input_a ^ input_b,
                   mux(opcode == NOT_OP,     ~input_a,
                   mux(opcode == SEL_SUM,    sel_sum_val, 0))))))))

        zero_flag <<= (result == 0)


Example().to_verilog_file("design.v", name="example")

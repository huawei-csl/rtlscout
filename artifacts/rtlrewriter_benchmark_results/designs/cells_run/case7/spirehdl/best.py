from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.expr import mux, Const
from spire.optimize import arithmetic_optimized


@arithmetic_optimized(objective="area")
def alu_datapath(input_a, input_b, input_c, input_d, opcode, sel):
    ac = input_a + input_c
    bd = input_b + input_d
    sum_all = (ac + bd)[0:8]
    sel_sum_val = mux(sel, ac, bd)[0:8]
    sub_val = (input_a - input_b)[0:8]
    not_val = (~input_a)[0:8]
    and_val = input_a & input_b
    or_val  = input_a | input_b
    xor_val = input_a ^ input_b

    op0 = opcode[0]
    op1 = opcode[1]
    op2 = opcode[2]

    m00 = mux(op0, sub_val, sum_all)
    m01 = mux(op0, or_val, and_val)
    m10 = mux(op0, not_val, xor_val)
    m11 = mux(op0, sum_all, sel_sum_val)

    m0 = mux(op1, m01, m00)
    m1 = mux(op1, m11, m10)

    result_raw = mux(op2, m1, m0)
    result = mux(opcode[3], 0, result_raw)
    zero_flag = (result == 0)
    return result, zero_flag


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
        r, z = alu_datapath(
            self.io.input_a, self.io.input_b, self.io.input_c, self.io.input_d,
            self.io.opcode, self.io.sel
        )
        self.io.result <<= r
        self.io.zero_flag <<= z


Example().to_verilog_file("design.v", name="example", simplify=True)

from spire import Component, IORecord, Input, Output, UInt
from spire.expr import mux
from spire.optimize import abc_optimized, ABC_RECIPES

@abc_optimized(abc_script=ABC_RECIPES["area"])
def alu_logic(a, b, c, d, op0, op1, op2, op3, sel):
    ac = a + c
    bd = b + d
    sum4 = ac + bd
    sel_sum_val = mux(sel, ac, bd)
    sub = a - b

    lo   = mux(op0, sub, sum4)
    mid  = mux(op0, a | b, a & b)
    hi0  = mux(op0, ~a, a ^ b)
    hi1  = mux(op0, sum4, sel_sum_val)

    lower  = mux(op1, mid, lo)
    upper  = mux(op1, hi1, hi0)
    sel_res = mux(op2, upper, lower)
    result = mux(op3, 0, sel_res)[0:8]
    return result

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
        op = self.io.opcode
        result = alu_logic(
            self.io.input_a, self.io.input_b, self.io.input_c, self.io.input_d,
            op[0], op[1], op[2], op[3], self.io.sel
        )
        self.io.result <<= result
        self.io.zero_flag <<= (result == 0)

Example().to_verilog_file("design.v", name="example")

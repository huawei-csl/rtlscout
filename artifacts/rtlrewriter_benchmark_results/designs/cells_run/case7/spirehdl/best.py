"""Optimized 8-bit ALU - v11: stack abc + arithmetic."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, mux, Const, cat
from spirehdl.optimize import abc_optimized, arithmetic_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def alu_logic(a, b, c, d, opcode, sel):
    op = opcode[0:3]
    is_sub = (op == 0b001)
    is_sel_sum = (op == 0b110)
    zero_ac = is_sel_sum & ~sel
    zero_bd = is_sel_sum & sel
    zero8 = Const(0, UInt(8))

    op1 = mux(zero_ac, zero8, a)
    op2 = mux(is_sub, ~b, mux(zero_bd, zero8, b))
    op3 = mux(is_sub | zero_ac, zero8, c)
    op4 = mux(is_sub | zero_bd, zero8, d)
    sum_val = op1 + op2 + op3 + op4 + is_sub

    is_logic = op[2] ^ op[1]
    logic_val = mux(op[2],
                    mux(op[0], ~a, a ^ b),
                    mux(op[0], a | b, a & b))
    r = mux(is_logic, logic_val, sum_val)
    r8 = r[0:8]
    result_val = mux(opcode[3], Const(0, UInt(8)), r8)
    zero_flag = (result_val == 0)
    return cat(result_val, zero_flag)


m = Module("example", with_clock=False, with_reset=False)
a = m.input(UInt(8), "input_a")
b = m.input(UInt(8), "input_b")
c = m.input(UInt(8), "input_c")
d = m.input(UInt(8), "input_d")
opcode = m.input(UInt(4), "opcode")
sel = m.input(UInt(1), "sel")
result = m.output(UInt(8), "result")
zero_flag = m.output(UInt(1), "zero_flag")

out = alu_logic(a, b, c, d, opcode, sel)
result <<= out[0:8]
zero_flag <<= out[8]

m.to_verilog_file("design.v")

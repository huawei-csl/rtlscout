"""Try stacking abc_optimized on top of arithmetic_optimized."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Bool, Const, mux, cat
from spirehdl.optimize import abc_optimized, arithmetic_optimized

m = Module("example", with_clock=False, with_reset=False)
input_a = m.input(UInt(8), "input_a")
input_b = m.input(UInt(8), "input_b")
input_c = m.input(UInt(8), "input_c")
input_d = m.input(UInt(8), "input_d")
opcode  = m.input(UInt(4), "opcode")
sel     = m.input(UInt(1), "sel")
result    = m.output(UInt(8), "result")
zero_flag = m.output(UInt(1), "zero_flag")

@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def alu_core(input_a, input_b, input_c, input_d, opcode, sel):
    op0 = opcode[0]
    op1 = opcode[1]
    op2 = opcode[2]
    op3 = opcode[3]

    is_sub = ~op2 & ~op1 & op0
    not_b = ~input_b
    second = mux(is_sub, not_b, input_c)
    adder1 = (input_a + second + cat(is_sub))[0:8]

    sum_bd = input_b + input_d
    sum_all = (adder1 + sum_bd)[0:8]
    sel_sum = mux(sel, adder1, sum_bd)

    is_sum = ~(op0 ^ op1) & ~(op1 ^ op2)

    xor_not_input = mux(op0, Const(0xFF, UInt(8)), input_b)
    xor_not_result = input_a ^ xor_not_input

    bitwise_lo = mux(op0, input_a | input_b, input_a & input_b)

    non_sum_lo = mux(op1, bitwise_lo, adder1)
    non_sum_hi = mux(op1, sel_sum, xor_not_result)
    non_sum = mux(op2, non_sum_hi, non_sum_lo)

    inner = mux(is_sum, sum_all, non_sum)
    return mux(op3, Const(0, UInt(8)), inner)

result <<= alu_core(input_a, input_b, input_c, input_d, opcode, sel)
zero_flag <<= (result == Const(0, UInt(8)))

m.to_verilog_file("design.v")

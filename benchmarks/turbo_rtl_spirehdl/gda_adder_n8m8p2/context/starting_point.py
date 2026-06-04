"""SpireHDL starting point for GDA_St_N8_M8_P2 — approximate 8-bit adder.

Mirrors the reference Verilog one-for-one: each `and`/`or`/`xor` gate and
each `assign` becomes an explicit `w = Wire(UInt(W), name="<name>"); w <<=
<expr>` with the matching width, so yosys/abc see the same fine-grained
netlist the golden exposes.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, cat

m = Module("GDA_St_N8_M8_P2", with_clock=False, with_reset=False)
in1 = m.input(UInt(8), "in1")
in2 = m.input(UInt(8), "in2")
res = m.output(UInt(9), "res")

# and/xor gates for bits 0..6
g0 = Wire(UInt(1), name="g0"); g0 <<= in1[0] & in2[0]
g1 = Wire(UInt(1), name="g1"); g1 <<= in1[1] & in2[1]
g2 = Wire(UInt(1), name="g2"); g2 <<= in1[2] & in2[2]
g3 = Wire(UInt(1), name="g3"); g3 <<= in1[3] & in2[3]
g4 = Wire(UInt(1), name="g4"); g4 <<= in1[4] & in2[4]
g5 = Wire(UInt(1), name="g5"); g5 <<= in1[5] & in2[5]
g6 = Wire(UInt(1), name="g6"); g6 <<= in1[6] & in2[6]

p0 = Wire(UInt(1), name="p0"); p0 <<= in1[0] ^ in2[0]
p1 = Wire(UInt(1), name="p1"); p1 <<= in1[1] ^ in2[1]
p2 = Wire(UInt(1), name="p2"); p2 <<= in1[2] ^ in2[2]
p3 = Wire(UInt(1), name="p3"); p3 <<= in1[3] ^ in2[3]
p4 = Wire(UInt(1), name="p4"); p4 <<= in1[4] ^ in2[4]
p5 = Wire(UInt(1), name="p5"); p5 <<= in1[5] ^ in2[5]
p6 = Wire(UInt(1), name="p6"); p6 <<= in1[6] ^ in2[6]

# c1..c7 and carry_pred_1..6 (verbatim from the golden)
c1 = Wire(UInt(1), name="c1"); c1 <<= g0
c2 = Wire(UInt(1), name="c2"); c2 <<= g1
p1c1 = Wire(UInt(1), name="p1c1"); p1c1 <<= p1 & c1
carry_pred_1 = Wire(UInt(1), name="carry_pred_1"); carry_pred_1 <<= c2 | p1c1

c3 = Wire(UInt(1), name="c3"); c3 <<= g2
p2c2 = Wire(UInt(1), name="p2c2"); p2c2 <<= p2 & c2
carry_pred_2 = Wire(UInt(1), name="carry_pred_2"); carry_pred_2 <<= c3 | p2c2

c4 = Wire(UInt(1), name="c4"); c4 <<= g3
p3c3 = Wire(UInt(1), name="p3c3"); p3c3 <<= p3 & c3
carry_pred_3 = Wire(UInt(1), name="carry_pred_3"); carry_pred_3 <<= c4 | p3c3

c5 = Wire(UInt(1), name="c5"); c5 <<= g4
p4c4 = Wire(UInt(1), name="p4c4"); p4c4 <<= p4 & c4
carry_pred_4 = Wire(UInt(1), name="carry_pred_4"); carry_pred_4 <<= c5 | p4c4

c6 = Wire(UInt(1), name="c6"); c6 <<= g5
p5c5 = Wire(UInt(1), name="p5c5"); p5c5 <<= p5 & c5
carry_pred_5 = Wire(UInt(1), name="carry_pred_5"); carry_pred_5 <<= c6 | p5c5

c7 = Wire(UInt(1), name="c7"); c7 <<= g6
p6c6 = Wire(UInt(1), name="p6c6"); p6c6 <<= p6 & c6
carry_pred_6 = Wire(UInt(1), name="carry_pred_6"); carry_pred_6 <<= c7 | p6c6

# Per-bit sums — 2 bits wide (matches golden's `wire [2:0] temp1..temp8`
# which only uses bits [1:0]). Only the LSB feeds res, except temp8 which
# contributes both bits.
temp1 = Wire(UInt(2), name="temp1"); temp1 <<= in1[0] + in2[0]
temp2 = Wire(UInt(2), name="temp2"); temp2 <<= (in1[1] + c1) + in2[1]
temp3 = Wire(UInt(2), name="temp3"); temp3 <<= (carry_pred_1 + in1[2]) + in2[2]
temp4 = Wire(UInt(2), name="temp4"); temp4 <<= (carry_pred_2 + in2[3]) + in1[3]
temp5 = Wire(UInt(2), name="temp5"); temp5 <<= (carry_pred_3 + in1[4]) + in2[4]
temp6 = Wire(UInt(2), name="temp6"); temp6 <<= (in2[5] + carry_pred_4) + in1[5]
temp7 = Wire(UInt(2), name="temp7"); temp7 <<= (in2[6] + carry_pred_5) + in1[6]
temp8 = Wire(UInt(2), name="temp8"); temp8 <<= in1[7] + (in2[7] + carry_pred_6)

# assign res[8:0] = {temp8[1:0], temp7[0], temp6[0], temp5[0], temp4[0], temp3[0], temp2[0], temp1[0]};
# spirehdl cat is LSB-first
res <<= cat(temp1[0], temp2[0], temp3[0], temp4[0], temp5[0], temp6[0], temp7[0], temp8[0], temp8[1])

m.to_verilog_file("design.v")

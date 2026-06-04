"""SpireHDL starting point for multiplier_block — 32-bit constant multiplier by 3853.

Mirrors the reference Verilog one-for-one: every `assign` becomes an explicit
`w = Wire(UInt(32), name="<name>"); w <<= <expr>`, which creates a 32-bit
cut-point at each intermediate so yosys/abc see the same widths as the
verilog golden.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire

m = Module("multiplier_block", with_clock=False, with_reset=False)
i_data0 = m.input(UInt(32), "i_data0")
o_data0 = m.output(UInt(32), "o_data0")

# Reference chain, mirrored assign-for-assign at 32-bit width:
#   assign w1   = i_data0;
#   assign w2   = w1 << 1;
#   assign w256 = w1 << 8;
#   assign w257 = w256 + w1;
#   assign w259 = w257 + w2;
#   assign w4112 = w257 << 4;
#   assign w3853 = w4112 - w259;
#   assign o_data0 = w3853;
w1    = Wire(UInt(32), name="w1");    w1    <<= i_data0
w2    = Wire(UInt(32), name="w2");    w2    <<= w1 << 1
w256  = Wire(UInt(32), name="w256");  w256  <<= w1 << 8
w257  = Wire(UInt(32), name="w257");  w257  <<= w256 + w1
w259  = Wire(UInt(32), name="w259");  w259  <<= w257 + w2
w4112 = Wire(UInt(32), name="w4112"); w4112 <<= w257 << 4
w3853 = Wire(UInt(32), name="w3853"); w3853 <<= w4112 - w259

o_data0 <<= w3853

m.to_verilog_file("design.v")

"""Most aggressive: XOR all 9 inputs, register, then pass through to output reg."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register

m = Module("example", with_clock=True, with_reset=False)

inputs = {}
for nm in "abcdefghi":
    inputs[nm] = m.input(UInt(1), f"in_{nm}")
sum_out = m.output(UInt(1), "sum")

# Stage 1: XOR all 9 inputs, register
parity = inputs["a"] ^ inputs["b"] ^ inputs["c"] ^ inputs["d"] ^ inputs["e"] ^ inputs["f"] ^ inputs["g"] ^ inputs["h"] ^ inputs["i"]

r1 = Register(UInt(1), name="r1")
r1 <<= parity

# Stage 2: Just pass through
sum_reg = Register(UInt(1), name="sum_reg")
sum_reg <<= r1
sum_out <<= sum_reg

m.to_verilog_file("design.v")

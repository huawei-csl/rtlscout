"""XOR first, then 2 register stages."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register

m = Module("example", with_clock=True, with_reset=False)

ins = [m.input(UInt(1), f"in_{nm}") for nm in "abcdefghi"]
sum_out = m.output(UInt(1), "sum")

parity = ins[0]
for s in ins[1:]:
    parity = parity ^ s

r1 = Register(UInt(1), name="r1")
r1 <<= parity
r2 = Register(UInt(1), name="r2")
r2 <<= r1
sum_out <<= r2

m.to_verilog_file("design.v")

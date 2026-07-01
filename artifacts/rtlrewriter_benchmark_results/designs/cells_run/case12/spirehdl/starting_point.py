"""SpireHDL starting point for case12 — `example` (commutativity / sharing).

Six 32-bit output expressions over eight 32-bit inputs X..T. Mirrors each
`assign outputN = <expr>;` from the golden verbatim — no intermediate
Wire is declared in the golden, so none here either.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt

m = Module("example", with_clock=False, with_reset=False)
X = m.input(UInt(32), "X")
Y = m.input(UInt(32), "Y")
Z = m.input(UInt(32), "Z")
P = m.input(UInt(32), "P")
Q = m.input(UInt(32), "Q")
R = m.input(UInt(32), "R")
S = m.input(UInt(32), "S")
T = m.input(UInt(32), "T")
output1 = m.output(UInt(32), "output1")
output2 = m.output(UInt(32), "output2")
output3 = m.output(UInt(32), "output3")
output4 = m.output(UInt(32), "output4")
output5 = m.output(UInt(32), "output5")
output6 = m.output(UInt(32), "output6")

output1 <<= (X * Y) + (Z + P)
output2 <<= (P + Z) * (Q - R)
output3 <<= (Y + S + X) + T
output4 <<= (Y * X + Q) * (P + X)
output5 <<= (X * Y + P) - (R + P + X)
output6 <<= (X + Y + P) * (Q - R)

m.to_verilog_file("design.v")

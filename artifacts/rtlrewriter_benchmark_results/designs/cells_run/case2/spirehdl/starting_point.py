"""SpireHDL starting point for case2 — `arithmetic_operations`.

Six 32-bit output expressions over eight 32-bit inputs A..H. Mirrors each
`assign resultN = <expr>;` from the golden directly on the output port; no
intermediate Wire is declared in the golden either.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt

m = Module("arithmetic_operations", with_clock=False, with_reset=False)
A = m.input(UInt(32), "A")
B = m.input(UInt(32), "B")
C = m.input(UInt(32), "C")
D = m.input(UInt(32), "D")
E = m.input(UInt(32), "E")
F = m.input(UInt(32), "F")
G = m.input(UInt(32), "G")
H = m.input(UInt(32), "H")
result1 = m.output(UInt(32), "result1")
result2 = m.output(UInt(32), "result2")
result3 = m.output(UInt(32), "result3")
result4 = m.output(UInt(32), "result4")
result5 = m.output(UInt(32), "result5")
result6 = m.output(UInt(32), "result6")

result1 <<= (A + B) + (C * D)
result2 <<= (D * C) + (E - F)
result3 <<= (B + G + A) + H
result4 <<= (D * C + E) * (B + A)
result5 <<= (C * D + B) - (F + B + A)
result6 <<= (A + C + B) * (E - F)

m.to_verilog_file("design.v")

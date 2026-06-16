"""Try OAI21 decomposition per bit:
f = ~((x | NOR(a,b)) & NAND(a,b))
= ~((x | ~(a|b)) & ~(a&b))

This should use NOR + NAND + OAI21 = 4+4+6 = 14 transistors per bit
Total: 8 * 14 = 112 transistors
"""
from spirehdl.spirehdl import UInt, Bool, Const, mux, cat
from spirehdl.spirehdl_module import Module

m = Module("example", with_clock=False, with_reset=False)
x      = m.input(UInt(1), "x")
sel    = m.input(UInt(1), "sel")
a      = m.input(UInt(8), "a")
b      = m.input(UInt(8), "b")
result = m.output(UInt(8), "result")

# Per bit: f = ~((x | ~(a|b)) & ~(a&b))
bits = []
for i in range(8):
    ai = a[i]
    bi = b[i]
    nor_ab = ~(ai | bi)     # NOR
    nand_ab = ~(ai & bi)    # NAND
    oai = ~((x | nor_ab) & nand_ab)  # OAI21
    bits.append(oai)

result <<= cat(*bits)

m.to_verilog_file("design.v")

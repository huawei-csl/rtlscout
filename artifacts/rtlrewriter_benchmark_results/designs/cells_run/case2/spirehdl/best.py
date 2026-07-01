"""SpireHDL design for arithmetic_operations - with abc and arithmetic optimization."""
from dataclasses import dataclass
from spirehdl.spirehdl_module import Component, Module
from spirehdl.spirehdl import UInt, Signal
from spirehdl.optimize import abc_optimized, arithmetic_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def compute(A, B, C, D, E, F, G, H):
    CD = (C * D)[0:32]
    AB = (A + B)[0:32]
    EF = (E - F)[0:32]
    ABC = (AB + C)[0:32]
    CDF = (CD - F)[0:32]
    r1 = (AB + CD)[0:32]
    r2 = (CDF + E)[0:32]
    r3 = (AB + G + H)[0:32]
    r4 = ((CD + E)[0:32] * AB)[0:32]
    r5 = (CDF - A)[0:32]
    r6 = (ABC * EF)[0:32]
    return r1, r2, r3, r4, r5, r6


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

r1, r2, r3, r4, r5, r6 = compute(A, B, C, D, E, F, G, H)
result1 <<= r1
result2 <<= r2
result3 <<= r3
result4 <<= r4
result5 <<= r5
result6 <<= r6

m.to_verilog_file("design.v")

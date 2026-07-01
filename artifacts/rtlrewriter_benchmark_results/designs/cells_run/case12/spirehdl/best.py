"""Split optimization into separate ABC calls per output."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.optimize import abc_optimized, arithmetic_optimized


# Shared primitives
@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 20; &put")
@arithmetic_optimized(objective="area")
def mul32(a, b):
    return a * b


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 20; &put")
@arithmetic_optimized(objective="area")
def add32(a, b):
    return a + b


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 20; &put")
@arithmetic_optimized(objective="area")
def sub32(a, b):
    return a - b


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 20; &put")
@arithmetic_optimized(objective="area")
def add3_32(a, b, c):
    return a + b + c


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 20; &put")
@arithmetic_optimized(objective="area")
def add4_32(a, b, c, d):
    return a + b + c + d


m = Module("example", with_clock=False, with_reset=False)
X = m.input(UInt(32), "X")
Y = m.input(UInt(32), "Y")
Z = m.input(UInt(32), "Z")
P = m.input(UInt(32), "P")
Q = m.input(UInt(32), "Q")
R = m.input(UInt(32), "R")
S = m.input(UInt(32), "S")
T = m.input(UInt(32), "T")
o1 = m.output(UInt(32), "output1")
o2 = m.output(UInt(32), "output2")
o3 = m.output(UInt(32), "output3")
o4 = m.output(UInt(32), "output4")
o5 = m.output(UInt(32), "output5")
o6 = m.output(UInt(32), "output6")

XY = mul32(X, Y)
PZ = add32(P, Z)
QR = sub32(Q, R)
PX = add32(P, X)
RX = add32(R, X)
PXY = add32(PX, Y)
XYQ = add32(XY, Q)

o1 <<= add32(XY, PZ)
o2 <<= mul32(PZ, QR)
o3 <<= add4_32(Y, S, X, T)
o4 <<= mul32(XYQ, PX)
o5 <<= sub32(XY, RX)
o6 <<= mul32(PXY, QR)

m.to_verilog_file("design.v")

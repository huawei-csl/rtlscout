"""Try grouping results that share CD into blocks for combined optimization."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.optimize import arithmetic_optimized, abc_optimized

# CD multiplier - shared
@abc_optimized(abc_script="strash; &get -n; &deepsyn -J 3 -T 20; &put", cache_read="none")
@arithmetic_optimized(objective="area")
def opt_mul(a, b):
    return a * b

# Adder with resyn2 (lighter, for when deepsyn overhead hurts)
resyn2 = "strash; balance; rewrite -l; refactor -l; balance; rewrite -l; rewrite -lz; balance; refactor -lz; rewrite -lz; balance"

@abc_optimized(abc_script=resyn2)
@arithmetic_optimized(objective="area")
def opt_add(a, b):
    return a + b

@abc_optimized(abc_script=resyn2)
@arithmetic_optimized(objective="area")
def opt_sub(a, b):
    return a - b

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

# Common subexpressions
CD = m.wire(UInt(32), "CD")
CD <<= opt_mul(C, D)

AB = m.wire(UInt(32), "AB")
AB <<= opt_add(A, B)

EF = m.wire(UInt(32), "EF")
EF <<= opt_sub(E, F)

result1 <<= opt_add(AB, CD)
result2 <<= opt_add(CD, EF)
result3 <<= opt_add(opt_add(AB, G), H)

CDE = m.wire(UInt(32), "CDE")
CDE <<= opt_add(CD, E)
result4 <<= opt_mul(CDE, AB)

result5 <<= opt_sub(opt_sub(CD, A), F)

ABC_w = m.wire(UInt(32), "ABC_w")
ABC_w <<= opt_add(AB, C)
result6 <<= opt_mul(ABC_w, EF)

m.to_verilog_file("design.v")

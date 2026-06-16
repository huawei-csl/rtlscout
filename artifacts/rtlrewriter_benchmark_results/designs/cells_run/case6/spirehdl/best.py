from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.optimize import abc_optimized, arithmetic_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def add4(a, b, c, d):
    return (a + b) + (c + d)


m = Module("example", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
c = m.input(UInt(8), "c")
d = m.input(UInt(8), "d")
s = m.output(UInt(10), "sum")
s <<= add4(a, b, c, d)
m.to_verilog_file("design.v")

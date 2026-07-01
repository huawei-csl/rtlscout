"""Seed + arithmetic + abc stacked."""
from spirehdl.spirehdl import UInt, cat
from spirehdl.spirehdl_module import Module
from spirehdl.optimize import abc_optimized, arithmetic_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def compute(x):
    x2 = (x << 2)[0:32]
    x3 = (x << 3)[0:32]
    x4 = (x << 4)[0:32]
    x6 = (x << 6)[0:32]
    x9 = (x3 + x)[0:32]
    y = (x9 + x2)[0:32]
    z = (x9 + x4)[0:32]
    w = (x6 - x)[0:32]
    return cat(y, z, w)


m = Module("example", with_clock=False, with_reset=False)
x = m.input(UInt(32), "x")
y = m.output(UInt(32), "y")
z = m.output(UInt(32), "z")
w = m.output(UInt(32), "w")

packed = compute(x)
y <<= packed[0:32]
z <<= packed[32:64]
w <<= packed[64:96]

m.to_verilog_file("design.v")

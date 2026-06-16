"""Optimize each output separately with ABC."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt
from spirehdl.optimize import abc_optimized, arithmetic_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def compute_y(x):
    return ((x << 3) + x)[0:32]


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def compute_z(x, y_full):
    return ((x << 5) - y_full)[0:32]


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 30; &put")
@arithmetic_optimized(objective="area")
def compute_w(y_full):
    return ((y_full << 3) + y_full)[0:32]


m = Module("example", with_clock=False, with_reset=False)
x = m.input(UInt(32), "x")
y = m.output(UInt(32), "y")
z = m.output(UInt(32), "z")
w = m.output(UInt(32), "w")

yv = compute_y(x)
y <<= yv
# Reconstruct y_full at 33 bits via cat? Just use 32-bit y, but z and w need 33 bits or wrap?
# Use the y output directly (32-bit) for further computations since output is mod 2^32 anyway
z <<= compute_z(x, yv)
w <<= compute_w(yv)

m.to_verilog_file("design.v")

"""Try x3-based sharing: 13=16-3, 25=8*3+1, 63=64-1."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, cat
from spirehdl.optimize import arithmetic_optimized

m = Module("example", with_clock=False, with_reset=False)
x = m.input(UInt(32), "x")
y = m.output(UInt(32), "y")
z = m.output(UInt(32), "z")
w = m.output(UInt(32), "w")

@arithmetic_optimized(objective="area")
def compute_all(x):
    x3 = x + (x << 1)         # 3x (1 add)
    y_val = (x << 4) - x3     # 16x - 3x = 13x (1 sub)
    z_val = (x3 << 3) + x     # 24x + x = 25x (1 add)
    w_val = (x << 6) - x      # 64x - x = 63x (1 sub)
    return cat(y_val[0:32], z_val[0:32], w_val[0:32])

result = compute_all(x)
y <<= result[0:32]
z <<= result[32:64]
w <<= result[64:96]

m.to_verilog_file("design.v")

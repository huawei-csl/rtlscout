"""Try a different approach: use arithmetic_optimized on each pair (add/sub) 
while keeping the overall structure intact. The idea is to keep the output 
truncation inside the optimized functions."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Const, cat
from spirehdl.optimize import arithmetic_optimized

@arithmetic_optimized(objective="area")
def nine_x_and_81x(x):
    """Compute 9x and 81x together - they share 9x."""
    nine_x = (x << 3) + x
    eighty_one_x = (nine_x << 3) + nine_x
    return cat(nine_x[0:32], eighty_one_x[0:32])

@arithmetic_optimized(objective="area")
def twenty_three_x(x, nine_x):
    """Compute 23x = 32x - 9x."""
    return (x << 5) - nine_x

m = Module("example", with_clock=False, with_reset=False)
x = m.input(UInt(32), "x")
y = m.output(UInt(32), "y")
z = m.output(UInt(32), "z")
w = m.output(UInt(32), "w")

yw_result = nine_x_and_81x(x)
y <<= yw_result[0:32]
w <<= yw_result[32:64]

z <<= twenty_three_x(x, yw_result[0:32])[0:32]

m.to_verilog_file("design.v")

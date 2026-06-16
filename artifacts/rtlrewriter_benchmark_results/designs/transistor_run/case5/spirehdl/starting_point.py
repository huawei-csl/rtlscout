"""SpireHDL starting point for case5 — `example` (8-bit adder, bit-width).

Mirrors the golden: store the 9-bit sum through a 128-bit internal register
then truncate to 9 bits at the output. The 128-bit width has no functional
effect (yosys prunes the unused upper bits), but is preserved so the
starting point matches the verilog baseline's structure.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire

m = Module("example", with_clock=False, with_reset=False)
a   = m.input(UInt(8), "a")
b   = m.input(UInt(8), "b")
sum_out = m.output(UInt(9), "sum")

internal_sum = Wire(UInt(128), name="internal_sum")
internal_sum <<= a + b
sum_out <<= internal_sum[0:9]

m.to_verilog_file("design.v")

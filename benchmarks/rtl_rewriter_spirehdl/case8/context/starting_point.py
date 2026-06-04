"""SpireHDL starting point for case8 — `inefficient_multiplier` (bit-width).

Mirrors the golden: `sel` chooses between (A × B) and (C × D); both
operands are zero-extended to 32 bits in 32-bit internal registers before
the multiplication, and the 16-bit `product` output is the low 16 bits of
the 32-bit internal_product. The 32-bit widths have no functional effect
(yosys prunes the unused upper bits) but match the verilog baseline.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, mux

m = Module("inefficient_multiplier", with_clock=False, with_reset=False)
multiplicandA = m.input(UInt(8), "multiplicandA")
multiplierB   = m.input(UInt(8), "multiplierB")
multiplicandC = m.input(UInt(8), "multiplicandC")
multiplierD   = m.input(UInt(8), "multiplierD")
sel           = m.input(UInt(1), "sel")
product       = m.output(UInt(16), "product")

internal_multiplicand = Wire(UInt(32), name="internal_multiplicand")
internal_multiplier   = Wire(UInt(32), name="internal_multiplier")
internal_product      = Wire(UInt(32), name="internal_product")

internal_multiplicand <<= mux(sel, multiplicandA, multiplicandC)
internal_multiplier   <<= mux(sel, multiplierB,   multiplierD)
internal_product      <<= internal_multiplicand * internal_multiplier
product <<= internal_product[0:16]

m.to_verilog_file("design.v")

"""Spire starting point for case8 — `inefficient_multiplier` (bit-width).

Mirrors the golden: `sel` chooses between (A × B) and (C × D); both
operands are zero-extended to 32 bits in 32-bit internal registers before
the multiplication, and the 16-bit `product` output is the low 16 bits of
the 32-bit internal_product. The 32-bit widths have no functional effect
(yosys prunes the unused upper bits) but match the verilog baseline.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire
from spire.expr import mux


class InefficientMultiplier(Component):
    def __init__(self):
        self.io = IORecord(
            multiplicandA=Input(UInt(8)),
            multiplierB=Input(UInt(8)),
            multiplicandC=Input(UInt(8)),
            multiplierD=Input(UInt(8)),
            sel=Input(UInt(1)),
            product=Output(UInt(16)),
        )
        self.elaborate()

    def elaborate(self):
        multiplicandA = self.io.multiplicandA
        multiplierB   = self.io.multiplierB
        multiplicandC = self.io.multiplicandC
        multiplierD   = self.io.multiplierD
        sel           = self.io.sel
        product       = self.io.product

        internal_multiplicand = Wire(UInt(32), name="internal_multiplicand")
        internal_multiplier   = Wire(UInt(32), name="internal_multiplier")
        internal_product      = Wire(UInt(32), name="internal_product")

        internal_multiplicand <<= mux(sel, multiplicandA, multiplicandC)
        internal_multiplier   <<= mux(sel, multiplierB,   multiplierD)
        internal_product      <<= internal_multiplicand * internal_multiplier
        product <<= internal_product[0:16]


InefficientMultiplier().to_verilog_file("design.v", name="inefficient_multiplier")

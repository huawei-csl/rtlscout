"""SpireHDL starting point for case6 — `example` (4-input 8-bit chain sum).

Mirrors the golden one Wire per `assign <w> = <expr>;`: sum_ab (9b),
sum_abc (10b), sum_abcd (11b), and the 10-bit output `sum`.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire

m = Module("example", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
c = m.input(UInt(8), "c")
d = m.input(UInt(8), "d")
sum_out = m.output(UInt(10), "sum")

sum_ab   = Wire(UInt(9),  name="sum_ab");   sum_ab   <<= a + b
sum_abc  = Wire(UInt(10), name="sum_abc");  sum_abc  <<= sum_ab + c
sum_abcd = Wire(UInt(11), name="sum_abcd"); sum_abcd <<= sum_abc + d

sum_out <<= sum_abcd

m.to_verilog_file("design.v")

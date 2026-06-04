"""SpireHDL starting point for the 8b/10b encoder benchmark.

Mirrors the reference Verilog one-for-one: every `assign` becomes an explicit
`w = Wire(UInt(1), name="<name>"); w <<= <expr>`. Each wire is 1-bit to match
the golden's scalar `wire` declarations, so yosys/abc see identical widths
to the verilog sibling.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, cat

m = Module("encoder", with_clock=False, with_reset=False)
in_8b = m.input(UInt(8), "in_8b")
dataK = m.input(UInt(1), "dataK")
out_10b = m.output(UInt(10), "out_10b")

# assign A..H = in_8b[0..7];
A = Wire(UInt(1), name="A"); A <<= in_8b[0]
B = Wire(UInt(1), name="B"); B <<= in_8b[1]
C = Wire(UInt(1), name="C"); C <<= in_8b[2]
D = Wire(UInt(1), name="D"); D <<= in_8b[3]
E = Wire(UInt(1), name="E"); E <<= in_8b[4]
F = Wire(UInt(1), name="F"); F <<= in_8b[5]
G = Wire(UInt(1), name="G"); G <<= in_8b[6]
H = Wire(UInt(1), name="H"); H <<= in_8b[7]
# assign S = 0;
S = Wire(UInt(1), name="S"); S <<= 0

# assign L03 = (~C & ~A) & ~B;
L03 = Wire(UInt(1), name="L03"); L03 <<= (~C & ~A) & ~B
# assign L30 = (B & A) & C;
L30 = Wire(UInt(1), name="L30"); L30 <<= (B & A) & C
# assign L12 = (~A & (~C & B)) | (((~B & ~A) & C) | ((A & ~C) & ~B));
L12 = Wire(UInt(1), name="L12")
L12 <<= (~A & (~C & B)) | (((~B & ~A) & C) | ((A & ~C) & ~B))
# assign L21 = ((A & ~B) & C) | (~A & (C & B)) | (A & (~C & B));
L21 = Wire(UInt(1), name="L21")
L21 <<= ((A & ~B) & C) | (~A & (C & B)) | (A & (~C & B))

# Per-bit output drivers, one 1-bit wire per `assign out_10b[i] = ...;`.
b9 = Wire(UInt(1), name="out9"); b9 <<= A
b8 = Wire(UInt(1), name="out8"); b8 <<= (~D & L03) | (~(L30 & D) & B)
# bit 7: inner `E+~D` is 2-bit, AND with 1-bit L03 zeroes the top bit, so
# reduce to `L03 & (E ^ ~D)`, then `| C`.
b7 = Wire(UInt(1), name="out7"); b7 <<= (L03 & (E ^ (~D))) | C
b6 = Wire(UInt(1), name="out6"); b6 <<= D & ~(L30 & D)
b5 = Wire(UInt(1), name="out5")
b5 <<= ((D & L03) & ~E) | (L12 & (~E & ~D)) | (E & ~(D & L03))
# bit 4: inner `((E & ~D) | (D & ~E))` is `E^D`; then `((E^D)+dataK) & L12`
# truncates to `L12 & ((E^D) ^ dataK)` for the same reason.
b4 = Wire(UInt(1), name="out4")
b4 <<= (((~D & L30) & E)
        | ((L12 & ((E ^ D) ^ dataK)) | ((L21 & ~E) & ~D))
        | (L30 & (D & E)))
# bit 3: `~((H & (G & F)) & (dataK | S)) & F`.   S=0 so `dataK|S == dataK`.
b3 = Wire(UInt(1), name="out3"); b3 <<= ~((H & (G & F)) & dataK) & F
b2 = Wire(UInt(1), name="out2"); b2 <<= G | (~H & ~F)
b1 = Wire(UInt(1), name="out1"); b1 <<= H
b0 = Wire(UInt(1), name="out0")
b0 <<= ((H & (G & F)) & dataK) | (~H & (~F & G)) | (~G & F)

# spirehdl cat() is LSB-first in argument order
out_10b <<= cat(b0, b1, b2, b3, b4, b5, b6, b7, b8, b9)

m.to_verilog_file("design.v")

"""SpireHDL starting point for DiffCheck — RGB555 color-proximity predicate.

Mirrors the reference Verilog one-for-one: each `wire [W-1:0] name = expr;`
becomes `w = Wire(UInt(W), name="name"); w <<= expr`. Widths are held down
at each stage (6/7/8 bits) so yosys/abc see the same bit-widths as the
verilog golden. Sign extensions are done in bit-space via `cat(x, x[msb])`
to avoid spirehdl's `cast(unsigned_concat, SInt(wider))` zero-extension
footgun.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, cat

m = Module("DiffCheck", with_clock=False, with_reset=False)
rgb1 = m.input(UInt(15), "rgb1")
rgb2 = m.input(UInt(15), "rgb2")
result = m.output(UInt(1), "result")

# wire [5:0] r = rgb1[4:0] - rgb2[4:0];
r = Wire(UInt(6), name="r"); r <<= rgb1[0:5] - rgb2[0:5]
g = Wire(UInt(6), name="g"); g <<= rgb1[5:10] - rgb2[5:10]
b = Wire(UInt(6), name="b"); b <<= rgb1[10:15] - rgb2[10:15]

# wire [6:0] t = $signed(r) + $signed(b);   -- sign-extend both to 7 bits
r7 = Wire(UInt(7), name="r7"); r7 <<= cat(r, r[5])
b7 = Wire(UInt(7), name="b7"); b7 <<= cat(b, b[5])
t  = Wire(UInt(7), name="t");  t  <<= r7 + b7

# wire [6:0] gx = {g[5], g};
gx = Wire(UInt(7), name="gx"); gx <<= cat(g, g[5])

# wire [7:0] y = $signed(gx) + $signed(t);
gx8 = Wire(UInt(8), name="gx8"); gx8 <<= cat(gx, gx[6])
t8  = Wire(UInt(8), name="t8");  t8  <<= cat(t, t[6])
y   = Wire(UInt(8), name="y");   y   <<= gx8 + t8

# wire [6:0] u = $signed(r) - $signed(b);
u = Wire(UInt(7), name="u"); u <<= r7 - b7

# wire [7:0] v = $signed({g, 1'b0}) - $signed(t);
gshl7 = Wire(UInt(7), name="gshl7"); gshl7 <<= cat(0, g)             # {g, 1'b0}
gshl8 = Wire(UInt(8), name="gshl8"); gshl8 <<= cat(gshl7, gshl7[6])  # sign-extend
t8v   = Wire(UInt(8), name="t8v");   t8v   <<= cat(t, t[6])
v     = Wire(UInt(8), name="v");     v     <<= gshl8 - t8v

# Range predicates — unsigned compares on the 8-bit and 7-bit wires.
y_inside = Wire(UInt(1), name="y_inside"); y_inside <<= (y < 0x18) | (y >= 0xE8)
u_inside = Wire(UInt(1), name="u_inside"); u_inside <<= (u < 0x04) | (u >= 0x7C)
v_inside = Wire(UInt(1), name="v_inside"); v_inside <<= (v < 0x06) | (v >= 0xFA)

# assign result = !(u_inside & v_inside & y_inside);
result <<= ~(u_inside & v_inside & y_inside)

m.to_verilog_file("design.v")

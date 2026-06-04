"""SpireHDL starting point for adder_4bit — registered 4-bit adder (+ cout hash).

Mirrors the reference Verilog one-for-one. Uses `Register(typ, name=...)` for
each `reg` in the golden and `Wire(typ, name=...)` for each `assign`. The
module has no reset (only `clk`), so `with_reset=False`.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register

m = Module("adder_4bit", with_clock=True, with_reset=False)
a = m.input(UInt(4), "a")
b = m.input(UInt(4), "b")
cin = m.input(UInt(1), "cin")
sum_out = m.output(UInt(4), "sum")
cout = m.output(UInt(1), "cout")

# reg [3:0] sum_reg;  always @(posedge clk) sum_reg <= (b + cin) + a;
sum_reg = Register(UInt(4), name="sum_reg")
sum_reg <<= (b + cin) + a

# reg cout_reg;       always @(posedge clk) cout_reg <= (cin & a[3]) | (b[3] & (cin | a[3]));
cout_reg = Register(UInt(1), name="cout_reg")
cout_reg <<= (cin & a[3]) | (b[3] & (cin | a[3]))

# assign sum = sum_reg;
# assign cout = cout_reg;
sum_out <<= sum_reg
cout <<= cout_reg

m.to_verilog_file("design.v")

"""SpireHDL starting point for average_module — running-accumulator 'average'.

Mirrors the reference Verilog one-for-one. The golden uses a synchronous
active-high `reset` port (not named `rst`), so we set `with_reset=False` to
prevent spirehdl from auto-creating a `rst` port, declare `reset` as a
regular input, and implement the synchronous reset explicitly as a `mux` on
each register's next-state. This matches the golden's `always @(posedge clk)
if (reset) ... else ...` structure exactly and keeps the port name as `reset`.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register, cat, mux

m = Module("average_module", with_clock=True, with_reset=False)
reset = m.input(UInt(1), "reset")
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
c = m.input(UInt(8), "c")
d = m.input(UInt(8), "d")
average = m.output(UInt(8), "average")

# State registers. Each starts at 0 under synchronous reset.
sum_reg     = Register(UInt(8), name="sum_reg")
carry_reg   = Register(UInt(4), name="carry_reg")
average_reg = Register(UInt(8), name="average_reg")

# Combinational next-state computation, mirroring
#   {sum, carry} <= ((b + {4{carry}}) + d) + (c + a);
#   average      <= sum >> 2;
# `{4{carry}}` is a 16-bit replication of the 4-bit carry register.
carry_rep = Wire(UInt(16), name="carry_rep")
carry_rep <<= cat(carry_reg, carry_reg, carry_reg, carry_reg)

# Big sum — spirehdl widens naturally; we truncate to 12 bits to match the
# golden's `{sum, carry}` 12-bit LHS.
big_sum = Wire(UInt(12), name="big_sum")
big_sum <<= (b + carry_rep) + d + (c + a)

# Split {sum, carry}: lower 4 bits → next_carry, upper 8 bits → next_sum.
next_carry = Wire(UInt(4), name="next_carry"); next_carry <<= big_sum[0:4]
next_sum   = Wire(UInt(8), name="next_sum");   next_sum   <<= big_sum[4:12]
next_avg   = Wire(UInt(8), name="next_avg");   next_avg   <<= sum_reg >> 2

# Synchronous active-high reset implemented as a mux on each register's next-state.
sum_reg     <<= mux(reset, 0, next_sum)
carry_reg   <<= mux(reset, 0, next_carry)
average_reg <<= mux(reset, 0, next_avg)

# Output is the registered 'average' value.
average <<= average_reg

m.to_verilog_file("design.v")

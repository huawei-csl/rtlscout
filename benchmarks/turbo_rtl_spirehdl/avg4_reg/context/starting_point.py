"""Spire starting point for average_module — running-accumulator 'average'.

Mirrors the reference Verilog one-for-one. The golden uses a synchronous
active-high `reset` port (not named `rst`), so we set `with_reset=False` to
prevent spirehdl from auto-creating a `rst` port, declare `reset` as a
regular input, and implement the synchronous reset explicitly as a `mux` on
each register's next-state. This matches the golden's `always @(posedge clk)
if (reset) ... else ...` structure exactly and keeps the port name as `reset`.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire, Register
from spire.expr import cat, mux


class AverageModule(Component):
    def __init__(self):
        self.io = IORecord(
            reset=Input(UInt(1)),
            a=Input(UInt(8)),
            b=Input(UInt(8)),
            c=Input(UInt(8)),
            d=Input(UInt(8)),
            average=Output(UInt(8)),
        )
        self.elaborate()

    def elaborate(self):
        # alias every port so the original body is unchanged
        reset = self.io.reset
        a = self.io.a
        b = self.io.b
        c = self.io.c
        d = self.io.d
        average = self.io.average

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


AverageModule().to_verilog_file("design.v", name="average_module", with_clock=True)

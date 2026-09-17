"""Spire starting point for case1 — `example` (9-input registered chain adder).

Mirrors the reference verilog one-for-one: 9 1-bit `in_*` ports get registered
into `reg_*` each cycle, and `sum` is the 1-bit-truncated running sum of the
9 registered bits (i.e. parity of the inputs).

Note: the reference verilog only explicitly declares `reg_a, reg_b, reg_c` and
relies on yosys to infer the remaining six `reg_d..reg_i` from their use inside
`always @(posedge clk)`. Spire makes them explicit `Register` instances.
"""
from spire import Component, IORecord, Input, Output, UInt, Register


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            **{f"in_{nm}": Input(UInt(1)) for nm in "abcdefghi"},
            sum=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        # alias every port so the original body is unchanged
        inputs = {nm: getattr(self.io, f"in_{nm}") for nm in "abcdefghi"}
        sum_out = self.io.sum

        regs = {}
        for nm in "abcdefghi":
            r = Register(UInt(1), name=f"reg_{nm}")
            r <<= inputs[nm]
            regs[nm] = r

        # output reg sum;  sum <= reg_a + ... + reg_i;
        # sum is 1-bit so the trailing fit_width truncates the full 4-bit sum to its LSB.
        sum_reg = Register(UInt(1), name="sum_reg")
        sum_reg <<= (regs["a"] + regs["b"] + regs["c"] + regs["d"] + regs["e"]
                     + regs["f"] + regs["g"] + regs["h"] + regs["i"])
        sum_out <<= sum_reg


Example().to_verilog_file("design.v", name="example", with_clock=True)

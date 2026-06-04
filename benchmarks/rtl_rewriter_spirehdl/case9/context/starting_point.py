"""SpireHDL starting point for case9 — `example` (6-state FSM, 3-bit encoding).

Golden uses async posedge-reset (port name `reset`, not `rst`). Following the
turbo_rtl idiom: `with_reset=False`, declare `reset` as a regular 1-bit input,
implement reset as `mux(reset, S0, next_state)` on the register. This is
synchronous rather than async, but matches the functional FSM semantics once
reset is released.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register, mux

S0, S1, S2, S3, S4, S5 = 0, 1, 2, 3, 4, 5

m = Module("example", with_clock=True, with_reset=False)
reset        = m.input(UInt(1), "reset")
input_signal = m.input(UInt(2), "input_signal")
output_signal = m.output(UInt(1), "output_signal")

current_state = Register(UInt(3), name="current_state")

# next_state is a combinational Wire driven by a big mux chain.
next_state = Wire(UInt(3), name="next_state")

# Helpers for input_signal 2-bit patterns.
i_eq = lambda v: input_signal == v

# Per-state next_state selection; unmatched input_signal patterns fall through
# to the state itself (matching the golden's `default to staying in the same
# state` comment and missing-arm behaviour).
ns_S0 = mux(i_eq(0), S0, mux(i_eq(1), S1, mux(i_eq(2), S2, S3)))          # all 4 listed → last is S3 (i==3)
ns_S1 = mux(i_eq(0), S0, mux(i_eq(1), S3, mux(i_eq(3), S5, current_state)))
ns_S2 = mux(i_eq(0), S1, mux(i_eq(1), S3, mux(i_eq(2), S2, S4)))
ns_S3 = mux(i_eq(0), S1, mux(i_eq(1), S0, mux(i_eq(2), S4, S5)))
ns_S4 = mux(i_eq(0), S0, mux(i_eq(1), S1, mux(i_eq(2), S2, S5)))
ns_S5 = mux(i_eq(0), S1, mux(i_eq(1), S4, mux(i_eq(2), S0, current_state)))

next_state <<= mux(current_state == S0, ns_S0,
              mux(current_state == S1, ns_S1,
              mux(current_state == S2, ns_S2,
              mux(current_state == S3, ns_S3,
              mux(current_state == S4, ns_S4,
              mux(current_state == S5, ns_S5, current_state))))))

current_state <<= mux(reset, S0, next_state)

# Output: 1 in S0, S2, S4; 0 otherwise.
output_signal <<= mux(current_state == S0, 1,
                  mux(current_state == S2, 1,
                  mux(current_state == S4, 1, 0)))

m.to_verilog_file("design.v")

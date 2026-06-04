"""SpireHDL starting point for case10 — `example` (7-state FSM, 1-bit input).

Golden uses async posedge-reset (port `reset`). Synchronous mux-reset mirror
per the turbo_rtl idiom.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register, mux

S0, S1, S2, S3, S4, S5, S6 = 0, 1, 2, 3, 4, 5, 6

m = Module("example", with_clock=True, with_reset=False)
reset = m.input(UInt(1), "reset")
x     = m.input(UInt(1), "x")
output_signal = m.output(UInt(1), "output_signal")

state = Register(UInt(3), name="state")

# Per-state (next_state, out) pairs, selected by x.
ns_S0 = mux(x, S2, S1); o_S0 = 1
ns_S1 = mux(x, S5, S3); o_S1 = 1
ns_S2 = mux(x, S4, S5); o_S2 = 0
ns_S3 = mux(x, S6, S1); o_S3 = 1
ns_S4 = mux(x, S2, S5); o_S4 = 0
ns_S5 = mux(x, S3, S4); o_S5 = 0
ns_S6 = mux(x, S6, S5); o_S6 = 0

next_state = Wire(UInt(3), name="next_state")
next_state <<= mux(state == S0, ns_S0,
              mux(state == S1, ns_S1,
              mux(state == S2, ns_S2,
              mux(state == S3, ns_S3,
              mux(state == S4, ns_S4,
              mux(state == S5, ns_S5,
              mux(state == S6, ns_S6, S0)))))))  # default → S0

output_signal <<= mux(state == S0, o_S0,
                  mux(state == S1, o_S1,
                  mux(state == S2, o_S2,
                  mux(state == S3, o_S3,
                  mux(state == S4, o_S4,
                  mux(state == S5, o_S5,
                  mux(state == S6, o_S6, 0)))))))

state <<= mux(reset, S0, next_state)

m.to_verilog_file("design.v")

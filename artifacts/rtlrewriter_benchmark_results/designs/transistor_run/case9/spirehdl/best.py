"""FSM - flowy last attempt."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register, mux, cat
from spirehdl.optimize import flowy_optimized

m = Module("example", with_clock=True, with_reset=False)
reset        = m.input(UInt(1), "reset")
input_signal = m.input(UInt(2), "input_signal")
output_signal = m.output(UInt(1), "output_signal")

current_state = Register(UInt(3), name="current_state")

s = current_state
inp = input_signal

@flowy_optimized(direct=True, iterations=3, mockturtle_chains=5,
                 mockturtle_chain_len=10, mockturtle_chain_workers=5,
                 selection_metric='aig_count', cache_read="none", cache_write="none")
def compute_next_state_vB(s, inp):
    s0 = s[0]; s1 = s[1]; s2 = s[2]
    i0 = inp[0]; i1 = inp[1]
    
    # Use raw SOP form
    ns0 = (~i1) | ((~s2) & (~i0)) | (s2 & (~s1) & i0)
    ns1 = ((~s2) & (~s1) & i0) | ((~s0) & i0) | ((~s2) & s1 & s0 & i1) | (i1 & i0)
    ns2 = ((~s2) & s1 & (~i1) & i0) | (s1 & i1 & (~i0)) | (s2 & s0 & (~i0)) | (s2 & (~s0) & i1) | ((~s1) & s0 & (~i1) & (~i0))
    
    return cat(ns0, ns1, ns2)

ns_val = compute_next_state_vB(s, inp)

current_state <<= mux(reset, 5, ns_val)
output_signal <<= s[2]

m.to_verilog_file("design.v")

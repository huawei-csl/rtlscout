"""Minimized FSM: only 4 equivalence classes.
A={S0,S3} out=1
B={S1} out=1
C={S5} out=0
D={S2,S4,S6} out=0

Transitions:
A: x=0->B, x=1->D
B: x=0->A, x=1->C
C: x=0->D, x=1->A
D: x=0->C, x=1->D

Initial: A.

Encoding: A=10, B=11, C=00, D=01. output=state[1].
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register, mux, cat, Const

m = Module("example", with_clock=True, with_reset=False)
reset = m.input(UInt(1), "reset")
x     = m.input(UInt(1), "x")
output_signal = m.output(UInt(1), "output_signal")

state = Register(UInt(2), name="state")
s0 = state[0]
s1 = state[1]
nx = ~x
ns1_ = ~s1
ns0_ = ~s0

# Codes: A=10 (s1=1,s0=0), B=11 (s1=1,s0=1), C=00, D=01
# ns1 = 1 when:
#   A,x=0 -> B(11): 1
#   B,x=0 -> A(10): 1
#   C,x=1 -> A(10): 1
# ns1 = (s1 & ~x) | (~s1 & ~s0 & x)

# ns0 = 1 when:
#   A,x=0 -> B(11)
#   A,x=1 -> D(01)
#   C,x=0 -> D(01)
#   D,x=1 -> D(01)
# i.e., A | (C & ~x) | (D & x)
# A=s1&~s0; C=~s1&~s0; D=~s1&s0
# ns0 = (s1 & ~s0) | (~s1 & ~s0 & ~x) | (~s1 & s0 & x)

# Let's try to factor:
# ns0 = (s1 & ~s0) | (~s1 & (~s0 & ~x | s0 & x))
#     = (s1 & ~s0) | (~s1 & ~(s0 ^ x))  -- XOR-based... probably costly
# Simpler form:
# ns0 = mux(s1, ~s0, mux(s0, x, ~x))
#     = mux(s1, ~s0, x ^ ~s0)?  let me check
# When s1=1: ns0 = ~s0  (matches: A->ns0=1, A->ns0=1; B->ns0=0, B->ns0=0)
# When s1=0: 
#   s0=0 (C): ns0 = ~x  (C,x=0->1, C,x=1->0 wait but C,x=1->A(10), ns0=0 OK)
#   s0=1 (D): ns0 = x   (D,x=0->C(00),ns0=0; D,x=1->D(01),ns0=1) ✓
# So when s1=0: ns0 = mux(s0, x, ~x) = s0 ^ ~x = ~(s0 ^ x)

# Actually: when s1=0, ns0 = ~(s0 ^ x)? Check:
#   s0=0,x=0: ~(0)=1 ✓
#   s0=0,x=1: ~(1)=0 ✓
#   s0=1,x=0: ~(1)=0 ✓
#   s0=1,x=1: ~(0)=1 ✓
# Yes. So ns0 = mux(s1, ~s0, ~(s0 ^ x))

# But XOR may cost more than direct. Let's try direct:
A = s1 & ns0_   # A=10
B = s1 & s0     # B=11
C = ns1_ & ns0_ # C=00
D = ns1_ & s0   # D=01

ns1 = (s1 & nx) | (C & x)
ns0 = A | (C & nx) | (D & x)

next_state = Wire(UInt(2), name="next_state")
next_state <<= cat(ns0, ns1)

output_signal <<= s1

state <<= mux(reset, Const(2, UInt(2)), next_state)  # A=10=2

m.to_verilog_file("design.v")

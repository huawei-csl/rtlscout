"""Test specific encodings.

Minimized states: A, B, C, D
A: out=1, x=0->B, x=1->C
B: out=1, x=0->A, x=1->D
C: out=0, x=0->D, x=1->C
D: out=0, x=0->C, x=1->A
Init: A

For x=0: A<->B, C<->D (both pairs swap)
For x=1: A->C, B->D, C->C, D->A

Let me analyze the structure. For x=0, the transitions form two 2-cycles:
A<->B and C<->D. For x=1: A->C->C (C is absorbing), B->D->A->C.

Looking for encodings where:
1. Output is a single bit (A,B share a bit value; C,D share opposite)
2. The x=0 swap within pairs is simple (XOR with something)
3. The x=1 logic is simple

Already tried A=0,B=1,C=2,D=3 (26 transistors):
  out = ~s1
  ns(x=0) = state ^ 1 → ns1=s1, ns0=~s0
  ns1(x=1) = NAND(s1,s0), ns0(x=1) = s0&~s1

Let me try A=2,B=3,C=0,D=1:
  out = s1
  x=0: A(10)->B(11), B(11)->A(10), C(00)->D(01), D(01)->C(00)
    → toggle s0: ns1=s1, ns0=~s0 (same as before)
  x=1: A(10)->C(00), B(11)->D(01), C(00)->C(00), D(01)->A(10)
    ns1(x=1): (0,0)->0, (0,1)->1, (1,0)->0, (1,1)->0 = ~s1&s0
    ns0(x=1): (0,0)->0, (0,1)->0, (1,0)->0, (1,1)->1 = s1&s0
  Init = A = 2

  So: out=s1, ns1=mux(x, ~s1&s0, s1), ns0=mux(x, s1&s0, ~s0)
  Init=2, reset puts state to 2.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, mux, cat, Const

m = Module("example", with_clock=True, with_reset=False)
reset = m.input(UInt(1), "reset")
x     = m.input(UInt(1), "x")
output_signal = m.output(UInt(1), "output_signal")

state = Register(UInt(2), name="state")
s0 = state[0]
s1 = state[1]

# A=2, B=3, C=0, D=1
output_signal <<= s1

ns1 = mux(x, ~s1 & s0, s1)
ns0 = mux(x, s1 & s0, ~s0)

ns = cat(ns0, ns1)

state <<= mux(reset, Const(2, UInt(2)), ns[0:2])

m.to_verilog_file("design.v")

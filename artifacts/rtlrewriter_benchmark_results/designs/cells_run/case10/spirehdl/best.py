"""Minimized 4-state FSM for case10 — encoding where output = state bit.

Classes: {S0,S3}=A, {S1}=B, {S2,S4,S6}=C, {S5}=D
Encoding: A=10, B=11, C=00, D=01
  → output = s1 (A,B have s1=1; C,D have s1=0)

Transitions:
A(10): x=0->B(11), x=1->C(00)
B(11): x=0->A(10), x=1->D(01)
C(00): x=0->D(01), x=1->C(00)
D(01): x=0->C(00), x=1->A(10)

next[0] = mux(x, s0 & s1, ~s0)
next[1] = mux(x, s0 & ~s1, s1)
output  = s1
Reset to A=10 (value 2)
"""
from spire import Component, IORecord, Input, Output, UInt, Wire, Register
from spire.expr import mux, cat, Const


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            reset=Input(UInt(1)),
            x=Input(UInt(1)),
            output_signal=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        reset = self.io.reset
        x = self.io.x

        state = Register(UInt(2), name="state")
        s1 = state[1]
        s0 = state[0]

        # next[0]: x=0 -> ~s0, x=1 -> s0 & s1
        nx0 = mux(x, s0 & s1, ~s0)
        # next[1]: x=0 -> s1, x=1 -> s0 & ~s1
        nx1 = mux(x, s0 & ~s1, s1)

        # Reset to A=10 (value 2)
        next_state = mux(reset, 2, cat(nx0, nx1))

        state <<= next_state
        self.io.output_signal <<= s1


Example().to_verilog_file("design.v", name="example", with_clock=True)

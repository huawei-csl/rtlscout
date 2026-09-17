"""Encoding: A=00, B=10, C=11, D=01 -> output = ~s0
A(00) out=1, B(10) out=1, C(11) out=0, D(01) out=0
s0: 0,0,1,1 -> out = ~s0

Transitions:
A(00): x=1->C(11), x=0->B(10)
B(10): x=1->D(01), x=0->A(00)
C(11): x=1->C(11), x=0->D(01)
D(01): x=1->A(00), x=0->C(11)
"""
from spire import Component, IORecord, Input, Output, UInt, Wire, Register
from spire.expr import mux

A, B, C, D = 0, 2, 3, 1


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
        output_signal = self.io.output_signal

        state = Register(UInt(2), name="state")

        next_state = Wire(UInt(2), name="next_state")
        next_state <<= mux(state == A, mux(x, C, B),
                      mux(state == B, mux(x, D, A),
                      mux(state == C, mux(x, C, D),
                      mux(state == D, mux(x, A, C), A))))

        output_signal <<= ~state[0]

        state <<= mux(reset, A, next_state)


Example().to_verilog_file("design.v", name="example", with_clock=True)

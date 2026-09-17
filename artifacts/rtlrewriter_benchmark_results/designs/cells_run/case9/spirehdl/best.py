from spire import Component, IORecord, Input, Output, UInt, Register
from spire.expr import mux, cat, Const

# 4-state minimized FSM. Encoding: C=00, A=01, D=10, B=11
# Output: A(01)->1, B(11)->1, C(00)->0, D(10)->0 => output = s0 (bit0)
# Reset to A=01 (value 1)

# Transitions (using class names A,B,C,D):
# A: 0->A, 1->C, 2->B, 3->D
# B: 0->C, 1->D, 2->B, 3->A
# C: 0->A, 1->D, 2->C, 3->D
# D: 0->C, 1->A, 2->A, 3->D

# Encoding: C=00, A=01, D=10, B=11  (bit0, bit1)
# s0': C: ~i1&~i0, A: ~i0, D: i0^i1, B: i1
# s1': C: i0,       A: i1,  D: i0&i1, B: i0^i1

class Example(Component):
    def __init__(self):
        self.io = IORecord(
            reset=Input(UInt(1)),
            input_signal=Input(UInt(2)),
            output_signal=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        reset        = self.io.reset
        inp         = self.io.input_signal
        output_signal = self.io.output_signal

        s = Register(UInt(2), name="state")
        s0 = s[0]
        s1 = s[1]

        i0 = inp[0]
        i1 = inp[1]

        # C=00, A=01, D=10, B=11
        is_C = ~s0 & ~s1
        is_A = s0 & ~s1
        is_D = ~s0 & s1

        ns0 = mux(is_C, ~i1 & ~i0,
             mux(is_A, ~i0,
             mux(is_D, i0 ^ i1,
                  i1)))

        ns1 = mux(is_C, i0,
             mux(is_A, i1,
             mux(is_D, i0 & i1,
                  i0 ^ i1)))

        ns = cat(ns0, ns1)

        s <<= mux(reset, Const(1, UInt(2)), ns)  # reset to A=01

        output_signal <<= s0


Example().to_verilog_file("design.v", name="example", with_clock=True)

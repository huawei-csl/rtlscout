"""Try computing next-state bits directly from state bits and input bits.

Minimized 4-state FSM:
  A(00): 0->A(00), 1->B(01), 2->C(10), 3->D(11)  out=1
  B(01): 0->A(00), 1->D(11), 2->B(01), 3->D(11)  out=0
  C(10): 0->B(01), 1->D(11), 2->C(10), 3->A(00)  out=1
  D(11): 0->B(01), 1->A(00), 2->A(00), 3->D(11)  out=0

Let me compute the next-state truth table directly:
  state[1:0] x input[1:0] -> next[1:0]

  s1 s0 i1 i0 | ns1 ns0
  0  0  0  0  |  0   0   (A->A)
  0  0  0  1  |  0   1   (A->B)
  0  0  1  0  |  1   0   (A->C)
  0  0  1  1  |  1   1   (A->D)
  0  1  0  0  |  0   0   (B->A)
  0  1  0  1  |  1   1   (B->D)
  0  1  1  0  |  0   1   (B->B)
  0  1  1  1  |  1   1   (B->D)
  1  0  0  0  |  0   1   (C->B)
  1  0  0  1  |  1   1   (C->D)
  1  0  1  0  |  1   0   (C->C)
  1  0  1  1  |  0   0   (C->A)
  1  1  0  0  |  0   1   (D->B)
  1  1  0  1  |  0   0   (D->A)
  1  1  1  0  |  0   0   (D->A)
  1  1  1  1  |  1   1   (D->D)

ns1: 0 0 1 1 0 1 0 1 0 1 1 0 0 0 0 1
ns0: 0 1 0 1 0 1 1 1 1 1 0 0 1 0 0 1

Let me see if these can be simplified with Karnaugh maps or Boolean algebra.

ns0 truth table (s1,s0,i1,i0):
00: 0 1 0 1  01: 0 1 1 1  11: 1 0 0 1  10: 1 1 0 0

ns0 = ? Let me write it as a 4-variable K-map:
       i1i0=00 01 11 10
s1s0=00:  0   1  1  0   -> s0 when i=01 or 11... 
Actually let me just try the mux approach but with state bits directly.
"""
from spire import Component, IORecord, Input, Output, UInt, Register
from spire.expr import mux, cat

class Example(Component):
    def __init__(self):
        self.io = IORecord(
            reset=Input(UInt(1)),
            input_signal=Input(UInt(2)),
            output_signal=Output(UInt(1)),
        )
        self.elaborate()

    def elaborate(self):
        reset = self.io.reset
        inp = self.io.input_signal
        out = self.io.output_signal

        state = Register(UInt(2), name="state")
        s0 = state[0]
        s1 = state[1]
        i0 = inp[0]
        i1 = inp[1]

        # Next-state truth table (computed above):
        # ns1: 0 0 1 1 | 0 1 0 1 | 0 1 1 0 | 0 0 0 1  (by s1s0: 00,01,11,10 x i1i0: 00,01,11,10)
        # ns0: 0 1 0 1 | 0 1 1 1 | 1 0 0 1 | 1 1 0 0

        # Let me compute ns1 and ns0 as functions of s1,s0,i1,i0
        # Using the mux approach: select on state, then on input
        # But let's try to find simpler boolean expressions
        
        # ns0: 
        # s=00: ns0 = i0  (0,1,1,0 -> i0? no: 00->0,01->1,11->1,10->0 => ns0 = i0 when i1=0, ~i0 when i1=1? No: 11->1,10->0 => ns0=i0)
        # Actually for s=00: i=00->0, i=01->1, i=11->1, i=10->0 => ns0 = i0
        # s=01: i=00->0, i=01->1, i=11->1, i=10->1 => ns0 = i0 | i1
        # s=11: i=00->1, i=01->0, i=11->1, i=10->0 => ns0 = ~i1 & ~i0 | i1 & i0 = ~(i0^i1)? 
        #   00->1, 01->0, 10->0, 11->1 => ns0 = ~(i0 ^ i1) = i0 XNOR i1
        # s=10: i=00->1, i=01->1, i=11->0, i=10->0 => ns0 = ~i1
        
        # ns1:
        # s=00: i=00->0, 01->0, 11->1, 10->1 => ns1 = i1
        # s=01: i=00->0, 01->1, 11->1, 10->0 => ns1 = i1 & i0 | ... 01->1,11->1 => ns1 = i0
        #   Wait: 00->0, 01->1, 11->1, 10->0 => ns1 = i0
        # s=11: i=00->0, 01->0, 11->1, 10->0 => ns1 = i1 & i0
        # s=10: i=00->0, 01->1, 11->0, 10->1 => ns1 = i0 ^ i1? 
        #   00->0, 01->1, 11->0, 10->1 => ns1 = i0 ^ i1
        
        # So:
        # ns0 = mux(s1, 
        #   mux(s0, i0 & ~i1 | i1 & i0, ~i1),  # s1=1: s0=1->XNOR, s0=0->~i1
        #   mux(s0, i0 | i1, i0))               # s1=0: s0=1->i0|i1, s0=0->i0
        # 
        # ns1 = mux(s1,
        #   mux(s0, i1 & i0, i0 ^ i1),  # s1=1: s0=1->i1&i0, s0=0->i0^i1
        #   mux(s0, i0, i1))             # s1=0: s0=1->i0, s0=0->i1

        # Simplify ns0 for s1=1, s0=1: i0 & ~i1 | i1 & i0 = i0 & (~i1 | i1) = i0
        # Wait: 00->1, 01->0, 11->1, 10->0 for s=11
        # That's i0 XNOR i1 = ~(i0 ^ i1). But let me recheck:
        # s=11 (D): 0->B(01), 1->A(00), 2->A(00), 3->D(11)
        # i=00 (0): ns=01 => ns0=1
        # i=01 (1): ns=00 => ns0=0  
        # i=10 (2): ns=00 => ns0=0
        # i=11 (3): ns=11 => ns0=1
        # So ns0 for s=11: i=0->1, i=1->0, i=2->0, i=3->1 => ~(i0 ^ i1)? 
        # i=0(00):1, i=1(01):0, i=2(10):0, i=3(11):1 => yes, XNOR
        
        # Simplify: ns0 = mux(s1, mux(s0, ~(i0^i1), ~i1), mux(s0, i0|i1, i0))
        # Actually let me re-examine:
        # s1=0, s0=0 (A): ns0 = i0  (0->0, 1->1, 2->0, 3->1 => i0)
        # s1=0, s0=1 (B): ns0 = ?  (0->0, 1->1, 2->1, 3->1 => i0 | i1)
        # s1=1, s0=0 (C): ns0 = ~i1 (0->1, 1->1, 2->0, 3->0 => ~i1)  
        #   Wait: C=10: 0->B(01) ns0=1, 1->D(11) ns0=1, 2->C(10) ns0=0, 3->A(00) ns0=0
        #   i=0->1, i=1->1, i=2->0, i=3->0 => ~i1. Yes.
        # s1=1, s0=1 (D): ns0 = ~(i0^i1) (0->1, 1->0, 2->0, 3->1)
        
        # ns1:
        # s1=0, s0=0 (A): 0->0, 1->0, 2->1, 3->1 => i1
        # s1=0, s0=1 (B): 0->0, 1->1, 2->0, 3->1 => i0
        # s1=1, s0=0 (C): 0->0, 1->1, 2->1, 3->0 => i0 ^ i1
        # s1=1, s0=1 (D): 0->0, 1->0, 2->0, 3->1 => i1 & i0

        ns0 = mux(s1,
              mux(s0, ~(i0 ^ i1), ~i1),
              mux(s0, i0 | i1, i0))
        
        ns1 = mux(s1,
              mux(s0, i1 & i0, i0 ^ i1),
              mux(s0, i0, i1))
        
        next_state = mux(reset, 0, cat(ns0, ns1))
        state <<= next_state

        # Output: ~state[0] (1 for A=00, C=10; 0 for B=01, D=11)
        out <<= ~s0


Example().to_verilog_file("design.v", name="example", with_clock=True)

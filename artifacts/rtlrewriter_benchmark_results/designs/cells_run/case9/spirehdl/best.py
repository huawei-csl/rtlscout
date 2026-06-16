"""FSM via LUT, fill don't-cares for max sharing."""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, Register, mux, cat, Const

trans = [
    [0,1,2,3],
    [0,3,1,5],
    [1,3,2,4],
    [1,0,4,5],
    [0,1,2,5],
    [1,4,0,5],
]

m = Module("example", with_clock=True, with_reset=False)
reset        = m.input(UInt(1), "reset")
input_signal = m.input(UInt(2), "input_signal")
output_signal = m.output(UInt(1), "output_signal")

current_state = Register(UInt(3), name="current_state")
next_state = Wire(UInt(3), name="next_state")

# cat(input_signal, current_state) -> input in low 2 bits, state in high 3 bits
# index = state*4 + input
values = [0]*32
for s in range(6):
    for i in range(4):
        values[s*4 + i] = trans[s][i]
# don't-cares: state 6,7 -> fill same as state 4,5
for i in range(4):
    values[6*4 + i] = trans[4][i]
    values[7*4 + i] = trans[5][i]

idx = cat(input_signal, current_state)  # input low, state high

def build_tree(values, bits):
    if len(values) == 1:
        return Const(values[0], UInt(3))
    half = len(values) // 2
    lo = build_tree(values[:half], bits[1:])
    hi = build_tree(values[half:], bits[1:])
    return mux(bits[0], hi, lo)

idx_bits = [idx[k:k+1] for k in range(5)][::-1]
next_state <<= build_tree(values, idx_bits)

current_state <<= mux(reset, Const(0, UInt(3)), next_state)
output_signal <<= ~current_state[0:1]

m.to_verilog_file("design.v")

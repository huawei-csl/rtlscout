"""SpireHDL port of `top` (pcie) — scrambler → encoder → PISO → SIPO → decoder → descrambler.

Mirrors rtl_dataset/pcie.v0.v's 7 submodules inlined into one Module. The
verilog top hardcodes the encoder/decoder's `rd=1` and `k=0` inputs, so this
port only implements the (k=0, rd=1) branches of the 8b/10b lookup tables
(the `if (k) … else …` constant branch is dead code under the top's wiring).

Reset semantics for every submodule's flop: `always @(posedge clk or
negedge rst)` — async active-low rst. Use `with_reset=False` + explicit
`mux(~rst, init, next)` per register (the reset port is named `rst`, but
spirehdl's `with_reset=True` async-reset emits `posedge rst` not
`negedge rst` — so we drive it explicitly).
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, Wire, Const, mux, cat

m = Module("top", with_clock=True, with_reset=False)

rst    = m.input(UInt(1), "rst")
s_en   = m.input(UInt(1), "s_en")
d_en   = m.input(UInt(1), "d_en")
m_piso = m.input(UInt(1), "m_piso")
m_sipo = m.input(UInt(1), "m_sipo")
datain = m.input(UInt(8), "datain")
dataout = m.output(UInt(8), "dataout")

# Encoder (k=0): 256 entries (data_in → 10-bit posrd encoding)
ENCODER = {
    0x00: 0b0110001011,
    0x01: 0b1000101011,
    0x02: 0b0100101011,
    0x03: 0b1100010100,
    0x04: 0b0010101011,
    0x05: 0b1010010100,
    0x06: 0b0110010100,
    0x07: 0b0001110100,
    0x08: 0b0001101011,
    0x09: 0b1001010100,
    0x0a: 0b0101010100,
    0x0b: 0b1101000100,
    0x0c: 0b0011010100,
    0x0d: 0b1011000100,
    0x0e: 0b0111000100,
    0x0f: 0b1010001011,
    0x10: 0b1001001011,
    0x11: 0b1000110100,
    0x12: 0b0100110100,
    0x13: 0b1100100100,
    0x14: 0b0010110100,
    0x15: 0b1010100100,
    0x16: 0b0110100100,
    0x17: 0b0001011011,
    0x18: 0b0011001011,
    0x19: 0b1001100100,
    0x1a: 0b0101100100,
    0x1b: 0b0010011011,
    0x1c: 0b0011100100,
    0x1d: 0b0100011011,
    0x1e: 0b1000011011,
    0x1f: 0b0101001011,
    0x20: 0b0110001001,
    0x21: 0b1000101001,
    0x22: 0b0100101001,
    0x23: 0b1100011001,
    0x24: 0b0010101001,
    0x25: 0b1010011001,
    0x26: 0b0110011001,
    0x27: 0b0001111001,
    0x28: 0b0001101001,
    0x29: 0b1001011001,
    0x2a: 0b0101011001,
    0x2b: 0b1101001001,
    0x2c: 0b0011011001,
    0x2d: 0b1011001001,
    0x2e: 0b0111001001,
    0x2f: 0b1010001001,
    0x30: 0b1001001001,
    0x31: 0b1000111001,
    0x32: 0b0100111001,
    0x33: 0b1100101001,
    0x34: 0b0010111001,
    0x35: 0b1010101001,
    0x36: 0b0110101001,
    0x37: 0b0001011001,
    0x38: 0b0011001001,
    0x39: 0b1001101001,
    0x3a: 0b0101101001,
    0x3b: 0b0010011001,
    0x3c: 0b0011101001,
    0x3d: 0b0100011001,
    0x3e: 0b1000011001,
    0x3f: 0b0101001001,
    0x40: 0b0110000101,
    0x41: 0b1000100101,
    0x42: 0b0100100101,
    0x43: 0b1100010101,
    0x44: 0b0010100101,
    0x45: 0b1010010101,
    0x46: 0b0110010101,
    0x47: 0b0001110101,
    0x48: 0b0001100101,
    0x49: 0b1001010101,
    0x4a: 0b0101010101,
    0x4b: 0b1101000101,
    0x4c: 0b0011010101,
    0x4d: 0b1011000101,
    0x4e: 0b0111000101,
    0x4f: 0b1010000101,
    0x50: 0b1001000101,
    0x51: 0b1000110101,
    0x52: 0b0100110101,
    0x53: 0b1100100101,
    0x54: 0b0010110101,
    0x55: 0b1010100101,
    0x56: 0b0110100101,
    0x57: 0b0001010101,
    0x58: 0b0011000101,
    0x59: 0b1001100101,
    0x5a: 0b0101100101,
    0x5b: 0b0010010101,
    0x5c: 0b0011100101,
    0x5d: 0b0100010101,
    0x5e: 0b1000010101,
    0x5f: 0b0101000101,
    0x60: 0b0110001100,
    0x61: 0b1000101100,
    0x62: 0b0100101100,
    0x63: 0b1100010011,
    0x64: 0b0010101100,
    0x65: 0b1010010011,
    0x66: 0b0110010011,
    0x67: 0b0001110011,
    0x68: 0b0001101100,
    0x69: 0b1001010011,
    0x6a: 0b0101010011,
    0x6b: 0b1101000011,
    0x6c: 0b0011010011,
    0x6d: 0b1011000011,
    0x6e: 0b0111000011,
    0x6f: 0b1010001100,
    0x70: 0b1001001100,
    0x71: 0b1000110011,
    0x72: 0b0100110011,
    0x73: 0b1100100011,
    0x74: 0b0010110011,
    0x75: 0b1010100011,
    0x76: 0b0110100011,
    0x77: 0b0001011100,
    0x78: 0b0011001100,
    0x79: 0b1001100011,
    0x7a: 0b0101100011,
    0x7b: 0b0010011100,
    0x7c: 0b0011100011,
    0x7d: 0b0100011100,
    0x7e: 0b1000011100,
    0x7f: 0b0101001100,
    0x80: 0b0110001101,
    0x81: 0b1000101101,
    0x82: 0b0100101101,
    0x83: 0b1100010010,
    0x84: 0b0010101101,
    0x85: 0b1010010010,
    0x86: 0b0110010010,
    0x87: 0b0001110010,
    0x88: 0b0001101101,
    0x89: 0b1001010010,
    0x8a: 0b0101010010,
    0x8b: 0b0010100010,
    0x8c: 0b0011010010,
    0x8d: 0b1011000010,
    0x8e: 0b0111000010,
    0x8f: 0b1010001101,
    0x90: 0b1001001101,
    0x91: 0b1000110010,
    0x92: 0b0100110010,
    0x93: 0b1100100010,
    0x94: 0b0010110010,
    0x95: 0b1010100010,
    0x96: 0b0110100010,
    0x97: 0b0001011101,
    0x98: 0b0011001101,
    0x99: 0b1001100010,
    0x9a: 0b0101100010,
    0x9b: 0b0010011101,
    0x9c: 0b0011100010,
    0x9d: 0b0100011101,
    0x9e: 0b1000011101,
    0x9f: 0b0101001101,
    0xa0: 0b0110001010,
    0xa1: 0b1000101010,
    0xa2: 0b0100101010,
    0xa3: 0b1100011010,
    0xa4: 0b0010101010,
    0xa5: 0b1010011010,
    0xa6: 0b0110011010,
    0xa7: 0b0001111010,
    0xa8: 0b0001101010,
    0xa9: 0b1001011010,
    0xaa: 0b0101011010,
    0xab: 0b1101001010,
    0xac: 0b0011011010,
    0xad: 0b1011001010,
    0xae: 0b0111001010,
    0xaf: 0b1010001010,
    0xb0: 0b1001001010,
    0xb1: 0b1000111010,
    0xb2: 0b0100111010,
    0xb3: 0b1100101010,
    0xb4: 0b0010111010,
    0xb5: 0b1010101010,
    0xb6: 0b0110101010,
    0xb7: 0b0001011010,
    0xb8: 0b0011001010,
    0xb9: 0b1001101010,
    0xba: 0b0101101010,
    0xbb: 0b0010011010,
    0xbc: 0b0011101010,
    0xbd: 0b0100011010,
    0xbe: 0b1000011010,
    0xbf: 0b0101001010,
    0xc0: 0b0110000110,
    0xc1: 0b1000100110,
    0xc2: 0b0100100110,
    0xc3: 0b1100010110,
    0xc4: 0b0010100110,
    0xc5: 0b1010010110,
    0xc6: 0b0110010110,
    0xc7: 0b0001110110,
    0xc8: 0b0001100110,
    0xc9: 0b1001010110,
    0xca: 0b0101010110,
    0xcb: 0b1101000110,
    0xcc: 0b0011010110,
    0xcd: 0b1011000110,
    0xce: 0b0111000110,
    0xcf: 0b1010000110,
    0xd0: 0b1001000110,
    0xd1: 0b1000110110,
    0xd2: 0b0100110110,
    0xd3: 0b1100100110,
    0xd4: 0b0010110110,
    0xd5: 0b1010100110,
    0xd6: 0b0110100110,
    0xd7: 0b0001010110,
    0xd8: 0b0011000110,
    0xd9: 0b1001100110,
    0xda: 0b0101100110,
    0xdb: 0b0010010110,
    0xdc: 0b0011100110,
    0xdd: 0b0100010110,
    0xde: 0b1000010110,
    0xdf: 0b0101000110,
    0xe0: 0b0110001110,
    0xe1: 0b1000101110,
    0xe2: 0b0100101110,
    0xe3: 0b1100010001,
    0xe4: 0b0010101110,
    0xe5: 0b1010010001,
    0xe6: 0b0110010001,
    0xe7: 0b0001110001,
    0xe8: 0b0001101110,
    0xe9: 0b1001010001,
    0xea: 0b0101010001,
    0xeb: 0b1101001000,
    0xec: 0b0011010001,
    0xed: 0b1011001000,
    0xee: 0b0111001000,
    0xef: 0b1010001110,
    0xf0: 0b1001001110,
    0xf1: 0b1000110001,
    0xf2: 0b0100110001,
    0xf3: 0b1100100001,
    0xf4: 0b0010110001,
    0xf5: 0b1010100001,
    0xf6: 0b0110100001,
    0xf7: 0b0001011110,
    0xf8: 0b0011001110,
    0xf9: 0b1001100001,
    0xfa: 0b0101100001,
    0xfb: 0b0010011110,
    0xfc: 0b0011100001,
    0xfd: 0b0100011110,
    0xfe: 0b1000011110,
    0xff: 0b0101001110,
}

# Decoder (k=0, rd=1): 256 entries (10-bit → 8-bit)
DECODER = {
    0b0001010101: 0x57,
    0b0001010110: 0xd7,
    0b0001011001: 0x37,
    0b0001011010: 0xb7,
    0b0001011011: 0x17,
    0b0001011100: 0x77,
    0b0001011101: 0x97,
    0b0001011110: 0xf7,
    0b0001100101: 0x48,
    0b0001100110: 0xc8,
    0b0001101001: 0x28,
    0b0001101010: 0xa8,
    0b0001101011: 0x08,
    0b0001101100: 0x68,
    0b0001101101: 0x88,
    0b0001101110: 0xe8,
    0b0001110001: 0xe7,
    0b0001110010: 0x87,
    0b0001110011: 0x67,
    0b0001110100: 0x07,
    0b0001110101: 0x47,
    0b0001110110: 0xc7,
    0b0001111001: 0x27,
    0b0001111010: 0xa7,
    0b0010010101: 0x5b,
    0b0010010110: 0xdb,
    0b0010011001: 0x3b,
    0b0010011010: 0xbb,
    0b0010011011: 0x1b,
    0b0010011100: 0x7b,
    0b0010011101: 0x9b,
    0b0010011110: 0xfb,
    0b0010100010: 0x8b,
    0b0010100101: 0x44,
    0b0010100110: 0xc4,
    0b0010101001: 0x24,
    0b0010101010: 0xa4,
    0b0010101011: 0x04,
    0b0010101100: 0x64,
    0b0010101101: 0x84,
    0b0010101110: 0xe4,
    0b0010110001: 0xf4,
    0b0010110010: 0x94,
    0b0010110011: 0x74,
    0b0010110100: 0x14,
    0b0010110101: 0x54,
    0b0010110110: 0xd4,
    0b0010111001: 0x34,
    0b0010111010: 0xb4,
    0b0011000101: 0x58,
    0b0011000110: 0xd8,
    0b0011001001: 0x38,
    0b0011001010: 0xb8,
    0b0011001011: 0x18,
    0b0011001100: 0x78,
    0b0011001101: 0x98,
    0b0011001110: 0xf8,
    0b0011010001: 0xec,
    0b0011010010: 0x8c,
    0b0011010011: 0x6c,
    0b0011010100: 0x0c,
    0b0011010101: 0x4c,
    0b0011010110: 0xcc,
    0b0011011001: 0x2c,
    0b0011011010: 0xac,
    0b0011100001: 0xfc,
    0b0011100010: 0x9c,
    0b0011100011: 0x7c,
    0b0011100100: 0x1c,
    0b0011100101: 0x5c,
    0b0011100110: 0xdc,
    0b0011101001: 0x3c,
    0b0011101010: 0xbc,
    0b0100010101: 0x5d,
    0b0100010110: 0xdd,
    0b0100011001: 0x3d,
    0b0100011010: 0xbd,
    0b0100011011: 0x1d,
    0b0100011100: 0x7d,
    0b0100011101: 0x9d,
    0b0100011110: 0xfd,
    0b0100100101: 0x42,
    0b0100100110: 0xc2,
    0b0100101001: 0x22,
    0b0100101010: 0xa2,
    0b0100101011: 0x02,
    0b0100101100: 0x62,
    0b0100101101: 0x82,
    0b0100101110: 0xe2,
    0b0100110001: 0xf2,
    0b0100110010: 0x92,
    0b0100110011: 0x72,
    0b0100110100: 0x12,
    0b0100110101: 0x52,
    0b0100110110: 0xd2,
    0b0100111001: 0x32,
    0b0100111010: 0xb2,
    0b0101000101: 0x5f,
    0b0101000110: 0xdf,
    0b0101001001: 0x3f,
    0b0101001010: 0xbf,
    0b0101001011: 0x1f,
    0b0101001100: 0x7f,
    0b0101001101: 0x9f,
    0b0101001110: 0xff,
    0b0101010001: 0xea,
    0b0101010010: 0x8a,
    0b0101010011: 0x6a,
    0b0101010100: 0x0a,
    0b0101010101: 0x4a,
    0b0101010110: 0xca,
    0b0101011001: 0x2a,
    0b0101011010: 0xaa,
    0b0101100001: 0xfa,
    0b0101100010: 0x9a,
    0b0101100011: 0x7a,
    0b0101100100: 0x1a,
    0b0101100101: 0x5a,
    0b0101100110: 0xda,
    0b0101101001: 0x3a,
    0b0101101010: 0xba,
    0b0110000101: 0x40,
    0b0110000110: 0xc0,
    0b0110001001: 0x20,
    0b0110001010: 0xa0,
    0b0110001011: 0x00,
    0b0110001100: 0x60,
    0b0110001101: 0x80,
    0b0110001110: 0xe0,
    0b0110010001: 0xe6,
    0b0110010010: 0x86,
    0b0110010011: 0x66,
    0b0110010100: 0x06,
    0b0110010101: 0x46,
    0b0110010110: 0xc6,
    0b0110011001: 0x26,
    0b0110011010: 0xa6,
    0b0110100001: 0xf6,
    0b0110100010: 0x96,
    0b0110100011: 0x76,
    0b0110100100: 0x16,
    0b0110100101: 0x56,
    0b0110100110: 0xd6,
    0b0110101001: 0x36,
    0b0110101010: 0xb6,
    0b0111000010: 0x8e,
    0b0111000011: 0x6e,
    0b0111000100: 0x0e,
    0b0111000101: 0x4e,
    0b0111000110: 0xce,
    0b0111001000: 0xee,
    0b0111001001: 0x2e,
    0b0111001010: 0xae,
    0b1000010101: 0x5e,
    0b1000010110: 0xde,
    0b1000011001: 0x3e,
    0b1000011010: 0xbe,
    0b1000011011: 0x1e,
    0b1000011100: 0x7e,
    0b1000011101: 0x9e,
    0b1000011110: 0xfe,
    0b1000100101: 0x41,
    0b1000100110: 0xc1,
    0b1000101001: 0x21,
    0b1000101010: 0xa1,
    0b1000101011: 0x01,
    0b1000101100: 0x61,
    0b1000101101: 0x81,
    0b1000101110: 0xe1,
    0b1000110001: 0xf1,
    0b1000110010: 0x91,
    0b1000110011: 0x71,
    0b1000110100: 0x11,
    0b1000110101: 0x51,
    0b1000110110: 0xd1,
    0b1000111001: 0x31,
    0b1000111010: 0xb1,
    0b1001000101: 0x50,
    0b1001000110: 0xd0,
    0b1001001001: 0x30,
    0b1001001010: 0xb0,
    0b1001001011: 0x10,
    0b1001001100: 0x70,
    0b1001001101: 0x90,
    0b1001001110: 0xf0,
    0b1001010001: 0xe9,
    0b1001010010: 0x89,
    0b1001010011: 0x69,
    0b1001010100: 0x09,
    0b1001010101: 0x49,
    0b1001010110: 0xc9,
    0b1001011001: 0x29,
    0b1001011010: 0xa9,
    0b1001100001: 0xf9,
    0b1001100010: 0x99,
    0b1001100011: 0x79,
    0b1001100100: 0x19,
    0b1001100101: 0x59,
    0b1001100110: 0xd9,
    0b1001101001: 0x39,
    0b1001101010: 0xb9,
    0b1010000101: 0x4f,
    0b1010000110: 0xcf,
    0b1010001001: 0x2f,
    0b1010001010: 0xaf,
    0b1010001011: 0x0f,
    0b1010001100: 0x6f,
    0b1010001101: 0x8f,
    0b1010001110: 0xef,
    0b1010010001: 0xe5,
    0b1010010010: 0x85,
    0b1010010011: 0x65,
    0b1010010100: 0x05,
    0b1010010101: 0x45,
    0b1010010110: 0xc5,
    0b1010011001: 0x25,
    0b1010011010: 0xa5,
    0b1010100001: 0xf5,
    0b1010100010: 0x95,
    0b1010100011: 0x75,
    0b1010100100: 0x15,
    0b1010100101: 0x55,
    0b1010100110: 0xd5,
    0b1010101001: 0x35,
    0b1010101010: 0xb5,
    0b1011000010: 0x8d,
    0b1011000011: 0x6d,
    0b1011000100: 0x0d,
    0b1011000101: 0x4d,
    0b1011000110: 0xcd,
    0b1011001000: 0xed,
    0b1011001001: 0x2d,
    0b1011001010: 0xad,
    0b1100010001: 0xe3,
    0b1100010010: 0x83,
    0b1100010011: 0x63,
    0b1100010100: 0x03,
    0b1100010101: 0x43,
    0b1100010110: 0xc3,
    0b1100011001: 0x23,
    0b1100011010: 0xa3,
    0b1100100001: 0xf3,
    0b1100100010: 0x93,
    0b1100100011: 0x73,
    0b1100100100: 0x13,
    0b1100100101: 0x53,
    0b1100100110: 0xd3,
    0b1100101001: 0x33,
    0b1100101010: 0xb3,
    0b1101000011: 0x6b,
    0b1101000100: 0x0b,
    0b1101000101: 0x4b,
    0b1101000110: 0xcb,
    0b1101001000: 0xeb,
    0b1101001001: 0x2b,
    0b1101001010: 0xab,
}


rstn_inv = Wire(UInt(1), name="rstn_inv"); rstn_inv <<= ~rst  # reset-active = ~rst (rst active-low)

# Default PCIe LFSR seed (used by both scrambler and descrambler)
PCIE_LFSR_SEED = 0b1100_1010_0001_1110


# ===========================================================================
# scrambler — 16-bit LFSR, 8 bits scrambled per cycle.
# Combinationally unrolls the 8-iteration for-loop from the verilog.
# ===========================================================================
def make_scrambler(scrambler_en, scrambler_in):
    lfsr_r = Register(UInt(16), name="scr_lfsr")
    dout_r = Register(UInt(8),  name="scr_dout")

    # Unroll the 8-iteration scrambling loop.
    cur_lfsr = lfsr_r
    scrambled_bits = []  # bit i of output
    for i in range(8):
        msb = cur_lfsr[15]                              # temp_lfsr[15]
        scrambled_bits.append(scrambler_in[i] ^ msb)    # datain[i] ^ msb
        # feedback = temp_lfsr[15] ^ temp_lfsr[4] ^ temp_lfsr[3] ^ temp_lfsr[2]
        feedback = cur_lfsr[15] ^ cur_lfsr[4] ^ cur_lfsr[3] ^ cur_lfsr[2]
        # new temp_lfsr = {temp_lfsr[14:0], feedback}
        # cat is LSB-first: cat(feedback, lfsr[0:15]) → {lfsr[14:0], feedback} in verilog notation
        cur_lfsr = cat(feedback, cur_lfsr[0:15])

    new_lfsr = cur_lfsr  # final LFSR state after 8 iterations
    scrambled = cat(*scrambled_bits)  # LSB-first → bit 0 first

    # Sequential update: if !rst → SEED/0; else if enable → update; else hold
    lfsr_next = mux(scrambler_en, new_lfsr, lfsr_r)
    dout_next = mux(scrambler_en, scrambled, dout_r)
    lfsr_r <<= mux(rstn_inv, Const(PCIE_LFSR_SEED, UInt(16)), lfsr_next)
    dout_r <<= mux(rstn_inv, Const(0, UInt(8)), dout_next)
    return dout_r


# ===========================================================================
# encoder — 8b/10b lookup with k=0/rd=1 hardcoded by the top wiring.
# Only need the k=0 branch; only need the posrd column (rd=1).
# Translates to a 256-entry mux tree. yosys+abc collapses to ~40 cells.
# ===========================================================================
def make_encoder(data_in_8):
    """Combinational lookup data_in[7:0] → 10-bit 8b/10b code (rd=1, k=0).

    Built as a balanced binary mux tree using BITS of `data_in_8` as selects:
    256 leaves → 128 → ... → 1, 8 levels of 2:1 muxes. Synthesises to native
    MUX2 cells in nangate45 with O(log N) delay. The previous form
    (linear cascade `mux(data_in == Const(di), ..., chain)` over the dict)
    made yosys+abc build a deeper AOI/OAI gate chain (see router for
    the same diagnosis & fix).
    """
    out = Wire(UInt(10), name="enc_out")
    leaves = [Const(ENCODER[k], UInt(10)) for k in range(256)]
    for bit in range(8):
        leaves = [mux(data_in_8[bit], leaves[i + 1], leaves[i])
                  for i in range(0, len(leaves), 2)]
    out <<= leaves[0]
    return out


# ===========================================================================
# piso — parallel-in serial-out shift register, mode-controlled.
#   mode=1: load `in` into temp.
#   mode=0: shift out LSB on `out`, shift temp right (zero-fill).
# ===========================================================================
def make_piso(piso_in):
    temp_r = Register(UInt(10), name="piso_temp")
    out_r  = Register(UInt(1),  name="piso_out")

    temp_next = mux(m_piso, piso_in, cat(temp_r[1:10], Const(0, UInt(1))))
    # ↑ cat is LSB-first: lower 9 bits = temp_r[1:10] (= verilog temp[9:1]),
    #   top bit (=verilog [9]) = 0 → matches verilog `{1'b0, temp[WIDTH-1:1]}`
    out_next  = mux(m_piso, out_r,   temp_r[0])  # if mode → hold out; else → temp[0]

    temp_r <<= mux(rstn_inv, Const(0, UInt(10)), temp_next)
    out_r  <<= mux(rstn_inv, Const(0, UInt(1)),  out_next)
    return out_r


# ===========================================================================
# sipo — serial-in parallel-out shift register, mode-controlled.
#   mode=1: shift `in` into MSB, temp right-shifts.
#   mode=0: snapshot temp → out.
# ===========================================================================
def make_sipo(sipo_in):
    temp_r = Register(UInt(10), name="sipo_temp")
    out_r  = Register(UInt(10), name="sipo_out")

    # mode=1: temp <= {in, temp[width-1:1]} = LSB-first cat(temp[1:10], in)
    temp_next = mux(m_sipo, cat(temp_r[1:10], sipo_in), temp_r)
    # mode=0: out <= temp
    out_next  = mux(m_sipo, out_r, temp_r)

    temp_r <<= mux(rstn_inv, Const(0, UInt(10)), temp_next)
    out_r  <<= mux(rstn_inv, Const(0, UInt(10)), out_next)
    return out_r


# ===========================================================================
# decoder — 8b/10b reverse lookup with k=0/rd=1 hardcoded.
# Inputs is `dec_in` (10-bit). Output is 8-bit byte.
# Only need rd=1 branch of k=0 table.
# ===========================================================================
def make_decoder(dec_in_10):
    out = Wire(UInt(8), name="dec_out")
    chain = Const(0, UInt(8))  # default for unmapped codes
    for code, byte in DECODER.items():
        chain = mux(dec_in_10 == Const(code, UInt(10)), Const(byte, UInt(8)), chain)
    out <<= chain
    return out


# ===========================================================================
# descrambler — same LFSR as scrambler but with `enable` gating + the 8-step
# loop computed inside the always-edge block (so the new lfsr/dataout are
# committed only when enable=1). Equivalent combinationally to the scrambler
# loop above; the difference is whether the seed/output update on every cycle
# (scrambler always evaluates the combinational block) vs only when enabled
# (descrambler gates the registered output).
# ===========================================================================
def make_descrambler(des_in):
    lfsr_r   = Register(UInt(16), name="des_lfsr")
    dout_r   = Register(UInt(8),  name="des_dout")

    cur_lfsr = lfsr_r
    descrambled_bits = []
    for i in range(8):
        msb = cur_lfsr[15]
        descrambled_bits.append(des_in[i] ^ msb)
        feedback = cur_lfsr[15] ^ cur_lfsr[4] ^ cur_lfsr[3] ^ cur_lfsr[2]
        cur_lfsr = cat(feedback, cur_lfsr[0:15])
    new_lfsr     = cur_lfsr
    descrambled  = cat(*descrambled_bits)

    lfsr_next = mux(d_en, new_lfsr, lfsr_r)
    dout_next = mux(d_en, descrambled, dout_r)
    lfsr_r <<= mux(rstn_inv, Const(PCIE_LFSR_SEED, UInt(16)), lfsr_next)
    dout_r <<= mux(rstn_inv, Const(0, UInt(8)), dout_next)
    return dout_r


# ===========================================================================
# Wire it all up — scrambler → encoder → PISO → SIPO → decoder → descrambler
# ===========================================================================
s_out  = make_scrambler(s_en, datain)
e_out  = make_encoder(s_out)
p_out  = make_piso(e_out)
dec_in = make_sipo(p_out)
des_in = make_decoder(dec_in)
final  = make_descrambler(des_in)

dataout <<= final

m.to_verilog_file("design.v")

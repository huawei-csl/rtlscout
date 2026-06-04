"""SpireHDL port of `datapath` — AES datapath (1064 LOC, 7 modules).

All 7 verilog submodules inlined into one SpireHDL `Module`. The 250-LOC
GF-math `sBox_8` is replaced with 4 precomputed 256-entry LUTs (one per
{enc/dec output, enc_dec input mode} combination). The verilog computes
both outputs from a SHARED input pipeline whose isomorphism transform
depends on `enc_dec`, producing "garbage" patterns for the off-axis
output (sbox_out_enc when enc_dec=DEC, sbox_out_dec when enc_dec=ENC).
The downstream logic feeds sbox_out_enc into key_expander regardless of
enc_dec, so those garbage values must be replicated faithfully.

Reset semantics: `always @(posedge clk, negedge rst_n)` — async active-low
rst_n. Standard `with_reset=False` + `mux(rst_active, init, next)` pattern.
"""
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register, Wire, Const, mux, cat

# ============================================================================
# AES S-box tables for sBox_8 — 4 tables.
# See _debug/compute_sbox_tables.py for the Python sim of the verilog GF math.
# ============================================================================
SBOX_ENC_OUT_WHEN_ENC = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
SBOX_ENC_OUT_WHEN_DEC = [
    0x6b, 0x84, 0x81, 0xb9, 0x71, 0x33, 0x6c, 0x89, 0x5b, 0xa4, 0x2e, 0xa7, 0xf3, 0x18, 0x87, 0xe0,
    0x32, 0xe9, 0x96, 0xd2, 0xc4, 0x25, 0x9c, 0xb1, 0x0d, 0x56, 0x85, 0xd8, 0x57, 0x60, 0x2f, 0xf2,
    0x29, 0x6f, 0x61, 0x4f, 0x4d, 0x15, 0xa1, 0xea, 0x72, 0x20, 0x7e, 0xba, 0x9a, 0xff, 0x0a, 0x1e,
    0x9b, 0x3a, 0x10, 0x05, 0x78, 0x3d, 0xfc, 0xc0, 0xf4, 0x8c, 0x31, 0x43, 0xdc, 0x35, 0xc5, 0xe3,
    0x88, 0xc1, 0x7b, 0x3b, 0xae, 0xbf, 0xe5, 0xd0, 0xa6, 0x73, 0xd1, 0xaf, 0xce, 0x24, 0xbc, 0x23,
    0xc3, 0xb6, 0x5c, 0x55, 0xa2, 0x53, 0x19, 0x1c, 0xef, 0xf1, 0xe6, 0x08, 0x52, 0x77, 0x86, 0x90,
    0x1d, 0x22, 0xd6, 0x63, 0x68, 0x7a, 0xfb, 0xa5, 0x64, 0xb4, 0xad, 0x00, 0x06, 0xdf, 0xc7, 0x21,
    0xda, 0x04, 0x28, 0x49, 0xed, 0xd4, 0xc6, 0x5d, 0x34, 0xaa, 0x65, 0x42, 0x7c, 0xb3, 0x2a, 0x9e,
    0xb7, 0x02, 0x8d, 0xbb, 0x01, 0x1a, 0x5e, 0x0e, 0x40, 0x07, 0x8e, 0x91, 0x39, 0x82, 0x8a, 0x97,
    0x5f, 0x8b, 0xca, 0xbe, 0x95, 0x94, 0x12, 0x8f, 0xf6, 0xde, 0x2c, 0x30, 0x16, 0xd5, 0x7f, 0xfd,
    0xf9, 0x26, 0x54, 0xa9, 0x09, 0x67, 0x48, 0x0b, 0xe2, 0xa3, 0x79, 0xd9, 0xc9, 0x6a, 0x44, 0x4b,
    0xbd, 0x17, 0xcb, 0x7d, 0x69, 0xe4, 0x51, 0x80, 0xdb, 0x03, 0x2b, 0x83, 0x4e, 0xb0, 0x93, 0x45,
    0x37, 0x41, 0xf7, 0x50, 0x14, 0x3e, 0x76, 0x6e, 0xe1, 0xac, 0x92, 0xb2, 0xdd, 0xec, 0x4c, 0xf0,
    0x47, 0x4a, 0x13, 0xe8, 0x75, 0x9d, 0x62, 0xf8, 0x1b, 0xab, 0x70, 0xb8, 0x3c, 0xcc, 0x99, 0x6d,
    0x0f, 0xc8, 0xa8, 0x3f, 0xb5, 0x46, 0x5a, 0xfe, 0xd3, 0x11, 0x27, 0xf5, 0xcd, 0x74, 0xfa, 0x58,
    0xcf, 0x59, 0x1f, 0x0c, 0x38, 0xeb, 0x98, 0xc2, 0xd7, 0xa0, 0xee, 0x66, 0x36, 0x9f, 0xe7, 0x2d,
]
SBOX_DEC_OUT_WHEN_DEC = [
    0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36, 0xa5, 0x38, 0xbf, 0x40, 0xa3, 0x9e, 0x81, 0xf3, 0xd7, 0xfb,
    0x7c, 0xe3, 0x39, 0x82, 0x9b, 0x2f, 0xff, 0x87, 0x34, 0x8e, 0x43, 0x44, 0xc4, 0xde, 0xe9, 0xcb,
    0x54, 0x7b, 0x94, 0x32, 0xa6, 0xc2, 0x23, 0x3d, 0xee, 0x4c, 0x95, 0x0b, 0x42, 0xfa, 0xc3, 0x4e,
    0x08, 0x2e, 0xa1, 0x66, 0x28, 0xd9, 0x24, 0xb2, 0x76, 0x5b, 0xa2, 0x49, 0x6d, 0x8b, 0xd1, 0x25,
    0x72, 0xf8, 0xf6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xd4, 0xa4, 0x5c, 0xcc, 0x5d, 0x65, 0xb6, 0x92,
    0x6c, 0x70, 0x48, 0x50, 0xfd, 0xed, 0xb9, 0xda, 0x5e, 0x15, 0x46, 0x57, 0xa7, 0x8d, 0x9d, 0x84,
    0x90, 0xd8, 0xab, 0x00, 0x8c, 0xbc, 0xd3, 0x0a, 0xf7, 0xe4, 0x58, 0x05, 0xb8, 0xb3, 0x45, 0x06,
    0xd0, 0x2c, 0x1e, 0x8f, 0xca, 0x3f, 0x0f, 0x02, 0xc1, 0xaf, 0xbd, 0x03, 0x01, 0x13, 0x8a, 0x6b,
    0x3a, 0x91, 0x11, 0x41, 0x4f, 0x67, 0xdc, 0xea, 0x97, 0xf2, 0xcf, 0xce, 0xf0, 0xb4, 0xe6, 0x73,
    0x96, 0xac, 0x74, 0x22, 0xe7, 0xad, 0x35, 0x85, 0xe2, 0xf9, 0x37, 0xe8, 0x1c, 0x75, 0xdf, 0x6e,
    0x47, 0xf1, 0x1a, 0x71, 0x1d, 0x29, 0xc5, 0x89, 0x6f, 0xb7, 0x62, 0x0e, 0xaa, 0x18, 0xbe, 0x1b,
    0xfc, 0x56, 0x3e, 0x4b, 0xc6, 0xd2, 0x79, 0x20, 0x9a, 0xdb, 0xc0, 0xfe, 0x78, 0xcd, 0x5a, 0xf4,
    0x1f, 0xdd, 0xa8, 0x33, 0x88, 0x07, 0xc7, 0x31, 0xb1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xec, 0x5f,
    0x60, 0x51, 0x7f, 0xa9, 0x19, 0xb5, 0x4a, 0x0d, 0x2d, 0xe5, 0x7a, 0x9f, 0x93, 0xc9, 0x9c, 0xef,
    0xa0, 0xe0, 0x3b, 0x4d, 0xae, 0x2a, 0xf5, 0xb0, 0xc8, 0xeb, 0xbb, 0x3c, 0x83, 0x53, 0x99, 0x61,
    0x17, 0x2b, 0x04, 0x7e, 0xba, 0x77, 0xd6, 0x26, 0xe1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0c, 0x7d,
]
SBOX_DEC_OUT_WHEN_ENC = [
    0x00, 0x01, 0x8d, 0xf6, 0xcb, 0x52, 0x7b, 0xd1, 0xe8, 0x4f, 0x29, 0xc0, 0xb0, 0xe1, 0xe5, 0xc7,
    0x74, 0xb4, 0xaa, 0x4b, 0x99, 0x2b, 0x60, 0x5f, 0x58, 0x3f, 0xfd, 0xcc, 0xff, 0x40, 0xee, 0xb2,
    0x3a, 0x6e, 0x5a, 0xf1, 0x55, 0x4d, 0xa8, 0xc9, 0xc1, 0x0a, 0x98, 0x15, 0x30, 0x44, 0xa2, 0xc2,
    0x2c, 0x45, 0x92, 0x6c, 0xf3, 0x39, 0x66, 0x42, 0xf2, 0x35, 0x20, 0x6f, 0x77, 0xbb, 0x59, 0x19,
    0x1d, 0xfe, 0x37, 0x67, 0x2d, 0x31, 0xf5, 0x69, 0xa7, 0x64, 0xab, 0x13, 0x54, 0x25, 0xe9, 0x09,
    0xed, 0x5c, 0x05, 0xca, 0x4c, 0x24, 0x87, 0xbf, 0x18, 0x3e, 0x22, 0xf0, 0x51, 0xec, 0x61, 0x17,
    0x16, 0x5e, 0xaf, 0xd3, 0x49, 0xa6, 0x36, 0x43, 0xf4, 0x47, 0x91, 0xdf, 0x33, 0x93, 0x21, 0x3b,
    0x79, 0xb7, 0x97, 0x85, 0x10, 0xb5, 0xba, 0x3c, 0xb6, 0x70, 0xd0, 0x06, 0xa1, 0xfa, 0x81, 0x82,
    0x83, 0x7e, 0x7f, 0x80, 0x96, 0x73, 0xbe, 0x56, 0x9b, 0x9e, 0x95, 0xd9, 0xf7, 0x02, 0xb9, 0xa4,
    0xde, 0x6a, 0x32, 0x6d, 0xd8, 0x8a, 0x84, 0x72, 0x2a, 0x14, 0x9f, 0x88, 0xf9, 0xdc, 0x89, 0x9a,
    0xfb, 0x7c, 0x2e, 0xc3, 0x8f, 0xb8, 0x65, 0x48, 0x26, 0xc8, 0x12, 0x4a, 0xce, 0xe7, 0xd2, 0x62,
    0x0c, 0xe0, 0x1f, 0xef, 0x11, 0x75, 0x78, 0x71, 0xa5, 0x8e, 0x76, 0x3d, 0xbd, 0xbc, 0x86, 0x57,
    0x0b, 0x28, 0x2f, 0xa3, 0xda, 0xd4, 0xe4, 0x0f, 0xa9, 0x27, 0x53, 0x04, 0x1b, 0xfc, 0xac, 0xe6,
    0x7a, 0x07, 0xae, 0x63, 0xc5, 0xdb, 0xe2, 0xea, 0x94, 0x8b, 0xc4, 0xd5, 0x9d, 0xf8, 0x90, 0x6b,
    0xb1, 0x0d, 0xd6, 0xeb, 0xc6, 0x0e, 0xcf, 0xad, 0x08, 0x4e, 0xd7, 0xe3, 0x5d, 0x50, 0x1e, 0xb3,
    0x5b, 0x23, 0x38, 0x34, 0x68, 0x46, 0x03, 0x8c, 0xdd, 0x9c, 0x7d, 0xa0, 0xcd, 0x1a, 0x41, 0x1c,
]

# Localparams from verilog
COL_0      = 0b000
COL_1      = 0b001
COL_2      = 0b010
COL_3      = 0b011
G_FUNCTION = 0b100

COL_RK      = 0b00      # COL (rk_sel)
MIXCOL_IN   = 0b01
MIXCOL_OUT  = 0b10

KEY_0 = 0b00
KEY_1 = 0b01
KEY_2 = 0b10
KEY_3 = 0b11

SHIFT_ROWS  = 0b00
ADD_RK_OUT  = 0b01
INPUT_SEL   = 0b10

KEY_HOST = 0
KEY_OUT  = 1

# ============================================================================
m = Module("datapath", with_clock=True, with_reset=False)

# === Top-level ports (mirror verilog port list verbatim) ===
bus_in           = m.input(UInt(32), "bus_in")
data_type        = m.input(UInt(2),  "data_type")
rk_sel           = m.input(UInt(2),  "rk_sel")
key_out_sel      = m.input(UInt(2),  "key_out_sel")
round_in         = m.input(UInt(4),  "round")
sbox_sel         = m.input(UInt(3),  "sbox_sel")
iv_en            = m.input(UInt(4),  "iv_en")
iv_sel_rd        = m.input(UInt(4),  "iv_sel_rd")
col_en_host      = m.input(UInt(4),  "col_en_host")
col_en_cnt_unit  = m.input(UInt(4),  "col_en_cnt_unit")
key_host_en      = m.input(UInt(4),  "key_host_en")
key_en           = m.input(UInt(4),  "key_en")
key_sel_rd       = m.input(UInt(2),  "key_sel_rd")
col_sel          = m.input(UInt(2),  "col_sel")
col_sel_host     = m.input(UInt(2),  "col_sel_host")
end_comp         = m.input(UInt(1),  "end_comp")
key_sel_in       = m.input(UInt(1),  "key_sel")
key_init         = m.input(UInt(1),  "key_init")
bypass_rk        = m.input(UInt(1),  "bypass_rk")
bypass_key_en    = m.input(UInt(1),  "bypass_key_en")
first_block      = m.input(UInt(1),  "first_block")
last_round       = m.input(UInt(1),  "last_round")
iv_cnt_en        = m.input(UInt(1),  "iv_cnt_en")
iv_cnt_sel       = m.input(UInt(1),  "iv_cnt_sel")
enc_dec          = m.input(UInt(1),  "enc_dec")
mode_ctr         = m.input(UInt(1),  "mode_ctr")
mode_cbc         = m.input(UInt(1),  "mode_cbc")
key_gen          = m.input(UInt(1),  "key_gen")
key_derivation_en = m.input(UInt(1), "key_derivation_en")
rst_n            = m.input(UInt(1),  "rst_n")

col_bus  = m.output(UInt(32), "col_bus")
key_bus  = m.output(UInt(32), "key_bus")
iv_bus   = m.output(UInt(32), "iv_bus")
end_aes  = m.output(UInt(1),  "end_aes")

rst_active = Wire(UInt(1), name="rst_active"); rst_active <<= ~rst_n


# ============================================================================
# data_swap helper (combinational, used 2× as SWAP_IN and SWAP_OUT)
# ============================================================================
def data_swap(data_in_32, swap_type):
    """4-mode swap: 00=none, 01=halfword, 10=byte-reverse, 11=bit-reverse."""
    word_0 = data_in_32
    word_1 = cat(data_in_32[16:32], data_in_32[0:16])
    word_2 = cat(data_in_32[24:32], data_in_32[16:24], data_in_32[8:16], data_in_32[0:8])
    word_3 = cat(*[data_in_32[31 - i] for i in range(32)])
    return mux(swap_type == Const(0, UInt(2)), word_0,
           mux(swap_type == Const(1, UInt(2)), word_1,
           mux(swap_type == Const(2, UInt(2)), word_2,
                                                word_3)))


# ============================================================================
# shift_rows helper
# ============================================================================
def shift_rows(data_in_128):
    state = [[None] * 4 for _ in range(4)]
    for l in range(4):
        for c in range(4):
            lo = 8 * ((4 - c) * 4 - l - 1)
            hi = 8 * ((4 - c) * 4 - l)
            state[l][c] = data_in_128[lo:hi]
    state_l = [[state[l][(c + l)     % 4] for c in range(4)] for l in range(4)]
    state_r = [[state[l][(c + 4 - l) % 4] for c in range(4)] for l in range(4)]
    bytes_enc = [None] * 16
    bytes_dec = [None] * 16
    for l in range(4):
        for c in range(4):
            byte_idx = (4 - c) * 4 - l - 1
            bytes_enc[byte_idx] = state_l[l][c]
            bytes_dec[byte_idx] = state_r[l][c]
    return cat(*bytes_enc), cat(*bytes_dec)


# ============================================================================
# mix_columns helper
# ============================================================================
def _gf_mult_02(b):
    shifted  = cat(Const(0, UInt(1)), b[0:7])
    poly_msk = mux(b[7], Const(0x1b, UInt(8)), Const(0, UInt(8)))
    return shifted ^ poly_msk


def _gf_mult_04(b):
    shifted  = cat(Const(0, UInt(2)), b[0:6])
    poly_1b  = mux(b[6], Const(0x1b, UInt(8)), Const(0, UInt(8)))
    poly_36  = mux(b[7], Const(0x36, UInt(8)), Const(0, UInt(8)))
    return (shifted ^ poly_1b) ^ poly_36


def mix_columns(mix_in_32):
    col = [mix_in_32[8 * i : 8 * (i + 1)] for i in range(4)]
    enc_bytes = []
    for j in range(4):
        sum_p = col[(j + 1) % 4] ^ col[(j + 2) % 4] ^ col[(j + 3) % 4]
        a     = col[j] ^ col[(j + 3) % 4]
        enc_bytes.append(_gf_mult_02(a) ^ sum_p)
    mix_out_enc = cat(*enc_bytes)
    y0 = _gf_mult_04(col[2] ^ col[0])
    y1 = _gf_mult_04(col[3] ^ col[1])
    y2 = _gf_mult_02(y1 ^ y0)
    y_lo = y2 ^ y0
    y_hi = y2 ^ y1
    add_mask = cat(y_lo, y_hi, y_lo, y_hi)
    mix_out_dec = mix_out_enc ^ add_mask
    return mix_out_enc, mix_out_dec


# ============================================================================
# key_expander helper
# ============================================================================
def key_expander(g_out_32, key_in_128, round_4, add_w_out_1, kx_enc_dec):
    key = [key_in_128[32 * (3 - i) : 32 * (4 - i)] for i in range(4)]
    # Verilog rc_dir: round==8→0x1b, round==9→0x36, else 8'h01 << round (truncated to 8 bits).
    # Round 10..15: 1<<round overflows 8 bits → rc_dir = 0.
    rc_dir = Const(0, UInt(8))  # default for round >= 10 (1<<round truncated to 0)
    for r in range(8):
        rc_dir = mux(round_4 == Const(r, UInt(4)), Const(1 << r, UInt(8)), rc_dir)
    rc_dir = mux(round_4 == Const(8, UInt(4)), Const(0x1b, UInt(8)),
             mux(round_4 == Const(9, UInt(4)), Const(0x36, UInt(8)), rc_dir))
    # Verilog rc_inv: round==0→0x36, round==1→0x1b, else 8'h80 >> (round-2).
    # Round 10..15: 0x80 >> (round-2) is 0 (shifts past 8 bits) → rc_inv = 0.
    rc_inv = Const(0, UInt(8))  # default for round >= 10
    for r in range(2, 10):
        rc_inv = mux(round_4 == Const(r, UInt(4)),
                      Const(0x80 >> (r - 2), UInt(8)), rc_inv)
    rc_inv = mux(round_4 == Const(1, UInt(4)), Const(0x1b, UInt(8)),
             mux(round_4 == Const(0, UInt(4)), Const(0x36, UInt(8)), rc_inv))
    rc = mux(kx_enc_dec, rc_dir, rc_inv)
    g_func = cat(g_out_32[0:24], g_out_32[24:32] ^ rc)
    ko_0 = key[0] ^ g_func
    ko_1 = mux(add_w_out_1, key[1] ^ key[0] ^ g_func, key[1] ^ key[0])
    ko_2 = key[2] ^ key[1]
    ko_3 = key[3] ^ key[2]
    # verilog KGO loop: for j=0: key_out[127:96] = ko_0; for j=3: key_out[31:0] = ko_3.
    # So MSB 32 bits = ko_0, LSB 32 bits = ko_3.
    # Spirehdl cat LSB-first: put ko_3 first (LSB), ko_0 last (MSB).
    key_out_128 = cat(ko_3, ko_2, ko_1, ko_0)
    rot_in = [
        mux(kx_enc_dec, key[3][8 * k : 8 * (k + 1)],
            key[3][8 * k : 8 * (k + 1)] ^ key[2][8 * k : 8 * (k + 1)])
        for k in range(4)
    ]
    g_in_bytes = [rot_in[(4 + l - 1) % 4] for l in range(4)]
    g_in_32 = cat(*g_in_bytes)
    return key_out_128, g_in_32


# ============================================================================
# sBox_8 word-level — 4-table LUT replacement for the GF math
# The verilog stores `base_new` (which already depends on enc_dec) and
# `out_gf_inv8_stage1` in pipeline registers. Both sbox_out_enc and
# sbox_out_dec are produced from the same pipelined input via different
# output isomorphisms; the off-axis output is a deterministic "garbage"
# pattern that downstream key_expander still consumes.
# ============================================================================
ed_pp_r = Register(UInt(1), name="sbox_ed_pp")


def sbox_8_word(sbox_in_32, sbox_enc_dec):
    """32-bit S-box: 4 byte-wise lookups. Returns (out_enc, out_dec).

    1-cycle pipeline: byte_pp + ed_pp capture, then 4-table comb lookup.
    Verilog reg has no reset clause; spirehdl init=0 matches 2-state startup.
    """
    global ed_pp_r
    ed_pp_r <<= sbox_enc_dec
    out_enc_bytes = []
    out_dec_bytes = []

    def _bit_tree_lookup(table, sel):
        """Balanced binary mux tree: 256 leaves → 1, 8 levels of 2:1 muxes.
        Replaces the linear `mux(sel == Const(k), Const(table[k]), chain)`
        cascade which yosys+abc tends to synthesise as a deep AOI/OAI chain
        (see router for the same diagnosis & fix)."""
        leaves = [Const(table[k], UInt(8)) for k in range(256)]
        for bit in range(8):
            leaves = [mux(sel[bit], leaves[i + 1], leaves[i])
                      for i in range(0, len(leaves), 2)]
        return leaves[0]

    for b in range(4):
        byte_in = sbox_in_32[8 * b : 8 * (b + 1)]
        byte_pp = Register(UInt(8), name=f"sbox_pp_byte_{b}")
        byte_pp <<= byte_in
        v_eoe = _bit_tree_lookup(SBOX_ENC_OUT_WHEN_ENC, byte_pp)
        v_eod = _bit_tree_lookup(SBOX_ENC_OUT_WHEN_DEC, byte_pp)
        v_doe = _bit_tree_lookup(SBOX_DEC_OUT_WHEN_ENC, byte_pp)
        v_dod = _bit_tree_lookup(SBOX_DEC_OUT_WHEN_DEC, byte_pp)
        out_enc_bytes.append(mux(ed_pp_r, v_eoe, v_eod))
        out_dec_bytes.append(mux(ed_pp_r, v_doe, v_dod))
    return cat(*out_enc_bytes), cat(*out_dec_bytes)


# ============================================================================
# Forward-declare cross-module wires
# ============================================================================
add_rk_out_w  = Wire(UInt(32), name="add_rk_out")
sbox_pp2_w    = Wire(UInt(32), name="sbox_pp2_wire")
key_mux_out_w = Wire(UInt(32), name="key_mux_out_wire")
sbox_input_w  = Wire(UInt(32), name="sbox_input_wire")
sbox_out_enc_w = Wire(UInt(32), name="sbox_out_enc")


# ============================================================================
# === BODY ===
# ============================================================================

bus_swap = Wire(UInt(32), name="bus_swap"); bus_swap <<= data_swap(bus_in, data_type)
col_bus <<= data_swap(sbox_input_w, data_type)

iv      = [Register(UInt(32), name=f"iv_{l}")      for l in range(4)]
bkp     = [Register(UInt(32), name=f"bkp_{l}")     for l in range(4)]
bkp_1   = [Register(UInt(32), name=f"bkp_1_{l}")   for l in range(4)]
col     = [Register(UInt(32), name=f"col_{l}")     for l in range(4)]
key     = [Register(UInt(32), name=f"key_{l}")     for l in range(4)]
key_host = [Register(UInt(32), name=f"key_host_{l}") for l in range(4)]

sbox_pp2_r            = Register(UInt(32), name="sbox_pp2")
col_en_cnt_unit_pp1_r = Register(UInt(4),  name="col_en_cnt_unit_pp1")
col_en_cnt_unit_pp2_r = Register(UInt(4),  name="col_en_cnt_unit_pp2")
key_en_pp1_r          = Register(UInt(4),  name="key_en_pp1")
round_pp1_r           = Register(UInt(4),  name="round_pp1")
col_sel_pp1_r         = Register(UInt(2),  init=INPUT_SEL, name="col_sel_pp1")
col_sel_pp2_r         = Register(UInt(2),  init=INPUT_SEL, name="col_sel_pp2")
key_out_sel_pp1_r     = Register(UInt(2),  name="key_out_sel_pp1")
key_out_sel_pp2_r     = Register(UInt(2),  name="key_out_sel_pp2")
rk_sel_pp1_r          = Register(UInt(2),  name="rk_sel_pp1")
rk_sel_pp2_r          = Register(UInt(2),  name="rk_sel_pp2")
key_sel_pp1_r         = Register(UInt(1),  name="key_sel_pp1")
rk_out_sel_pp1_r      = Register(UInt(1),  init=1, name="rk_out_sel_pp1")
rk_out_sel_pp2_r      = Register(UInt(1),  init=1, name="rk_out_sel_pp2")
last_round_pp1_r      = Register(UInt(1),  init=1, name="last_round_pp1")
last_round_pp2_r      = Register(UInt(1),  name="last_round_pp2")

# === IV_BKP_MUX (combinational) ===
col_en_w_bypass = mux(bypass_rk, col_en_cnt_unit, col_en_cnt_unit_pp2_r)
col_en = Wire(UInt(4), name="col_en"); col_en <<= col_en_host | col_en_w_bypass

iv_mux_out  = Const(0, UInt(32))
bkp_mux_out = Const(0, UInt(32))
for i in range(4):
    enable = col_en[i] | iv_sel_rd[i]
    iv_mux_out  = mux(enable, iv[i],  iv_mux_out)
    bkp_mux_out = mux(enable, bkp[i], bkp_mux_out)

iv_bkp_mux = mux(first_block & ~mode_ctr, iv_mux_out, bkp_mux_out)
xor_input_bkp_iv = mux(enc_dec & ~mode_ctr, bus_swap, add_rk_out_w) ^ iv_bkp_mux

data_in = mux(mode_cbc, mux(enc_dec | last_round, xor_input_bkp_iv, bus_swap),
          mux(mode_ctr, mux(last_round, xor_input_bkp_iv, iv_mux_out),
              bus_swap))

bkp_en_cbc = cat(*([mode_cbc & last_round & enc_dec] * 4)) & col_en_cnt_unit_pp2_r
bkp_en_other = cat(*([(mode_cbc & ~enc_dec) | mode_ctr] * 4)) & col_en_host
bkp_en = bkp_en_cbc | bkp_en_other

# === IV / BKP / BKP_1 generate-loop ===
col_in_w = Wire(UInt(128), name="col_in_wire")

for l in range(4):
    if l == 3:
        iv_l_en = iv_en[l] | iv_cnt_en
        iv_l_val_ctr = mux(iv_cnt_sel, (iv[l] + Const(1, UInt(1)))[0:32], bus_in)
        iv_l_val_else = mux(iv_cnt_sel, iv[l], bus_in)
        iv_l_val = mux(mode_ctr, iv_l_val_ctr, iv_l_val_else)
        iv_next = mux(iv_l_en, iv_l_val, iv[l])
    else:
        iv_next = mux(iv_en[l], bus_in, iv[l])

    iv[l] <<= mux(rst_active, Const(0, UInt(32)), iv_next)

    col_in_slice = col_in_w[32 * l : 32 * (l + 1)]
    bkp_val = mux(mode_ctr, bus_swap,
              mux(mode_cbc & enc_dec, col_in_slice, bkp_1[l]))
    bkp_next = mux(bkp_en[l], bkp_val, bkp[l])
    bkp[l] <<= mux(rst_active, Const(0, UInt(32)), bkp_next)

    bkp_1_next = mux(bkp_en[l], col_in_slice, bkp_1[l])
    bkp_1[l] <<= mux(rst_active, Const(0, UInt(32)), bkp_1_next)

# === col_in mux ===
col_sel_w_bypass = mux(bypass_rk, col_sel, col_sel_pp2_r)

sr_enc_w = Wire(UInt(128), name="sr_enc")
sr_dec_w = Wire(UInt(128), name="sr_dec")

col_in_shift = mux(enc_dec, sr_enc_w, sr_dec_w)
col_in_addrk = cat(add_rk_out_w, add_rk_out_w, add_rk_out_w, add_rk_out_w)
col_in_input = cat(data_in, data_in, data_in, data_in)
col_in_w <<= mux(col_sel_w_bypass == Const(SHIFT_ROWS, UInt(2)), col_in_shift,
             mux(col_sel_w_bypass == Const(ADD_RK_OUT, UInt(2)), col_in_addrk,
             mux(col_sel_w_bypass == Const(INPUT_SEL,  UInt(2)), col_in_input,
                                                                 Const(0, UInt(128)))))

# === COL register bank ===
for i in range(4):
    col_in_slice = col_in_w[32 * i : 32 * (i + 1)]
    col_idx = 3 - i
    col_l_en = col_en[col_idx]
    col_next = mux(col_l_en, col_in_slice, col[col_idx])
    col[col_idx] <<= mux(rst_active, Const(0, UInt(32)), col_next)

# === Shift Rows ===
sr_input_3 = mux(enc_dec, add_rk_out_w, col[3])
sr_input_0 = mux(enc_dec, col[0], add_rk_out_w)
sr_input   = cat(sr_input_3, col[2], col[1], sr_input_0)
sr_enc_calc, sr_dec_calc = shift_rows(sr_input)
sr_enc_w <<= sr_enc_calc
sr_dec_w <<= sr_dec_calc

# === SBOX input mux ===
# Verilog: sbox_sel | {1'b0, col_sel_host} = sbox_sel | (col_sel_host zero-extended to 3 bits)
# Spirehdl cat LSB-first: put col_sel_host at LSB, 0 at MSB → MSB-zero-extend.
sbox_sel_mux = sbox_sel | cat(col_sel_host, Const(0, UInt(1)))
g_in_w = Wire(UInt(32), name="g_in_wire")
sbox_input_w <<= mux(sbox_sel_mux == Const(COL_0,      UInt(3)), col[0],
                 mux(sbox_sel_mux == Const(COL_1,      UInt(3)), col[1],
                 mux(sbox_sel_mux == Const(COL_2,      UInt(3)), col[2],
                 mux(sbox_sel_mux == Const(COL_3,      UInt(3)), col[3],
                 mux(sbox_sel_mux == Const(G_FUNCTION, UInt(3)), g_in_w,
                                                                 Const(0, UInt(32)))))))

# === SBOX instance ===
enc_dec_sbox = enc_dec | key_gen
sbox_out_enc_calc, sbox_out_dec_calc = sbox_8_word(sbox_input_w, enc_dec_sbox)
sbox_out_enc_w <<= sbox_out_enc_calc
sbox_out_dec_w = Wire(UInt(32), name="sbox_out_dec"); sbox_out_dec_w <<= sbox_out_dec_calc

# === sbox_pp2 register ===
sbox_pp2_next = mux(enc_dec | mode_ctr, sbox_out_enc_w, sbox_out_dec_w ^ key_mux_out_w)
sbox_pp2_r <<= sbox_pp2_next
sbox_pp2_w <<= sbox_pp2_r

# === KEY / KEY_HOST register bank ===
key_out_w = Wire(UInt(128), name="key_out_wire")
key_en_sel  = mux(bypass_key_en, key_en, key_en_pp1_r)
key_sel_mux = mux(bypass_key_en, key_sel_in, key_sel_pp1_r)

for j in range(4):
    key_idx = 3 - j
    kh_en = key_host_en[key_idx] | key_derivation_en
    kh_val = mux(key_derivation_en, key[key_idx], bus_in)
    key_host[key_idx] <<= mux(rst_active, Const(0, UInt(32)),
                          mux(kh_en, kh_val, key_host[key_idx]))
    k_en = key_en_sel[key_idx] | key_init | key_host_en[key_idx]
    k_val_else = mux(key_host_en[key_idx], bus_in, key_host[key_idx])
    key_out_slice = key_out_w[32 * j : 32 * (j + 1)]
    k_val = mux(key_sel_mux, key_out_slice, k_val_else)
    key[key_idx] <<= mux(rst_active, Const(0, UInt(32)),
                     mux(k_en, k_val, key[key_idx]))

key_in_concat = cat(key[3], key[2], key[1], key[0])
key1_mux_cnt = bypass_key_en & enc_dec

# === key_expander instance ===
kx_enc_dec = enc_dec | key_gen
key_out_calc, g_in_calc = key_expander(sbox_out_enc_w, key_in_concat, round_pp1_r,
                                        key1_mux_cnt, kx_enc_dec)
key_out_w <<= key_out_calc
g_in_w <<= g_in_calc

# === key_mux_out (Mealy mux) ===
key_mux_sel = mux(bypass_key_en, key_out_sel,
              mux(enc_dec | mode_ctr, key_out_sel_pp2_r, key_out_sel_pp1_r))
key_mux_sel_combined = key_mux_sel | key_sel_rd
key_mux_out_w <<= mux(key_mux_sel_combined == Const(KEY_0, UInt(2)), key[0],
                  mux(key_mux_sel_combined == Const(KEY_1, UInt(2)), key[1],
                  mux(key_mux_sel_combined == Const(KEY_2, UInt(2)), key[2],
                                                                      key[3])))

# === mix_columns instance ===
mix_out_enc_w, mix_out_dec_w = mix_columns(sbox_pp2_w)

# === Add Round Key path ===
rk_sel_mux = mux(bypass_rk, rk_sel, rk_sel_pp2_r)
add_rd_key_in = mux(rk_sel_mux == Const(COL_RK,     UInt(2)), sbox_input_w,
                mux(rk_sel_mux == Const(MIXCOL_IN,  UInt(2)), sbox_pp2_w,
                mux(rk_sel_mux == Const(MIXCOL_OUT, UInt(2)), mix_out_enc_w,
                                                              Const(0, UInt(32)))))
add_rd = add_rd_key_in ^ key_mux_out_w
rk_out_sel = enc_dec | mode_ctr | bypass_rk
add_rk_sel = mux(bypass_rk, rk_out_sel, rk_out_sel_pp2_r)
add_rk_out_w <<= mux(add_rk_sel, add_rd,
                  mux(last_round_pp2_r, sbox_pp2_w, mix_out_dec_w))

end_aes <<= end_comp
iv_bus <<= iv_mux_out
key_bus <<= key_mux_out_w

# === Pipeline control registers ===
col_sel_pp1_r         <<= mux(rst_active, Const(INPUT_SEL, UInt(2)), col_sel)
col_sel_pp2_r         <<= mux(rst_active, Const(INPUT_SEL, UInt(2)), col_sel_pp1_r)
col_en_cnt_unit_pp1_r <<= mux(rst_active, Const(0, UInt(4)),
                          mux(~bypass_rk, col_en_cnt_unit, col_en_cnt_unit_pp1_r))
col_en_cnt_unit_pp2_r <<= mux(rst_active, Const(0, UInt(4)),
                          mux(~bypass_rk, col_en_cnt_unit_pp1_r, col_en_cnt_unit_pp2_r))
key_sel_pp1_r         <<= mux(rst_active, Const(KEY_HOST, UInt(1)), key_sel_in)
key_en_pp1_r          <<= mux(rst_active, Const(0, UInt(4)),
                          mux(~bypass_key_en, key_en, key_en_pp1_r))
round_pp1_r           <<= mux(rst_active, Const(0, UInt(4)), round_in)
key_out_sel_pp1_r     <<= mux(rst_active, Const(KEY_0, UInt(2)), key_out_sel)
key_out_sel_pp2_r     <<= mux(rst_active, Const(KEY_0, UInt(2)), key_out_sel_pp1_r)
rk_sel_pp1_r          <<= mux(rst_active, Const(COL_RK, UInt(2)), rk_sel)
rk_sel_pp2_r          <<= mux(rst_active, Const(COL_RK, UInt(2)), rk_sel_pp1_r)
rk_out_sel_pp1_r      <<= mux(rst_active, Const(1, UInt(1)), rk_out_sel)
rk_out_sel_pp2_r      <<= mux(rst_active, Const(1, UInt(1)), rk_out_sel_pp1_r)
last_round_pp1_r      <<= mux(rst_active, Const(1, UInt(1)), last_round)
last_round_pp2_r      <<= mux(rst_active, Const(0, UInt(1)), last_round_pp1_r)

m.to_verilog_file("design.v")

"""Draft translations of the smaller datapath submodules.

These are the easier 4 of the 7 submodules (data_swap, shift_rows,
mix_columns, key_expander) translated as standalone Python helper
functions. Each takes spirehdl Expr/Signal inputs and returns Expr
outputs, ready to drop into `context/starting_point.py` once the top
module is written.

To use:
    from spirehdl.spirehdl import UInt, Const, Wire, mux, cat
    # ... helpers below ...

    # In the top module:
    bus_swap = data_swap(bus_in, data_type, width=32)
    # ... etc ...

NOT YET INTEGRATED into a working `starting_point.py`. The top module
(`datapath`) still needs translation — see DEBUGGING.md "Pitfalls
anticipated" sections 1–5 for the recipe.
"""
from spirehdl.spirehdl import UInt, Const, Wire, mux, cat


# ============================================================================
# data_swap — byte-order swap based on swap_type[1:0]
# ============================================================================
def data_swap(data_in, swap_type, width=32):
    """Mirrors `module data_swap` (verilog lines 1026–1063).
    swap_type encoding:
       00: NO_SWAP        (pass-through)
       01: HALF_WORD_SWAP (swap [31:16] ↔ [15:0])
       10: BYTE_SWAP      (reverse bytes)
       11: BIT_SWAP       (reverse all bits)
    """
    # No swap
    word_0 = data_in
    # Half-word swap: {data_in[15:0], data_in[31:16]}
    word_1 = cat(data_in[16:width], data_in[0:16])
    # Byte swap: reverse 4 bytes
    word_2 = cat(data_in[24:32], data_in[16:24], data_in[8:16], data_in[0:8])
    # Bit swap: reverse all bits (use Python loop over bit indices)
    word_3 = cat(*[data_in[width - 1 - i] for i in range(width)])

    return mux(swap_type == Const(0, UInt(2)), word_0,
           mux(swap_type == Const(1, UInt(2)), word_1,
           mux(swap_type == Const(2, UInt(2)), word_2,
                                                word_3)))


# ============================================================================
# shift_rows — AES ShiftRows operation over 128-bit state
# ============================================================================
def shift_rows(data_in_128):
    """Mirrors `module shift_rows` (verilog lines 964–1024).

    State matrix layout (verilog `state[l][c]`):
        state[l][c] = data_in[BUS_WIDTH - 1 - 8*((ST_LINE*c + l))  -:  8]
        That is, byte (c, l) lives at MSB-first position c*4 + l in the
        128-bit word.

    Forward ShiftRows shifts left by row index: row l rotates left l columns.
    Inverse ShiftRows shifts right by row index.

    Returns (data_out_enc, data_out_dec) both 128-bit.
    """
    # Build the state matrix as a 4x4 list of 8-bit slices from data_in.
    # Verilog: state[l][c] = data_in[ 8*((4-c)*4 - l) - 1 : 8*((4-c)*4 - l - 1) ]
    #                       = byte at index (4-c)*4 - l - 1 in MSB-first ordering
    # In spirehdl, slice [lo:hi] is LSB-based, so we compute the equivalent.
    state = [[None] * 4 for _ in range(4)]
    for l in range(4):
        for c in range(4):
            # Verilog index range: 8*((4-c)*4 - l) - 1 : 8*((4-c)*4 - l - 1)
            hi = 8 * ((4 - c) * 4 - l)
            lo = 8 * ((4 - c) * 4 - l - 1)
            state[l][c] = data_in_128[lo:hi]

    # Apply shift:
    # state_sft_l[l][c] = state[l][(c + l) % 4]    (left, for ENC)
    # state_sft_r[l][c] = state[l][(c + 4 - l) % 4] (right, for DEC)
    state_sft_l = [[state[l][(c + l) % 4]      for c in range(4)] for l in range(4)]
    state_sft_r = [[state[l][(c + 4 - l) % 4]  for c in range(4)] for l in range(4)]

    # Pack state matrix back to 128-bit bus.
    # We collect bytes in LSB-first order for cat. Verilog packing matches the
    # same index formula as state[][] above. So:
    bytes_enc = [None] * 16
    bytes_dec = [None] * 16
    for l in range(4):
        for c in range(4):
            # The verilog assigns data_out[8*((4-c)*4 - l) - 1 : 8*((4-c)*4 - l - 1)]
            # = state_sft_*[l][c]. The lo bit of this byte is 8*((4-c)*4 - l - 1).
            byte_idx_lsb_first = (4 - c) * 4 - l - 1   # this is the lo/8 byte index
            bytes_enc[byte_idx_lsb_first] = state_sft_l[l][c]
            bytes_dec[byte_idx_lsb_first] = state_sft_r[l][c]
    data_out_enc = cat(*bytes_enc)   # cat is LSB-first → bytes[0] is bits [7:0]
    data_out_dec = cat(*bytes_dec)
    return data_out_enc, data_out_dec


# ============================================================================
# mix_columns — AES MixColumns + InverseMixColumns over 32-bit column
# ============================================================================
def _aes_mult_02(data_8):
    """GF(2^8) multiply by 02: ({a[6:0], 1'b0}) ^ ({8{a[7]}} & 8'h1b)."""
    # Left-shift by 1 (zero LSB) — cat is LSB-first
    shifted = cat(Const(0, UInt(1)), data_8[0:7])  # → 8-bit {a[6:0], 0}
    # 8-bit conditional XOR with 0x1b iff a[7]=1
    poly_mask = mux(data_8[7], Const(0x1b, UInt(8)), Const(0, UInt(8)))
    return shifted ^ poly_mask


def _aes_mult_04(data_8):
    """GF(2^8) multiply by 04: ((a << 2) ^ ({8{a[6]}} & 8'h1b)) ^ ({8{a[7]}} & 8'h36).
    Verilog: aes_mult_04 = ((data_in << 2) ^ {8{data_in[6]}} & 8'h1b) ^ {8{data_in[7]}} & 8'h36;
    """
    shifted = cat(Const(0, UInt(2)), data_8[0:6])     # 8-bit {a[5:0], 2'b00}
    poly_1b = mux(data_8[6], Const(0x1b, UInt(8)), Const(0, UInt(8)))
    poly_36 = mux(data_8[7], Const(0x36, UInt(8)), Const(0, UInt(8)))
    return (shifted ^ poly_1b) ^ poly_36


def mix_columns(mix_in_32):
    """Mirrors `module mix_columns` (verilog lines 518–584).

    Returns (mix_out_enc, mix_out_dec) both 32-bit.

    Forward MixColumns per column: out[j] = mult_02(col[j] ^ col[(j-1)%4]) ^ col[(j+1)%4] ^ col[(j+2)%4] ^ col[(j+3)%4]
    Inverse: encoded as enc + some additional XORs (see verilog).
    """
    # Extract the 4 column bytes (col[i] = mix_in[8*(i+1)-1 : 8*i])
    col = [mix_in_32[8*i : 8*(i+1)] for i in range(4)]

    # Forward MixColumns
    enc_bytes = []
    for j in range(4):
        sum_p = col[(j+1) % 4] ^ col[(j+2) % 4] ^ col[(j+3) % 4]
        a = col[j] ^ col[(j + 4 - 1) % 4]
        enc_bytes.append(_aes_mult_02(a) ^ sum_p)
    mix_out_enc = cat(*enc_bytes)  # LSB-first

    # Inverse MixColumns
    y0 = _aes_mult_04(col[2] ^ col[0])
    y1 = _aes_mult_04(col[3] ^ col[1])
    y2 = _aes_mult_02(y1 ^ y0)
    # Verilog: mix_out_dec = mix_out_enc ^ {2{y[2] ^ y[1], y[2] ^ y[0]}}
    # The {2{a, b}} = {a, b, a, b} in verilog (MSB-first replication of 16-bit pair).
    # That's the 16-bit value (y2^y1, y2^y0) replicated twice → 32-bit
    # = bytes [3..0]: (y2^y1, y2^y0, y2^y1, y2^y0)
    # cat LSB-first: bytes [0]=y2^y0, [1]=y2^y1, [2]=y2^y0, [3]=y2^y1
    y_pair_low  = y2 ^ y0
    y_pair_high = y2 ^ y1
    add_mask = cat(y_pair_low, y_pair_high, y_pair_low, y_pair_high)
    mix_out_dec = mix_out_enc ^ add_mask
    return mix_out_enc, mix_out_dec


# ============================================================================
# key_expander — Round-key derivation
# ============================================================================
def key_expander(g_out_32, key_in_128, round_4, add_w_out_1, enc_dec_1):
    """Mirrors `module key_expander` (verilog lines 587–690).

    Returns (key_out_128, g_in_32).
    """
    # key[i] = key_in[32*(i+1)-1 : 32*i]
    # Note: verilog assigns key[KEY_NUM-1-i] = key_in[32*(i+1)-1:32*i]
    # so key[3] = key_in[31:0], key[0] = key_in[127:96]
    key = [key_in_128[32*(3 - i) : 32*(4 - i)] for i in range(4)]

    # rc generation (round constant)
    # rc_dir: if round==8 → 0x1b; elif round==9 → 0x36; else → 0x01 << round (8-bit)
    rc_dir = mux(round_4 == Const(8, UInt(4)), Const(0x1b, UInt(8)),
             mux(round_4 == Const(9, UInt(4)), Const(0x36, UInt(8)),
                 # 0x01 << round, but only for round in [0..7]
                 cat(*[mux(round_4 == Const(i, UInt(4)),
                          Const(1 << i, UInt(8)), Const(0, UInt(8)))
                       for i in range(8)])))
    # Actually that cat-as-OR approach is wrong; better to build a proper mux
    rc_dir_chain = Const(1, UInt(8))  # default 0x01 for round=0
    for r in range(8):
        rc_dir_chain = mux(round_4 == Const(r, UInt(4)),
                            Const(1 << r, UInt(8)), rc_dir_chain)
    rc_dir_chain = mux(round_4 == Const(8, UInt(4)), Const(0x1b, UInt(8)),
                   mux(round_4 == Const(9, UInt(4)), Const(0x36, UInt(8)),
                       rc_dir_chain))

    # rc_inv: if round==1 → 0x1b; elif round==0 → 0x36; else 0x80 >> (round-2)
    rc_inv_chain = Const(0x80, UInt(8))  # default for round=2
    for r in range(2, 10):
        # round=2 → 0x80, round=3 → 0x40, ..., round=9 → 0x01
        rc_inv_chain = mux(round_4 == Const(r, UInt(4)),
                            Const(0x80 >> (r - 2), UInt(8)), rc_inv_chain)
    rc_inv_chain = mux(round_4 == Const(1, UInt(4)), Const(0x1b, UInt(8)),
                   mux(round_4 == Const(0, UInt(4)), Const(0x36, UInt(8)),
                       rc_inv_chain))

    rc = mux(enc_dec_1, rc_dir_chain, rc_inv_chain)

    # g_func = {g_out[31:24] ^ rc, g_out[23:0]}
    g_func = cat(g_out_32[0:24], g_out_32[24:32] ^ rc)

    # Key out generation (per row j):
    #   j=0:                key_out[127:96] = key[0] ^ g_func
    #   j=1: (add_w_out)?   key[1] ^ key[0] ^ g_func : key[1] ^ key[0]
    #   j=2:                key[2] ^ key[1]
    #   j=3:                key[3] ^ key[2]
    ko_0 = key[0] ^ g_func
    ko_1 = mux(add_w_out_1, key[1] ^ key[0] ^ g_func, key[1] ^ key[0])
    ko_2 = key[2] ^ key[1]
    ko_3 = key[3] ^ key[2]
    # Pack: key_out[127:96] = ko_0, [95:64] = ko_1, [63:32] = ko_2, [31:0] = ko_3
    # cat is LSB-first: cat(ko_3, ko_2, ko_1, ko_0) → {ko_0, ko_1, ko_2, ko_3} in verilog
    key_out_128 = cat(ko_3, ko_2, ko_1, ko_0)

    # g_in generation:
    # rot_in[k] = enc_dec ? key[3][8*(k+1)-1:8*k] : key[3][8*(k+1)-1:8*k] ^ key[2][8*(k+1)-1:8*k]
    # g_in[8*(l+1)-1:8*l] = rot_in[(4 + l - 1) % 4]
    rot_in = [
        mux(enc_dec_1,
            key[3][8*k : 8*(k+1)],
            key[3][8*k : 8*(k+1)] ^ key[2][8*k : 8*(k+1)])
        for k in range(4)
    ]
    g_in_bytes = [rot_in[(4 + l - 1) % 4] for l in range(4)]
    g_in_32 = cat(*g_in_bytes)

    return key_out_128, g_in_32


# ============================================================================
# sBox lookup — uses pre-computed AES table from aes_sbox.py
# ============================================================================
def sbox_lookup(sbox_in_8, enc_dec_1, SBOX_ENC, SBOX_DEC):
    """One-cycle pipelined S-box (replaces verilog's GF-math sBox_8).

    Verilog has `out_gf_pp <= ...; base_new_pp <= ...` inside sBox_8 — a
    1-cycle pipeline between input and output. The LUT-based equivalent
    must register either the input or the output to match latency.

    This helper returns COMBINATIONAL forward+inverse lookups; the caller
    must register the input before calling (or register the output after).

    Returns (sbox_out_enc, sbox_out_dec).
    """
    chain_enc = Const(0, UInt(8))
    chain_dec = Const(0, UInt(8))
    for k in range(256):
        match = sbox_in_8 == Const(k, UInt(8))
        chain_enc = mux(match, Const(SBOX_ENC[k], UInt(8)), chain_enc)
        chain_dec = mux(match, Const(SBOX_DEC[k], UInt(8)), chain_dec)
    return chain_enc, chain_dec

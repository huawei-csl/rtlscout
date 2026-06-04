"""Compute the 4 sBox_8 output tables by Python-simulating the verilog GF math.

The verilog sBox_8 (lines 713-963 of starting_point.v) implements:
    isomorphism(sbox_in) -> (base_new_enc, base_new_dec)   # 2x 8-bit
    base_new = ~(enc_dec ? base_new_enc : base_new_dec)
    out_gf_inv8_stage1 = gf_inv_8_stage1(base_new)         # 4-bit
    [pipeline reg]
    out_gf_inv8_1 = gf_inv_8_stage2(base_new, c=stage1_out)  # 8-bit
    sbox_out_enc = ~isomorphism_inv(out_gf_inv8_1, ENC)
    sbox_out_dec = ~isomorphism_inv(out_gf_inv8_1, DEC)

For each (sbox_in in [0,255], enc_dec in [0,1]), we compute both outputs.
The non-matching ones (enc with enc_dec=0, dec with enc_dec=1) are "garbage"
in the sense that they're not the standard AES sbox, but the verilog produces
them deterministically.

Emits 4 lists of 256 entries each as Python constants.
"""

def bit(x, i): return (x >> i) & 1
def xor(*bits):
    r = 0
    for b in bits: r ^= b & 1
    return r
def nor(a, b): return (~(a | b)) & 1
def nand(a, b): return (~(a & b)) & 1
def nxor(a, b): return (~(a ^ b)) & 1  # ~^ in verilog
def pack(*bits_msb_first):  # bits[0] is MSB
    r = 0
    for b in bits_msb_first:
        r = (r << 1) | (b & 1)
    return r


def gf_sq_2(inp):  # 2-bit in, 2-bit out
    # gf_sq_2 = {in[0], in[1]}  → MSB=in[0], LSB=in[1]
    return pack(bit(inp, 0), bit(inp, 1))

def gf_sclw_2(inp):
    # gf_sclw_2 = {^in, in[1]}
    return pack(xor(bit(inp, 0), bit(inp, 1)), bit(inp, 1))

def gf_sclw2_2(inp):
    # gf_sclw2_2 = {in[0], ^in}
    return pack(bit(inp, 0), xor(bit(inp, 0), bit(inp, 1)))

def gf_muls_2(in1, in2, in3, in4):  # in1,in2 2-bit; in3,in4 1-bit
    # gf_muls_2 = (~(in1 & in2)) ^ ({2{~(in3 & in4)}})
    nb = (~(in1 & in2)) & 0b11
    rep = (~(in3 & in4)) & 1
    return nb ^ (rep | (rep << 1))

def gf_muls_scl_2(in1, in2, in3, in4):
    nand_in1_in2 = (~(in1 & in2)) & 0b11
    nand_in3_in4 = (~(in3 & in4)) & 1
    # gf_muls_scl_2 = {nand_in3_in4 ^ nand_in1_in2[0], ^nand_in1_in2}
    bit_msb = nand_in3_in4 ^ bit(nand_in1_in2, 0)
    bit_lsb = xor(bit(nand_in1_in2, 0), bit(nand_in1_in2, 1))
    return pack(bit_msb, bit_lsb)

def gf_inv_4(inp):  # 4-bit
    in_hg = (inp >> 2) & 0b11
    in_lw = inp & 0b11
    xor_in_hg = xor(bit(in_hg, 0), bit(in_hg, 1))
    xor_in_lw = xor(bit(in_lw, 0), bit(in_lw, 1))
    # in_sq2_3[1] (MSB):  ~(in_hg[1] | in_lw[1]) ^ ~(xor_in_hg & xor_in_lw)
    # in_sq2_3[0] (LSB):  ~(xor_in_hg | xor_in_lw) ^ ~(in_hg[0] & in_lw[0])
    sq2_3_msb = nor(bit(in_hg, 1), bit(in_lw, 1)) ^ nand(xor_in_hg, xor_in_lw)
    sq2_3_lsb = nor(xor_in_hg, xor_in_lw) ^ nand(bit(in_hg, 0), bit(in_lw, 0))
    in_sq2_3 = pack(sq2_3_msb, sq2_3_lsb)
    out_gf_sq2_3 = gf_sq_2(in_sq2_3)
    out_gf_mul_2 = gf_muls_2(out_gf_sq2_3, in_lw,
                              xor(bit(out_gf_sq2_3, 0), bit(out_gf_sq2_3, 1)),
                              xor_in_lw)
    out_gf_mul_3 = gf_muls_2(out_gf_sq2_3, in_hg,
                              xor(bit(out_gf_sq2_3, 0), bit(out_gf_sq2_3, 1)),
                              xor_in_hg)
    # gf_inv_4 = {out_gf_mul_2, out_gf_mul_3}  ← MSB=out_gf_mul_2, LSB=out_gf_mul_3
    return (out_gf_mul_2 << 2) | out_gf_mul_3

def gf_muls_4(in1, in2):  # 4-bit, 4-bit
    in1_hg = (in1 >> 2) & 0b11
    in1_lw = in1 & 0b11
    in2_hg = (in2 >> 2) & 0b11
    in2_lw = in2 & 0b11
    xor_in1_hl = in1_hg ^ in1_lw
    xor_in2_hl = in2_hg ^ in2_lw
    out_gf_mul_1 = gf_muls_2(in1_hg, in2_hg, bit(in1, 3) ^ bit(in1, 2), bit(in2, 3) ^ bit(in2, 2))
    out_gf_mul_2 = gf_muls_2(in1_lw, in2_lw, bit(in1, 1) ^ bit(in1, 0), bit(in2, 1) ^ bit(in2, 0))
    out_gf_mul_scl_1 = gf_muls_scl_2(xor_in1_hl, xor_in2_hl,
                                       xor(bit(xor_in1_hl, 0), bit(xor_in1_hl, 1)),
                                       xor(bit(xor_in2_hl, 0), bit(xor_in2_hl, 1)))
    # {out_gf_mul_1 ^ out_gf_mul_scl_1, out_gf_mul_2 ^ out_gf_mul_scl_1}
    return ((out_gf_mul_1 ^ out_gf_mul_scl_1) << 2) | (out_gf_mul_2 ^ out_gf_mul_scl_1)

def gf_inv_8_stage1(inp):  # 8-bit in, 4-bit out
    in_hg = (inp >> 4) & 0xF
    in_lw = inp & 0xF
    h3 = bit(in_hg, 3); h2 = bit(in_hg, 2); h1 = bit(in_hg, 1); h0 = bit(in_hg, 0)
    l3 = bit(in_lw, 3); l2 = bit(in_lw, 2); l1 = bit(in_lw, 1); l0 = bit(in_lw, 0)
    xor_in_hg = h3 ^ h2 ^ h1 ^ h0
    xor_in_lw = l3 ^ l2 ^ l1 ^ l0
    c1 = nand(h3 ^ h2, l3 ^ l2)
    c2 = nand(h2 ^ h0, l2 ^ l0)
    c3 = nand(xor_in_hg, xor_in_lw)
    b3 = (nor(h2 ^ h0, l2 ^ l0) ^ nand(h3, l3)) ^ c1 ^ c3
    b2 = (nor(h3 ^ h1, l3 ^ l1) ^ nand(h2, l2)) ^ c1 ^ c2
    b1 = (nor(h1 ^ h0, l1 ^ l0) ^ nand(h1, l1)) ^ c2 ^ c3
    b0 = (nor(h0, l0) ^ nand(h1 ^ h0, l1 ^ l0)) ^ nand(h3 ^ h1, l3 ^ l1) ^ c2
    return pack(b3, b2, b1, b0)

def gf_inv_8_stage2(inp, c):  # 8-bit in, 4-bit c, 8-bit out
    in_hg = (inp >> 4) & 0xF
    in_lw = inp & 0xF
    out_gf_inv4_2 = gf_inv_4(c)
    out_gf_mul4_2 = gf_muls_4(out_gf_inv4_2, in_lw)
    out_gf_mul4_3 = gf_muls_4(out_gf_inv4_2, in_hg)
    return (out_gf_mul4_2 << 4) | out_gf_mul4_3

def isomorphism(inp):  # 8-bit in, returns (enc, dec) each 8-bit
    i7 = bit(inp, 7); i6 = bit(inp, 6); i5 = bit(inp, 5); i4 = bit(inp, 4)
    i3 = bit(inp, 3); i2 = bit(inp, 2); i1 = bit(inp, 1); i0 = bit(inp, 0)
    r1 = i7 ^ i5
    r2 = nxor(i7, i4)
    r3 = i6 ^ i0
    r4 = nxor(i5, r3)
    r5 = i4 ^ r4
    r6 = i3 ^ i0
    r7 = i2 ^ r1
    r8 = i1 ^ r3
    r9 = i3 ^ r8
    # enc = {r7~^r8, r5, in[1]^r4, r1~^r3, in[1]^r2^r6, ~in[0], r4, in[2]~^r9}
    enc = pack(nxor(r7, r8), r5, i1 ^ r4, nxor(r1, r3), i1 ^ r2 ^ r6, (~i0) & 1, r4, nxor(i2, r9))
    # dec = {r2, in[4]^r8, in[6]^in[4], r9, in[6]~^r2, r7, in[4]^r6, in[1]^r5}
    dec = pack(r2, i4 ^ r8, i6 ^ i4, r9, nxor(i6, r2), r7, i4 ^ r6, i1 ^ r5)
    return enc, dec

def isomorphism_inv(inp, op_type):  # 8-bit in, op_type=ENC(1) or DEC(0), 8-bit out
    i7 = bit(inp, 7); i6 = bit(inp, 6); i5 = bit(inp, 5); i4 = bit(inp, 4)
    i3 = bit(inp, 3); i2 = bit(inp, 2); i1 = bit(inp, 1); i0 = bit(inp, 0)
    r1 = i7 ^ i3
    r2 = i6 ^ i4
    r3 = i6 ^ i0
    r4 = nxor(i5, i3)
    r5 = nxor(i5, r1)
    r6 = nxor(i5, i1)
    r7 = nxor(i4, r6)
    r8 = i2 ^ r4
    r9 = i1 ^ r2
    r10 = r3 ^ r5
    if op_type == 1:  # ENC
        return pack(r4, r1, r3, r5, r2 ^ r5, r3 ^ r8, r7, r9)
    else:  # DEC
        return pack(nxor(i4, i1), i1 ^ r10, i2 ^ r10, nxor(i6, i1), r8 ^ r9, nxor(i7, r7), r6, (~i2) & 1)


def sbox_8(sbox_in, enc_dec):
    """Replicate verilog sBox_8. Returns (sbox_out_enc, sbox_out_dec)."""
    base_new_enc, base_new_dec = isomorphism(sbox_in)
    base_new = (~(base_new_enc if enc_dec else base_new_dec)) & 0xFF
    stage1 = gf_inv_8_stage1(base_new)
    out_gf_inv8_1 = gf_inv_8_stage2(base_new, stage1)
    enc = (~isomorphism_inv(out_gf_inv8_1, 1)) & 0xFF  # ENC=1
    dec = (~isomorphism_inv(out_gf_inv8_1, 0)) & 0xFF  # DEC=0
    return enc, dec


if __name__ == "__main__":
    # Sanity: AES-SBOX values should match in (enc_dec=1, enc_out) and (enc_dec=0, dec_out)
    AES_SBOX_ENC = [
        0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    ]
    AES_SBOX_DEC = [
        0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36, 0xa5, 0x38, 0xbf, 0x40, 0xa3, 0x9e, 0x81, 0xf3, 0xd7, 0xfb,
    ]
    print("Sanity check (first 16):")
    for i in range(16):
        enc1, dec1 = sbox_8(i, 1)   # enc_dec=1 → enc_out should be AES_ENC
        enc0, dec0 = sbox_8(i, 0)   # enc_dec=0 → dec_out should be AES_DEC
        ok_enc = enc1 == AES_SBOX_ENC[i]
        ok_dec = dec0 == AES_SBOX_DEC[i]
        print(f"  in={i:02x}: enc_dec=1 enc_out=0x{enc1:02x} (AES=0x{AES_SBOX_ENC[i]:02x} {'✓' if ok_enc else 'X'})  "
              f"enc_dec=0 dec_out=0x{dec0:02x} (AES=0x{AES_SBOX_DEC[i]:02x} {'✓' if ok_dec else 'X'})")

    # Now print the 4 tables
    print()
    print("# Tables for sBox_8 (input -> output) per enc_dec mode:")
    table_enc_when_dec = [sbox_8(i, 0)[0] for i in range(256)]  # sbox_out_enc when enc_dec=DEC=0
    table_enc_when_enc = [sbox_8(i, 1)[0] for i in range(256)]  # sbox_out_enc when enc_dec=ENC=1 → AES_ENC
    table_dec_when_dec = [sbox_8(i, 0)[1] for i in range(256)]  # sbox_out_dec when enc_dec=DEC=0 → AES_DEC
    table_dec_when_enc = [sbox_8(i, 1)[1] for i in range(256)]  # sbox_out_dec when enc_dec=ENC=1
    for name, tab in [("ENC_OUT_WHEN_DEC", table_enc_when_dec),
                       ("ENC_OUT_WHEN_ENC", table_enc_when_enc),
                       ("DEC_OUT_WHEN_DEC", table_dec_when_dec),
                       ("DEC_OUT_WHEN_ENC", table_dec_when_enc)]:
        print(f"SBOX_{name} = [")
        for i in range(0, 256, 16):
            row = ", ".join(f"0x{tab[i+j]:02x}" for j in range(16))
            print(f"    {row},")
        print("]")

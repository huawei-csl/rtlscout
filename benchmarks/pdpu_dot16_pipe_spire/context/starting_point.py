# Spire port of the PDPU posit dot-product-accumulate unit (pdpu_top).
#
# Functional, BIT-EXACT port of the reference architecture
# (github.com/qleenju/PDPU, ISCAS 2023): N=4 posit(8,2) element vectors,
# posit(16,2) accumulator/result, ALIGN_WIDTH=14 alignment window.
#
#   result = acc + a0*b0 + a1*b1 + a2*b2 + a3*b3     (single fused rounding)
#
# The unit is deliberately inexact vs ideal posit arithmetic: aligned
# mantissas are truncated to the 14-bit window, accumulation is modular
# (mod 2^18), and NaR inputs decode to zero contributions — all reproduced
# here exactly. The correctness contract is bit-identity to the reference
# for every input (see ../description.txt).
from spire import Component, IORecord, Input, Output, UInt, Register
from spire.expr import Const, mux, cat

# ---- configuration (reference defaults) ----
N = 16            # dot-product size
N_I, ES_I = 8, 2     # input posit format
N_O, ES_O = 16, 2    # accumulator/output posit format
AW = 14          # alignment window


def _clog2(n):
    return (n - 1).bit_length()

ND_I = _clog2(N_I - 1)                 # 3
ND_O = _clog2(N_O - 1)                 # 4
EW_I = ND_I + ES_I                     # 5  (rg_exp_i is EW_I+1 = 6 bits)
EW_O = ND_O + ES_O                     # 6  (rg_exp_o is EW_O+1 = 7 bits)
MANT_I = N_I - ES_I - 3                # 3  (mantissa 4 bits incl. implicit)
MANT_O = N_O - ES_O - 3                # 11 (mantissa 12 bits incl. implicit)
EXPW = max(EW_I + 1, EW_O)             # 6  (working exponents: 7 bits)
MUL_W = 2 * (MANT_I + 1)               # 8
CARRY_W = _clog2(N + 1)                # 3
SUM_W = AW + CARRY_W                   # 17 (accumulate in SUM_W+1 = 18 bits)


def _clz(x, w):
    """Leading-zero count of a w-bit value + all-zero flag.

    Binary reduction tree, mirroring upstream lzc.sv (MODE=1): flip the vector
    so index 0 is the MSB, then combine pairs up a clog2(w)-deep tree carrying
    (any-set, index-of-first-set). A serial priority chain would be w muxes
    deep -- on the 19-bit normalise path that was the critical path.
    """
    levels = _clog2(w)
    nodes = [(x[w - 1 - i], Const(i, UInt(levels))) for i in range(w)]
    while len(nodes) < (1 << levels):                 # pad to a full tree
        nodes.append((Const(0, UInt(1)), Const(0, UInt(levels))))
    while len(nodes) > 1:
        nxt = []
        for a, b in zip(nodes[0::2], nodes[1::2]):
            nxt.append((a[0] | b[0], mux(a[0], a[1], b[1])))
        nodes = nxt
    sel, idx = nodes[0]
    empty = ~sel
    cnt = mux(empty, Const(w, UInt(6)),
              cat(idx, Const(0, UInt(6 - levels)))[0:6])
    return cnt, empty


def _sext(x, fw, tw):
    """Sign-extend a fw-bit two's-complement value to tw bits."""
    if tw <= fw:
        return x[0:tw]
    s = x[fw - 1]
    return cat(*([x[0:fw]] + [s] * (tw - fw)))


def _neg(x, w):
    """Two's complement of a w-bit value, truncated to w bits."""
    return ((~x[0:w]) + 1)[0:w]


def _decode(op, n, es):
    """Posit decode -> (sign, rg_exp[nd+es+1 bits, signed], mant[n-es-2 bits,
    incl. implicit top bit]). Mirrors posit_decoder.sv exactly."""
    nd = _clog2(n - 1)
    sign = op[n - 1]
    low = op[0:n - 1]
    val = mux(sign, _neg(low, n - 1), low)
    reg_s = val[n - 2]
    lzc_in = mux(reg_s, (~val)[0:n - 1], val)
    cnt, empty = _clz(lzc_in, n - 1)
    runlength = mux(empty, Const(n - 1, UInt(6)), cnt)
    # regime_k: runlength-1 when regS (positive regime), else -runlength
    rk = mux(reg_s,
             (runlength - 1)[0:nd + 1],
             _neg(runlength[0:nd + 1], nd + 1))
    regime_bits = mux(empty, Const(n - 1, UInt(6)), (cnt + 1)[0:6])
    shifted = (val << regime_bits)[0:n - 1]
    exp = shifted[n - 1 - es:n - 1]                    # es bits
    rg_exp = cat(exp, rk)                              # nd+1+es bits, signed
    implicit = low != 0
    mant = cat(shifted[2:n - 1 - es], implicit)        # n-es-2 bits
    return sign, rg_exp, mant


def _encode(sign, rg_exp, mant, n, es, mant_w):
    """Posit encode with RNE rounding. Mirrors posit_encoder.sv exactly.
    rg_exp: EXPW+1-bit signed; mant: mant_w+1 bits incl. implicit."""
    not_zero = mant[mant_w]
    ew = EXPW  # encoder instantiated with EXP_WIDTH = top-level EXPW
    regime_k = rg_exp[es:ew + 1]                       # ew+1-es bits, signed
    rk_w = ew + 1 - es                                 # 5
    expf = rg_exp[0:es]
    sign_k = rg_exp[ew]
    # initial regime pattern: 000..01 (k negative) or 111..10 (k >= 0)
    rg_const_pos = Const(1, UInt(n - 1))
    regime = mux(sign_k, rg_const_pos, (~rg_const_pos)[0:n - 1])
    regime_bits = mux(sign_k,
                      ((~regime_k) + 2)[0:rk_w],
                      (regime_k + 2)[0:rk_w])
    # {regime, exp, mant[mant_w-1:0]} — cat is LSB-first
    rg_exp_mant = cat(mant[0:mant_w], expf, regime)    # (n-1)+es+mant_w bits
    max_shift = mant_w + es + 1                        # 16
    shift_amount = mux(regime_bits >= n,
                       Const(max_shift, UInt(6)),
                       (regime_bits + (mant_w + es - n + 1))[0:6])
    total_w = (n - 1) + es + mant_w + max_shift        # 46
    value_before = (rg_exp_mant << max_shift)[0:total_w]
    value_after = value_before >> shift_amount
    rounding = value_after[0:max_shift]                # low max_shift bits
    vbr = value_after[max_shift:max_shift + n - 1]     # n-1 bits
    round_bit = rounding[max_shift - 1]
    sticky = rounding[0:max_shift - 1] != 0
    round_value = round_bit & (sticky | vbr[0])
    var = (vbr + round_value)[0:n - 1]
    normal = mux(sign,
                 cat(_neg(var, n - 1), Const(1, UInt(1))),
                 cat(var, Const(0, UInt(1))))
    return mux(not_zero, normal, Const(0, UInt(n)))


# ---- radix-4 Booth multiplier, structural (mirrors upstream) --------------
def _booth_encode(code):
    """3-bit Booth code -> (neg, one, two). booth_encoder.sv verbatim."""
    c0, c1, c2 = code[0], code[1], code[2]
    neg = (c2 & ~c0) | (c2 & ~c1)
    two = (~c2 & c1 & c0) | (c2 & ~c1 & ~c0)
    one = (c1 & ~c0) | (~c1 & c0)
    return neg, one, two


def _gen_product(a, code, w):
    """gen_product.sv: (partial_prod[w+1 bits], sign)."""
    neg, one, two = _booth_encode(code)
    a_ext = cat(a, Const(0, UInt(1)))          # zero-extend to w+1
    a_sh = (a << 1)[0:w + 1]                   # 2*A
    tmp = mux(one, a_ext, mux(two, a_sh, Const(0, UInt(w + 1))))
    return mux(neg, ~tmp, tmp), neg


def _gen_prods(a, b, w):
    """gen_prods.sv for WIDTH_A=WIDTH_B=w: COUNT=(w+2)/2 partial products,
    each WIDTH_O=2w bits, with upstream's exact sign-extension stuffing."""
    wo = 2 * w
    count = (w + 2) // 2
    # Verilog {2'b00, b, 1'b0} -> Spire cat() is LSB-first
    multiplier = cat(Const(0, UInt(1)), b, Const(0, UInt(2)))
    tmps, signs = [], []
    for i in range(count):
        code = multiplier[2 * i:2 * i + 3]
        t, s = _gen_product(a, code, w)
        tmps.append(t); signs.append(s)
    pps = []
    # pp[0] = {~s0, s0, s0, tmp0}
    pps.append(cat(tmps[0], signs[0], signs[0], ~signs[0])[0:wo])
    # pp[i] = {1'b1, ~si, tmpi, 1'b0, s(i-1)} << (2i-2), truncated to wo
    for i in range(1, count - 1):
        v = cat(signs[i - 1], Const(0, UInt(1)), tmps[i], ~signs[i], Const(1, UInt(1)))
        pps.append((v << (2 * i - 2))[0:wo])
    # pp[last] = {tmp_last, 1'b0, s(last-1)} << (2*count-4)
    v = cat(signs[count - 2], Const(0, UInt(1)), tmps[count - 1])
    pps.append((v << (2 * count - 4))[0:wo])
    return pps


def _csa3(p0, p1, p2, w):
    """compressor_3to2.sv: bitwise full adders; carry_o = {1'b0,carry,1'b0}."""
    s_bits, c_bits = [], []
    for i in range(w):
        x, y, z = p0[i], p1[i], p2[i]
        s_bits.append((x ^ y) ^ z)
        c_bits.append(((x ^ y) & z) | (x & y))
    summ = cat(*s_bits)
    carry = cat(*c_bits)
    return summ[0:w], (carry << 1)[0:w]


def _booth_mul(a, b, w):
    """radix4_booth_multiplier.sv -> redundant (sum, carry), each 2w bits."""
    pps = _gen_prods(a, b, w)
    assert len(pps) == 3, f"expected 3 partial products for w={w}, got {len(pps)}"
    return _csa3(pps[0], pps[1], pps[2], 2 * w)


def _compress_4to2(p0, p1, p2, p3, w):
    """compressor_4to2.sv: counter_5to3 per bit with a rippling cout->cin,
    carry_o = {carry[w-1]+cin[w], carry[w-2:0], 1'b0}."""
    cin = Const(0, UInt(1))
    s_bits, c_bits, cins = [], [], []
    for i in range(w):
        x1, x2, x3, x4 = p0[i], p1[i], p2[i], p3[i]
        x12 = x1 ^ x2
        x1234 = x12 ^ x3 ^ x4
        s_bits.append(x1234 ^ cin)
        c_bits.append((x1234 & cin) | (~x1234 & x4))
        cins.append(cin)
        cin = (x12 & x3) | (~x12 & x1)          # cout
    summ = cat(*s_bits)[0:w]
    # carry_temp = carry[w-1] + cin[w] (2 bits), then {carry_temp, carry[w-2:0], 1'b0}
    ct = (cat(c_bits[w - 1], Const(0, UInt(1))) + cat(cin, Const(0, UInt(1))))[0:2]
    carry = cat(Const(0, UInt(1)), cat(*c_bits[0:w - 1]), ct)
    return summ, carry[0:w]


def _csa_tree(ops, w):
    """csa_tree.sv: recursive halving down to 1/2/3/4-input base cases."""
    n = len(ops)
    if n == 1:
        return ops[0], Const(0, UInt(w))
    if n == 2:
        return ops[0], ops[1]
    if n == 3:
        return _csa3(ops[0], ops[1], ops[2], w)
    if n == 4:
        return _compress_4to2(ops[0], ops[1], ops[2], ops[3], w)
    n_a = n // 2
    sa, ca = _csa_tree(ops[:n_a], w)
    sb, cb = _csa_tree(ops[n_a:], w)
    # upstream: operands_i_C = '{sum_A, carry_A, sum_B, carry_B}
    return _compress_4to2(cb, sb, ca, sa, w)



def _comparator(a, b, w):
    """comparator.sv: signed max of two (w+1)-bit values, MSB = sign.
    sign_ab {a[w],b[w]}: 10 -> b, 01 -> a, else magnitude compare."""
    sa, sb = a[w], b[w]
    mag = mux(a[0:w] > b[0:w], a, b)
    return mux(sa & ~sb, b, mux(~sa & sb, a, mag))


def _comp_tree(ops, w):
    """comp_tree.sv: recursive halving; log-depth signed max."""
    n = len(ops)
    if n == 1:
        return ops[0]
    if n == 2:
        return _comparator(ops[0], ops[1], w)
    n_a = n // 2
    return _comparator(_comp_tree(ops[:n_a], w), _comp_tree(ops[n_a:], w), w)



class PdpuDot4(Component):
    def __init__(self):
        self.io = IORecord(
            operands_a=Input(UInt(N * N_I)),
            operands_b=Input(UInt(N * N_I)),
            acc=Input(UInt(N_O)),
            result_o=Output(UInt(N_O)),
        )
        self.elaborate()

    def elaborate(self):
        """Structural port of upstream pdpu_top_pipelined: same five FFNR cut
        points AND the same redundant carry-save form across pipe2 (the Booth
        + CSA multiplier emits (sum, carry), which pipe2 registers and the
        next stage resolves with a single add, exactly as upstream does)."""
        a_bus = self.io.operands_a
        b_bus = self.io.operands_b
        acc = self.io.acc
        MW = MANT_I + 1                     # multiplicand width (4)

        # ---- decode ----
        signs, rg_exps_ab, mants_a, mants_b = [], [], [], []
        for i in range(N):
            sa, ea, ma = _decode(a_bus[8 * i:8 * i + 8], N_I, ES_I)
            sb, eb, mb = _decode(b_bus[8 * i:8 * i + 8], N_I, ES_I)
            signs.append(sa ^ sb)
            ea_x = _sext(ea, EW_I + 1, EXPW + 1)
            eb_x = _sext(eb, EW_I + 1, EXPW + 1)
            rg_exps_ab.append((ea_x + eb_x)[0:EXPW + 1])
            mants_a.append(ma); mants_b.append(mb)
        s_acc, e_acc, m_acc = _decode(acc, N_O, ES_O)

        # ===== pipe1
        p1_signs = [Register(UInt(1), name=f"pipe1_sign{i}") for i in range(N)]
        p1_rgc = [Register(UInt(EXPW + 1), name=f"pipe1_rgc{i}") for i in range(N)]
        p1_ma = [Register(UInt(MW), name=f"pipe1_ma{i}") for i in range(N)]
        p1_mb = [Register(UInt(MW), name=f"pipe1_mb{i}") for i in range(N)]
        p1_sacc = Register(UInt(1), name="pipe1_sacc")
        p1_eacc = Register(UInt(EXPW + 1), name="pipe1_eacc")
        p1_macc = Register(UInt(MANT_O + 1), name="pipe1_macc")
        for i in range(N):
            p1_signs[i] <<= signs[i]; p1_rgc[i] <<= rg_exps_ab[i]
            p1_ma[i] <<= mants_a[i]; p1_mb[i] <<= mants_b[i]
        p1_sacc <<= s_acc
        p1_eacc <<= e_acc[0:EXPW + 1]
        p1_macc <<= m_acc

        # ---- Booth + CSA multiply -> REDUNDANT (sum, carry); max exponent ----
        mul_sum, mul_carry = [], []
        for i in range(N):
            s, c = _booth_mul(p1_ma[i], p1_mb[i], MW)
            mul_sum.append(s); mul_carry.append(c)
        rg_exps = [p1_rgc[i] for i in range(N)] + [p1_eacc]
        all_signs = [p1_signs[i] for i in range(N)] + [p1_sacc]
        # upstream uses a comp_tree (log depth), NOT a serial compare chain
        max_e = _comp_tree(rg_exps, EXPW)

        # ===== pipe2 — registers the REDUNDANT product, as upstream does
        p2_signs = [Register(UInt(1), name=f"pipe2_sign{i}") for i in range(N + 1)]
        p2_rge = [Register(UInt(EXPW + 1), name=f"pipe2_rge{i}") for i in range(N + 1)]
        p2_max = Register(UInt(EXPW + 1), name="pipe2_rg_exp_max")
        p2_msum = [Register(UInt(MUL_W), name=f"pipe2_mul_sum{i}") for i in range(N)]
        p2_mcar = [Register(UInt(MUL_W), name=f"pipe2_mul_carry{i}") for i in range(N)]
        p2_macc = Register(UInt(MANT_O + 1), name="pipe2_macc")
        for i in range(N + 1):
            p2_signs[i] <<= all_signs[i]; p2_rge[i] <<= rg_exps[i]
        p2_max <<= max_e
        for i in range(N):
            p2_msum[i] <<= mul_sum[i]; p2_mcar[i] <<= mul_carry[i]
        p2_macc <<= p1_macc

        # resolve the carry-save pair (upstream: mants_norm_c = sum + carry)
        mants_c = [(p2_msum[i] + p2_mcar[i])[0:MUL_W] for i in range(N)]

        # ---- align ----
        aligned = []
        for idx in range(N + 1):
            if idx < N:
                prod = (mants_c[idx] << (AW - MUL_W))[0:AW]
            else:
                p13 = (p2_macc << (AW - MANT_O - 2))[0:AW - 1]
                prod = cat(p13, Const(0, UInt(1)))
            diff = (p2_max - p2_rge[idx])[0:EXPW + 1]
            sh_w = _clog2(AW + 1)
            clamp = diff[sh_w:EXPW + 1] != 0
            shift = mux(clamp, Const(AW, UInt(sh_w + 1)), diff[0:sh_w])
            aligned.append(prod >> shift)

        # ---- two's-complement BEFORE pipe3 (upstream: mantissa_comp) ----
        mant_comp = []
        for idx in range(N + 1):
            m_ext = cat(aligned[idx][0:AW], Const(0, UInt(SUM_W + 1 - AW)))
            mant_comp.append(mux(p2_signs[idx], _neg(m_ext, SUM_W + 1), m_ext))

        # ===== pipe3 — registers mantissa_comp, exactly as upstream
        p3_max = Register(UInt(EXPW + 1), name="pipe3_rg_exp_max")
        p3_mc = [Register(UInt(SUM_W + 1), name=f"pipe3_mantissa_comp{i}")
                 for i in range(N + 1)]
        p3_max <<= p2_max
        for idx in range(N + 1):
            p3_mc[idx] <<= mant_comp[idx]

        # ---- accumulate: CSA tree over all N+1 terms, then ONE final add
        #      (upstream: csa_tree -> sum_result = csa_sum + csa_carry) ----
        csa_sum, csa_carry = _csa_tree([p3_mc[i] for i in range(N + 1)], SUM_W + 1)
        total = (csa_sum + csa_carry)[0:SUM_W + 1]

        # ===== pipe4
        p4_sum = Register(UInt(SUM_W + 1), name="pipe4_sum_result")
        p4_max = Register(UInt(EXPW + 1), name="pipe4_rg_exp_max")
        p4_sum <<= total
        p4_max <<= p3_max

        # ---- normalize ----
        final_sign = p4_sum[SUM_W]
        sum_c = mux(final_sign, _neg(p4_sum, SUM_W + 1)[0:SUM_W], p4_sum[0:SUM_W])
        cnt, empty = _clz(sum_c, SUM_W)
        dp1 = CARRY_W + 2 - 1
        cnt_x = cat(cnt, Const(0, UInt(EXPW + 1 - 6)))
        adj = mux(empty, Const(0, UInt(EXPW + 1)),
                  (Const(dp1, UInt(EXPW + 1)) - cnt_x)[0:EXPW + 1])
        sum_norm = (sum_c << cnt)[0:SUM_W]
        final_rg_exp = (p4_max + adj)[0:EXPW + 1]
        keep = MANT_O + 2
        sticky = sum_norm[0:SUM_W - keep] != 0
        final_mant = cat(sticky, sum_norm[SUM_W - keep:SUM_W])

        # ===== pipe5
        p5_sign = Register(UInt(1), name="pipe5_final_sign")
        p5_exp = Register(UInt(EXPW + 1), name="pipe5_final_rg_exp")
        p5_mant = Register(UInt(MANT_O + 3), name="pipe5_final_mant")
        p5_sign <<= final_sign
        p5_exp <<= final_rg_exp
        p5_mant <<= final_mant

        self.io.result_o <<= _encode(p5_sign, p5_exp, p5_mant,
                                     N_O, ES_O, MANT_O + 2)


PdpuDot4().to_netlist("pdpu_top_pipelined", with_clock=True,
                      with_reset=False).to_verilog_file("design.v")

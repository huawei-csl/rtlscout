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
from spire import Component, IORecord, Input, Output, UInt
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
    """Leading-zero count of a w-bit value (priority chain, LSB->MSB so the
    highest set bit wins), plus the all-zero flag. cnt is 6 bits."""
    cnt = Const(w, UInt(6))
    for i in range(w):
        cnt = mux(x[i], Const(w - 1 - i, UInt(6)), cnt)
    return cnt, x == 0


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
        a_bus = self.io.operands_a
        b_bus = self.io.operands_b
        acc = self.io.acc

        # ---- decode all operands ----
        signs, rg_exps, mants = [], [], []
        for i in range(N):
            sa, ea, ma = _decode(a_bus[8 * i:8 * i + 8], N_I, ES_I)
            sb, eb, mb = _decode(b_bus[8 * i:8 * i + 8], N_I, ES_I)
            signs.append(sa ^ sb)
            # product exponent: signed sum in EXPW+1 bits
            ea_x = _sext(ea, EW_I + 1, EXPW + 1)
            eb_x = _sext(eb, EW_I + 1, EXPW + 1)
            rg_exps.append((ea_x + eb_x)[0:EXPW + 1])
            # exact mantissa product (the reference's Booth mult is exact)
            mants.append((ma * mb)[0:MUL_W])
        s_acc, e_acc, m_acc = _decode(acc, N_O, ES_O)
        signs.append(s_acc)
        rg_exps.append(e_acc[0:EXPW + 1])              # already EXPW+1 bits
        mants.append(m_acc)

        # ---- maximum exponent (signed, via biased keys) ----
        bias = 1 << EXPW
        keys = [(e ^ Const(bias, UInt(EXPW + 1)))[0:EXPW + 1] for e in rg_exps]
        max_e = rg_exps[0]
        max_k = keys[0]
        for e, k in zip(rg_exps[1:], keys[1:]):
            take = k > max_k
            max_e = mux(take, e, max_e)
            max_k = mux(take, k, max_k)

        # ---- align into the AW-bit window ----
        aligned = []
        for idx in range(N + 1):
            if idx < N:
                prod = (mants[idx] << (AW - MUL_W))[0:AW]
            else:
                # 12b << 1 = 13b; zero-extend into the 14-bit window
                p13 = (mants[idx] << (AW - MANT_O - 2))[0:AW - 1]
                prod = cat(p13, Const(0, UInt(1)))
            diff = (max_e - rg_exps[idx])[0:EXPW + 1]  # unsigned, >= 0
            sh_w = _clog2(AW + 1)                      # 4
            clamp = diff[sh_w:EXPW + 1] != 0
            shift = mux(clamp, Const(AW, UInt(sh_w + 1)), diff[0:sh_w])
            aligned.append(prod >> shift)

        # ---- two's-complement accumulate mod 2^(SUM_W+1) ----
        total = Const(0, UInt(SUM_W + 1))
        for idx in range(N + 1):
            m = aligned[idx][0:AW]
            m_ext = cat(m, Const(0, UInt(SUM_W + 1 - AW)))
            m_c = mux(signs[idx], _neg(m_ext, SUM_W + 1), m_ext)
            total = (total + m_c)[0:SUM_W + 1]

        final_sign = total[SUM_W]
        sum_c = mux(final_sign, _neg(total, SUM_W + 1)[0:SUM_W],
                    total[0:SUM_W])

        # ---- normalize ----
        cnt, empty = _clz(sum_c, SUM_W)
        # exp_adjust = DECIMAL_POINT - 1 - lzc = (CARRY_W + 2) - 1 - lzc,
        # identical in both branches of the reference's if/else.
        dp1 = CARRY_W + 2 - 1                          # 4
        cnt_x = cat(cnt, Const(0, UInt(EXPW + 1 - 6)))
        adj = mux(empty, Const(0, UInt(EXPW + 1)),
                  (Const(dp1, UInt(EXPW + 1)) - cnt_x)[0:EXPW + 1])
        sum_norm = (sum_c << cnt)[0:SUM_W]
        final_rg_exp = (max_e + adj)[0:EXPW + 1]

        # ---- final mantissa: {norm[SUM_W-1 : SUM_W-MANT_O-2], sticky} ----
        keep = MANT_O + 2                              # 13
        sticky = sum_norm[0:SUM_W - keep] != 0
        final_mant = cat(sticky, sum_norm[SUM_W - keep:SUM_W])  # keep+1 = 14b

        self.io.result_o <<= _encode(final_sign, final_rg_exp, final_mant,
                                     N_O, ES_O, MANT_O + 2)


PdpuDot4().to_verilog_file("design.v", name="pdpu_top")

"""Floating-point adder (IEEE-like) for spire_hdl.

A lightweight behavioural adder mirroring the interface of the multiplier
helpers. It supports configurable exponent/fraction widths and basic handling
of NaN/Inf/zero plus subnormal inputs by treating their implicit leading bit as
0 and using an exponent of 1 for alignment.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from spirehdl.spirehdl_module import Component, Module
from spirehdl.spirehdl import Expr, Signal, UInt, cat, mux, Const
from spirehdl.arithmetic.int_arithmetic_config import (
    AdderConfig,
    build_adder,
)


@dataclass
class FpAddIO:
    a: Signal
    b: Signal
    y: Signal

class FpAdd(Component):

    def __init__(self, EW: int, FW: int, adder_cfg: Optional[AdderConfig] = None, subnormals: bool = True) -> None:
        self.EW = EW
        self.FW = FW
        self.W = 1 + EW + FW
        self.BIAS = (1 << (EW - 1)) - 1
        self.MAX_E = (1 << EW) - 1
        self.adder_cfg = adder_cfg
        self.subnormals = subnormals

        self.io: FpAddIO = FpAddIO(
            a=Signal(name="a", typ=UInt(self.W), kind="input"),
            b=Signal(name="b", typ=UInt(self.W), kind="input"),
            y=Signal(name="y", typ=UInt(self.W), kind="output"),
        )

        self.elaborate()

    # Helpers -------------------------------------------------------------
    def _shift_right(self, mant: Expr, shift: Expr) -> Expr:
        return mant >> shift

    def _leading_one_pos(self, mant: Expr, width: int) -> Expr:
        """
        Return index of the most-significant set bit in mant[0:width).
        If mant is zero, returns 0 (caller should gate with an explicit zero check).
        """
        pos_width = max(1, (width - 1).bit_length())
        pos = Const(0, UInt(pos_width))
        found = Const(0, UInt(1))
        for i in range(width - 1, -1, -1):
            idx = Const(i, UInt(pos_width))
            pos = mux(found, pos, mux(mant[i], idx, pos))
            found = found | mant[i]
        return pos

    def _extract_fields(self, operand: Expr) -> Tuple[Expr, Expr, Expr]:
        sign = operand[self.W - 1]
        exp = operand[self.FW : self.W - 1]
        frac = operand[0 : self.FW]
        return sign, exp, frac

    def _classify_operand(self, exp: Expr, frac: Expr) -> Tuple[Expr, Expr, Expr, Expr, Expr]:
        is_e_zero = exp == 0
        is_f_zero = frac == 0
        is_zero = is_e_zero & is_f_zero
        is_e_all1 = exp == self.MAX_E
        is_nan = is_e_all1 & (frac != 0)
        is_inf = is_e_all1 & (frac == 0)
        return is_zero, is_nan, is_inf, is_e_zero, is_f_zero

    def _effective_fields(self, exp: Expr, frac: Expr, is_exp_zero: Expr) -> Tuple[Expr, Expr]:
        hidden = mux(is_exp_zero, 0, 1)
        # cat() expects LSB-first ordering, so place the hidden/implicit bit last
        # to make it the MSB of the mantissa.
        mant = cat(frac, hidden)
        eff_exp = mux(is_exp_zero, 1, exp)
        return mant, eff_exp

    def _compute_sticky(self, m_small_ext: Expr, exp_delta: Expr) -> Expr:
        """OR of all bits of m_small_ext that are shifted out during alignment.

        Bit i of m_small_ext is shifted out when exp_delta > i.
        m_small_ext has width FW+3 (mantissa FW+1 bits + 2 zero guard bits at LSB),
        so the two LSBs are always 0 and never contribute.
        """
        sticky = Const(0, UInt(1))
        for i in range(self.FW + 3):
            sticky = sticky | (m_small_ext[i] & (exp_delta > i))
        return sticky

    def _align_operands(self, mA: Expr, mB: Expr, eA_eff: Expr, eB_eff: Expr, sA: Expr, sB: Expr) -> Tuple[Expr, Expr, Expr, Expr, Expr, Expr]:
        eA_gt = eA_eff > eB_eff
        e_eq = eA_eff == eB_eff
        mA_ge = mA >= mB
        a_is_bigger = eA_gt | (e_eq & mA_ge)
        exp_delta = mux(a_is_bigger, eA_eff - eB_eff, eB_eff - eA_eff)

        m_big = mux(a_is_bigger, mA, mB)
        m_small = mux(a_is_bigger, mB, mA)
        s_big = mux(a_is_bigger, sA, sB)
        s_small = mux(a_is_bigger, sB, sA)
        e_big = mux(a_is_bigger, eA_eff, eB_eff)

        m_big_ext = cat(Const(0, UInt(2)), m_big)
        m_small_ext = cat(Const(0, UInt(2)), m_small)
        m_small_shift = self._shift_right(m_small_ext, exp_delta)

        sticky = self._compute_sticky(m_small_ext, exp_delta)

        return e_big, m_big_ext, m_small_shift, s_big, s_small, sticky

    def _combine_mantissas(self, m_big_ext: Expr, m_small_shift: Expr, s_big: Expr, s_small: Expr) -> Tuple[Expr, Expr, Expr]:
        same_sign = s_big == s_small
        mant_add = build_adder(m_big_ext, m_small_shift, self.adder_cfg) if self.adder_cfg is not None else m_big_ext + m_small_shift
        mant_sub = m_big_ext - m_small_shift
        mant_mag = mux(same_sign, mant_add, mant_sub)
        zero_mag = mant_mag == 0
        sign_out = mux(zero_mag, s_big & s_small, s_big)
        return mant_mag, sign_out, same_sign

    def _subnormal_frac(self, mant_mag: Expr, e_big: Expr) -> Expr:
        """Compute the FW-bit subnormal fraction for a result with effective exponent e_big.

        subnormal_frac = (mant_mag * 2^(e_big - 3))[FW-1:0]

        For e_big <= 3: right-shift mant_mag by (3 - e_big), take lower FW bits.
        For e_big >  3: left-shift mant_mag by (e_big - 3), take lower FW bits.

        Subnormal results are only possible when e_big <= FW+2 (beyond that, shift_norm
        would exceed the mantissa width, which cannot occur).
        """
        mag_width = mant_mag.typ.width  # FW+4
        result = Const(0, UInt(self.FW))
        for e_val in range(1, min(self.MAX_E + 1, self.FW + 3)):
            if e_val <= 3:
                ra = 3 - e_val  # right-shift amount
                hi = ra + self.FW
                if hi <= mag_width:
                    candidate = mant_mag[ra:hi]
                else:
                    candidate = Const(0, UInt(self.FW))
            else:
                la = e_val - 3  # left-shift amount
                candidate = (mant_mag << la)[0 : self.FW]
            result = mux(e_big == e_val, candidate, result)
        return result

    def _normalize(self, mant_mag: Expr, e_big: Expr) -> Tuple[Expr, Expr, Expr, Expr]:
        # mant_mag width is FW+4: [FW+3] is possible carry-out, [FW+2] is the expected hidden bit.
        overflow = mant_mag[self.FW + 3]
        mant_post_over = mant_mag >> 1  # normalize when carry-out is set

        # Otherwise, shift left so that the leading 1 sits at bit (FW+2)
        lead_pos = self._leading_one_pos(mant_mag, mant_mag.typ.width)
        shift_norm = (self.FW + 2) - lead_pos
        mant_norm = mux(overflow, mant_post_over, mant_mag << shift_norm)
        exp_pre = e_big + mux(overflow, 1, 0) - mux(overflow, 0, shift_norm)
        return mant_norm, exp_pre, overflow, shift_norm

    def _apply_rounding(
        self, mant_norm: Expr, exp_pre: Expr, overflow_flag: Expr, mant_mag: Expr, sticky_align: Expr, same_sign: Expr
    ) -> Tuple[Expr, Expr]:
        """Apply IEEE round-to-nearest-even using guard (G), round (R), sticky (S) bits.

        After normalization mant_norm layout:
          [FW+2]      hidden bit (implicit 1)
          [2:FW+2]    fraction (FW bits)
          [1]         guard G
          [0]         round R

        sticky_align: OR of bits shifted out of the small operand during alignment.
        In the overflow-normalization case (right shift by 1), mant_mag[0] is also
        shifted out and must be folded into S.

        For subtraction (same_sign=0), sticky bits mean the true result is BELOW
        mant_mag (the borrow propagation reduces the magnitude).  Using S to trigger
        round-up would over-round; instead sticky suppresses the tie-break round-up.
        """
        G = mant_norm[1]
        R = mant_norm[0]
        S = sticky_align | (overflow_flag & mant_mag[0])
        LSB = mant_norm[2]
        # Addition: round up when G & (R | S | LSB)  — standard RNE
        do_round_add = G & (R | S | LSB)
        # Subtraction: sticky means result < midpoint → only round up on exact tie (S==0)
        do_round_sub = G & (R | (S == 0) & LSB)
        do_round = mux(same_sign, do_round_add, do_round_sub)

        frac_raw = mant_norm[2 : self.FW + 2]
        round_carry = do_round & (frac_raw == (1 << self.FW) - 1)
        frac_final = mux(do_round, (frac_raw + 1)[0 : self.FW], frac_raw)
        exp_final = exp_pre + mux(round_carry, 1, 0)
        return frac_final, exp_final

    def _select_special_result(
        self,
        sign_out: Expr,
        exp_out: Expr,
        frac_out: Expr,
        sA: Expr,
        sB: Expr,
        is_infA: Expr,
        is_infB: Expr,
        is_nanA: Expr,
        is_nanB: Expr,
    ) -> Tuple[Expr, Expr, Expr]:
        nan_in = is_nanA | is_nanB
        inf_in = is_infA | is_infB

        # +Inf + (-Inf) = NaN; all other Inf cases = Inf
        both_inf_opposite = is_infA & is_infB & (sA != sB)
        use_nan = nan_in | both_inf_opposite
        use_inf = inf_in & ~use_nan
        # Inf sign: propagate from the one Inf operand; when both are same-sign Inf, use sign_out
        sign_special = mux(is_infA & ~is_infB, sA, mux(is_infB & ~is_infA, sB, sign_out))

        exp_field = mux(use_nan, self.MAX_E, mux(use_inf, self.MAX_E, exp_out))
        nan_payload = (
            Const(1 << (self.FW - 1 if self.FW > 0 else 0), UInt(self.FW))
            if self.FW > 0
            else Const(1, UInt(1))
        )
        frac_field = mux(use_nan, nan_payload, mux(use_inf, 0, frac_out))
        # NaN output always uses sign=0 (canonical quiet NaN)
        sign_field = mux(use_nan, 0, mux(use_inf, sign_special, sign_out))

        return sign_field, exp_field, frac_field

    def elaborate(self) -> None:
        a = self.io.a
        b = self.io.b
        y = self.io.y

        sA, eA, fA = self._extract_fields(a)
        sB, eB, fB = self._extract_fields(b)

        (
            _,
            is_nanA,
            is_infA,
            is_eA_zero,
            _,
        ) = self._classify_operand(eA, fA)
        (
            _,
            is_nanB,
            is_infB,
            is_eB_zero,
            _,
        ) = self._classify_operand(eB, fB)

        mA, eA_eff = self._effective_fields(eA, fA, is_eA_zero)
        mB, eB_eff = self._effective_fields(eB, fB, is_eB_zero)

        e_big, m_big_ext, m_small_shift, s_big, s_small, sticky = self._align_operands(
            mA, mB, eA_eff, eB_eff, sA, sB
        )
        mant_mag, sign_out, same_sign = self._combine_mantissas(m_big_ext, m_small_shift, s_big, s_small)

        mant_norm, exp_pre, overflow_flag, shift_norm = self._normalize(mant_mag, e_big)

        frac_final, exp_final = self._apply_rounding(mant_norm, exp_pre, overflow_flag, mant_mag, sticky, same_sign)

        # Subnormal output: when e_big <= shift_norm the normalized exponent exp_pre <= 0.
        # When subnormals=True, emit a subnormal result; otherwise flush to zero.
        is_subnormal_out = (~overflow_flag) & (e_big <= shift_norm)

        # Overflow: exponent reached MAX_E (includes rounding-induced overflow to Inf)
        overflow_exp = exp_final >= self.MAX_E

        is_zero_res = mant_mag == 0
        # Priority: zero > subnormal > overflow > normal.
        # is_subnormal_out must be checked before overflow_exp because negative exp_pre
        # wraps to a large unsigned value that incorrectly triggers overflow_exp.
        if self.subnormals:
            sub_frac = self._subnormal_frac(mant_mag, e_big)
            exp_out = mux(is_zero_res, 0,
                      mux(is_subnormal_out, 0,
                      mux(overflow_exp, self.MAX_E,
                      exp_final)))
            frac_out = mux(is_zero_res, 0,
                       mux(is_subnormal_out, sub_frac,
                       mux(overflow_exp, 0,
                       frac_final)))
        else:
            # Flush-to-zero: subnormal results become +0
            exp_out = mux(is_zero_res | is_subnormal_out, 0,
                      mux(overflow_exp, self.MAX_E,
                      exp_final))
            frac_out = mux(is_zero_res | is_subnormal_out, 0,
                       mux(overflow_exp, 0,
                       frac_final))

        sign_field, exp_field, frac_field = self._select_special_result(
            sign_out, exp_out, frac_out, sA, sB, is_infA, is_infB, is_nanA, is_nanB
        )

        y <<= cat(frac_field, exp_field[0 : self.EW], sign_field)


def build_fp_add(name: str, EW: int, FW: int, subnormals: bool = True) -> Module:
    comp = FpAdd(EW, FW, subnormals=subnormals)
    return comp.to_module(name, with_clock=False, with_reset=False)


def build_f16_add(name: str = "F16Add") -> Module:
    return build_fp_add(name, EW=5, FW=10)


def build_bf16_add(name: str = "BF16Add") -> Module:
    return build_fp_add(name, EW=8, FW=7)

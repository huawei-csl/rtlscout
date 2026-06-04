# =========================
# Floating-point multiplier
# (now with optional subnormals)
# =========================
# Parameterizable by exponent width (EW) and fraction width (FW).
# - float16:  EW=5, FW=10
# - bfloat16: EW=8, FW=7
#
# Args:
#   name: module name
#   EW, FW: widths
#   subnormals: enable subnormal in/out (gradual underflow). Default False = flush-to-zero.
#
# Requires: Module, UInt, Bool, mux, cat from your spire_hdl.

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from spirehdl.spirehdl_module import Component, Module
from spirehdl.spirehdl import *
from spirehdl.spirehdl_simulator import Simulator
from spirehdl.arithmetic.int_arithmetic_config import (
    MultiplierConfig,
    build_multiplier,
)


# Uses: Module, UInt, Bool, mux, cat (from your spire_hdl)


# ---- helpers used inside FpMulSN ----
def _or_reduce_bits(vec_expr: Expr, hi: int, lo: int) -> Expr:
    if hi < lo:
        return 0
    acc = 0
    for i in range(lo, hi + 1):
        acc = acc | vec_expr[i]
    return acc


def _prefix_or_bits(x: Expr, width: int) -> List[Expr]:
    """Return [ OR(x[0:0]), OR(x[0:1]), ..., OR(x[0:width-1]) ]"""
    out = []
    if width <= 0:
        return out
    acc = x[0]
    out.append(acc)
    for i in range(1, width):
        acc = acc | x[i]
        out.append(acc)
    return out


class FpMulSN(Component):

    @dataclass
    class IO:
        a: Signal  # input
        b: Signal  # input
        y: Signal  # output

    def __init__(self, EW: int, FW: int, *, subnormals: bool = True, always_subnormal_rounding: bool = False, mult_cfg: Optional[MultiplierConfig] = None) -> None:
        self.EW = EW
        self.FW = FW
        self.W = 1 + EW + FW
        self.subnormals = subnormals
        self.always_subnormal_rounding = always_subnormal_rounding # may be required for some configuration parameters for full compatimity when subnormal is false (no rounding errors, see tests)  
        self.BIAS = (1 << (EW - 1)) - 1
        self.MAX_E = (1 << EW) - 1
        self.MAX_FINITE_E = self.MAX_E - 1
        self.mult_cfg = mult_cfg

        self.io = self.IO(
            a=Signal(name="a", typ=UInt(self.W), kind="input"),
            b=Signal(name="b", typ=UInt(self.W), kind="input"),
            y=Signal(name="y", typ=UInt(self.W), kind="output"),
        )

        self.elaborate()
    def _extract_fields(self, a: Expr, b: Expr) -> Tuple[Expr, Expr, Expr, Expr, Expr, Expr]:
        W = self.W
        FW = self.FW
        sA = a[W - 1]
        sB = b[W - 1]
        eA = a[FW : W - 1]
        eB = b[FW : W - 1]
        fA = a[0:FW]
        fB = b[0:FW]
        return sA, sB, eA, eB, fA, fB

    def _classify_operands(self, eA: Expr, eB: Expr, fA: Expr, fB: Expr) -> Dict[str, Expr]:
        exp_all_ones = self.MAX_E

        is_eA_zero = eA == 0
        is_eB_zero = eB == 0
        is_fA_zero = fA == 0
        is_fB_zero = fB == 0

        is_zeroA = is_eA_zero & is_fA_zero
        is_zeroB = is_eB_zero & is_fB_zero

        is_eA_all1 = eA == exp_all_ones
        is_eB_all1 = eB == exp_all_ones

        is_nanA = is_eA_all1 & (fA != 0)
        is_nanB = is_eB_all1 & (fB != 0)
        is_infA = is_eA_all1 & (fA == 0)
        is_infB = is_eB_all1 & (fB == 0)

        is_nan_in = is_nanA | is_nanB | ((is_infA & is_zeroB) | (is_zeroA & is_infB))
        is_inf_in = is_infA | is_infB
        is_zero_in = is_zeroA | is_zeroB

        return {
            "is_eA_zero": is_eA_zero,
            "is_eB_zero": is_eB_zero,
            "is_zeroA": is_zeroA,
            "is_zeroB": is_zeroB,
            "is_nan_in": is_nan_in,
            "is_inf_in": is_inf_in,
            "is_zero_in": is_zero_in,
        }
    def _effective_operands(self, eA: Expr, eB: Expr, fA: Expr, fB: Expr, is_eA_zero: Expr, is_eB_zero: Expr) -> Tuple[Expr, Expr, Expr, Expr]:
        FW = self.FW
        if self.subnormals:
            hiddenA = mux(is_eA_zero, 0, 1)
            hiddenB = mux(is_eB_zero, 0, 1)
            mA_eff = cat(fA, hiddenA)
            mB_eff = cat(fB, hiddenB)
            eA_eff = mux(is_eA_zero, 1, eA)
            eB_eff = mux(is_eB_zero, 1, eB)
        else:
            mask = (1 << (1 + FW)) - 1
            mA_eff = (cat(fA, 1)) & mux(is_eA_zero, 0, mask)
            mB_eff = (cat(fB, 1)) & mux(is_eB_zero, 0, mask)
            eA_eff = eA
            eB_eff = eB
        return mA_eff, mB_eff, eA_eff, eB_eff

    def _leading_zero_count(self, prod: Expr) -> Expr:
        FW = self.FW
        PROD_W = 2 + 2 * FW
        msb_flags = []
        for i in range(PROD_W - 1, -1, -1):
            upper_zero = 1 if i == PROD_W - 1 else prod[i + 1 : PROD_W] == 0
            msb_flags.append(upper_zero & prod[i])

        lz = 0
        for idx, flag in enumerate(msb_flags):
            i = (PROD_W - 1) - idx
            lz_const = (PROD_W - 1) - i
            lz = mux(flag, lz_const, lz)

        return lz

    def _normalize_and_round(self, prod: Expr, lz: Expr) -> Tuple[Expr, Expr, Expr]:
        FW = self.FW
        PROD_W = 2 + 2 * FW

        need_right = lz <= (FW + 1)
        sr = (FW + 1) - lz
        sl = lz - (FW + 1)

        shifted = mux(need_right, prod >> sr, prod << sl)
        mant_pre = shifted[0:FW + 1]

        pref = _prefix_or_bits(prod, PROD_W)

        def _bit_at(vec: Expr, idx_expr: Expr) -> Expr:
            acc = 0
            for k in range(PROD_W):
                acc = mux(idx_expr == k, vec[k], acc)
            return acc

        def _pref_at(idx_expr: Expr) -> Expr:
            acc = 0
            for k in range(PROD_W):
                acc = mux(idx_expr == k, pref[k], acc)
            return acc

        guard_r = _bit_at(prod, sr - 1)
        sticky_r = _pref_at(sr - 2)
        guard = mux(need_right, guard_r, 0)
        sticky = mux(need_right, sticky_r, 0)

        lsb = mant_pre[0]
        round_up = guard & (sticky | lsb)

        mant_round = mant_pre + mux(round_up, 1, 0)
        carry = mant_round[FW + 1]
        mant_post = mux(carry, mant_round[1 : FW + 2], mant_round[0:FW + 1])
        frac_norm = mant_post[0:FW]
        return mant_post, frac_norm, carry

    def _exponent_path(self, eA_eff: Expr, eB_eff: Expr, carry: Expr, lz: Expr) -> Tuple[Expr, Expr, Expr, Expr]:
        EW = self.EW
        exp_sum = eA_eff + eB_eff
        lhs = (exp_sum + 1) + mux(carry, 1, 0)

        limit_under = self.BIAS + lz
        limit_over = (self.BIAS + self.MAX_FINITE_E) + lz

        underflow = lhs <= limit_under
        overflow = lhs > limit_over

        e_norm = lhs - limit_under
        exp_field_norm = e_norm[0:EW]
        return exp_field_norm, underflow, overflow, exp_sum

    def _subnormal_rounding_direct(self, prod: Expr, total_shift: Expr) -> Tuple[Expr, Expr]:
        """Single-step RNE rounding from raw prod to subnormal output.

        total_shift = BIAS + FW + 1 - exp_sum  (independent of lz and carry).
        Avoids the double-rounding that occurs when working from mant_post.
        """
        FW = self.FW
        PROD_W = 2 + 2 * FW

        frac_trunc = (prod >> total_shift)[0:FW]

        pref = _prefix_or_bits(prod, PROD_W)

        def _bit_at(idx_expr: Expr) -> Expr:
            acc = 0
            for k in range(PROD_W):
                acc = mux(idx_expr == k, prod[k], acc)
            return acc

        def _pref_at(idx_expr: Expr) -> Expr:
            acc = 0
            for k in range(PROD_W):
                acc = mux(idx_expr == k, pref[k], acc)
            return acc

        guard = _bit_at(total_shift - 1)
        sticky = _pref_at(total_shift - 2)

        lsb = frac_trunc[0]
        round_up = guard & (sticky | lsb)

        frac_trunc_zext = cat(frac_trunc, 0)
        frac_sum = frac_trunc_zext + mux(round_up, 1, 0)
        carry_s = frac_sum[FW]
        frac_field_sub = frac_sum[0:FW]
        exp_field_sub = mux(carry_s, 1, 0)
        return exp_field_sub, frac_field_sub

    def _pack_result(self, sY: Expr, exp_field_norm: Expr, frac_norm: Expr, *, is_nan_in: Expr, is_inf_in: Expr, is_zero_in: Expr, underflow: Expr, overflow: Expr, exp_field_sub: Optional[Expr], frac_field_sub: Optional[Expr]) -> Tuple[Expr, Expr, Expr]:
        EW = self.EW
        FW = self.FW
        all1_E = (1 << EW) - 1
        qnan_payload = (1 << (FW - 1)) if FW > 0 else 1

        is_nan = is_nan_in
        # Overflow must not trigger inf when the product is trivially zero;
        # lz is undefined for prod=0, so overflow can fire spuriously.
        is_inf = (~is_nan) & (is_inf_in | (overflow & ~is_zero_in))

        if self.subnormals:
            is_sub_out = (~is_nan) & (~is_inf) & underflow
            sub_is_zero = is_sub_out & ((exp_field_sub == 0) & (frac_field_sub == 0))
            is_zero = (~is_nan) & (~is_inf) & (is_zero_in | sub_is_zero)

            exp_field = mux(
                is_nan | is_inf,
                all1_E,
                mux(is_zero, 0, mux(is_sub_out, exp_field_sub, exp_field_norm)),
            )
            frac_field = mux(
                is_nan,
                qnan_payload,
                mux(is_inf | is_zero, 0, mux(is_sub_out, frac_field_sub, frac_norm)),
            )
        elif self.always_subnormal_rounding:
            # FTZ with correct subnormal/normal boundary: flush truly-subnormal outputs
            # to zero, but preserve the result when subnormal rounding reaches min_normal.
            is_sub_out = (~is_nan) & (~is_inf) & underflow
            sub_is_zero = is_sub_out & (exp_field_sub == 0)
            is_zero = (~is_nan) & (~is_inf) & (is_zero_in | sub_is_zero)

            exp_field = mux(
                is_nan | is_inf,
                all1_E,
                mux(is_zero, 0, mux(is_sub_out, exp_field_sub, exp_field_norm)),
            )
            frac_field = mux(
                is_nan,
                qnan_payload,
                mux(is_inf | is_zero, 0, mux(is_sub_out, frac_field_sub, frac_norm)),
            )
        else:
            is_zero = (~is_nan) & (~is_inf) & (is_zero_in | underflow)
            exp_field = mux(is_nan | is_inf, all1_E, mux(is_zero, 0, exp_field_norm))
            frac_field = mux(is_nan, qnan_payload, mux(is_inf | is_zero, 0, frac_norm))

        sign_field = mux(is_nan, 0, sY)
        return sign_field, exp_field, frac_field

    def elaborate(self) -> None:
        a = self.io.a
        b = self.io.b
        y = self.io.y

        sA, sB, eA, eB, fA, fB = self._extract_fields(a, b)
        cls = self._classify_operands(eA, eB, fA, fB)

        sY = sA ^ sB

        mA_eff, mB_eff, eA_eff, eB_eff = self._effective_operands(
            eA, eB, fA, fB, cls["is_eA_zero"], cls["is_eB_zero"]
        )

        prod = build_multiplier(mA_eff, mB_eff, self.mult_cfg) if self.mult_cfg is not None else mA_eff * mB_eff
        lz = self._leading_zero_count(prod)

        mant_post, frac_norm, carry = self._normalize_and_round(prod, lz)

        exp_field_norm, underflow, overflow, exp_sum = self._exponent_path(
            eA_eff, eB_eff, carry, lz
        )

        exp_field_sub = None
        frac_field_sub = None
        if self.subnormals or self.always_subnormal_rounding:
            total_shift = (self.BIAS + self.FW + 1) - exp_sum
            exp_field_sub, frac_field_sub = self._subnormal_rounding_direct(prod, total_shift)

        sign_field, exp_field, frac_field = self._pack_result(
            sY,
            exp_field_norm,
            frac_norm,
            is_nan_in=cls["is_nan_in"],
            is_inf_in=cls["is_inf_in"],
            is_zero_in=cls["is_zero_in"],
            underflow=underflow,
            overflow=overflow,
            exp_field_sub=exp_field_sub,
            frac_field_sub=frac_field_sub,
        )

        y <<= cat(frac_field, exp_field, sign_field)


def build_fp_mul_sn(name: str, EW: int, FW: int, *, subnormals: bool = True, always_subnormal_rounding: bool = False) -> "Module":
    comp = FpMulSN(EW, FW, subnormals=subnormals, always_subnormal_rounding=always_subnormal_rounding)
    return comp.to_module(name, with_clock=False, with_reset=False)



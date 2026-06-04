"""Optimised floating-point multiplier component (v15 architecture).

Logic copied verbatim from references/design_v15.py (lines 25-208).
Wrapped as a spirehdl Component; only the class/init boilerplate is new.
The multiplier and adder are made configurable via mult_cfg / adder_cfg.
"""

from dataclasses import dataclass
from typing import Optional

from spirehdl.spirehdl_module import Component
from spirehdl.spirehdl import *
from spirehdl.arithmetic.int_arithmetic_config import (
    AdderConfig,
    MultiplierConfig,
    build_adder,
    build_multiplier,
)


class FpMulV15(Component):
    """v15-optimised FP multiplier. IO is identical to FpMulSN."""

    @dataclass
    class IO:
        a: Signal
        b: Signal
        y: Signal

    def __init__(
        self,
        EW: int,
        FW: int,
        *,
        subnormals: bool = True,
        always_subnormal_rounding: bool = False,
        mult_cfg: Optional[MultiplierConfig] = None,
        adder_cfg: Optional[AdderConfig] = None,
    ) -> None:
        self.EW = EW
        self.FW = FW
        self.W = 1 + EW + FW
        self.BIAS = (1 << (EW - 1)) - 1
        self.MAX_E = (1 << EW) - 1
        self.MAX_FINITE_E = self.MAX_E - 1
        self.PROD_W = 2 * (FW + 1)
        self.subnormals = subnormals
        self.always_subnormal_rounding = always_subnormal_rounding
        self.mult_cfg = mult_cfg
        self.adder_cfg = adder_cfg

        self.io = self.IO(
            a=Signal(name="a", typ=UInt(self.W), kind="input"),
            b=Signal(name="b", typ=UInt(self.W), kind="input"),
            y=Signal(name="y", typ=UInt(self.W), kind="output"),
        )
        self.elaborate()

    def elaborate(self) -> None:
        # Map instance attributes to local names matching design_v15.py
        EW = self.EW
        FW = self.FW
        W = self.W
        BIAS = self.BIAS
        MAX_E = self.MAX_E
        MAX_FINITE_E = self.MAX_FINITE_E
        PROD_W = self.PROD_W
        mult_cfg = self.mult_cfg
        adder_cfg = self.adder_cfg
        a, b, y = self.io.a, self.io.b, self.io.y

        # --- Logic copied verbatim from references/design_v15.py (lines 25-208) ---
        sA = a[W - 1]
        sB = b[W - 1]
        eA = a[FW:W - 1]
        eB = b[FW:W - 1]
        fA = a[0:FW]
        fB = b[0:FW]

        is_eA_zero = eA == 0
        is_eB_zero = eB == 0
        is_fA_zero = fA == 0
        is_fB_zero = fB == 0
        is_zeroA = is_eA_zero & is_fA_zero
        is_zeroB = is_eB_zero & is_fB_zero

        is_eA_all1 = eA == MAX_E
        is_eB_all1 = eB == MAX_E
        is_nanA = is_eA_all1 & (~is_fA_zero)
        is_nanB = is_eB_all1 & (~is_fB_zero)
        is_infA = is_eA_all1 & is_fA_zero
        is_infB = is_eB_all1 & is_fB_zero

        is_nan_in = is_nanA | is_nanB | ((is_infA & is_zeroB) | (is_zeroA & is_infB))
        is_inf_in = is_infA | is_infB
        is_zero_in = is_zeroA | is_zeroB
        sY = sA ^ sB

        hiddenA = mux(is_eA_zero, 0, 1)
        hiddenB = mux(is_eB_zero, 0, 1)
        mA_eff = cat(fA, hiddenA)
        mB_eff = cat(fB, hiddenB)
        eA_eff = mux(is_eA_zero, 1, eA)
        eB_eff = mux(is_eB_zero, 1, eB)

        prod = build_multiplier(mA_eff, mB_eff, mult_cfg) if mult_cfg is not None else mA_eff * mB_eff

        # --- Prefix OR for sticky ---
        pref_or = [None] * PROD_W
        pref_or[0] = prod[0]
        for i in range(1, PROD_W):
            pref_or[i] = pref_or[i-1] | prod[i]

        # --- Pre-compute rounded mantissa for each leading-1 position ---
        # For each p: compute mant, guard, sticky, round_up, mant_rounded, carry
        mant_round_for = []
        carry_for = []
        lz_for = []

        for p in range(PROD_W):
            lo = max(0, p - FW)
            hi = p + 1
            nbits = hi - lo
            if nbits >= FW + 1:
                mant_val = prod[p-FW:p+1]
            else:
                mant_val = cat(Const(0, UInt(FW + 1 - nbits)), prod[lo:hi])

            if p >= FW + 1:
                guard_val = prod[p - FW - 1]
            else:
                guard_val = Const(0, UInt(1))

            if p >= FW + 2:
                sticky_val = pref_or[p - FW - 2]
            else:
                sticky_val = Const(0, UInt(1))

            lsb = mant_val[0]
            round_up = guard_val & (sticky_val | lsb)
            # Pre-compute the rounded mantissa (FW+2 bits to include carry)
            rounded = mant_val + mux(round_up, 1, 0)

            mant_round_for.append(rounded)
            carry_for.append(rounded[FW + 1])
            lz_for.append(Const(21 - p, UInt(5)))

        def make_item(p):
            return (prod[p], mant_round_for[p], lz_for[p])

        def merge_priority(lo_item, hi_item):
            lo_any, lo_mr, lo_lz = lo_item
            hi_any, hi_mr, hi_lz = hi_item
            any_set = hi_any | lo_any
            mr_sel = mux(hi_any, hi_mr, lo_mr)
            lz_sel = mux(hi_any, hi_lz, lo_lz)
            return (any_set, mr_sel, lz_sel)

        items = [make_item(p) for p in range(PROD_W)]
        while len(items) < 32:
            items.append((Const(0, UInt(1)), Const(0, UInt(FW+2)), Const(21, UInt(5))))

        while len(items) > 1:
            new_items = []
            for i in range(0, len(items), 2):
                merged = merge_priority(items[i], items[i+1])
                new_items.append(merged)
            items = new_items

        _, mant_round, lz = items[0]

        carry = mant_round[FW + 1]

        exp_sum = build_adder(eA_eff, eB_eff, adder_cfg) if adder_cfg is not None else eA_eff + eB_eff

        lhs_nc = exp_sum + 1
        lhs_c = exp_sum + 2

        limit_under = BIAS + lz
        limit_over = (BIAS + MAX_FINITE_E) + lz

        underflow_nc = lhs_nc <= limit_under
        overflow_nc = lhs_nc > limit_over
        e_norm_nc = (lhs_nc - limit_under)[0:EW]

        underflow_c = lhs_c <= limit_under
        overflow_c = lhs_c > limit_over
        e_norm_c = (lhs_c - limit_under)[0:EW]

        # --- Subnormal path ---
        def bsr(val, amt, width, nbits):
            r = val
            for i in range(nbits):
                s = 1 << i
                r = mux(amt[i], (r >> s)[0:width], r[0:width])
            return r

        total_shift = (BIAS + FW + 1) - exp_sum
        ts_m1 = (total_shift - 1)[0:5]

        prod_shifted = bsr(prod, ts_m1, PROD_W, 5)
        sub_guard = prod_shifted[0]
        frac_trunc = prod_shifted[1:FW+1]

        pref_vec = cat(*pref_or)
        ts_m2 = (total_shift - 2)[0:5]
        sub_sticky_val = bsr(pref_vec, ts_m2, PROD_W, 5)
        sub_sticky_raw = sub_sticky_val[0]
        sub_sticky = mux(total_shift <= 1, 0, sub_sticky_raw)

        sub_lsb = frac_trunc[0]
        sub_round_up = sub_guard & (sub_sticky | sub_lsb)

        frac_trunc_zext = cat(frac_trunc, Const(0, UInt(1)))
        frac_sum = frac_trunc_zext + mux(sub_round_up, 1, 0)
        carry_s = frac_sum[FW]
        frac_field_sub = frac_sum[0:FW]
        exp_field_sub = mux(carry_s, 1, 0)

        # --- Pack ---
        is_nan = is_nan_in
        is_not_nan = ~is_nan
        sub_is_zero = (exp_field_sub == 0) & (frac_field_sub == 0)

        is_inf_nc = is_not_nan & (is_inf_in | (overflow_nc & ~is_zero_in))
        is_sub_nc = is_not_nan & (~is_inf_nc) & underflow_nc
        is_zero_nc = is_not_nan & (~is_inf_nc) & (is_zero_in | (is_sub_nc & sub_is_zero))

        frac_norm_nc = mant_round[0:FW]
        frac_nc = mux(is_nan, Const(1 << (FW-1), UInt(FW)),
                  mux(is_inf_nc | is_zero_nc, Const(0, UInt(FW)),
                  mux(is_sub_nc, frac_field_sub, frac_norm_nc)))

        exp_nc = mux(is_nan | is_inf_nc, Const(MAX_E, UInt(EW)),
                 mux(is_zero_nc, Const(0, UInt(EW)),
                 mux(is_sub_nc, exp_field_sub, e_norm_nc)))

        is_inf_c = is_not_nan & (is_inf_in | (overflow_c & ~is_zero_in))
        is_sub_c = is_not_nan & (~is_inf_c) & underflow_c
        is_zero_c = is_not_nan & (~is_inf_c) & (is_zero_in | (is_sub_c & sub_is_zero))

        frac_norm_c = mant_round[1:FW+1]
        frac_c = mux(is_nan, Const(1 << (FW-1), UInt(FW)),
                 mux(is_inf_c | is_zero_c, Const(0, UInt(FW)),
                 mux(is_sub_c, frac_field_sub, frac_norm_c)))

        exp_c = mux(is_nan | is_inf_c, Const(MAX_E, UInt(EW)),
                mux(is_zero_c, Const(0, UInt(EW)),
                mux(is_sub_c, exp_field_sub, e_norm_c)))

        sign_field = mux(is_nan, 0, sY)

        result_nc = cat(frac_nc, exp_nc, sign_field)
        result_c = cat(frac_c, exp_c, sign_field)

        y <<= mux(carry, result_c, result_nc)


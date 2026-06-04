"""Optimised floating-point multiplier component (v22 architecture).

Logic copied verbatim from references/design_v22.py (lines 19-190).
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


class FpMulV22(Component):
    """v22-optimised FP multiplier. IO is identical to FpMulSN."""

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
        # Map instance attributes to local names matching design_v22.py
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

        # --- Logic copied verbatim from references/design_v22.py (lines 19-190) ---
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

        is_nan = is_nanA | is_nanB | ((is_infA & is_zeroB) | (is_zeroA & is_infB))
        is_inf = (is_infA | is_infB) & (~is_nan)
        is_zero = is_zeroA | is_zeroB

        sY = sA ^ sB

        hiddenA = mux(is_eA_zero, 0, 1)
        hiddenB = mux(is_eB_zero, 0, 1)
        mA_eff = cat(fA, hiddenA)
        mB_eff = cat(fB, hiddenB)
        eA_eff = mux(is_eA_zero, 1, eA)
        eB_eff = mux(is_eB_zero, 1, eB)

        prod = build_multiplier(mA_eff, mB_eff, mult_cfg) if mult_cfg is not None else mA_eff * mB_eff
        exp_sum = build_adder(eA_eff, eB_eff, adder_cfg) if adder_cfg is not None else eA_eff + eB_eff

        # CLZ
        def clz_2bit(hi, lo):
            az = (~hi) & (~lo)
            cnt = cat(~hi, az)
            return cnt, az

        def clz_merge(hi_cnt, hi_az, lo_cnt, lo_az, hi_w):
            total = mux(hi_az, hi_w + lo_cnt, hi_cnt)
            az = hi_az & lo_az
            return total, az

        level = []
        for i in range(8):
            cnt, az = clz_2bit(prod[2*i+1], prod[2*i])
            level.append((cnt, az, 2))

        while len(level) > 1:
            new_level = []
            for i in range(0, len(level), 2):
                lo_cnt, lo_az, lo_w = level[i]
                hi_cnt, hi_az, hi_w = level[i+1]
                mc, maz = clz_merge(hi_cnt, hi_az, lo_cnt, lo_az, hi_w)
                new_level.append((mc, maz, lo_w + hi_w))
            level = new_level

        clz_bot16 = level[0][0]
        az_bot16 = level[0][1]

        t_level = []
        for i in range(3):
            cnt, az = clz_2bit(prod[16 + 2*i+1], prod[16 + 2*i])
            t_level.append((cnt, az, 2))

        mc01, az01 = clz_merge(t_level[1][0], t_level[1][1], t_level[0][0], t_level[0][1], 2)
        mc_top6, az_top6 = clz_merge(t_level[2][0], t_level[2][1], mc01, az01, 2)

        lz_top = cat(mc_top6[0:4], Const(0, UInt(1)))
        lz = mux(az_top6, (6 + clz_bot16)[0:5], lz_top[0:5])

        # Prefix OR
        pref_or = [None] * PROD_W
        pref_or[0] = prod[0]
        for i in range(1, PROD_W):
            pref_or[i] = pref_or[i-1] | prod[i]
        pref_vec = cat(*pref_or)

        def bsr(val, amt, width, nbits):
            r = val
            for i in range(nbits):
                s = 1 << i
                r = mux(amt[i], (r >> s)[0:width], r[0:width])
            return r

        sr = ((FW + 1) - lz)[0:5]
        total_shift = (BIAS + FW + 1) - exp_sum
        ts_m1 = (total_shift - 1)[0:5]

        lhs_nc = exp_sum + 1
        lhs_c = exp_sum + 2
        limit_under = BIAS + lz
        limit_over = (BIAS + 30) + lz

        underflow_nc = lhs_nc <= limit_under
        overflow_nc = lhs_nc > limit_over
        e_norm_nc = (lhs_nc - limit_under)[0:EW]

        underflow_c = lhs_c <= limit_under
        overflow_c = lhs_c > limit_over
        e_norm_c = (lhs_c - limit_under)[0:EW]

        sr_m1 = (sr - 1)[0:5]
        use_sub_shift = underflow_nc
        prod_shift_amt = mux(use_sub_shift, ts_m1, sr_m1)
        combined_shifted = bsr(prod, prod_shift_amt, PROD_W, 5)

        sr_m2 = (sr - 2)[0:5]
        ts_m2 = (total_shift - 2)[0:5]
        sticky_shift_amt = mux(use_sub_shift, ts_m2, sr_m2)
        sticky_shifted = bsr(pref_vec, sticky_shift_amt, PROD_W, 5)
        sticky_raw = sticky_shifted[0]

        # Unified guard/sticky
        sr_is_zero = sr == 0
        shift_too_small = mux(use_sub_shift, total_shift <= 1, sr <= 1)

        guard = mux(shift_too_small, 0, combined_shifted[0])
        sticky = mux(shift_too_small, 0, sticky_raw)

        # Shared mantissa: 11 bits
        # For normal: combined_shifted[1:12] (or prod[0:11] when sr=0)
        # For subnormal: combined_shifted[1:11] zero-extended to 11 (mask bit 10)
        raw_mant = mux(sr_is_zero & (~use_sub_shift), prod[0:FW+1], combined_shifted[1:FW+2])

        # In subnormal mode, mask bit 10 to isolate 10-bit fraction in the shared adder
        # bit 10 of raw_mant = combined_shifted[11]
        mant_bit10 = mux(use_sub_shift, 0, raw_mant[FW])
        mant_pre = cat(raw_mant[0:FW], mant_bit10)  # 11 bits with bit 10 masked in sub mode

        # Shared rounding adder
        lsb_bit = mant_pre[0]
        round_up = guard & (sticky | lsb_bit)
        mant_round = mant_pre + mux(round_up, 1, 0)  # 12 bits

        # Normal carry: bit 11
        carry = mant_round[FW + 1]

        # Subnormal carry: bit 10 (since bit 10 was masked to 0, carry at bit 10 = overflow of 10-bit fraction)
        carry_s = mant_round[FW]
        frac_field_sub = mant_round[0:FW]
        exp_field_sub = mux(carry_s, 1, 0)

        # Pack
        e_norm = mux(carry, e_norm_c, e_norm_nc)
        frac_norm = mux(carry, mant_round[1:FW+1], mant_round[0:FW])
        underflow = mux(carry, underflow_c, underflow_nc)
        overflow = mux(carry, overflow_c, overflow_nc)

        is_not_nan = ~is_nan
        sub_is_zero = (exp_field_sub == 0) & (frac_field_sub == 0)

        is_inf_out = is_not_nan & (is_inf | (overflow & ~is_zero))
        is_sub_out = is_not_nan & (~is_inf_out) & underflow
        is_zero_out = is_not_nan & (~is_inf_out) & (is_zero | (is_sub_out & sub_is_zero))

        frac_out = mux(is_nan, Const(1 << (FW-1), UInt(FW)),
                   mux(is_inf_out | is_zero_out, Const(0, UInt(FW)),
                   mux(is_sub_out, frac_field_sub, frac_norm)))

        exp_out = mux(is_nan | is_inf_out, Const(MAX_E, UInt(EW)),
                  mux(is_zero_out, Const(0, UInt(EW)),
                  mux(is_sub_out, exp_field_sub, e_norm)))

        sign_field = mux(is_nan, 0, sY)

        y <<= cat(frac_out, exp_out, sign_field)


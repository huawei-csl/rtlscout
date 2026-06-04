"""Optimized floating-point multiplier component (v21 architecture).

Logic copied verbatim from references/design_v21_mod.py.
Wrapped as a spirehdl Component; only the class/init boilerplate is new.
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


class FpMulOpt(Component):
    """v21-optimised FP multiplier. IO is identical to FpMulSN."""

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
        # Map instance attributes to local names matching design_v21_mod.py
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

        # --- Logic copied verbatim from references/design_v21_mod.py (lines 57-259) ---
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

        #prod = mA_eff * mB_eff
        prod = build_multiplier(mA_eff, mB_eff, mult_cfg) if mult_cfg is not None else mA_eff * mB_eff

        # --- CLZ ---
        PADDED = 32
        prod_padded = cat(prod, Const(0, UInt(PADDED - PROD_W)))

        def clz_2bit(hi, lo):
            az = (~hi) & (~lo)
            cnt = cat(~hi, az)
            return cnt, az

        def clz_merge(hi_cnt, hi_az, lo_cnt, lo_az, hi_w):
            total = mux(hi_az, hi_w + lo_cnt, hi_cnt)
            az = hi_az & lo_az
            return total, az

        level = []
        for i in range(16):
            cnt, az = clz_2bit(prod_padded[2*i+1], prod_padded[2*i])
            level.append((cnt, az, 2))

        while len(level) > 1:
            new_level = []
            for i in range(0, len(level), 2):
                lo_cnt, lo_az, lo_w = level[i]
                hi_cnt, hi_az, hi_w = level[i+1]
                mc, maz = clz_merge(hi_cnt, hi_az, lo_cnt, lo_az, hi_w)
                new_level.append((mc, maz, lo_w + hi_w))
            level = new_level

        clz_32 = level[0][0]
        lz = (clz_32 - (PADDED - PROD_W))[0:5]

        def bsr(val, amt, width, nbits):
            r = val
            for i in range(nbits):
                s = 1 << i
                r = mux(amt[i], (r >> s)[0:width], r[0:width])
            return r

        def bsl(val, amt, width, nbits):
            r = val
            for i in range(nbits):
                s = 1 << i
                r = mux(amt[i], (r << s)[0:width], r[0:width])
            return r

        need_right = lz <= (FW + 1)
        sr = ((FW + 1) - lz)[0:5]
        sl = (lz - (FW + 1))[0:5]

        prod_sr = bsr(prod, sr, PROD_W, 5)
        prod_sl = bsl(prod, sl, PROD_W, 5)
        shifted = mux(need_right, prod_sr, prod_sl)
        mant_pre = shifted[0:FW + 1]

        sr_m1 = (sr - 1)[0:5]
        guard_bsr = bsr(prod, sr_m1, PROD_W, 5)
        guard_r = guard_bsr[0]

        pref_or = [None] * PROD_W
        pref_or[0] = prod[0]
        for i in range(1, PROD_W):
            pref_or[i] = pref_or[i-1] | prod[i]
        pref_vec = cat(*pref_or)

        sr_m2 = (sr - 2)[0:5]
        sticky_bsr = bsr(pref_vec, sr_m2, PROD_W, 5)
        sticky_r = sticky_bsr[0]
        sticky_r_safe = mux(sr <= 1, 0, sticky_r)

        guard = mux(need_right, guard_r, 0)
        sticky = mux(need_right, sticky_r_safe, 0)

        lsb_bit = mant_pre[0]
        round_up = guard & (sticky | lsb_bit)
        mant_round = mant_pre + mux(round_up, 1, 0)
        carry = mant_round[FW + 1]

        exp_sum = eA_eff + eB_eff
        exp_sum = build_adder(eA_eff, eB_eff, adder_cfg) if adder_cfg is not None else eA_eff + eB_eff
        lhs_nc = exp_sum + 1
        lhs_c = exp_sum + 2

        # or use adder config
        #lhs_nc = build_adder(exp_sum, Const(1, UInt(EW)), adder_cfg) if adder_cfg is not None else exp_sum + 1
        #lhs_c = build_adder(exp_sum, Const(2, UInt(EW)), adder_cfg) if adder_cfg is not None else exp_sum + 2

        limit_under = BIAS + lz
        limit_over = (BIAS + MAX_FINITE_E) + lz

        underflow_nc = lhs_nc <= limit_under
        overflow_nc = lhs_nc > limit_over
        e_norm_nc = (lhs_nc - limit_under)[0:EW]

        underflow_c = lhs_c <= limit_under
        overflow_c = lhs_c > limit_over
        e_norm_c = (lhs_c - limit_under)[0:EW]

        total_shift = (BIAS + FW + 1) - exp_sum
        ts5 = total_shift[0:5]

        frac_sub_raw = bsr(prod, ts5, PROD_W, 5)
        frac_trunc = frac_sub_raw[0:FW]

        ts_m1 = (total_shift - 1)[0:5]
        sub_grd_val = bsr(prod, ts_m1, PROD_W, 5)
        sub_guard = sub_grd_val[0]

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

        # --- Pack with different mux ordering ---
        # Try: first select normal/subnormal/special, then carry
        is_nan = is_nan_in
        is_not_nan = ~is_nan

        # For each carry case, build the full 16-bit result and select at the end
        # This means the carry mux is the very LAST thing

        sub_is_zero = (exp_field_sub == 0) & (frac_field_sub == 0)

        # No-carry packed result
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

        # Carry packed result
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

        # Pack each variant
        result_nc = cat(frac_nc, exp_nc, sign_field)
        result_c = cat(frac_c, exp_c, sign_field)

        # Final carry mux at the very end
        y <<= mux(carry, result_c, result_nc)


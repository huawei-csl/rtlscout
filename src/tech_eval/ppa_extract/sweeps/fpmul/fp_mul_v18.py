"""Optimised floating-point multiplier component (v18 architecture).

Logic copied verbatim from references/design_v18.py (lines 19-151).
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


class FpMulV18(Component):
    """v18-optimised FP multiplier. IO is identical to FpMulSN."""

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
        # Map instance attributes to local names matching design_v18.py
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

        # --- Logic copied verbatim from references/design_v18.py (lines 19-151) ---
        sA = a[15]
        sB = b[15]
        eA = a[10:15]
        eB = b[10:15]
        fA = a[0:10]
        fB = b[0:10]

        sY = sA ^ sB

        is_eA_zero = eA == 0
        is_eB_zero = eB == 0
        is_zeroA = a[0:15] == 0
        is_zeroB = b[0:15] == 0

        is_eA_all1 = eA == 31
        is_eB_all1 = eB == 31

        is_infA = is_eA_all1 & (fA == 0)
        is_infB = is_eB_all1 & (fB == 0)
        is_nanA = is_eA_all1 & (~(fA == 0))
        is_nanB = is_eB_all1 & (~(fB == 0))

        is_nan_in = is_nanA | is_nanB | (is_infA & is_zeroB) | (is_zeroA & is_infB)
        is_inf_in = is_infA | is_infB
        is_zero_in = is_zeroA | is_zeroB

        hiddenA = mux(is_eA_zero, 0, 1)
        hiddenB = mux(is_eB_zero, 0, 1)
        mA_eff = cat(fA, hiddenA)
        mB_eff = cat(fB, hiddenB)

        eA_eff = mux(is_eA_zero, 1, eA)
        eB_eff = mux(is_eB_zero, 1, eB)

        prod = build_multiplier(mA_eff, mB_eff, mult_cfg) if mult_cfg is not None else mA_eff * mB_eff

        exp_sum = build_adder(eA_eff, eB_eff, adder_cfg) if adder_cfg is not None else eA_eff + eB_eff

        # Tree-based LZC for 22-bit product
        # Pad to 32 bits (power of 2) for clean tree, then adjust
        # Actually, let's use a hierarchical approach on the 22 bits directly
        # Split into groups, find LZ in each group, combine

        # Alternative: use the cascaded mux (same as before, it's efficient enough)
        lz = Wire(UInt(5), "lz")
        lz_val = Const(21, UInt(5))
        for i in range(PROD_W):
            lz_val = mux(prod[i], PROD_W - 1 - i, lz_val)
        lz <<= lz_val

        # Normal: sr = 11 - lz (clamped to 0)
        sr = Wire(UInt(5), "sr")
        sr <<= mux(lz <= (FW + 1), ((FW + 1) - lz)[0:5], 0)

        # Normal right shift
        shifted = prod >> sr
        mant_pre = shifted[0:FW + 1]

        # Guard/sticky for normal (sr range 0-11)
        guard_val = Const(0, UInt(1))
        sticky_val = Const(0, UInt(1))
        for s in range(1, FW + 2):
            g = prod[s - 1]
            st = Const(0, UInt(1))
            if s >= 2:
                st_acc = prod[0]
                for bit in range(1, s - 1):
                    st_acc = st_acc | prod[bit]
                st = st_acc
            guard_val = mux(sr == s, g, guard_val)
            sticky_val = mux(sr == s, st, sticky_val)

        round_up = guard_val & (sticky_val | mant_pre[0])

        mant_round = mant_pre + mux(round_up, 1, 0)
        carry = mant_round[FW + 1]
        mant_post = mux(carry, mant_round[1:FW + 2], mant_round[0:FW + 1])
        frac_norm = mant_post[0:FW]

        # Exponent
        lhs = (exp_sum + 1) + mux(carry, 1, 0)
        limit_under = BIAS + lz
        limit_over = (BIAS + MAX_FINITE_E) + lz

        underflow = lhs <= limit_under
        overflow = lhs > limit_over

        e_norm = lhs - limit_under
        exp_field_norm = e_norm[0:EW]

        # Subnormal path
        total_shift = (BIAS + FW + 1) - exp_sum

        frac_trunc = (prod >> total_shift)[0:FW]

        # Optimized subnormal guard/sticky: use incremental OR
        guard_sub = Const(0, UInt(1))
        sticky_sub = Const(0, UInt(1))
        or_acc = Const(0, UInt(1))
        for s in range(1, PROD_W + 1):
            guard_sub = mux(total_shift == s, prod[s - 1], guard_sub)
            sticky_sub = mux(total_shift == s, or_acc, sticky_sub)
            or_acc = or_acc | prod[s - 1]

        round_up_sub = guard_sub & (sticky_sub | frac_trunc[0])

        frac_sum = cat(frac_trunc, Const(0, UInt(1))) + mux(round_up_sub, 1, 0)
        carry_s = frac_sum[FW]
        frac_field_sub = frac_sum[0:FW]
        exp_field_sub = mux(carry_s, 1, 0)

        # Output
        is_nan = is_nan_in
        is_inf = (~is_nan) & (is_inf_in | (overflow & ~is_zero_in))
        is_sub_out = (~is_nan) & (~is_inf) & underflow
        sub_is_zero = is_sub_out & (exp_field_sub == 0) & (frac_field_sub == 0)
        is_zero = (~is_nan) & (~is_inf) & (is_zero_in | sub_is_zero)

        exp_normal_or_sub = mux(is_sub_out, exp_field_sub, exp_field_norm)
        frac_normal_or_sub = mux(is_sub_out, frac_field_sub, frac_norm)

        exp_field = mux(is_zero, 0, exp_normal_or_sub)
        frac_field = mux(is_zero, 0, frac_normal_or_sub)

        exp_field = mux(is_inf, 31, exp_field)
        frac_field = mux(is_inf, 0, frac_field)

        exp_field = mux(is_nan, 31, exp_field)
        frac_field = mux(is_nan, 512, frac_field)

        sign_field = mux(is_nan, 0, sY)

        y <<= cat(frac_field, exp_field, sign_field)


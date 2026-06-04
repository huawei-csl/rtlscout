#!/usr/bin/env python3
"""FP16 multiplier benchmark: entire FpMulSN logic wrapped in @flowy_optimized.

Builds the original (unoptimized) and the decorator-optimized version,
then compares AIG gate counts.
"""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so we can import from benchmarks/
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Const, Expr, mux, cat
from spirehdl.spirehdl_aiger import AigerExporter
from spirehdl.optimize import flowy_optimized

# ── FP16 parameters ──────────────────────────────────────────────────────────
EW = 5
FW = 10
W = 1 + EW + FW        # 16
BIAS = (1 << (EW - 1)) - 1  # 15
MAX_E = (1 << EW) - 1       # 31
MAX_FINITE_E = MAX_E - 1    # 30
PROD_W = 2 + 2 * FW         # 22


def aig_gate_count(m: Module) -> int:
    """Return the AND-gate count from the AAG header."""
    m.collect_signals()
    header = AigerExporter(m).get_aag()[0].split()
    return int(header[5])  # A (AND gates)


# ── Helper functions (same as in FpMulSN) ────────────────────────────────────

def _prefix_or_bits(x, width):
    """Return [OR(x[0:0]), OR(x[0:1]), …, OR(x[0:width-1])]"""
    out = []
    if width <= 0:
        return out
    acc = x[0]
    out.append(acc)
    for i in range(1, width):
        acc = acc | x[i]
        out.append(acc)
    return out


# ── @flowy_optimized: full FP16 multiply ─────────────────────────────────────

_FLOWY_KWARGS = dict(direct=True, iterations=1, mockturtle_chains=1,
                     mockturtle_chain_len=200, mockturtle_chain_workers=1,
                     nb_runs=50, nb_workers=50)


def _fpmul_f16_body(a, b):
    """Complete IEEE-754 FP16 multiply with subnormal support — raw logic."""

    # ---- extract fields ----
    sA = a[W - 1]
    sB = b[W - 1]
    eA = a[FW:W - 1]
    eB = b[FW:W - 1]
    fA = a[0:FW]
    fB = b[0:FW]

    # ---- classify operands ----
    is_eA_zero = eA == 0
    is_eB_zero = eB == 0
    is_fA_zero = fA == 0
    is_fB_zero = fB == 0

    is_zeroA = is_eA_zero & is_fA_zero
    is_zeroB = is_eB_zero & is_fB_zero

    is_eA_all1 = eA == MAX_E
    is_eB_all1 = eB == MAX_E

    is_nanA = is_eA_all1 & (fA != 0)
    is_nanB = is_eB_all1 & (fB != 0)
    is_infA = is_eA_all1 & (fA == 0)
    is_infB = is_eB_all1 & (fB == 0)

    is_nan_in = is_nanA | is_nanB | ((is_infA & is_zeroB) | (is_zeroA & is_infB))
    is_inf_in = is_infA | is_infB
    is_zero_in = is_zeroA | is_zeroB

    sY = sA ^ sB

    # ---- effective operands (subnormals=True) ----
    hiddenA = mux(is_eA_zero, 0, 1)
    hiddenB = mux(is_eB_zero, 0, 1)
    mA_eff = cat(fA, hiddenA)
    mB_eff = cat(fB, hiddenB)
    eA_eff = mux(is_eA_zero, 1, eA)
    eB_eff = mux(is_eB_zero, 1, eB)

    # ---- multiply mantissas ----
    prod = mA_eff * mB_eff

    # ---- leading zero count ----
    msb_flags = []
    for i in range(PROD_W - 1, -1, -1):
        upper_zero = 1 if i == PROD_W - 1 else prod[i + 1:PROD_W] == 0
        msb_flags.append(upper_zero & prod[i])

    lz = 0
    for idx, flag in enumerate(msb_flags):
        i = (PROD_W - 1) - idx
        lz_const = (PROD_W - 1) - i
        lz = mux(flag, lz_const, lz)

    # ---- normalize and round ----
    need_right = lz <= (FW + 1)
    sr = (FW + 1) - lz
    sl = lz - (FW + 1)

    shifted = mux(need_right, prod >> sr, prod << sl)
    mant_pre = shifted[0:FW + 1]

    pref = _prefix_or_bits(prod, PROD_W)

    def _bit_at(vec, idx_expr):
        acc = 0
        for k in range(PROD_W):
            acc = mux(idx_expr == k, vec[k], acc)
        return acc

    def _pref_at(idx_expr):
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
    mant_post = mux(carry, mant_round[1:FW + 2], mant_round[0:FW + 1])
    frac_norm = mant_post[0:FW]

    # ---- exponent path ----
    exp_sum = eA_eff + eB_eff
    lhs = (exp_sum + 1) + mux(carry, 1, 0)

    limit_under = BIAS + lz
    limit_over = (BIAS + MAX_FINITE_E) + lz

    underflow = lhs <= limit_under
    overflow = lhs > limit_over

    e_norm = lhs - limit_under
    exp_field_norm = e_norm[0:EW]

    # ---- subnormal rounding (direct) ----
    total_shift = (BIAS + FW + 1) - exp_sum

    frac_trunc = (prod >> total_shift)[0:FW]

    def _sub_bit_at(idx_expr):
        acc = 0
        for k in range(PROD_W):
            acc = mux(idx_expr == k, prod[k], acc)
        return acc

    def _sub_pref_at(idx_expr):
        acc = 0
        for k in range(PROD_W):
            acc = mux(idx_expr == k, pref[k], acc)
        return acc

    sub_guard = _sub_bit_at(total_shift - 1)
    sub_sticky = _sub_pref_at(total_shift - 2)

    sub_lsb = frac_trunc[0]
    sub_round_up = sub_guard & (sub_sticky | sub_lsb)

    frac_trunc_zext = cat(frac_trunc, 0)
    frac_sum = frac_trunc_zext + mux(sub_round_up, 1, 0)
    carry_s = frac_sum[FW]
    frac_field_sub = frac_sum[0:FW]
    exp_field_sub = mux(carry_s, 1, 0)

    # ---- pack result ----
    all1_E = (1 << EW) - 1
    qnan_payload = (1 << (FW - 1))

    is_nan = is_nan_in
    is_inf = (~is_nan) & (is_inf_in | (overflow & ~is_zero_in))

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
    sign_field = mux(is_nan, 0, sY)

    return cat(frac_field, exp_field, sign_field)


# ── Build original (no optimization) ─────────────────────────────────────────

def build_original():
    from benchmarks.fpmul_f16.context.spire_hdl_float_mult_sn import build_fp_mul_sn
    return build_fp_mul_sn("fpmul_f16_orig", EW, FW, subnormals=True)


# ── Build optimized (with @flowy_optimized) ───────────────────────────────────

# Default decorated version (no pareto_point)
fpmul_f16_optimized = flowy_optimized(**_FLOWY_KWARGS)(_fpmul_f16_body)


def build_optimized(pareto_point=None):
    if pareto_point is not None:
        opt_fn = flowy_optimized(**_FLOWY_KWARGS, pareto_point=pareto_point)(_fpmul_f16_body)
    else:
        opt_fn = fpmul_f16_optimized
    m = Module("fp_mul_e5f10", with_clock=False, with_reset=False)
    a = m.input(UInt(W), "a")
    b = m.input(UInt(W), "b")
    y = m.output(UInt(W), "y")
    y <<= opt_fn(a, b)
    return m


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pareto-point", type=int, default=None,
                        help="Select Nth Pareto-front design (default: best by aig_count)")
    cli_args = parser.parse_args()

    print("Building original FP16 multiplier...")
    m_orig = build_original()
    gates_orig = aig_gate_count(m_orig)
    print(f"Original:  {gates_orig} AIG gates")

    pp = cli_args.pareto_point
    label = f"pareto_point={pp}" if pp is not None else "best"
    print(f"\nBuilding @flowy_optimized FP16 multiplier ({label})...")
    m_opt = build_optimized(pareto_point=pp)
    gates_opt = aig_gate_count(m_opt)
    print(f"Optimized: {gates_opt} AIG gates")

    delta = gates_orig - gates_opt
    pct = delta / gates_orig * 100 if gates_orig else 0
    print(f"\nReduction: {delta} gates ({pct:.1f}%)")

    # Write design.v for run_eval
    suffix = f"_pareto_{pp}" if pp is not None else ""
    out_name = f"design{suffix}.v"
    m_opt.to_verilog_file(out_name)
    print(f"\nWrote {out_name}")

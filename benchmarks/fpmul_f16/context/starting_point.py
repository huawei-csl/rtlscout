# Starting point for fp_mul_e5f10 — floating-point multiplier.
# This script produces a correct design. Modify to optimize.
#
# The FpMulSN component is in spire_hdl_float_mult_sn.py (same directory).
# Edit that file to change the multiplier architecture.
from spire_hdl_float_mult_sn import FpMulSN

component = FpMulSN(
    EW=5,
    FW=10,
    subnormals=True,
)
m = component.to_module("fp_mul_e5f10", with_clock=False, with_reset=False)
m.to_verilog_file("design.v")

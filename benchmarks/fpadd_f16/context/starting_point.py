# Starting point for fp_add_e5f10 — floating-point adder.
# This script produces a correct design. Modify to optimize.
#
# The FpAdd component is in spire_hdl_float_add.py (same directory).
# Edit that file to change the adder architecture.
from spire_hdl_float_add import FpAdd

component = FpAdd(
    EW=5,
    FW=10,
    subnormals=True,
)
m = component.to_module("fp_add_e5f10", with_clock=False, with_reset=False)
m.to_verilog_file("design.v")

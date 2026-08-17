# Starting point for fp_add_e8f23 — floating-point adder.
# This script produces a correct design. Modify to optimize.
#
# The FpAdd component is in spire_hdl_float_add.py (same directory).
# Edit that file to change the adder architecture.
from spire_hdl_float_add import FpAdd

component = FpAdd(
    EW=8,
    FW=23,
    subnormals=True,
)
m = component.to_netlist("fp_add_e8f23", with_clock=False, with_reset=False)
m.to_verilog_file("design.v")

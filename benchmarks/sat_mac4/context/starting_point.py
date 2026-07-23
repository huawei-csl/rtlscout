"""sat_mac4 — a working spire starting point.

y = c + a*b, saturating at 255. The helper functions are pure combinational subcircuits — good
design-DB slot candidates (decorate with @from_design_db, run ./evaluate_design to register the
slots, fill them, re-evaluate to splice the selections).
"""
from spire import UInt
from spire.component import Netlist
from spire.expr import mux_if


def mul4(a, b):
    """4x4 -> 8-bit product."""
    return a * b


def sat_add8(c, p):
    """Saturating 8-bit add: c + p, clamped at 255 on overflow."""
    t = c + p                        # 9 bits wide
    return mux_if(t[8], 255, t[0:8])


def build():
    m = Netlist("sat_mac4", with_clock=False, with_reset=False)
    a = m.input(UInt(4), "a")
    b = m.input(UInt(4), "b")
    c = m.input(UInt(8), "c")
    y = m.output(UInt(8), "y")
    y <<= sat_add8(c, mul4(a, b))
    return m


if __name__ == "__main__":
    build().to_verilog_file("design.v")   # the evaluator runs this file and reads design.v

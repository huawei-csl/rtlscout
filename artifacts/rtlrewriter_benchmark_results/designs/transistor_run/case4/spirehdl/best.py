"""Approach AA: nested abc - deepsyn seed 3 then seed 0."""
from spire import Component, IORecord, Input, Output, UInt
from spire.optimize import abc_optimized


@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 60 -S 0; &put")
@abc_optimized(abc_script="strash; &get -n; &deepsyn -T 120 -S 3; &put")
def compute_all(x):
    y_val = ((x << 3) + (x << 2) + x)[0:32]
    z_val = ((y_val << 1) - x)[0:32]
    w_val = ((z_val << 1) + y_val)[0:32]
    return y_val, z_val, w_val


class Example(Component):
    def __init__(self):
        self.io = IORecord(
            x=Input(UInt(32)),
            y=Output(UInt(32)),
            z=Output(UInt(32)),
            w=Output(UInt(32)),
        )
        self.elaborate()

    def elaborate(self):
        x = self.io.x
        y_val, z_val, w_val = compute_all(x)
        self.io.y <<= y_val
        self.io.z <<= z_val
        self.io.w <<= w_val


Example().to_verilog_file("design.v", name="example")

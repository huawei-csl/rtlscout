"""SpireHDL design for case12 — Best approach: Component + replace_arithmetic_ops(area).
Try with output5 expressed as X*(Y-1) - R which might enable MAC detection differently."""
from dataclasses import dataclass
from spirehdl.spirehdl_module import Module, Component
from spirehdl.spirehdl import UInt, Signal, Const
from spirehdl.arithmetic.int_arithmetic_config import ArithmeticAutoConfig, replace_arithmetic_ops

@dataclass
class ExampleIO:
    X: Signal
    Y: Signal
    Z: Signal
    P: Signal
    Q: Signal
    R: Signal
    S: Signal
    T: Signal
    output1: Signal
    output2: Signal
    output3: Signal
    output4: Signal
    output5: Signal
    output6: Signal

class Example(Component):
    def __init__(self):
        self.io = ExampleIO(
            X=Signal(name="X", typ=UInt(32), kind="input"),
            Y=Signal(name="Y", typ=UInt(32), kind="input"),
            Z=Signal(name="Z", typ=UInt(32), kind="input"),
            P=Signal(name="P", typ=UInt(32), kind="input"),
            Q=Signal(name="Q", typ=UInt(32), kind="input"),
            R=Signal(name="R", typ=UInt(32), kind="input"),
            S=Signal(name="S", typ=UInt(32), kind="input"),
            T=Signal(name="T", typ=UInt(32), kind="input"),
            output1=Signal(name="output1", typ=UInt(32), kind="output"),
            output2=Signal(name="output2", typ=UInt(32), kind="output"),
            output3=Signal(name="output3", typ=UInt(32), kind="output"),
            output4=Signal(name="output4", typ=UInt(32), kind="output"),
            output5=Signal(name="output5", typ=UInt(32), kind="output"),
            output6=Signal(name="output6", typ=UInt(32), kind="output"),
        )
        self.elaborate()

    def elaborate(self):
        X = self.io.X
        Y = self.io.Y
        Z = self.io.Z
        P = self.io.P
        Q = self.io.Q
        R = self.io.R
        S = self.io.S
        T = self.io.T

        xy = X * Y
        zp = Z + P
        qr = Q - R
        x_plus_y = X + Y
        
        # Express output5 as X*Y - (X + R) to make it a MAC: X*Y + (-(X+R))
        # = X*Y - X - R
        xr = X + R  # shared subtraction target
        
        self.io.output1 <<= xy + zp
        self.io.output2 <<= zp * qr
        self.io.output3 <<= x_plus_y + S + T
        self.io.output4 <<= (xy + Q) * (P + X)
        self.io.output5 <<= xy - xr
        self.io.output6 <<= (x_plus_y + P) * qr

comp = Example()
replace_arithmetic_ops(comp, ArithmeticAutoConfig(objective="area"))
module = comp.to_module("example")
module.to_verilog_file("design.v")

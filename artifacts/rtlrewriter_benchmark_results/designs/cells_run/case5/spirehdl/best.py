from dataclasses import dataclass
from spirehdl.spirehdl import UInt, Signal
from spirehdl.spirehdl_module import Component
from spirehdl.arithmetic.int_arithmetic_config import ArithmeticAutoConfig, replace_arithmetic_ops


@dataclass
class AddIO:
    a: Signal
    b: Signal
    sum: Signal


class Adder(Component):
    def __init__(self):
        self.io = AddIO(
            a=Signal(name="a", typ=UInt(8), kind="input"),
            b=Signal(name="b", typ=UInt(8), kind="input"),
            sum=Signal(name="sum", typ=UInt(9), kind="output"),
        )
        self.elaborate()

    def elaborate(self):
        self.io.sum <<= self.io.a + self.io.b


adder = Adder()
replace_arithmetic_ops(adder, ArithmeticAutoConfig(objective="area"))
module = adder.to_netlist("example")
module.to_verilog_file("design.v")

"""Optimized with replace_arithmetic_ops (area objective)."""
from spire import Component, IORecord, Input, Output, UInt
from spire.expr import Wire
from spire.arithmetic.int_arithmetic_config import ArithmeticAutoConfig, replace_arithmetic_ops


class ArithmeticOperations(Component):
    def __init__(self):
        self.io = IORecord(
            A=Input(UInt(32)), B=Input(UInt(32)), C=Input(UInt(32)), D=Input(UInt(32)),
            E=Input(UInt(32)), F=Input(UInt(32)), G=Input(UInt(32)), H=Input(UInt(32)),
            result1=Output(UInt(32)), result2=Output(UInt(32)), result3=Output(UInt(32)),
            result4=Output(UInt(32)), result5=Output(UInt(32)), result6=Output(UInt(32)),
        )
        self.elaborate()

    def elaborate(self):
        A, B, C, D = self.io.A, self.io.B, self.io.C, self.io.D
        E, F, G, H = self.io.E, self.io.F, self.io.G, self.io.H

        cd = Wire(UInt(32)); cd <<= C * D       # C*D mod 2^32
        ab = Wire(UInt(32)); ab <<= A + B       # A+B mod 2^32
        ef = Wire(UInt(32)); ef <<= E - F       # E-F mod 2^32

        self.io.result1 <<= ab + cd
        self.io.result2 <<= cd + ef
        self.io.result3 <<= ab + G + H
        cde = Wire(UInt(32)); cde <<= cd + E
        self.io.result4 <<= cde * ab
        fa = Wire(UInt(32)); fa <<= F + A
        self.io.result5 <<= cd - fa
        abc = Wire(UInt(32)); abc <<= ab + C
        self.io.result6 <<= abc * ef


comp = ArithmeticOperations()
replace_arithmetic_ops(comp, ArithmeticAutoConfig(objective="area"))
comp.to_verilog_file("design.v", name="arithmetic_operations")

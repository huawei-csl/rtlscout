"""Spire starting point for conversor_num_16b — 5-digit BCD to 16-bit binary.

Mirrors the reference Verilog one-for-one: every `assign` becomes an explicit
`w = Wire(UInt(16), name="<name>"); w <<= <expr>`, creating a 16-bit cut-point
at each intermediate. Without these cut-points spirehdl's natural width
growth (`4b * 14b = 18b`, plus further widening on each `+`) produces 18- to
20-bit adders whose upper bits are dropped only at the output — the extra
carry chain does not get optimized out by yosys+abc and hurts ADP by ~22%.
"""
from spire import Component, IORecord, Input, Output, UInt, Wire


class ConversorNum16B(Component):
    def __init__(self):
        self.io = IORecord(
            numeros=Input(UInt(20)),
            operador=Output(UInt(16)),
        )
        self.elaborate()

    def elaborate(self):
        # alias every port so the original body is unchanged
        numeros = self.io.numeros
        operador = self.io.operador

        # Digit products, one wire per `assign num_expN = 10^N * {12'b0, numeros[x:y]};`
        num_exp4 = Wire(UInt(16), name="num_exp4"); num_exp4 <<= numeros[16:20] * 10000
        num_exp3 = Wire(UInt(16), name="num_exp3"); num_exp3 <<= numeros[12:16] * 1000
        num_exp2 = Wire(UInt(16), name="num_exp2"); num_exp2 <<= numeros[8:12]  * 100
        num_exp1 = Wire(UInt(16), name="num_exp1"); num_exp1 <<= numeros[4:8]   * 10
        num_exp0 = Wire(UInt(16), name="num_exp0"); num_exp0 <<= numeros[0:4]

        # Same sum grouping as the golden:
        #   assign operador = (num_exp4 + (num_exp1 + num_exp3)) + (num_exp0 + num_exp2);
        s13 = Wire(UInt(16), name="s13"); s13 <<= num_exp1 + num_exp3
        s02 = Wire(UInt(16), name="s02"); s02 <<= num_exp0 + num_exp2
        hi  = Wire(UInt(16), name="hi");  hi  <<= num_exp4 + s13
        operador <<= hi + s02


ConversorNum16B().to_verilog_file("design.v", name="conversor_num_16b")

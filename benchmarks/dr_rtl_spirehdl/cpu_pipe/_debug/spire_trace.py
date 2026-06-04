"""Step the spirehdl dcpu16_cpu through vectors.dat using the spirehdl
Simulator. Dumps key registers per cycle so we can diff against the
verilog golden's trace.

Usage:
    cd benchmarks/dr_rtl_spirehdl/cpu_pipe/_debug
    python spire_trace.py > spire_trace.log
"""
import sys
import os
import tempfile
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

START = REPO / "benchmarks/dr_rtl_spirehdl/cpu_pipe/context/starting_point.py"

tmpdir = tempfile.mkdtemp(prefix="spire_cpu_trace_")
os.chdir(tmpdir)

spec = importlib.util.spec_from_file_location("cpu_design", START)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.m

from spirehdl.spirehdl_simulator import Simulator
sim = Simulator(m)

VECTORS = REPO / "benchmarks/dr_rtl_spirehdl/cpu_pipe/vectors.dat"
lines = [l.strip() for l in VECTORS.read_text().splitlines() if l and not l.startswith("#")]


def parse_line(line):
    p = line.split()
    return {
        "f_ack": int(p[0], 16),
        "f_dti": int(p[1], 16),
        "g_ack": int(p[2], 16),
        "g_dti": int(p[3], 16),
        "exp_f_adr": int(p[4], 16),
        "exp_f_dto": int(p[5], 16),
        "exp_f_stb": int(p[6], 16),
        "exp_f_wre": int(p[7], 16),
        "exp_g_adr": int(p[8], 16),
        "exp_g_dto": int(p[9], 16),
        "exp_g_stb": int(p[10], 16),
        "exp_g_wre": int(p[11], 16),
    }


# 3-cycle reset
sim.set("rst", 1)
sim.set("f_ack", 0)
sim.set("f_dti", 0)
sim.set("g_ack", 0)
sim.set("g_dti", 0)
for _ in range(3):
    sim.step()
sim.set("rst", 0)


def dump(label, exp):
    sigs = ["pha", "ireg", "opc", "_bra", "bra", "_rwa", "_rwe", "rra", "rwa", "rwe",
            "regR", "regO", "CC", "regA", "regB", "regPC", "wpc", "regSP",
            "_rSP", "wsp", "ea", "eb", "g_adr_r", "g_stb_r", "_adr", "_stb", "_wre",
            "f_adr_r", "f_stb_r", "f_wre_r", "_rd", "ena_wire"]
    vals = {}
    for s in sigs:
        try:
            vals[s] = sim.get(s)
        except Exception as e:
            pass
    outs = ["f_adr", "f_dto", "f_stb", "f_wre", "g_adr", "g_dto", "g_stb", "g_wre"]
    ok = True
    for o in outs:
        try:
            actual = sim.get(o)
            expected = exp[f"exp_{o}"]
            vals[o] = f"{actual:x}" + ("" if actual == expected else f"(exp:{expected:x})")
            if actual != expected:
                ok = False
        except Exception:
            pass
    flag = "  " if ok else "**"
    print(f"{flag}{label} " + " ".join(f"{k}={v}" for k, v in vals.items()))


for i, raw in enumerate(lines[:60]):
    v = parse_line(raw)
    sim.set("f_ack", v["f_ack"])
    sim.set("f_dti", v["f_dti"])
    sim.set("g_ack", v["g_ack"])
    sim.set("g_dti", v["g_dti"])
    sim.step()
    dump(f"vec={i:3d}", v)

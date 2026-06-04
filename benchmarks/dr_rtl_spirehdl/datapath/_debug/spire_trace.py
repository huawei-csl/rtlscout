"""Spirehdl Simulator trace for datapath. Steps through vectors.dat and
dumps key registers + outputs vs expected per cycle.

Usage:
    cd benchmarks/dr_rtl_spirehdl/datapath/_debug
    python spire_trace.py > spire_trace.log
"""
import sys
sys.setrecursionlimit(20000)
import os
import tempfile
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

START = REPO / "benchmarks/dr_rtl_spirehdl/datapath/context/starting_point.py"

tmpdir = tempfile.mkdtemp(prefix="spire_dp_trace_")
os.chdir(tmpdir)

spec = importlib.util.spec_from_file_location("dp_design", START)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.m

from spirehdl.spirehdl_simulator import Simulator
sim = Simulator(m)

VECTORS = REPO / "benchmarks/dr_rtl_spirehdl/datapath/vectors.dat"
lines = [l.strip() for l in VECTORS.read_text().splitlines() if l and not l.startswith("#")]

INPUT_NAMES = [
    "bus_in", "data_type", "rk_sel", "key_out_sel", "round", "sbox_sel",
    "iv_en", "iv_sel_rd", "col_en_host", "col_en_cnt_unit", "key_host_en",
    "key_en", "key_sel_rd", "col_sel", "col_sel_host", "end_comp", "key_sel",
    "key_init", "bypass_rk", "bypass_key_en", "first_block", "last_round",
    "iv_cnt_en", "iv_cnt_sel", "enc_dec", "mode_ctr", "mode_cbc", "key_gen",
    "key_derivation_en",
]
EXP_NAMES = ["col_bus", "key_bus", "iv_bus", "end_aes"]


def parse_line(line):
    p = line.split()
    d = {}
    for i, n in enumerate(INPUT_NAMES):
        d[n] = int(p[i], 16)
    for j, n in enumerate(EXP_NAMES):
        d[f"exp_{n}"] = int(p[len(INPUT_NAMES) + j], 16)
    return d


# Reset
sim.set("rst_n", 0)
for n in INPUT_NAMES:
    sim.set(n, 0)
for _ in range(3):
    sim.step()
sim.set("rst_n", 1)


def dump(label, exp):
    sigs = ["round_pp1", "key_0", "key_1", "key_2", "key_3",
            "col_0", "col_1", "col_2", "col_3",
            "iv_0", "iv_1", "iv_2", "iv_3",
            "sbox_pp2", "sbox_ed_pp", "sbox_pp_byte_0",
            "rk_sel_pp1", "rk_sel_pp2", "col_sel_pp1", "col_sel_pp2",
            "key_out_sel_pp1", "key_out_sel_pp2"]
    vals = {}
    for s in sigs:
        try:
            v = sim.get(s)
            vals[s] = f"{v:x}"
        except Exception:
            pass
    ok = True
    for o in EXP_NAMES:
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


for i, raw in enumerate(lines[:15]):
    v = parse_line(raw)
    for n in INPUT_NAMES:
        sim.set(n, v[n])
    sim.step()
    dump(f"vec={i:3d}", v)

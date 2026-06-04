"""Step the spirehdl router_top through vectors.dat using the spirehdl
Simulator (deps/spire-hdl/src/spirehdl/spirehdl_simulator.py). Dumps the
FSM's present_state + key internal signals every cycle so we can diff
against the verilog golden's trace.

Usage:
    cd benchmarks/dr_rtl_spirehdl/router/_debug
    python spire_trace.py > spire_trace.log
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

# Load the spirehdl Module by importing the starting_point script.
# starting_point.py calls `m.to_verilog_file("design.v")` at the end,
# which writes design.v into the cwd. We don't care about that here —
# we just need the `m` (Module) reference.
import importlib.util
START = REPO / "benchmarks/dr_rtl_spirehdl/router/context/starting_point.py"

# Change cwd so to_verilog_file doesn't pollute the benchmark dir.
import os, tempfile
tmpdir = tempfile.mkdtemp(prefix="spire_router_trace_")
os.chdir(tmpdir)

spec = importlib.util.spec_from_file_location("router_design", START)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.m

from spirehdl.spirehdl_simulator import Simulator
sim = Simulator(m)

# Read vectors.dat
VECTORS = REPO / "benchmarks/dr_rtl/router/vectors.dat"
lines = []
for line in VECTORS.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    lines.append(line)

# Header columns (from tb.sv inspection):
# packet_valid read_enb_0 read_enb_1 read_enb_2 datain vldout_0 vldout_1 vldout_2 err busy data_out_0 data_out_1 data_out_2
# Format is hex per the dr_rtl_tb_gen.py switch to %h.


def parse_line(s):
    """vectors.dat: <pv> <re0> <re1> <re2> <datain> <vld0> <vld1> <vld2> <err> <busy> <do0> <do1> <do2> — all hex."""
    parts = s.split()
    return {
        "packet_valid": int(parts[0], 16),
        "read_enb_0":   int(parts[1], 16),
        "read_enb_1":   int(parts[2], 16),
        "read_enb_2":   int(parts[3], 16),
        "datain":       int(parts[4], 16),
        # expected outputs:
        "exp_vldout_0":   int(parts[5], 16),
        "exp_vldout_1":   int(parts[6], 16),
        "exp_vldout_2":   int(parts[7], 16),
        "exp_err":        int(parts[8], 16),
        "exp_busy":       int(parts[9], 16),
        "exp_data_out_0": int(parts[10], 16),
        "exp_data_out_1": int(parts[11], 16),
        "exp_data_out_2": int(parts[12], 16),
    }


# --- Reset phase: tb holds resetn=0 for 3 cycles ---
sim.set("resetn", 0)
sim.set("packet_valid", 0)
sim.set("read_enb_0", 0)
sim.set("read_enb_1", 0)
sim.set("read_enb_2", 0)
sim.set("datain", 0)
for i in range(3):
    sim.step()

# Deassert reset, then drive each vector
sim.set("resetn", 1)


def dump_signals(label):
    """Peek the signals we care about for the FSM divergence diff."""
    sig_names = [
        "present_state",
        "fifo_empty_0", "fifo_full_0", "incrementer_0",
        "read_ptr_0", "write_ptr_0", "count_0", "dataout_r_0", "temp_0",
        "w_enb_0", "dout",
        "fifo_0_0", "fifo_0_1", "fifo_0_2", "fifo_0_3",
    ]
    vals = {}
    for n in sig_names:
        try:
            vals[n] = sim.get(n)
        except Exception as e:
            vals[n] = f"ERR({e})"
    out_names = ["vldout_0", "vldout_1", "vldout_2", "err", "busy",
                 "data_out_0", "data_out_1", "data_out_2"]
    for n in out_names:
        try:
            vals[n] = sim.get(n)
        except Exception as e:
            vals[n] = f"ERR({e})"
    parts = [f"{k}={v}" for k, v in vals.items()]
    print(f"{label} {' '.join(parts)}")


# Drive vectors.dat (1 line per cycle), dump state after each step
N_CYCLES = min(80, len(lines))   # extend coverage to find the next divergence
for i, raw in enumerate(lines[:N_CYCLES]):
    v = parse_line(raw)
    sim.set("packet_valid", v["packet_valid"])
    sim.set("read_enb_0", v["read_enb_0"])
    sim.set("read_enb_1", v["read_enb_1"])
    sim.set("read_enb_2", v["read_enb_2"])
    sim.set("datain", v["datain"])
    sim.step()
    # The vectors.dat row's expected values are sampled *after* the
    # tb's @(posedge clk); #1; — i.e. one full clock edge after applying
    # the inputs. So compare exp_X to our peeked output after step().
    exp = {k: v[k] for k in v if k.startswith("exp_")}
    actual_busy = sim.get("busy")
    actual_vldout_2 = sim.get("vldout_2")
    actual_err = sim.get("err")
    match_busy = (actual_busy == v["exp_busy"])
    match_vldout_2 = (actual_vldout_2 == v["exp_vldout_2"])
    match_err = (actual_err == v["exp_err"])
    flag = " " if (match_busy and match_vldout_2 and match_err) else "*"
    dump_signals(f"{flag}cyc={i:3d} input(pv={v['packet_valid']} datain={v['datain']:02x} re=[{v['read_enb_0']}{v['read_enb_1']}{v['read_enb_2']}])"
                  f" | exp(busy={v['exp_busy']} vldout_2={v['exp_vldout_2']} err={v['exp_err']})")

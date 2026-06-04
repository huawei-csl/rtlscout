#!/usr/bin/env python3
"""Testbench generator for benchmarks/dr_rtl/<name>/.

Promoted (with extensions) from /tmp/rtl_rewriter_tb_gen.py. Produces the same
data-driven tb.sv + LFSR-stimulus vectors.dat pair, but sourced from the
hkust-zhiyao/DR_RTL `rtl_dataset/` baselines and writing into
`benchmarks/dr_rtl/<name>/`.

Differences from the rtl_rewriter generator:
  - `reset_active_low: bool` per-spec field. Generator inverts the assert/deassert
    polarity in both the probe tb (vector capture) and the shipped tb.sv.
  - `.sv` source files are supported. If the entry lists `source_ext: "sv"`,
    the file is copied to `context/starting_point.sv` and the verilator probe
    build picks that up.
  - `--case <name>` CLI filter to regenerate a single benchmark in place.
  - The benchmark directory is bootstrapped from scratch: this script writes
    `context/starting_point.{v,sv}`, `description.txt`, `metadata.json`,
    `tb.sv`, and `vectors.dat`. No pre-existing case dir required.

Per-case spec fields:
  case            short benchmark name → benchmarks/dr_rtl/<case>/
  module          top module name (must match the file's `module <name>` decl)
  mode            "comb" | "seq"
  inputs          [(port_name, width_in_bits), ...]
  outputs         [(port_name, width_in_bits), ...]
  desc            free-text description spliced into description.txt
  source_url      raw.githubusercontent URL for the baseline .v / .sv
  source_path     repo-relative path recorded in metadata.json (e.g. "rtl_dataset/ticket_machine.v0.v")
  source_ext      "v" (default) or "sv"
  clock_port      seq only — clock port name in golden
  reset_port      seq only — reset port name, or None
  reset_active_low seq only — True if reset asserts on 0 (default False)
"""
import argparse
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent  # benchmarks/dr_rtl/
N_RANDOM = 2000
N_RESET = 3
SEED1 = 0xDEADBEEF
SEED2 = 0xCAFEBABE

# `mode` is "comb" for pure combinational, "seq" for clocked (with optional reset).
BENCHMARKS = [
    # ---- Tier 1: small / clean ----
    {
        "case": "ticket", "module": "ticket_machine", "mode": "seq",
        "clock_port": "clk", "reset_port": "clear", "reset_active_low": False,
        "inputs":  [("ten", 1), ("twenty", 1)],
        "outputs": [("ready", 1), ("dispense", 1), ("return_sig", 1), ("bill", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/ticket_machine.v0.v",
        "source_path": "rtl_dataset/ticket_machine.v0.v",
        "source_ext":  "v",
        "desc": (
            "Vending-machine ticket FSM with sync active-high `clear` reset. "
            "Inputs `ten` and `twenty` accumulate coin value through a one-hot "
            "state register; outputs are Moore signals `ready`, `dispense`, "
            "`return_sig`, and `bill`. State advances on `posedge clk`; on "
            "`clear=1` the next clock edge returns the FSM to the RDY state."
        ),
    },
    # ---- Tier 4: CPUs ----
    {
        "case": "cpu_pipe", "module": "dcpu16_cpu", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": False,
        "inputs":  [("f_ack", 1), ("f_dti", 16),
                    ("g_ack", 1), ("g_dti", 16)],
        "outputs": [("f_adr", 16), ("f_dto", 16), ("f_stb", 1), ("f_wre", 1),
                    ("g_adr", 16), ("g_dto", 16), ("g_stb", 1), ("g_wre", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/cpu_pipe.v0.v",
        "source_path": "rtl_dataset/cpu_pipe.v0.v",
        "source_ext":  "v",
        "desc": (
            "DCPU-16 pipelined CPU core. Sync active-high `rst`. Two memory "
            "buses: `f_*` (fetch) and `g_*` (general). Each bus exposes "
            "16-bit `*_adr` / `*_dto` outputs and `*_stb` / `*_wre` strobes, "
            "with the external memory driving back `*_dti[15:0]` data and "
            "`*_ack` ready. Random stimulus produces deterministic but "
            "architecturally-meaningless capture/replay — useful for "
            "synthesis cost but not for any semantic optimisation."
        ),
    },
    {
        "case": "tv80", "module": "tv80_core", "mode": "seq",
        "clock_port": "clk", "reset_port": "reset_n", "reset_active_low": True,
        "inputs":  [("cen", 1), ("wait_n", 1), ("int_n", 1),
                    ("nmi_n", 1), ("busrq_n", 1),
                    ("dinst", 8), ("di", 8)],
        "outputs": [("m1_n", 1), ("iorq", 1), ("no_read", 1), ("write", 1),
                    ("rfsh_n", 1), ("halt_n", 1), ("busak_n", 1),
                    ("A", 16), ("d_o", 8), ("mc", 3), ("ts", 3),
                    ("intcycle_n", 1), ("IntE", 1), ("stop", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/tv80.v0.v",
        "source_path": "rtl_dataset/tv80.v0.v",
        "source_ext":  "v",
        "desc": (
            "TV80 — synthesizable Z80 CPU core (with 8080 / GB modes via "
            "parameters). Sync active-low `reset_n`. `cen` is the clock "
            "enable; `int_n`, `nmi_n`, `busrq_n`, `wait_n` are interrupt / "
            "bus / wait control signals; `dinst[7:0]` and `di[7:0]` are "
            "instruction-bus and data-bus inputs respectively. Outputs are "
            "the full Z80 bus signal set (`m1_n`, `iorq`, `rfsh_n`, "
            "`halt_n`, `busak_n`, `A[15:0]`, `d_o[7:0]`, …) plus tracing "
            "fields `mc[2:0]`/`ts[2:0]`/`intcycle_n`/`IntE`/`stop`."
        ),
    },
    {
        "case": "arm_cpu1", "module": "arm9_compatiable_code", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": False,
        "inputs":  [("cpu_en", 1), ("cpu_restart", 1),
                    ("fiq", 1), ("irq", 1),
                    ("ram_abort", 1), ("ram_rdata", 32),
                    ("rom_abort", 1), ("rom_data", 32)],
        "outputs": [("ram_addr", 32), ("ram_cen", 1), ("ram_flag", 4),
                    ("ram_wdata", 32), ("ram_wen", 1),
                    ("rom_addr", 32), ("rom_en", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/arm_cpu1.v0.v",
        "source_path": "rtl_dataset/arm_cpu1.v0.v",
        "source_ext":  "v",
        "desc": (
            "ARM9-compatible CPU core (~2800 LOC). Async active-high `rst`. "
            "`cpu_en` advances the pipeline; `cpu_restart` reloads PC. "
            "Interrupt inputs `fiq` / `irq`; abort signals `ram_abort` / "
            "`rom_abort`. Memory bus: `rom_addr[31:0]`/`rom_en` for "
            "instruction fetch (`rom_data[31:0]` driving back), "
            "`ram_addr[31:0]`/`ram_wdata[31:0]`/`ram_cen`/`ram_wen`/"
            "`ram_flag[3:0]` for the data side (`ram_rdata[31:0]` driving "
            "back). Random stimulus is architecturally meaningless."
        ),
    },
    {
        "case": "arm_cpu2", "module": "risclite_mx", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": False,
        "inputs":  [("cpu_en", 1),
                    ("ram_rdata", 32), ("rom_data", 32)],
        "outputs": [("ram_addr", 32), ("ram_cen", 1), ("ram_flag", 4),
                    ("ram_wdata", 32), ("ram_wen", 1),
                    ("rom_addr", 32), ("rom_en", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/arm_cpu2.v0.v",
        "source_path": "rtl_dataset/arm_cpu2.v0.v",
        "source_ext":  "v",
        "desc": (
            "RISClite — slimmed ARM-compatible RISC CPU core (~1200 LOC). "
            "Async active-high `rst`. `cpu_en` advances the pipeline. "
            "Memory bus same shape as `arm_cpu1` — `rom_addr` / `rom_data` / "
            "`rom_en` for fetch, `ram_addr` / `ram_wdata` / `ram_rdata` / "
            "`ram_cen` / `ram_wen` / `ram_flag` for data. No external "
            "interrupt or abort inputs. Random stimulus same caveat as "
            "`arm_cpu1` / `cpu_pipe` / `tv80`."
        ),
    },
    # ---- Tier 3: SV + heavy ----
    {
        "case": "aes", "module": "key_expansion_128aes", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst_async_n", "reset_active_low": True,
        "inputs":  [("i_start", 1), ("i_key", 128)],
        "outputs": [("o_done", 1), ("o_expanded_key", 1408)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/aes.v0.sv",
        "source_path": "rtl_dataset/aes.v0.sv",
        "source_ext":  "sv",
        "desc": (
            "AES-128 key expansion. SystemVerilog (uses `always_ff`, "
            "multi-dim unpacked arrays, generate blocks). Async active-low "
            "`rst_async_n` clears the expanded-key register. `i_key[127:0]` "
            "is the input key; `i_start` triggers the 10-step round-key "
            "schedule. After 10 cycles, `o_done` rises and `o_expanded_key` "
            "(11 × 128 = 1408 bits) carries the full expanded key from round "
            "0 (the input key) through round 10."
        ),
    },
    {
        "case": "i2c", "module": "i2c_master_top", "mode": "seq",
        "clock_port": "wb_clk_i", "reset_port": "wb_rst_i", "reset_active_low": False,
        # arst_i is a second async reset; with no second reset_port the LFSR
        # drives it freely. Because it's deterministic stimulus the
        # capture/replay still self-passes, but agent-side optimisations that
        # change async-reset handling could fail correctness.
        "inputs":  [("arst_i", 1),
                    ("wb_adr_i", 3), ("wb_dat_i", 8),
                    ("wb_we_i", 1), ("wb_stb_i", 1), ("wb_cyc_i", 1),
                    ("scl_pad_i", 1), ("sda_pad_i", 1)],
        "outputs": [("wb_dat_o", 8), ("wb_ack_o", 1), ("wb_inta_o", 1),
                    ("scl_pad_o", 1), ("scl_padoen_o", 1),
                    ("sda_pad_o", 1), ("sda_padoen_o", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/i2c.v0.v",
        "source_path": "rtl_dataset/i2c.v0.v",
        "source_ext":  "v",
        # i2c.v0.v has plenty of synopsys pragmas (full_case / parallel_case);
        # strip them defensively, same reasoning as spi1.
        "source_patches": [
            ("// synopsys full_case parallel_case", ""),
            ("//synopsys full_case parallel_case",  ""),
            ("// synopsys parallel_case full_case", ""),
            ("//synopsys parallel_case full_case",  ""),
            ("// synopsys parallel_case", ""),
            ("//synopsys parallel_case",  ""),
            ("// synopsys full_case", ""),
            ("//synopsys full_case",  ""),
        ],
        "desc": (
            "Wishbone-mapped I2C master controller. Sync active-high "
            "`wb_rst_i` is the main reset; the design also has a second "
            "async reset `arst_i` whose active level is set by parameter "
            "ARST_LVL=0 (the generator drives `arst_i` as a normal LFSR "
            "input — deterministic capture/replay still works). Wishbone "
            "interface: `wb_adr_i[2:0]` + `wb_dat_i[7:0]` + we/stb/cyc → "
            "`wb_dat_o[7:0]` + `wb_ack_o`. I2C pads: separate input "
            "(`scl_pad_i`/`sda_pad_i`), output (`scl_pad_o`/`sda_pad_o`), "
            "and output-enable (`*_padoen_o`, active-low) — no real tri-state."
        ),
    },
    # ---- Tier 2: protocols / moderate complexity ----
    {
        "case": "uart", "module": "uart_top_design", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": False,
        "inputs":  [("address", 2), ("write_data", 32), ("we", 1),
                    ("rx", 1), ("re", 1)],
        "outputs": [("tx", 1), ("read_data", 8)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/UART.v0.v",
        "source_path": "rtl_dataset/UART.v0.v",
        "source_ext":  "v",
        "desc": (
            "UART top design (transmitter, receiver, baudrate generator, "
            "register file). Sync active-high `rst`. Memory-mapped register "
            "writes via `address[1:0]` + `write_data[31:0]` + `we` (set "
            "baud / control / TX data); reads via `re` produce `read_data[7:0]`. "
            "Serial `tx` is driven by the TX FSM, `rx` is the line input."
        ),
    },
    {
        "case": "spi1", "module": "simple_spi_top", "mode": "seq",
        "clock_port": "clk_i", "reset_port": "rst_i", "reset_active_low": True,
        "inputs":  [("cyc_i", 1), ("stb_i", 1), ("adr_i", 2), ("we_i", 1),
                    ("dat_i", 8), ("miso_i", 1)],
        "outputs": [("dat_o", 8), ("ack_o", 1), ("inta_o", 1),
                    ("sck_o", 1), ("mosi_o", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/simple_spi.v0.v",
        "source_path": "rtl_dataset/simple_spi.v0.v",
        "source_ext":  "v",
        # Patches:
        #  - Strip `include "timescale.v"` (file not in the DR_RTL repo;
        #    verilator handles `timescale fine without it).
        #  - Drop the `// synopsys full_case parallel_case` pragma on the
        #    espr case statement. Verilator enforces it strictly at runtime
        #    and aborts when the LFSR rolls an unmapped value (12..15);
        #    removing the pragma + our `-Wno-CASEINCOMPLETE` lets the design
        #    fall through cleanly (clkcnt keeps its current value, which is
        #    fine — the SPI rate field is sw-managed in real use).
        "source_patches": [
            ('`include "timescale.v"', "// `include \"timescale.v\" -- stripped"),
            ("// synopsys full_case parallel_case", ""),
            ("//synopsys full_case parallel_case",  ""),
        ],
        "desc": (
            "Simple SPI master with a Wishbone-style bus interface. Async "
            "active-low `rst_i`; Wishbone signals `cyc_i`, `stb_i`, "
            "`adr_i[1:0]`, `we_i`, `dat_i[7:0]` drive the register-mapped "
            "SPI control / status / data registers, and `dat_o[7:0]` + "
            "`ack_o` complete the read/write. Serial side: `sck_o`, "
            "`mosi_o`, `miso_i`. `inta_o` is the SPI interrupt output."
        ),
    },
    {
        "case": "spi2", "module": "spi", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": False,
        "inputs":  [("addr", 3), ("we", 1), ("write_data", 32), ("re", 1)],
        "outputs": [("read_data", 32)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/SPI.v0.v",
        "source_path": "rtl_dataset/SPI.v0.v",
        "source_ext":  "v",
        "desc": (
            "Memory-mapped SPI master with an internal SPI slave + RAM "
            "(loopback-style benchmark). Sync active-high `rst`. Register "
            "writes via `addr[2:0]` + `write_data[31:0]` + `we`; reads via "
            "`re` produce `read_data[31:0]`. No external SPI pins — the SPI "
            "master and slave are wired together internally."
        ),
    },
    {
        "case": "communicate", "module": "sync_serial_communication_tx_rx", "mode": "seq",
        "clock_port": "clk", "reset_port": "reset_n", "reset_active_low": True,
        "inputs":  [("sel", 3), ("data_in", 64)],
        "outputs": [("data_out", 64), ("done", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/communication.v0.v",
        "source_path": "rtl_dataset/communication.v0.v",
        "source_ext":  "v",
        "desc": (
            "Synchronous serial TX → RX loopback with selectable data width. "
            "Async active-low `reset_n`. `data_in[63:0]` is the parallel "
            "word fed into the TX block; `sel[2:0]` selects how many bits "
            "are transmitted; `data_out[63:0]` is the parallel word "
            "reconstructed by the RX block; `done` signals end-of-transmission."
        ),
    },
    {
        "case": "router", "module": "router_top", "mode": "seq",
        "clock_port": "clk", "reset_port": "resetn", "reset_active_low": True,
        "inputs":  [("packet_valid", 1),
                    ("read_enb_0", 1), ("read_enb_1", 1), ("read_enb_2", 1),
                    ("datain", 8)],
        "outputs": [("vldout_0", 1), ("vldout_1", 1), ("vldout_2", 1),
                    ("err", 1), ("busy", 1),
                    ("data_out_0", 8), ("data_out_1", 8), ("data_out_2", 8)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/router.v0.v",
        "source_path": "rtl_dataset/router.v0.v",
        "source_ext":  "v",
        # Verilator rejects assignments of 'z to a regular reg. The two
        # tri-state lines below are functional don't-cares (set the per-FIFO
        # output to high-impedance on soft_reset / count==0); replacing them
        # with 0 keeps the design synthesizable AND verilator-acceptable, and
        # gives a deterministic captured-vector replay.
        "source_patches": [
            ("dataout<=8'bzz;", "dataout<=8'd0; // patched from 8'bzz"),
            ("dataout<=8'bz;",  "dataout<=8'd0; // patched from 8'bz"),
        ],
        "desc": (
            "3-channel packet router. Sync active-low `resetn`. "
            "`packet_valid` + `datain[7:0]` ingest a stream of bytes whose "
            "header byte's two LSBs select the output channel. Each "
            "channel has a 16-entry FIFO read out via `read_enb_<n>` and "
            "produces `data_out_<n>[7:0]` + `vldout_<n>`. `err` and `busy` "
            "are global status outputs."
        ),
    },
    {
        "case": "pcie", "module": "top", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": True,
        "inputs":  [("s_en", 1), ("d_en", 1), ("m_piso", 1), ("m_sipo", 1),
                    ("datain", 8)],
        "outputs": [("dataout", 8)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/pcie.v0.v",
        "source_path": "rtl_dataset/pcie.v0.v",
        "source_ext":  "v",
        "desc": (
            "PCIe-style serial data pipeline: scrambler → PISO (8→10b "
            "encode + parallel-in-serial-out) → SIPO (serial-in-parallel-out + "
            "10→8b decode) → descrambler. Async active-low `rst`. `s_en` "
            "and `d_en` are enables for the scrambler and descrambler "
            "stages, `m_piso` / `m_sipo` mode-select the encoder/decoder, "
            "`datain[7:0]` is the byte stream input, `dataout[7:0]` is the "
            "recovered byte stream output. Top module is unhelpfully named "
            "`top` — `--top-module top` already pins it correctly in the "
            "verilator + yosys probe builds."
        ),
    },
    {
        "case": "fifo", "module": "fifo", "mode": "seq",
        "clock_port": "clk_in", "reset_port": "rst", "reset_active_low": True,
        # NOTE: `clk_out` is a SECOND clock the LFSR-generator can't drive
        # like a real clock — it's listed as a regular input here. The
        # generator's single-clock model means the read side is sampled at
        # whatever `clk_out` value the LFSR happens to roll. Baseline-vs-
        # baseline replay still works, but any optimisation that changes
        # CDC timing will likely break correctness against captured vectors.
        "inputs":  [("dataIn", 32), ("insert", 1), ("flush", 1),
                    ("remove", 1), ("clk_out", 1)],
        "outputs": [("full", 1), ("empty", 1), ("dataOut", 32)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/FIFO.v0.v",
        "source_path": "rtl_dataset/FIFO.v0.v",
        "source_ext":  "v",
        "desc": (
            "Async dual-clock FIFO (32-bit data, 128-deep). Async active-low "
            "`rst`. The DR_RTL baseline declares two clock ports — `clk_in` "
            "(write side) and `clk_out` (read side). The generator drives "
            "`clk_in` as the main clock and feeds `clk_out` as an LFSR "
            "input; baseline-vs-baseline self-replay passes deterministically, "
            "but **be aware** that any optimisation changing CDC synchroniser "
            "depth or read-pointer latency may break correctness against the "
            "captured vectors. A hand-written dual-clock tb would be the "
            "right way to make this benchmark agent-friendly — see "
            "`NOTES_dr_rtl_scaffolding.md` for the forward-looking suggestion."
        ),
    },
    {
        "case": "vending", "module": "vending_machine", "mode": "seq",
        "clock_port": "clk", "reset_port": "reset", "reset_active_low": False,
        "inputs":  [("condition", 1), ("sel", 1),
                    ("discountA", 1024), ("discountB", 1024),
                    ("discountC", 1024), ("discountD", 1024)],
        "outputs": [("total_discount", 1024), ("sell_signal", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/vending_machine.v0.v",
        "source_path": "rtl_dataset/vending_machine.v0.v",
        "source_ext":  "v",
        "desc": (
            "Vending-machine FSM with parameterised wide discount registers. "
            "`DATA_WIDTH=64`, `K=16` → `discountA..D` are each "
            "`K*DATA_WIDTH=1024` bits. The current `total_discount` is one "
            "of two combinational sums (`discountA+discountB` or "
            "`discountC+discountD`) selected by `sel`; the FSM walks an "
            "11-state graph driven by `condition` and emits a 1-bit "
            "`sell_signal`. Async active-high `reset` returns the FSM to S0."
        ),
    },
    {
        "case": "datapath", "module": "datapath", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst_n", "reset_active_low": True,
        "inputs":  [("bus_in", 32), ("data_type", 2), ("rk_sel", 2),
                    ("key_out_sel", 2), ("round", 4), ("sbox_sel", 3),
                    ("iv_en", 4), ("iv_sel_rd", 4),
                    ("col_en_host", 4), ("col_en_cnt_unit", 4),
                    ("key_host_en", 4), ("key_en", 4),
                    ("key_sel_rd", 2), ("col_sel", 2), ("col_sel_host", 2),
                    ("end_comp", 1), ("key_sel", 1), ("key_init", 1),
                    ("bypass_rk", 1), ("bypass_key_en", 1),
                    ("first_block", 1), ("last_round", 1),
                    ("iv_cnt_en", 1), ("iv_cnt_sel", 1),
                    ("enc_dec", 1), ("mode_ctr", 1), ("mode_cbc", 1),
                    ("key_gen", 1), ("key_derivation_en", 1)],
        "outputs": [("col_bus", 32), ("key_bus", 32),
                    ("iv_bus", 32), ("end_aes", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/datapath.v0.v",
        "source_path": "rtl_dataset/datapath.v0.v",
        "source_ext":  "v",
        "desc": (
            "AES datapath. Holds the 4 × 32-bit column / key / IV registers, "
            "the sbox lookup, MixColumns, and the round-key schedule. "
            "`bus_in[31:0]` is the shared write-data bus; per-stage enables "
            "(`col_en_host` / `col_en_cnt_unit`, `key_host_en` / `key_en`, "
            "`iv_en`) decide which register column is loaded each cycle. "
            "Selector ports (`rk_sel`, `key_out_sel`, `sbox_sel`, `col_sel`, "
            "`col_sel_host`, `key_sel_rd`, `iv_sel_rd`) drive the various "
            "input muxes. Async active-low `rst_n` clears state; outputs are "
            "the three 32-bit buses + 1-bit `end_aes`."
        ),
    },
    {
        "case": "dsp", "module": "DSP", "mode": "seq",
        "clock_port": "clk", "reset_port": None,
        "inputs":  [("opMode", 8),
                    ("CEA", 1), ("CEB", 1), ("CEC", 1), ("CECarryIn", 1),
                    ("CED", 1), ("CEM", 1), ("CEOpMode", 1), ("CEP", 1),
                    ("rstA", 1), ("rstB", 1), ("rstC", 1), ("rstCarryIn", 1),
                    ("rstD", 1), ("rstM", 1), ("rstOpMode", 1), ("rstP", 1),
                    ("A", 18), ("B", 18), ("D", 18), ("C", 48),
                    ("carryIn", 1), ("BCIn", 18), ("PCIn", 48)],
        "outputs": [("BCOut", 18), ("PCOut", 48), ("P", 48),
                    ("M", 36), ("carryOut", 1), ("carryOutF", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/DSP.v0.v",
        "source_path": "rtl_dataset/DSP.v0.v",
        "source_ext":  "v",
        "desc": (
            "DSP slice with pre-add/sub → 18×18 multiplier → 48-bit "
            "post-add/sub pipeline, modelled on the Xilinx DSP48-style block. "
            "Pipeline stages are independently gated by per-stage clock "
            "enables (`CEA..CEP`) and per-stage sync resets (`rstA..rstP`). "
            "`opMode[7:0]` selects mux/add/sub modes along the pipeline; "
            "inputs `A`/`B`/`D` are 18-bit, `C`/`PCIn` are 48-bit. Outputs "
            "`P`/`PCOut` are 48-bit accumulator results, `M` is the 36-bit "
            "multiplier output, `BCOut` is the B-cascade output. No single "
            "reset port — all `rst*` signals are treated as regular stimulus "
            "inputs and verilator's 2-state init zeros every pipeline "
            "register at t=0."
        ),
    },
    {
        "case": "cpu_fsm", "module": "mini_cpu", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst", "reset_active_low": False,
        "inputs":  [("en", 1),
                    ("imem_we", 1), ("imem_addr", 8), ("imem_wdata", 16),
                    ("rf_we", 1), ("rf_addr", 2), ("rf_wdata", 8)],
        "outputs": [("PC", 8), ("halt", 1),
                    ("dbg_r0", 8), ("dbg_r1", 8), ("dbg_r2", 8), ("dbg_r3", 8),
                    ("dbg_state", 3)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/cpu_fsm.v0.v",
        "source_path": "rtl_dataset/cpu_fsm.v0.v",
        "source_ext":  "v",
        "desc": (
            "Tiny FSM-style CPU with an 8-deep 16-bit instruction memory and "
            "a 4 × 8-bit register file. Sync active-high `rst` initialises "
            "PC=0, state=FETCH, and the register file to {0x11, 0x22, 0x33, "
            "0x44}. `en` advances the fetch/decode/exec FSM; ports "
            "`imem_we / imem_addr / imem_wdata` write the program memory and "
            "`rf_we / rf_addr / rf_wdata` write the register file. Debug "
            "outputs `PC`, `halt`, `dbg_r0..r3`, and `dbg_state` are sampled "
            "every cycle by the testbench."
        ),
    },
    {
        "case": "lstm", "module": "lstm_cell", "mode": "comb",
        "inputs":  [("c_in", 16), ("h_in", 16), ("X", 16)],
        "outputs": [("c_out", 16), ("h_out", 16)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/LSTM.v0.v",
        "source_path": "rtl_dataset/LSTM.v0.v",
        "source_ext":  "v",
        "desc": (
            "One LSTM cell, purely combinational. Inputs are the previous cell "
            "state `c_in`, the previous hidden state `h_in`, and the current "
            "input `X`, all 16-bit signed Q8.8 fixed-point. Internal "
            "submodules compute forget/input/cell/output gates via "
            "ConcatMultAdd + piecewise sigmoid/tanh approximations; outputs "
            "`c_out` and `h_out` are the new cell and hidden states. Weights "
            "and biases are hard-coded constants in the source."
        ),
    },
    {
        "case": "controller", "module": "control_unit", "mode": "seq",
        "clock_port": "clk", "reset_port": "rst_n", "reset_active_low": True,
        "inputs":  [("operation_mode", 2), ("aes_mode", 2),
                    ("start", 1), ("disable_core", 1)],
        "outputs": [("sbox_sel", 3), ("rk_sel", 2),
                    ("key_out_sel", 2), ("col_sel", 2),
                    ("key_en", 4), ("col_en", 4), ("round", 4),
                    ("bypass_rk", 1), ("bypass_key_en", 1), ("key_sel", 1),
                    ("iv_cnt_en", 1), ("iv_cnt_sel", 1),
                    ("key_derivation_en", 1),
                    ("end_comp", 1), ("key_init", 1), ("key_gen", 1),
                    ("mode_ctr", 1), ("mode_cbc", 1), ("last_round", 1),
                    ("encrypt_decrypt", 1)],
        "source_url":  "https://raw.githubusercontent.com/hkust-zhiyao/DR_RTL/main/rtl_dataset/controller.v0.v",
        "source_path": "rtl_dataset/controller.v0.v",
        "source_ext":  "v",
        "desc": (
            "AES control unit FSM. Sequences AES rounds (key expansion, round "
            "key selection, mixcol, last-round handling) for ECB / CBC / CTR "
            "modes and three operation modes (encryption, key derivation, "
            "decryption-with-derivation). Inputs `operation_mode[1:0]`, "
            "`aes_mode[1:0]`, `start`, `disable_core` drive an internal state "
            "register; outputs are control signals to the AES datapath "
            "(sbox/rk/col/key muxes, round counter, mode/last-round flags). "
            "Sync active-low `rst_n` returns the FSM to the IDLE state."
        ),
    },
]


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------
def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("CMD FAILED:", cmd)
        print(r.stdout)
        print(r.stderr)
        raise RuntimeError("subprocess failed")
    return r


def sv_width(w):
    return f"[{w-1}:0]" if w > 1 else ""


# ---------------------------------------------------------------------------
# Combinational probe + tb
# ---------------------------------------------------------------------------
def build_probe_tb_comb(spec):
    module = spec["module"]
    ins = spec["inputs"]
    outs = spec["outputs"]

    decls = []
    for name, w in ins:
        decls.append(f"  logic {sv_width(w)} {name};")
    for name, w in outs:
        decls.append(f"  logic {sv_width(w)} {name};")

    conns = ",\n    ".join([f".{n}({n})" for n, _ in ins + outs])

    assign_inputs = [
        "      lfsr  = {lfsr[30:0],  lfsr[31]  ^ lfsr[21]  ^ lfsr[1]  ^ lfsr[0]};",
        "      lfsr2 = {lfsr2[30:0], lfsr2[30] ^ lfsr2[6]  ^ lfsr2[4] ^ lfsr2[1]};",
    ]
    combined = "{lfsr2, lfsr}"
    cursor = 0
    for name, w in ins:
        if cursor + w > 64:
            assign_inputs.append(
                "      lfsr  = {lfsr[30:0],  lfsr[31]  ^ lfsr[21]  ^ lfsr[1]  ^ lfsr[0]};")
            assign_inputs.append(
                "      lfsr2 = {lfsr2[30:0], lfsr2[30] ^ lfsr2[6]  ^ lfsr2[4] ^ lfsr2[1]};")
            cursor = 0
        if w == 1:
            assign_inputs.append(f"      {name} = {combined}[{cursor}];")
        else:
            assign_inputs.append(f"      {name} = {combined}[{cursor+w-1}:{cursor}];")
        cursor += w

    # Use %h for capture+sscanf so arbitrary-width vectors round-trip; %0d
    # truncates to 64-bit on parse.
    fmt = " ".join(["%h"] * (len(ins) + len(outs)))
    disp_vars = ", ".join([n for n, _ in ins] + [n for n, _ in outs])

    det_cases = []
    det_cases.append("    // all-zero\n"
                     + "\n".join([f"    {n} = 0;" for n, _ in ins])
                     + "\n    #1;\n"
                     + f'    $display("{fmt}", {disp_vars});')
    det_cases.append("    // all-ones\n"
                     + "\n".join([f"    {n} = '1;" for n, _ in ins])
                     + "\n    #1;\n"
                     + f'    $display("{fmt}", {disp_vars});')

    return f"""`timescale 1ns/1ps
module probe_tb;
{chr(10).join(decls)}

  {module} dut (
    {conns}
  );

  int i;
  logic [31:0] lfsr;
  logic [31:0] lfsr2;

  initial begin
    lfsr  = 32'h{SEED1:08X};
    lfsr2 = 32'h{SEED2:08X};

{chr(10).join(det_cases)}

    for (i = 0; i < {N_RANDOM}; i++) begin
{chr(10).join(assign_inputs)}
      #1;
      $display("{fmt}", {disp_vars});
    end
    $finish;
  end
endmodule
"""


def build_tb_sv_comb(spec):
    module = spec["module"]
    ins = spec["inputs"]
    outs = spec["outputs"]

    port_decls = []
    for name, w in ins:
        port_decls.append(f"  logic {sv_width(w)} {name};")
    for name, w in outs:
        port_decls.append(f"  logic {sv_width(w)} {name};")
        port_decls.append(f"  logic {sv_width(w)} expected_{name};")

    conns = ",\n    ".join([f".{n}({n})" for n, _ in ins + outs])

    n_fields = len(ins) + len(outs)
    fmt = " ".join(["%h"] * n_fields)
    scan_args = ", ".join([n for n, _ in ins] + [f"expected_{n}" for n, _ in outs])
    cmp_expr = " || ".join([f"{n} !== expected_{n}" for n, _ in outs])
    err_fmt_in  = " ".join([f"{n}=%h" for n, _ in ins])
    err_fmt_out = " ".join([f"exp_{n}=%h act_{n}=%h" for n, _ in outs])
    err_args_in  = ", ".join([n for n, _ in ins])
    err_args_out = ", ".join(sum([[f"expected_{n}", n] for n, _ in outs], []))

    return f"""`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

{chr(10).join(port_decls)}

  {module} dut (
    {conns}
  );

  integer fd, rc, line_num;
  string line_buf;

  initial begin
    total_checks = 0;
    total_errors = 0;
    fd = $fopen("vectors.dat", "r");
    if (fd == 0) begin
      $display("ERROR: cannot open vectors.dat");
      $fatal(1);
    end
    line_num = 0;
    while (!$feof(fd)) begin
      line_num = line_num + 1;
      void'($fgets(line_buf, fd));
      if (line_buf.len() == 0) continue;
      if (line_buf.substr(0, 0) == "#") continue;
      rc = $sscanf(line_buf, "{fmt}", {scan_args});
      if (rc != {n_fields}) continue;
      #1;
      total_checks = total_checks + 1;
      if ({cmp_expr}) begin
        $display("TB_ERROR line=%0d {err_fmt_in} {err_fmt_out}",
                 line_num, {err_args_in}, {err_args_out});
        total_errors = total_errors + 1;
      end
    end
    $fclose(fd);
    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
"""


# ---------------------------------------------------------------------------
# Sequential probe + tb (clk + optional reset, polarity flag)
# ---------------------------------------------------------------------------
def _reset_polarity(spec):
    """Return (assert_val, deassert_val) literal strings for the reset port."""
    if spec.get("reset_active_low", False):
        return "1'b0", "1'b1"
    return "1'b1", "1'b0"


def build_probe_tb_seq(spec):
    module = spec["module"]
    ins = spec["inputs"]
    outs = spec["outputs"]
    clk = spec["clock_port"]
    rst = spec.get("reset_port")
    rst_assert, rst_deassert = _reset_polarity(spec)

    decls = []
    for name, w in ins:
        decls.append(f"  logic {sv_width(w)} {name};")
    for name, w in outs:
        decls.append(f"  logic {sv_width(w)} {name};")
    decls.append(f"  logic {clk};")
    if rst:
        decls.append(f"  logic {rst};")

    conns = [f".{clk}({clk})"]
    if rst:
        conns.append(f".{rst}({rst})")
    for name, _ in ins + outs:
        conns.append(f".{name}({name})")
    conns_str = ",\n    ".join(conns)

    assign_inputs = [
        "      lfsr  = {lfsr[30:0],  lfsr[31]  ^ lfsr[21]  ^ lfsr[1]  ^ lfsr[0]};",
        "      lfsr2 = {lfsr2[30:0], lfsr2[30] ^ lfsr2[6]  ^ lfsr2[4] ^ lfsr2[1]};",
    ]
    combined = "{lfsr2, lfsr}"
    cursor = 0
    for name, w in ins:
        if cursor + w > 64:
            assign_inputs.append(
                "      lfsr  = {lfsr[30:0],  lfsr[31]  ^ lfsr[21]  ^ lfsr[1]  ^ lfsr[0]};")
            assign_inputs.append(
                "      lfsr2 = {lfsr2[30:0], lfsr2[30] ^ lfsr2[6]  ^ lfsr2[4] ^ lfsr2[1]};")
            cursor = 0
        if w == 1:
            assign_inputs.append(f"      {name} = {combined}[{cursor}];")
        else:
            assign_inputs.append(f"      {name} = {combined}[{cursor+w-1}:{cursor}];")
        cursor += w

    fmt = " ".join(["%h"] * (len(ins) + len(outs)))
    disp_vars = ", ".join([n for n, _ in ins] + [n for n, _ in outs])

    rst_init     = f"    {rst} = {rst_assert};\n" if rst else ""
    rst_release  = f"    {rst} = {rst_deassert};\n" if rst else ""

    return f"""`timescale 1ns/1ps
module probe_tb;
{chr(10).join(decls)}

  {module} dut (
    {conns_str}
  );

  int i;
  logic [31:0] lfsr;
  logic [31:0] lfsr2;

  initial {clk} = 0;
  always #5 {clk} = ~{clk};

  initial begin
    lfsr  = 32'h{SEED1:08X};
    lfsr2 = 32'h{SEED2:08X};
{rst_init}{chr(10).join(f"    {n} = '0;" for n, _ in ins)}

    repeat ({N_RESET}) @(posedge {clk});
    #1;
{rst_release}
    for (i = 0; i < {N_RANDOM}; i++) begin
{chr(10).join(assign_inputs)}
      @(posedge {clk});
      #1;
      $display("{fmt}", {disp_vars});
    end
    $finish;
  end
endmodule
"""


def build_tb_sv_seq(spec):
    module = spec["module"]
    ins = spec["inputs"]
    outs = spec["outputs"]
    clk = spec["clock_port"]
    rst = spec.get("reset_port")
    rst_assert, rst_deassert = _reset_polarity(spec)

    port_decls = []
    for name, w in ins:
        port_decls.append(f"  logic {sv_width(w)} {name};")
    for name, w in outs:
        port_decls.append(f"  logic {sv_width(w)} {name};")
        port_decls.append(f"  logic {sv_width(w)} expected_{name};")
    port_decls.append(f"  logic {clk};")
    if rst:
        port_decls.append(f"  logic {rst};")

    conns = [f".{clk}({clk})"]
    if rst:
        conns.append(f".{rst}({rst})")
    for name, _ in ins + outs:
        conns.append(f".{name}({name})")
    conns_str = ",\n    ".join(conns)

    n_fields = len(ins) + len(outs)
    fmt = " ".join(["%h"] * n_fields)
    scan_args = ", ".join([n for n, _ in ins] + [f"expected_{n}" for n, _ in outs])
    cmp_expr = " || ".join([f"{n} !== expected_{n}" for n, _ in outs])
    err_fmt_in  = " ".join([f"{n}=%h" for n, _ in ins])
    err_fmt_out = " ".join([f"exp_{n}=%h act_{n}=%h" for n, _ in outs])
    err_args_in  = ", ".join([n for n, _ in ins])
    err_args_out = ", ".join(sum([[f"expected_{n}", n] for n, _ in outs], []))

    rst_init     = f"    {rst} = {rst_assert};\n" if rst else ""
    rst_release  = f"    {rst} = {rst_deassert};\n" if rst else ""

    return f"""`timescale 1ns/1ps
module tb;
  int total_checks;
  int total_errors;

{chr(10).join(port_decls)}

  {module} dut (
    {conns_str}
  );

  integer fd, rc, line_num;
  string line_buf;

  initial {clk} = 0;
  always #5 {clk} = ~{clk};

  initial begin
    total_checks = 0;
    total_errors = 0;
{rst_init}{chr(10).join(f"    {n} = '0;" for n, _ in ins)}

    repeat ({N_RESET}) @(posedge {clk});
    #1;
{rst_release}
    fd = $fopen("vectors.dat", "r");
    if (fd == 0) begin
      $display("ERROR: cannot open vectors.dat");
      $fatal(1);
    end
    line_num = 0;
    while (!$feof(fd)) begin
      line_num = line_num + 1;
      void'($fgets(line_buf, fd));
      if (line_buf.len() == 0) continue;
      if (line_buf.substr(0, 0) == "#") continue;
      rc = $sscanf(line_buf, "{fmt}", {scan_args});
      if (rc != {n_fields}) continue;
      @(posedge {clk});
      #1;
      total_checks = total_checks + 1;
      if ({cmp_expr}) begin
        $display("TB_ERROR line=%0d {err_fmt_in} {err_fmt_out}",
                 line_num, {err_args_in}, {err_args_out});
        total_errors = total_errors + 1;
      end
    end
    $fclose(fd);
    $display("TB_SUMMARY total=%0d errors=%0d", total_checks, total_errors);
    if (total_errors != 0) $fatal(1, "FAIL");
    $display("PASS");
    $finish;
  end
endmodule
"""


# ---------------------------------------------------------------------------
# Source fetch + description / metadata
# ---------------------------------------------------------------------------
def fetch_source(spec, dest: Path):
    """Download spec['source_url'] to dest, then apply any source_patches.

    Patches are list of (old, new) string substitutions, applied in order.
    Each patch is idempotent (a no-op once `old` is gone), so the function is
    safe to re-run on an already-patched file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with urllib.request.urlopen(spec["source_url"]) as resp:
            dest.write_bytes(resp.read())

    patches = spec.get("source_patches", [])
    if patches:
        text = dest.read_text()
        for old, new in patches:
            text = text.replace(old, new)
        dest.write_text(text)


def write_description(spec, out_dir: Path, source_filename: str):
    text = (
        spec["desc"].rstrip()
        + "\n\n"
        + f"`context/{source_filename}` provides the verbatim DR_RTL baseline "
        + "as a starting point for optimization.\n"
    )
    (out_dir / "description.txt").write_text(text)


def write_metadata(spec, out_dir: Path):
    md = {
        "name": spec["case"],
        "module_name": spec["module"],
        "cost_metric": ["yosys_wires", "yosys_cells"],
        "tb_module": "tb",
        "tb_mode": spec["mode"],
        "source": {
            "repo": "https://github.com/hkust-zhiyao/DR_RTL",
            "path": spec["source_path"],
        },
    }
    if spec["mode"] == "seq":
        md["clock_port"] = spec["clock_port"]
        md["reset_port"] = spec.get("reset_port")
        if spec.get("reset_port"):
            md["reset_active_low"] = spec.get("reset_active_low", False)
    (out_dir / "metadata.json").write_text(json.dumps(md, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Per-case driver
# ---------------------------------------------------------------------------
def generate_vectors(spec, work: Path, source_file: Path):
    """Build probe_tb against the golden, run it, return captured stdout lines."""
    golden_name = "golden.sv" if spec.get("source_ext", "v") == "sv" else "golden.v"
    shutil.copy(source_file, work / golden_name)

    if spec["mode"] == "comb":
        (work / "probe_tb.sv").write_text(build_probe_tb_comb(spec))
    else:
        (work / "probe_tb.sv").write_text(build_probe_tb_seq(spec))

    run([
        "verilator", "--binary", "--timing", "--top-module", "probe_tb",
        "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNOPTFLAT", "-Wno-LATCH",
        "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL", "-Wno-CASEINCOMPLETE",
        "-Wno-SELRANGE", "-Wno-COMBDLY", "-Wno-MULTIDRIVEN", "-Wno-IMPLICIT",
        "-Wno-SYNCASYNCNET",
        "-j", "0", "-o", "probe_exe",
        golden_name, "probe_tb.sv",
    ], cwd=work)

    r = subprocess.run(["./obj_dir/probe_exe"], cwd=work,
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise RuntimeError("probe run failed")
    lines = [l for l in r.stdout.splitlines()
             if l.strip() and not l.startswith("-")]
    return lines


def write_benchmark(spec):
    out = BENCH_ROOT / spec["case"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "context").mkdir(exist_ok=True)

    ext = spec.get("source_ext", "v")
    source_filename = f"starting_point.{ext}"
    source_file = out / "context" / source_filename
    fetch_source(spec, source_file)

    write_description(spec, out, source_filename)
    write_metadata(spec, out)

    work = out / ".gen_tmp"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    try:
        lines = generate_vectors(spec, work, source_file)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    header = "# " + " ".join(
        [n for n, _ in spec["inputs"]] + [n for n, _ in spec["outputs"]])
    (out / "vectors.dat").write_text(header + "\n" + "\n".join(lines) + "\n")

    if spec["mode"] == "comb":
        (out / "tb.sv").write_text(build_tb_sv_comb(spec))
    else:
        (out / "tb.sv").write_text(build_tb_sv_seq(spec))

    print(f"[ok] {spec['case']:14s} {spec['mode']:4s} "
          f"module={spec['module']:32s}  vectors={len(lines)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--case", action="append", default=None,
                   help="Generate only the named case (repeatable). "
                        "Omit to generate every case in BENCHMARKS.")
    p.add_argument("--list", action="store_true",
                   help="List the known case names and exit.")
    args = p.parse_args()

    if args.list:
        for spec in BENCHMARKS:
            print(f"{spec['case']:14s}  {spec['module']:30s}  mode={spec['mode']}")
        return

    selected = (
        [s for s in BENCHMARKS if s["case"] in args.case]
        if args.case else list(BENCHMARKS)
    )
    if args.case:
        missing = set(args.case) - {s["case"] for s in BENCHMARKS}
        if missing:
            raise SystemExit(
                f"Unknown case(s): {sorted(missing)}. "
                f"Known: {[s['case'] for s in BENCHMARKS]}"
            )

    for spec in selected:
        write_benchmark(spec)


if __name__ == "__main__":
    main()

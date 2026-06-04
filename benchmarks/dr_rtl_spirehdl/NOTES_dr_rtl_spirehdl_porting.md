# DR_RTL → SpireHDL porting notes

Running write-up for `benchmarks/dr_rtl_spirehdl/` — the SpireHDL mirror of
`benchmarks/dr_rtl/`. Scope of this iteration: **5 largest portable designs**
(`datapath` 1064 LOC, `cpu_pipe` 926, `pcie` 923, `i2c` 915, `router` 594);
the 3 ARM/Z80 CPUs (`tv80`, `arm_cpu1`, `arm_cpu2`) are explicitly out of
scope as multi-day full-instruction-decoder ports.

## Session log

### Session 1 — scaffolding + ticket warmup + partial router

- Created `benchmarks/dr_rtl_spirehdl/<case>/` for each of the 5 designs
  (+ added `ticket` as a warmup proof-of-concept) with `tb.sv` +
  `vectors.dat` + `metadata.json` + `description.txt` copied from the
  verilog sibling. Added `"language": "spirehdl"` and
  `"starting_point": "context/starting_point.py"` to each
  `metadata.json`.
- `tb.sv` and `vectors.dat` are **bit-identical** to the verilog
  siblings (verified via `diff -q`) — the "Hard invariant" from
  `benchmarks/turbo_rtl/README.md:31-37`.
- **`ticket` ported in two complete variants**, both pass 2000/2000:
  - `context/starting_point.py` — hand-written mux-cascade style.
    33 cells / 37 wires / 258 transistors. Matches verilog cell
    count exactly.
  - `context/starting_point_fsm_api.py` — idiomatic `State` /
    `switch_` / `case_` / `if_` / `elif_` API (see
    `deps/spire-hdl/README_state_machines.md`). 95 cells / 99 wires /
    608 transistors. ~3× larger because yosys+abc doesn't fully
    collapse the switch's condition-tracking machinery. Reads closer
    to the verilog's three-`always`-block structure.
  - Both serve as templates for the larger ports.
- **`router` partially ported** — see "Designs we tried but skipped"
  below. 500-LOC translation inlining all 5 submodules; data-path
  logic verified correct, FSM state-tracking has a subtle divergence
  bug that needs a probe-trace to find.
- **`i2c`, `pcie`, `cpu_pipe`, `datapath`** — scaffolded only;
  `starting_point.py` is TODO for subsequent sessions.

## Per-design porting analysis

Each of the 5 designs has a detailed entry below. The analysis informs
the per-session estimate, the module-flattening strategy, and the
expected gotchas.

### `router` (594 LOC, 5 modules) — recommended first port

Module breakdown:
- `router_top` (52 LOC) — pure instantiation of 4 submodules + a
  `generate for` that instantiates `router_fifo` 3×.
- `router_sync` (135 LOC) — channel-select FSM with 5-bit
  per-channel soft-reset counters (counts to 30 then asserts
  `soft_reset_<n>`).
- `router_fsm` (139 LOC) — 8-state main FSM
  (`decode_address`/`load_first_data`/`load_data`/`load_parity`/
  `fifo_full_state`/`load_after_full`/`check_parity_error`/
  `wait_till_empty`). Outputs derived as `assign` from `present_state`
  comparisons.
- `router_fifo` (147 LOC) — 16-entry × 9-bit FIFO. **Has a `reg [8:0]
  fifo [15:0]` memory array** that must be translated carefully —
  spirehdl supports register arrays via a `list[Register]` pattern.
  Already patched in the verilog source: two `8'bzz` lines became
  `8'd0` so the design is verilator-clean.
- `router_reg` (112 LOC) — header-byte hold register + parity tracking
  + low_packet_valid signal generation. Several `always @(posedge clk)`
  blocks with `if/else` ladders.

**Reset semantics:** all 5 modules use `if(!resetn) ... else ...` inside
`always @(posedge clk)` — synchronous active-low reset. So in spirehdl:
`Module(name, with_clock=True, with_reset=False)` + explicit
`resetn = m.input(UInt(1), "resetn")` + `mux(~resetn, init, next)` per
register.

**Memory array (`router_fifo`):** the 16×9-bit `fifo` array gets
addressed via `read_ptr` and `write_ptr`. SpireHDL translation:
```python
fifo = [Register(UInt(9), init=0, name=f"fifo_{i}") for i in range(16)]
# Read: mux on read_ptr to select among the 16 registers
read_data = mux_tree_over(fifo, read_ptr[0:4])
# Write: each register's next-state guards on `write_ptr == i & write_enb`
for i in range(16):
    fifo[i] <<= mux((write_enb & ~full) & (write_ptr[0:4] == i), {temp, datain}, fifo[i])
```
This is a ~16-mux tree on the read side; yosys+abc will collapse to
something reasonable but the spirehdl source will be ~50 LOC just for
the FIFO array.

**Estimated port effort:** 3–4 hours for a faithful translation, +1 hour
to debug the FIFO mux semantics against the probe tb. **Top priority.**

### `i2c` (915 LOC, 3 modules)

Module breakdown:
- `i2c_master_bit_ctrl` (~410 LOC) — bit-level FSM with start/stop/
  read/write/ack states. Lots of clk-prescaler logic for SCL gen.
- `i2c_master_byte_ctrl` (~280 LOC) — byte-level FSM that drives the
  bit-controller. State variables for tx/rx shift registers.
- `i2c_master_top` (~225 LOC) — Wishbone interface + register file
  (control / status / clock-prescale / TX / RX). Decodes `wb_adr_i`
  into the 8 internal registers.

**Reset semantics:** Synchronous active-high `wb_rst_i` AND
asynchronous active-low (or high, depends on ARST_LVL parameter)
`arst_i`. Per the verilog source, both apply via
`always @(posedge wb_clk_i or negedge arst_i)` for some flops and
`always @(posedge wb_clk_i)` with `if (wb_rst_i)` for others.

**Spirehdl approach:** `Module(with_clock=True, with_reset=False)`,
declare both `wb_rst_i` and `arst_i` as inputs, and per-register
implement the appropriate `mux(reset_cond, init_val, next_val)` pattern.

**Pitfalls:**
- The Wishbone register-write decoder is a `case (wb_adr_i)` with
  8 entries — translate as a Python-level dict lookup or a mux tree.
- The `i2c_master_bit_ctrl` uses `synopsys full_case parallel_case`
  pragmas (the verilog source already has them stripped via
  `source_patches`). Spirehdl doesn't have those pragmas — translate
  case statements as full mux trees.
- Open-drain SDA/SCL outputs are split into `*_pad_o` (always 0) and
  `*_padoen_o` (the actual output-enable). Spirehdl can emit this
  directly — no real tri-state.

**Estimated port effort:** 5–6 hours. State-machine-heavy but the
Wishbone interface and FSMs are mechanical.

### `cpu_pipe` (926 LOC, 5 modules)

Module breakdown:
- `dcpu16_cpu` (top, ~30 LOC) — instantiates the 4 submodules.
- `dcpu16_alu` (~265 LOC) — ALU with 8 opcodes (`SET`/`ADD`/`SUB`/
  `AND`/`OR`/`XOR`/`SHL`/`SHR`). Combinational; output via
  `casex (opc)`.
- `dcpu16_mbus` (~260 LOC) — memory bus arbiter between fetch and
  general buses. Multiple FSMs for the bus protocol.
- `dcpu16_ctl` (~370 LOC) — control unit. Decodes instructions into
  ALU opcodes + bus operations. **This is the hardest module** — it's
  effectively the instruction decoder.

**Reset semantics:** synchronous active-high `rst` in
`always @(posedge clk) if (rst) ... else ...` style. Use
`with_reset=False` + `mux(rst, init, next)`.

**Pitfalls:**
- The control unit's instruction decoder uses `casex` (don't-care
  match patterns). Spirehdl has no direct `casex` equivalent —
  translate manually to a chain of `(opcode & mask) == pattern`
  comparisons. Tedious for 30+ opcodes.
- The mbus arbiter has multiple interacting FSMs. Risk of subtle
  pipeline bugs in the spirehdl version that pass the probe but
  fail on longer traces.

**Estimated port effort:** 6–8 hours. **Defer to last** — most likely
to hit a skip-and-document wall on the casex-heavy decoder.

### `pcie` (923 LOC, 7 modules)

Module breakdown:
- `top` (61 LOC) — pure instantiation.
- `piso` (29 LOC), `sipo` (19 LOC) — tiny shift registers. Trivial.
- `scrambler` (60 LOC), `descrambler` (50 LOC) — LFSR-based.
  Mechanical translation.
- `encoder` (353 LOC) — **8b/10b encoder lookup table**. ~256 case
  entries, each mapping an 8-bit input to two 10-bit outputs (selected
  by `rd` bit). Mechanical but big — translate as a Python dict, then
  emit via `mux_tree` over the dict.
- `decoder` (351 LOC) — symmetric 10b/8b decoder lookup table.

**Reset semantics:** mostly `always @(posedge clk or negedge rst)` with
`if (!rst)` → async active-low reset. Use `with_reset=False` + explicit
`mux(~rst, init, next)`.

**Pitfalls:**
- The encoder/decoder lookup tables are large. Naive translation
  produces a 256-deep mux tree which yosys handles fine but the
  spirehdl source is ~500 LOC of repetitive `Wire` declarations.
  **Use Python list comprehensions** to keep the source manageable:
  ```python
  ENCODER_TABLE = {
      0x00: (0b1001110100, 0b0110001011),
      0x01: (0b0111010100, 0b1000101011),
      ...
  }
  # Emit the mux tree
  data_out_pos_rd = mux_tree(data_in, [tbl[1] for k, tbl in ENCODER_TABLE.items()])
  data_out_neg_rd = mux_tree(data_in, [tbl[0] for k, tbl in ENCODER_TABLE.items()])
  data_out = mux(rd, data_out_pos_rd, data_out_neg_rd)
  ```
- The encoder also has a separate K-character lookup (~12 entries) for
  when `k=1` — handle as a second table.

**Estimated port effort:** 4–5 hours, mostly mechanical data entry for
the tables. Lowest variance estimate of the 5.

### `datapath` (1064 LOC, 7 modules)

Module breakdown:
- `datapath` (top, ~516 LOC) — register banks (col / key / iv / bkp)
  + muxes + 4-way generate loops. The bulk of the design.
- `mix_columns` (~70 LOC) — Galois-field xtime operations.
- `key_expander` (~104 LOC) — round key generation.
- `sBox` (~22 LOC) — top-level sbox dispatcher.
- `sBox_8` (~251 LOC) — **AES S-box lookup table**. 256-entry case for
  both encrypt and decrypt directions.
- `shift_rows` (~62 LOC) — byte permutation.
- `data_swap` (~38 LOC) — byte-order swap based on data_type.

**Reset semantics:** `always @(posedge clk, negedge rst_n)` — async
active-low. The 4-way `generate for` blocks iterate over the 4 columns,
so each block becomes a Python loop:
```python
for l in range(4):
    iv_l   = Register(UInt(32), init=0, name=f"iv_{l}")
    bkp_l  = Register(UInt(32), init=0, name=f"bkp_{l}")
    # ... per-column logic ...
```

**Pitfalls:**
- The S-box table is a 256-entry case; same approach as pcie encoder
  (Python dict + mux_tree).
- `mix_columns` uses bit-level manipulations (`{a[6:0], 1'b0} ^
  ({8{a[7]}} & 8'h1B)`) — Galois multiply by 2. Translate carefully
  using spirehdl bit-slice / concat operations. `cat` is LSB-first so
  watch the bit order.
- Multiple parallel pipeline stages (`*_pp1`, `*_pp2` suffix
  registers). Each pp register needs its own `Register(..., init=0)`.

**Estimated port effort:** 6–8 hours. Multi-module, dense math, large
lookup table. Second most likely to hit a wall.

## Translation conventions (reference)

Pulled from `benchmarks/turbo_rtl/README.md:233-318`. Standard imports
for every starting_point.py:

```python
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, SInt, Wire, Register, mux, cat
```

**`with_reset` decision tree** (per `turbo_rtl/README.md:281-318`):

- **No reset, clk-only:** `with_reset=False`. No reset port added.
- **Async active-high `rst` to 0:** `with_reset=True`. Auto-creates
  `rst` input; emits `always @(posedge clk or posedge rst)`. Use
  `Register(typ, init=0, ...)`.
- **Reset port named anything else** (`resetn`, `rst_n`, `arst_i`,
  `reset_n`, `wb_rst_i`) **or sync reset**: `with_reset=False` +
  explicit `m.input(UInt(1), "<port_name>")` + `mux(reset_cond,
  init_val, next_val)` per register.

All 5 dr_rtl designs in this iteration fall into the third category
(custom reset port names). So the recipe is uniform:

```python
m = Module(name="<top>", with_clock=True, with_reset=False)
rst_port = m.input(UInt(1), "<resetn|rst|rst_n|...>")
# Per register:
r = Register(UInt(W), name="<name>")
r <<= mux(<is_reset_active>, <init>, <next_val>)
```

**Width discipline** (`turbo_rtl/README.md:243-253`): set each wire to
its verilog-declared width. SpireHDL arithmetic grows widths by
default (`UInt(n)+UInt(n) → UInt(n+1)`, `*` produces `n+m` bits);
truncation only happens at the final `output <<=`. Use explicit
`Wire(UInt(W), name="X"); X <<= expr` at every stage to force the
cut-point — this saves ~20% ADP on average (`turbo_rtl/README.md:249`'s
`bcd_to_bin_16b`: 4.28M → 3.36M ADP from this alone).

**Multi-module designs:** all 5 designs here are multi-module
(3–7 modules each). Strategy: **inline submodules as Python helper
functions** that take a Module handle. Loses the verilog submodule
names but produces a single flat netlist. Alternative is multiple
Module(...) calls + m.instance(...), but that's more boilerplate and
the inlined approach matches how
`benchmarks/rtl_rewriter_spirehdl/case*` already does it.

## Per-design status

| Case | LoC v | Modules | Scaffolded? | Ported? | Cells | Wires | Notes |
|---|---:|---:|:-:|:-:|---:|---:|---|
| `router`    |  594 | 5 | ✅ | ❌ TODO | — | — | Recommended first port. 16-entry FIFO array is the trickiest part. |
| `i2c`       |  915 | 3 | ✅ | ❌ TODO | — | — | Wishbone interface + 2-stage FSM. Mechanical. |
| `pcie`      |  923 | 7 | ✅ | ❌ TODO | — | — | Mostly 8b/10b table data — use Python dicts. |
| `cpu_pipe`  |  926 | 5 | ✅ | ❌ TODO | — | — | `casex`-heavy decoder. Likely skip-and-document. |
| `datapath`  | 1064 | 7 | ✅ | ❌ TODO | — | — | AES S-box + GF math. Hardest after cpu_pipe. |

**Scaffolded** = `dr_rtl_spirehdl/<case>/` exists with bit-identical
`tb.sv` / `vectors.dat` + adjusted `description.txt` + `metadata.json`
with `language: spirehdl` / `starting_point: context/starting_point.py`.

**Ported** = `context/starting_point.py` exists, the probe tb shows
zero MISMATCH lines across 500+ random vectors, AND `run_eval.py
--language spirehdl --cost-metric yosys_cells` reports PASS 2000/2000.

## Designs we tried but skipped

### `router` — partial port, 22 / 2000 vectors pass

`context/starting_point.py` exists with a 500-LOC inlined-submodules
translation but currently fails the 2000-vector tb.sv at vector ~22.
The data-path logic is correct — `err`, `vldout_*`, and `data_out_*`
all match the verilog at the first failing vector. The mismatch is
solely on the FSM's `busy` output, suggesting `present_state` advances
to a different state than the verilog's FSM at some point.

What's working:
- `router_reg`'s parity / err logic (`err` matches).
- `router_fifo`'s read/write/empty/full tracking (`vldout_*` and
  `data_out_*` match).
- The first ~22 cycles entirely (the initial period before the first
  packet finishes loading).

What's not:
- After the first ~22 cycles, `act_busy=1` while `exp_busy=0` (or
  vice-versa) — meaning my FSM's `present_state` is in a different
  state-class (busy vs not-busy) than the verilog's.

Likely candidates for the bug (not yet narrowed down):
- Subtle timing difference in `parity_done` / `low_packet_valid`
  feedback into the FSM's `LOAD_AFTER_FULL` transition logic.
- `temp_fsm` register sampling timing — verilog updates `temp` only
  when `detect_add` is high; my mux pattern does the same but Python
  scoping issues might have hidden a typo.
- Soft-reset match condition: the FSM jumps back to `DECODE_ADDR`
  when `(soft_reset_X & temp_fsm == X)`. If my match is misfiring,
  the FSM short-circuits prematurely.

Next-session debug recipe:
1. Build a probe tb that instantiates BOTH the verilog `router_top`
   AND the spirehdl-emitted `design.v` (renamed to `router_top_spire`),
   drives the same vectors into both, and dumps `present_state` from
   each into a side-by-side trace.
2. Find the first cycle where the two `present_state` values diverge.
3. Walk back one cycle and check `(packet_valid, datain, fifo_full,
   fifo_empty_0/1/2, parity_done, low_packet_valid, detect_add,
   soft_reset_match)` for that cycle to see which next-state input
   differs.

File is left in place at `benchmarks/dr_rtl_spirehdl/router/context/starting_point.py`
so a follow-up session can pick up the debug without re-translating
500 LOC. The benchmark dir does NOT claim to self-pass — the README's
status table reports it as "❌ partial".

## Translation gotchas (expected, populate as we hit them)

Pulled forward from `turbo_rtl/README.md:320-340`; concrete things to
watch for in these 5 designs:

- **`cat` is LSB-first.** `cat(b0, b1, ..., b9)` emits Verilog
  `{b9, ..., b1, b0}`. Easy to get backwards on
  `vending`'s 1024-bit ports, `aes`'s 1408-bit output, or pcie's
  10-bit encoder outputs.
- **Verilog `+` on 1-bit values returns 2 bits.** Use `^` (XOR) when
  the enclosing context only cares about the LSB.
- **Verilog `||` (logical OR) → spirehdl `(x != 0) | y`** when operands
  are wider than 1 bit.
- **`cast(expr, SInt(wider))` zero-extends an unsigned source.** To
  sign-extend, do `cat(x, x[msb])` in bit-space first.
- **`_maybe_share` auto-naming** can attach a Python variable name to
  an intermediate sub-expression and force an unintended width.
  Watch for `wire signed [W:0] foo;` in the emitted verilog where you
  intended unsigned.
- **Memory arrays** (`router_fifo`'s 16×9, `cpu_pipe`'s register file):
  spirehdl doesn't have a native Memory primitive in the standard API.
  Translate as `list[Register]` + explicit mux on read.

## Spirehdl-side biases (will populate after ports)

Per `turbo_rtl/README.md:389-413`: spirehdl-emitted verilog tends to
land on a different abc local optimum than the equivalent hand-written
verilog. The yosys+abc flow on spirehdl-emitted verilog often produces
ADP numbers 5–15% different in either direction. Expect this in the
comparison table — it's not a defect of the spirehdl port, just the
known "source structure influences post-yosys AIG topology" effect.

## Forward-looking suggestions

(populate as we learn from porting)

- **Multi-session pacing:** target 1 port per session for the smaller
  4 (router, i2c, pcie, datapath) and split cpu_pipe across 2 sessions
  if its instruction decoder is tractable. ~5 sessions total for the
  full 5.
- **Probe-tb first:** always write the equivalence probe (per
  `turbo_rtl/README.md:346-356`) BEFORE running the full framework
  eval. Probes give targeted MISMATCH lines that point at specific
  failing input bits; the full eval just says "Correctness: FAIL".
- **Module helper functions:** for multi-module designs, write Python
  functions that take a Module handle + input signals and emit
  `Wire`/`Register` into it. Keeps the source modular and lets you
  unit-test sub-translations independently.

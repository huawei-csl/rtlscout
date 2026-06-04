# DR_RTL scaffolding notes

Running process write-up for the `benchmarks/dr_rtl/` family. Captures what we
built, what worked, what didn't, and what we recommend doing differently in
the next iteration. Grows as designs land; current state below.

## What we did, in order

1. **Promoted the rtl_rewriter testbench generator.** Copied
   `/tmp/rtl_rewriter_tb_gen.py` to `benchmarks/dr_rtl/scripts/dr_rtl_tb_gen.py` with these
   additions:
   - `reset_active_low: bool` per-spec field. The `_reset_polarity` helper
     returns `("1'b0", "1'b1")` when set; the probe tb and the shipped tb.sv
     both pick up the inverted polarity automatically.
   - `.sv` source extension. `source_ext: "sv"` makes the generator copy the
     baseline to `context/starting_point.sv` and pass it (as `golden.sv`)
     into the verilator probe build. `read_verilog -sv` and `verilator -sv`
     are already on by default in the existing scripts, so no other plumbing
     was needed.
   - `--case <name>` CLI filter to regenerate a single design in place;
     `--list` to dump the known cases.
   - Self-bootstrapping benchmark directory: the generator downloads the
     baseline from `raw.githubusercontent.com`, writes `description.txt` and
     `metadata.json` from the BENCHMARKS spec, then runs the same probe →
     vectors.dat → tb.sv pipeline as the rtl_rewriter generator.

2. **Tier 1: `ticket`** — `ticket_machine` from `rtl_dataset/ticket_machine.v0.v`.
   Synchronous active-high `clear`, four 1-bit Moore outputs. Baseline self-passes
   `tb.sv` at 2000/2000 first try; cells=33, wires=35, transistors=258. No
   source-side edits required.

3. **Tier 1: `controller`** — `control_unit` from `rtl_dataset/controller.v0.v`,
   the AES control FSM (~545 LOC). First exercise of `reset_active_low: True`
   (sync `rst_n`). 4 inputs, 19 outputs (mix of multi-bit muxes and 1-bit
   flags). Baseline self-passes at 2000/2000; cells=257, wires=235, transistors=1376.
   No source-side edits required.

4. **Tier 1: `lstm`** — `lstm_cell` from `rtl_dataset/LSTM.v0.v`, ~135 LOC.
   Purely combinational, 3 × 16-bit signed inputs (`c_in`, `h_in`, `X`),
   2 × 16-bit signed outputs (`c_out`, `h_out`), internal sigmoid/tanh
   piecewise approximations and 16×16→32 multipliers. Baseline self-passes
   at 2002/2002 (comb mode includes all-zero / all-ones corners); cells=16311,
   wires=16202, transistors=32670. By far the largest gate count of Tier 1 —
   the multipliers dominate.

5. **Tier 1: `cpu_fsm`** — `mini_cpu` from `rtl_dataset/cpu_fsm.v0.v`, an FSM
   CPU with 4 × 8-bit register file and 8 × 16-bit instruction memory.
   Concern going in was X-propagation through the register file under random
   stimulus; **didn't materialise** because verilator's default 2-state
   semantics zero every reg at t=0, the generator holds `rst=1` for 3 cycles
   to land the FSM in FETCH, and the captured-from-golden behaviour is
   bit-identical to the same DUT replay. Baseline self-passes 2000/2000;
   cells=9129, wires=5209, transistors=54688. Note: this is the smallest of
   the CPU-style designs in DR_RTL; full CPUs (cpu_pipe, tv80, arm_cpu1/2)
   are still expected to be harder.

6. **Tier 1: `dsp`** — `DSP` from `rtl_dataset/DSP.v0.v`, Xilinx-DSP48-style
   pipelined multiplier-accumulator. The wrinkle: **8 independent per-stage
   resets** (`rstA`, `rstB`, …, `rstP`) instead of a single reset port. The
   generator only models one reset port, so the entry uses
   `reset_port: None` and lets the LFSR drive all the rst* signals as
   regular stimulus inputs. Verilator's 2-state init still zeros pipeline
   registers at t=0, so there's no X-prop even without a held reset. Baseline
   self-passes 2000/2000; cells=3533, wires=3233, transistors=3060.

8. **Tier 2: `vending`** — `vending_machine` from `rtl_dataset/vending_machine.v0.v`,
   FSM with parameterised `K*DATA_WIDTH=1024`-bit discount registers. First failure
   of the campaign: `$sscanf("%d", …)` capped the 1024-bit values at 64 bits.
   Switched the generator to emit `%h` for `$display`/`$sscanf`/error formatting;
   `vending` now self-passes 2000/2000 (cells=17357, wires=16336, transistors=125992).
   See "Already hit" below for the full root cause + fix.

7. **Tier 1: `datapath`** — `datapath` from `rtl_dataset/datapath.v0.v`,
   the AES datapath (column / key / IV register banks + sbox + mixcolumns).
   ~480 LOC, **async active-low `rst_n`** (`always @(posedge clk, negedge
   rst_n)`). 29 inputs (including a 32-bit `bus_in`), 4 outputs (three 32-bit
   buses + 1-bit `end_aes`). The generator's `reset_active_low: True`
   handled the async-edge case correctly — both the probe and the shipped
   tb.sv hold `rst_n=0` for 3 cycles and the design's negedge-rst_n branch
   fires once during that window. Baseline self-passes 2000/2000; cells=5615,
   wires=4156, transistors=27668.

9. **Tier 2 + 3 + 4** scaffolded similarly — `vending`, `uart`, `spi1`,
   `spi2`, `communicate`, `router`, `pcie`, `fifo`, `aes` (SystemVerilog),
   `i2c`, `cpu_pipe`, `tv80`, `arm_cpu1`, `arm_cpu2`. All 20 self-pass
   2000/2000 against their LFSR-generated `tb.sv` / `vectors.dat`. Hex
   `vectors.dat` (forced by `vending`'s 1024-bit ports) covers all wide-port
   designs uniformly. Three designs (`spi1`, `router`, `i2c`) needed small
   `source_patches` in the BENCHMARKS spec — see "Already hit" below.

10. **Nangate45 PPA sweep** — added
    [`benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py`](../../benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py)
    on top of the existing `tech_eval.get_ppa(..., technology="nangate45")`
    API. Default `--target-delay-ps 100` (= 0.1 ns, matches the paper's
    constraint). 17/20 designs characterize cleanly; one design (`pcie`)
    needs a fallback yosys path with `synth -flatten` + a netlist
    post-processor that drops yosys-emitted `wire`/`reg` declarations
    that duplicate port decls (OpenROAD's structural `read_verilog`
    rejects them). 3 designs (`uart`, `spi2`, `fifo`) can't be measured
    on this flow at all — inferred latches or memory-driven async resets
    that Nangate45's cell library doesn't have cells for. Results in
    [`eval_nangate45_ppa.json`](eval_nangate45_ppa.json).

11. **Paper references injected.** Transcribed Table 2 from
    arXiv:2604.14989 (the Dr. RTL paper) into
    [`benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py`](../../benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py)
    and ran it. Each design's `metadata.json` now has a `reference` block
    carrying paper-baseline + paper-Dr.RTL WNS, TNS, and area, plus design
    stats (LoC / NoM / gates / regs) and `paper_target_delay_ns = 0.1`.
    Values are verbatim — no derived/converted fields stored. See
    "Paper references" below for the schema and rationale.

12. **Unified comparison table.** Added
    [`benchmarks/dr_rtl/scripts/dr_rtl_compare_table.py`](../../benchmarks/dr_rtl/scripts/dr_rtl_compare_table.py)
    that joins `eval_nangate45_ppa.json` with each `metadata.json:reference`
    and emits the `### Unified table: Ours vs Dr. RTL paper Table 2`
    markdown block in [`README.md`](README.md). Adds derived
    `delay_ns = 0.1 − WNS_ns` and `ADP = delay × area` columns; reports
    Δ% (ours vs paper-base) for WNS, Area, and ADP using the paper's
    sign convention (negative = improvement). See "Comparison table
    (README)" below for derivation details and re-run recipe.

## Per-design status table

| `<name>` | Module | Mode | Tier | Self-passes? | Wires | Cells | Transistors | Notes |
|---|---|---|---|---|---:|---:|---:|---|
| `ticket`     | `ticket_machine` | seq (clk, sync `clear`)             | 1 | PASS 2000/2000 |    35 |    33 |    258 | First test of the generator. |
| `controller` | `control_unit`   | seq (clk, sync active-low `rst_n`)  | 1 | PASS 2000/2000 |   235 |   257 |   1376 | First test of `reset_active_low=True`. |
| `lstm`       | `lstm_cell`      | comb                                | 1 | PASS 2002/2002 | 16202 | 16311 |  32670 | Multipliers dominate the cell count. |
| `cpu_fsm`    | `mini_cpu`       | seq (clk, sync `rst`)               | 1 | PASS 2000/2000 |  5209 |  9129 |  54688 | X-prop didn't bite — verilator zero-init + 3-cycle reset hold sufficed. |
| `dsp`        | `DSP`            | seq (clk; 8 per-stage rst* as inputs) | 1 | PASS 2000/2000 |  3233 |  3533 |   3060 | No single reset_port; per-stage `rst*` driven by LFSR. |
| `datapath`   | `datapath`       | seq (clk, async active-low `rst_n`) | 1 | PASS 2000/2000 |  4156 |  5615 |  27668 | First async-reset design — `reset_active_low=True` Just Worked. |
| `vending`    | `vending_machine`| seq (clk, async active-high `reset`) | 2 | PASS 2000/2000 | 16336 | 17357 | 125992 | First wide-port design (1024-bit). Forced switch from %d to %h. |
| `uart`       | `uart_top_design`| seq (clk, sync `rst`)               | 2 | PASS 2000/2000 |   343 |   494 |    264 | First-try clean. |
| `spi1`       | `simple_spi_top` | seq (`clk_i`, async active-low `rst_i`) | 2 | PASS 2000/2000 |   371 |   477 |   1784 | Required source patches: stripped `` `include "timescale.v" `` and removed `// synopsys full_case parallel_case` on the espr case. |
| `spi2`       | `spi`            | seq (clk, sync `rst`)               | 2 | PASS 2000/2000 |   357 |   635 |    368 | First-try clean. Internal SPI master+slave+mem loopback. |
| `communicate`| `sync_serial_communication_tx_rx` | seq (clk, async active-low `reset_n`) | 2 | PASS 2000/2000 |  1009 |  1350 |      0 | First-try clean. |
| `router`     | `router_top`     | seq (clk, sync active-low `resetn`) | 2 | PASS 2000/2000 |  1240 |  1707 |      0 | Required source patch: replaced two `8'bzz` tristate assignments in `router_fifo` with `8'd0` (verilator doesn't accept Z assigns to a reg). |
| `pcie`       | `top`            | seq (clk, async active-low `rst`)   | 2 | PASS 2000/2000 |  2641 |  2731 |      0 | First-try clean. Top module unhelpfully named `top` — `--top-module` thread already handles it. |
| `fifo`       | `fifo`           | seq (`clk_in`, async active-low `rst`; `clk_out` driven as LFSR input) | 2 | PASS 2000/2000 |  9250 | 13389 |      0 | **Surprise PASS** — see "Already hit" below. Dual-clock CDC didn't break baseline-vs-baseline replay because clk_out from LFSR is deterministic. CDC-changing optimisations are still likely to break correctness — caveat the user. |
| `aes`        | `key_expansion_128aes` (SystemVerilog) | seq (clk, async active-low `rst_async_n`) | 3 | PASS 2000/2000 | 16799 | 19710 |  15426 | First `.sv` source. `read_verilog -sv` + `verilator -sv` handled `always_ff` and multi-dim unpacked arrays without any source patch. 1408-bit wide output handled by the hex format change. |
| `i2c`        | `i2c_master_top` | seq (`wb_clk_i`, sync active-high `wb_rst_i`; `arst_i` async-reset as LFSR input) | 3 | PASS 2000/2000 |   347 |   398 |   2230 | Required source patch to strip several `// synopsys full_case parallel_case` pragmas. Second async-reset (`arst_i`) treated as random input; same caveat as `fifo` re: reset-handling optimisations. |
| `cpu_pipe`   | `dcpu16_cpu`     | seq (clk, sync active-high `rst`)   | 4 | PASS 2000/2000 |  3823 |  4155 |      0 | **Surprise PASS** — see "CPUs" note below. |
| `tv80`       | `tv80_core`      | seq (clk, sync active-low `reset_n`) | 4 | PASS 2000/2000 |   625 |   631 |   4462 | First-try clean. Cells number is small (~631) — the source has three modules in one file and the agent will be optimising the full hierarchy. |
| `arm_cpu1`   | `arm9_compatiable_code` | seq (clk, async active-high `rst`) | 4 | PASS 2000/2000 | 19873 | 21178 | 159100 | First-try clean. Largest design in the campaign — ~2800 LOC. |
| `arm_cpu2`   | `risclite_mx`    | seq (clk, async active-high `rst`)  | 4 | PASS 2000/2000 |  7829 |  8603 |  59788 | First-try clean. ~1200 LOC. |

Designs in the pipeline (Tier 1 remaining → 2 → 3 → 4) will be added as they land.

## Difficulties — encountered and expected

### Already hit

**vending (Tier 2): `$sscanf("%d", …)` truncates at 64 bits.** First attempt at
`vending_machine` (1024-bit `total_discount`) FAILed 996/2000. Captured values
in `vectors.dat` were correct (verilator's `$display("%0d", …)` widens to the
operand's actual bit width), but tb.sv's `$sscanf("%d", line, expected_total_discount)`
parsed only the low 64 bits into the 1024-bit `expected_total_discount` reg —
upper 960 bits stayed zero, comparison against the DUT's full output failed.

**Fix:** switch the generator to emit `%h` for both `$display` and `$sscanf`
everywhere — error messages too. `%h` round-trips arbitrary widths cleanly.
Re-ran all 7 benchmarks under the new format; six unchanged Tier-1 numbers, and
`vending` now PASSes at 2000/2000 with 17357 cells / 16336 wires / 125992
transistors. Decimal would have been fine for designs with all-≤64-bit ports
(every rtl_rewriter case, every Tier 1 dr_rtl design except vending), but
hex costs nothing and removes the silent-truncation footgun.

**spi1: `` `include "timescale.v"`` not in the DR_RTL repo.** Verilator and
yosys both error out on the missing include. Fix: per-spec
`source_patches: list[(old_str, new_str)]` mechanism — applied to the
downloaded file in `fetch_source`, idempotent (no-op once the old string is
gone). For spi1, strip the include line; for router (below) replace the
tri-state assigns. The patches live in `BENCHMARKS` so they're inspectable
and the per-design fix is documented at its source.

**spi1: synopsys full_case pragma rejected by verilator runtime.** With
`-Wno-CASEINCOMPLETE` we already silence the lint warning; but verilator
still asserts at runtime when the `case (espr) // synopsys full_case
parallel_case` falls through on values 12–15 (only 0–11 are mapped in the
SPI rate field). Patch: drop the `synopsys full_case parallel_case` comment;
verilator then treats it as a regular incomplete case (clkcnt holds value),
which is functionally fine for a SW-managed control register.

**router: `8'bzz` rejected by verilator (Unsupported tristate construct: ASSIGNDLY).**
Two lines inside `router_fifo`'s read logic assign `8'bzz` / `8'bz` to a regular
`reg` on soft_reset / count==0. Verilator doesn't model Z on a non-net.
Patch: replace `8'bzz` and `8'bz` with `8'd0` — functionally a small change
(idle output becomes 0 instead of high-impedance, which on a synthesizable
target was already going to be 0 anyway since the output is wired to a flop),
and the captured-vector replay is deterministic.

**fifo: dual-clock didn't bite (surprisingly).** The DR_RTL `fifo`
declares two clock ports (`clk_in`, `clk_out`) crossing an async FIFO. The
generator's single-clock model drives `clk_in` as the test clock and feeds
`clk_out` as a regular LFSR-driven input — so `clk_out` toggles randomly
rather than at a fixed period. Baseline-vs-baseline replay nevertheless
PASSes 2000/2000 (cells=13389, wires=9250) because the captured behaviour
matches the same DUT exactly. **Important caveat:** any optimisation that
changes CDC synchroniser depth or alters the relative timing between the
two clock domains will likely break correctness against the captured
vectors, even when functionally equivalent. The benchmark is usable for
synthesis cost comparisons; it should be treated with care for any
correctness-gated agent run.

**Overall result: 20/20 PASS.** The expected hard cases (dual-clock `fifo`,
SystemVerilog `aes`, CPU-like `cpu_fsm` / `cpu_pipe` / `tv80` / `arm_cpu1` /
`arm_cpu2`) all self-passed against captured baseline vectors. Where source
patches were required (`spi1`, `router`, `i2c`), the patches are recorded
in the BENCHMARKS spec via the `source_patches` field — see "Generator"
in `README.md` for invocation. The single global change that mattered most
was switching `%d` → `%h` everywhere in the generator, which removed the
silent-64-bit-truncation in `$sscanf` and unlocked all wide-port designs
(`vending` 1024-bit, `aes` 1408-bit, the ARM cores' 32-bit buses).

**Tier 1 surprises:** zero. All six Tier-1 designs self-passed on the first
generator run after writing the port list. Three small lessons:

- **Multi-reset designs (e.g. DSP):** if a design has *N* per-stage resets
  instead of one global reset, you can leave `reset_port: None` and feed all
  the rst* nets as regular LFSR-driven inputs. Verilator's 2-state default-zero
  init covers the t=0 X-prop case that you'd otherwise rely on the reset to
  handle.
- **Async-reset works out of the box.** `datapath` uses
  `always @(posedge clk, negedge rst_n)` (async active-low). The generator's
  3-cycle reset hold lands on the negedge of the test's deassertion, so the
  design sees a clean reset-then-deassert sequence identical to what a
  hand-written tb would do. No extra plumbing needed beyond
  `reset_active_low=True`.
- **`cpu_fsm` didn't X-prop**, against expectations. We expected register-file
  reads to glitch on unknown values; verilator's 2-state init + the FSM
  resetting state to FETCH (so reads come from initialised RF entries
  0x11/0x22/0x33/0x44) kept everything deterministic. Suggests the bigger
  CPUs (cpu_pipe, tv80, arm*) might be more tractable than feared too —
  worth a try at Tier 4 instead of pre-skipping.

### Expected (will be filled in as we hit them)

#### Dual-clock (`fifo` from `rtl_dataset/FIFO.v0.v`)

**Outcome: PASSed unexpectedly.** See "Already hit → fifo" above. The
single-clock generator drove `clk_out` as a regular LFSR input, which gave a
deterministic capture/replay against the same DUT. Caveat applies: a
re-implementation that changes CDC depth or relative timing between the two
domains will likely fail correctness against the captured vectors. Do not use
this benchmark as a correctness oracle for CDC-changing optimisations.

#### Active-low reset

The polarity flag (`reset_active_low: True`) covers the common case (controller's
sync `rst_n`). Two failure modes are worth watching for:

- A design that uses `posedge rst_n` as an *async* reset edge (semantically
  wrong but seen). The generator's 3-cycle hold then deassert still works, but
  the captured behaviour during the assert window may differ between probe and
  tb.sv if anything else changes simultaneously. If it shows up, document and
  skip rather than patch.
- A design that wires the reset net into a combinational path. The probe holds
  `rst = asserted` while inputs ramp; the tb does too. If the design's outputs
  during reset are X (e.g. uninitialised regs being read by a comb mux), the
  `!==` check fails. Again — skip, don't band-aid.

#### CPUs (`cpu_pipe`, `tv80`, `arm_cpu1`, `arm_cpu2`)

**Outcome: all four PASSed first try, baseline-vs-baseline.** The expected
X-propagation through the register file never materialised because:

1. Verilator's default 2-state semantics zero every register at t=0, so reads
   from unwritten memory just return 0, not X.
2. The captured-vs-DUT replay is the *same* DUT, so even architecturally
   meaningless behaviour reproduces bit-identically.

**Caveat for agent use** (same as `fifo` / `i2c`'s second-reset): the
captured-vector stream is deterministic for the baseline but not for any
re-implementation that changes pipeline latency, async-reset handling, or
internal sequencer timing. The benchmark is fine as a **synthesis cost
oracle** (yosys cells / wires / transistors are a property of the design,
not the stimulus). It is **fragile as a correctness oracle** for any
optimisation that touches the CPU's pipelined / interrupt / reset behaviour.

For a stronger correctness gate on CPUs, see the forward-looking suggestion
on `tb_mode: "synth_only"` below — drop the correctness check entirely and
rely on yosys synthesis pass/fail.

#### Wide ports (`vending` 1024-bit, `aes` 1408-bit output)

Mechanically the existing LFSR-rolling logic (`build_probe_tb_seq:assign_inputs`)
already handles `cursor + w > 64` by re-rolling, so wide ports compile. The
result is a huge `vectors.dat`: each 1024-bit value as decimal is ~310 chars,
times 2000 lines, times the number of wide ports. We'll commit it as-is for now
and only switch to `%h` / `$sscanf("%h", …)` if file size or sscanf perf becomes
a real problem.

#### SystemVerilog (`aes`)

`aes.v0.sv` uses `always_ff`, multi-dim unpacked arrays, generate blocks with
non-constant expressions. `verilator -sv` and `read_verilog -sv` should accept
it but yosys 0.33's `synth` macro may not fully handle multi-dim unpacked arrays.
We'll spot any concrete failure at Tier 3 and either flatten the source or
skip — don't pre-decide.

## Paper references (`metadata.json.reference`)

Each `benchmarks/dr_rtl/<case>/metadata.json` carries a `reference` block
populated from Table 2 of the Dr. RTL paper
([arXiv:2604.14989](https://arxiv.org/pdf/2604.14989)). The numbers come from
the paper's `Commercial Synthesis` (baseline) and `w/ Dr. RTL Optimization`
columns. Injected by `benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py` — the source-of-truth
transcription lives in that script's `TABLE2` constant so it can be re-applied
if metadata regenerates.

### What the paper measured

> *"All designs are synthesized with Synopsys Design Compiler using the Nangate
> 45 nm library under fixed synthesis constraints for fair comparison. In
> particular, we use a tight clock period of 0.1 ns to force aggressive
> synthesis optimization across all paths."* — arXiv:2604.14989, §setup.

So the paper's synthesis constraint envelope is **0.1 ns** — recorded in the
metadata as `paper_target_delay_ns: 0.1`. The paper itself uses the phrase
"clock period"; we call the same quantity `target_delay` everywhere in our
scripts (e.g. `benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py`'s `--target-delay-ps 100`).
**Same number, two terminologies** — keeping the field name aligned with our
own scripts makes cross-file comparison frictionless.

### What we store

**Verbatim from the paper, no derived/converted fields.** The paper reports
WNS, TNS (both in ns) and area (μm²) for two columns: `Commercial Synthesis`
(baseline) and `w/ Dr. RTL Optimization`. We record each value as-is. The
`%improvement` fields next to the optimized values are also straight from the
paper (negative = improvement vs baseline).

If a reader wants to compare against our own `eval_nangate45_ppa.json`'s
`delay_ps` field (which is the critical-path *arrival time* in ps, not slack),
they can recover an arrival-time-equivalent from the paper's WNS:

```
delay_ps ≈ (paper_target_delay_ns − WNS_ns) × 1000          # setup ≈ 0
```

We deliberately do NOT pre-compute this and store it in metadata — keeping
the recorded values 1:1 with the paper means there's no ambiguity about what
the paper actually claimed vs what we derived. Conversion is a one-liner if
needed (see `benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py` for the corresponding identity
on our own measurements, and the README's "Relationship between Delay and
Worst slack" section for the full derivation including the setup-time term).

### Schema

Flat fields, matching the style of `benchmarks/rtl_rewriter/case*/metadata.json`:

```json
{
  "reference": {
    "paper_source": "arXiv:2604.14989 (Dr. RTL), Table 2",
    "paper_design_name": "ticket",
    "paper_target_delay_ns": 0.1,
    "paper_synthesis_tool": "Synopsys Design Compiler + Nangate 45 nm",

    // Design statistics (independent of optimization)
    "paper_loc": 134,
    "paper_num_modules": 1,
    "paper_num_gates_baseline": 56,
    "paper_num_registers_baseline": 6,

    // Commercial-synthesis baseline column — verbatim
    "paper_baseline_wns_ns":  -0.23,
    "paper_baseline_tns_ns":  -1.24,
    "paper_baseline_area_um2": 78,

    // w/ Dr. RTL Optimization column — verbatim
    "paper_drrtl_wns_ns":  -0.09,
    "paper_drrtl_wns_improvement_pct": -60.9,
    "paper_drrtl_tns_ns":  -0.47,
    "paper_drrtl_tns_improvement_pct": -62.1,
    "paper_drrtl_area_um2": 45,
    "paper_drrtl_area_improvement_pct": -41.8,
    "paper_drrtl_sec_pass_pct": 65
  }
}
```

### Name mapping

The paper's Table 2 design labels match our `benchmarks/dr_rtl/<case>/`
directory names **everywhere except one** — the paper has a typo:

| Paper name | Our case dir | Notes |
|---|---|---|
| `datapth` | `datapath` | paper typo; `metadata.json.reference.paper_design_name` records the literal "datapth" so the audit trail is preserved |

All other 19 names are identical (`vending`, `ticket`, `lstm`, `dsp`,
`communicate`, `spi1`, `cpu_fsm`, `aes`, `fifo`, `spi2`, `uart`, `controller`,
`router`, `cpu_pipe`, `pcie`, `i2c`, `tv80`, `arm_cpu1`, `arm_cpu2`).

### Re-injection

```bash
python benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py
```

The script overwrites any existing `reference` block (it does NOT merge),
so if you've hand-edited the reference block, your changes will be lost.
Other top-level fields (`name`, `module_name`, `tb_module`, `source`,
clock/reset metadata, …) are preserved untouched.

## Comparison table (README)

The unified "Ours vs Dr. RTL paper Table 2" block in
[`README.md`](README.md) is **generated**, not hand-maintained. The generator
is [`benchmarks/dr_rtl/scripts/dr_rtl_compare_table.py`](../../benchmarks/dr_rtl/scripts/dr_rtl_compare_table.py);
it prints a markdown table to stdout that gets pasted into the README's
`### Unified table: Ours vs Dr. RTL paper Table 2` section.

### Inputs (three joins)

| Source | Provides | Produced by |
|---|---|---|
| `benchmarks/dr_rtl/eval_nangate45_ppa.json` | our `worst_slack_ns`, `area_um2` per case | `benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py` |
| `benchmarks/dr_rtl/<case>/metadata.json:reference` | paper Table 2 — baseline + Dr.RTL `wns_ns` / `area_um2` | `benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py` |
| Hard-coded constant `PAPER_TARGET_DELAY_NS = 0.1` | the synthesis-constraint envelope shared by both flows | — |

Refreshing the table is therefore a three-step pipeline; each step is
idempotent and only the steps whose inputs changed actually need to re-run:

```bash
# 1. Refresh our PPA numbers (only if RTL or target-delay changed)
python benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py --target-delay-ps 100 --processes 4

# 2. Refresh paper refs (only if paper TABLE2 transcription edited)
python benchmarks/dr_rtl/scripts/dr_rtl_inject_paper_refs.py

# 3. Regenerate the markdown table
python benchmarks/dr_rtl/scripts/dr_rtl_compare_table.py
```

Then paste step 3's stdout into the README between the
`### Unified table: …` header and the next `**What this comparison is…**`
paragraph.

### Derivations

For every column (ours / paper-base / paper-Dr.RTL), the table reports three
metrics: **WNS** (verbatim), **Area** (verbatim), and **ADP** (derived).

**ADP** uses the same `(target_delay − WNS)` derivation across all three
columns:

```
delay_ns  = PAPER_TARGET_DELAY_NS − WNS_ns        # = 0.1 − WNS_ns
ADP       = delay_ns × area_um2                    # units: μm²·ns
```

**Why one derivation across all three columns** — the paper only reports
WNS (not arrival time), so for paper-base and paper-Dr.RTL we have no
choice but to derive. Applying the *same* derivation to ours (rather than
using our STA-measured `delay_ps` field) means the ~30 ps setup-time
under-estimate that this formula carries is a **constant offset across each
row** that cancels out of the ratio. The trade-off: our row's ADP is ~30 ps
× area higher than the STA-accurate value would give, but the ΔADP %
deltas are bias-free. This matters most on tight-WNS small designs (where
30 ps is a meaningful fraction of total delay) and least on large designs
(where it's noise).

**Sign convention for Δ columns** — paper's own ("negative = improvement"):

```
ΔWNS   = (|ours_wns|  − |base_wns|)  / |base_wns|   × 100    # smaller |slack| = better
ΔArea  = ( ours_area  −  base_area)  /  base_area   × 100    # smaller area  = better
ΔADP   = ( ours_adp   −  base_adp )  /  base_adp    × 100    # smaller ADP   = better
```

`ΔWNS` uses absolute values because both WNS columns are negative
("violating" timing under the 0.1 ns constraint); a less-negative ours
is a smaller `|WNS|`, which is better. `ΔArea` and `ΔADP` are vanilla
relative-percent changes — both inputs are positive.

### N/A rows

Three designs (`uart`, `spi2`, `fifo`) don't have our-side PPA numbers
(inferred latches / memory-driven async reset on Nangate45; see "Designs
that don't characterize under this flow" in the README). The generator
emits `N/A` in those rows' ours-side cells and all three Δ columns; the
paper-base and paper-Dr.RTL columns are still populated so the paper's
own claim is visible.

### Display formatting

- WNS: signed, 2 decimal places (`-0.23`, `-7.12`).
- Area, ADP: comma thousand-separator, 1 decimal place when < 1000, integer otherwise (`55.6`, `128,692`).
- Δ: signed, 1 decimal place, with `%` suffix (`-91.3%`, `+2537.0%`).
- N/A: literal string when a value can't be computed.

### When to re-run

- **Changed `target_delay_ps`** in `benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py`:
  re-run steps 1 + 3, **and** update `PAPER_TARGET_DELAY_NS` in both
  `dr_rtl_inject_paper_refs.py` and `dr_rtl_compare_table.py` if you want
  the paper rows derived under the new constraint (note: the paper itself
  is fixed at 0.1 ns, so changing the constant means the table is no longer
  apples-to-apples with the paper).
- **Changed RTL or fixed a baseline patch** in `benchmarks/dr_rtl/scripts/dr_rtl_tb_gen.py`:
  re-run steps 1 + 3.
- **Found a transcription error in `TABLE2`** in `dr_rtl_inject_paper_refs.py`:
  re-run steps 2 + 3.
- **No change to inputs**: skip everything; the README table is already
  current.

## Forward-looking suggestions

These are recommendations for the *next* iteration; not in scope now.

1. **spirehdl mirror — exclude any verilog design that doesn't self-pass.**
   `benchmarks/turbo_rtl/README.md` invariant: spirehdl mirrors must share the
   verilog variant's `tb.sv` + `vectors.dat` bit-identically. A verilog design
   without a working tb.sv (dual-clock `fifo`, glitchy async-reset designs,
   uninitialised CPUs) **cannot** have a spirehdl mirror under this model.
   Decide the exclusion list once Tier 1–3 settle.

2. **Dual-clock / handwritten-tb track.** A separate family
   `benchmarks/dr_rtl_handtb/` (or similar) with hand-written `tb.sv` per
   design, no LFSR generator. Reserved for FIFO-style designs where the
   protocol *is* the design. Small benefit vs cost of writing 1–2 hand tbs.

3. **`tb_mode: "synth_only"` for CPUs.** Add a branch in `core/runner.py` /
   `core/evaluation.py` that skips the verilator correctness gate when
   `metadata["tb_mode"] == "synth_only"`. Lets cells/wires/transistors numbers
   be measured on tv80/arm/etc without committing to a meaningful stimulus.
   Smallest possible change to make these designs scoreable.

4. **Hex vectors.dat.** If wide-port `vending` / `aes` cause real problems,
   switch the generator from `%0d` / `%d` to `%h` / `$sscanf("%h", …)`.
   `rtl_rewriter` cases never needed this so we don't change the precedent
   pre-emptively.

5. **Multirun pipeline.** `experiments/rtl_rewriter_multirun.py` is hardcoded
   to two roots and integer case numbers. Either generalise it (`--family`
   + string IDs) or fork `experiments/dr_rtl_multirun.py`. Decide once we
   know which dr_rtl designs are usable.

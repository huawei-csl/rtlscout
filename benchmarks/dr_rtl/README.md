# `dr_rtl` benchmarks

Scaffolded from [HKUST-zhiyao/DR_RTL](https://github.com/hkust-zhiyao/DR_RTL)'s
`rtl_dataset/`. Each design is the *baseline* (`*.v0.{v,sv}`) the agent should
optimise; DR_RTL does not publish reference optimised companions, so the
`reference` block in `metadata.json` records only our reproduced baseline
numbers.

Same shape as `benchmarks/rtl_rewriter/case<N>/`:

```
benchmarks/dr_rtl/<name>/
  description.txt
  metadata.json
  tb.sv                 # data-driven self-checking testbench (module `tb`)
  vectors.dat           # LFSR-seeded random stimulus + corners (2000 vectors)
  context/
    starting_point.v   (or .sv)   # verbatim baseline from DR_RTL
```

`run_benchmark.py --benchmark dr_rtl/<name>` resolves it via the relative-path
lookup in `core/benchmarks.py:load_benchmarks`.

## Status

See [`NOTES_dr_rtl_scaffolding.md`](NOTES_dr_rtl_scaffolding.md) for the running
process write-up — per-design status table, difficulties encountered, and
forward-looking suggestions for designs that don't fit the random-stimulus
testbench model.

| Case | Module | Mode | Baseline self-passes? | Wires | Cells | Transistors |
|---|---|---|---|---:|---:|---:|
| `ticket`     | `ticket_machine` | seq  | PASS 2000/2000 |    35 |    33 |    258 |
| `controller` | `control_unit`   | seq  | PASS 2000/2000 |   235 |   257 |   1376 |
| `lstm`       | `lstm_cell`      | comb | PASS 2002/2002 | 16202 | 16311 |  32670 |
| `cpu_fsm`    | `mini_cpu`       | seq  | PASS 2000/2000 |  5209 |  9129 |  54688 |
| `dsp`        | `DSP`            | seq  | PASS 2000/2000 |  3233 |  3533 |   3060 |
| `datapath`   | `datapath`       | seq  | PASS 2000/2000 |  4156 |  5615 |  27668 |
| `vending`    | `vending_machine`| seq  | PASS 2000/2000 | 16336 | 17357 | 125992 |
| `uart`       | `uart_top_design`| seq  | PASS 2000/2000 |   343 |   494 |    264 |
| `spi1`       | `simple_spi_top` | seq  | PASS 2000/2000 |   371 |   477 |   1784 |
| `spi2`       | `spi`            | seq  | PASS 2000/2000 |   357 |   635 |    368 |
| `communicate`| `sync_serial_communication_tx_rx` | seq | PASS 2000/2000 |  1009 |  1350 |      0 |
| `router`     | `router_top`     | seq  | PASS 2000/2000 |  1240 |  1707 |      0 |
| `pcie`       | `top`            | seq  | PASS 2000/2000 |  2641 |  2731 |      0 |
| `fifo`       | `fifo`           | seq  | PASS 2000/2000 |  9250 | 13389 |      0 |
| `aes`        | `key_expansion_128aes` (SV) | seq | PASS 2000/2000 | 16799 | 19710 |  15426 |
| `i2c`        | `i2c_master_top` | seq  | PASS 2000/2000 |   347 |   398 |   2230 |
| `cpu_pipe`   | `dcpu16_cpu`     | seq  | PASS 2000/2000 |  3823 |  4155 |      0 |
| `tv80`       | `tv80_core`      | seq  | PASS 2000/2000 |   625 |   631 |   4462 |
| `arm_cpu1`   | `arm9_compatiable_code` | seq | PASS 2000/2000 | 19873 | 21178 | 159100 |
| `arm_cpu2`   | `risclite_mx`    | seq  | PASS 2000/2000 |  7829 |  8603 |  59788 |

## Nangate45 PPA characterization (apples-to-apples vs DR_RTL)

The DR_RTL paper uses Synopsys DC against `lib/nangate.db` — the binary form of
**NangateOpenCellLibrary**. We synthesize the same library (the source
`NangateOpenCellLibrary_typical.lib` shipped with OpenROAD-flow-scripts) via
yosys + abc + OpenROAD STA. Same cell areas / power tables; different synth
engine, so absolute numbers differ from DC. Re-extract with:

```bash
python benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py --target-delay-ps 100 --processes 4
```

Numbers below are at `target_delay = 100 ps` (= **0.1 ns**, the user-requested
budget). Units handled as: abc gets `100` (ps, per `template.py:116`);
the `.lib` is `time_unit "1 ns"` so STA reports in ns, then `lib_time_to_ps`
converts back — `delay` is always in **picoseconds**. STA's `worst_slack`
is reported in **nanoseconds** (the lib's native unit) under the script
template's default `period = 5 ns` clock.

**Relationship between `Delay (ps)` and `Worst slack (ns)`.** Both columns
describe the **same** worst-slack timing path but report different quantities:

- `Delay (ps)` is the data **arrival time** at that path's endpoint (yosys
  prints it as `wns`, but it's actually the arrival, not the slack — see
  `core/ppa_extraction.py:329`).
- `Worst slack (ns)` is the standard `required − actual` for that same path,
  reported by OpenROAD's `report_worst_slack`.

Tied together by the timing identity:

```
worst_slack_ns ≈ (constraint_ns − setup_time_ns) − delay_ps / 1000
```

For every design in the table the binding constraint is
`set_max_delay = 0.1 ns` (the `target_delay`, applied to all paths originating
at primary inputs — `template.py:228`), not the script's `period = 5 ns`
clock (which only binds for pure reg-to-reg paths). Nangate45 DFF setup time
is ≈ 0.03 ns, so:

```
worst_slack_ns ≈ 0.07 − delay_ps / 1000
```

Quick check on `ticket`: `0.07 − 89.1/1000 = -0.019 ≈ -0.02 ns` ✓ matches the
table. The identity holds across all 17 designs to within ±0.03 ns (residual
is per-endpoint-cell setup variation: DFF_X1 vs DFF_X2 vs DFF_X4, etc.).

So `Worst slack` adds no independent information once you know `Delay` and
the target — it's there mainly as a sanity check that the STA constraint was
applied as expected.

### Unified table: Ours vs Dr. RTL paper Table 2

WNS, Area, and ADP for every design, side-by-side. **Ours** is
`eval_nangate45_ppa.json` (yosys + abc + OpenROAD STA on
`NangateOpenCellLibrary_typical.lib` at `target_delay = 100 ps`). **base** and
**Dr.RTL** are arXiv:2604.14989 Table 2 (Synopsys DC at clock period 0.1 ns).

Regenerate the table with:
```bash
python benchmarks/dr_rtl/scripts/dr_rtl_compare_table.py
```

`Δ*` columns are **ours vs paper-base**, using the paper's own sign convention
(negative = improvement, positive = regression). ADP uses a derived delay so
it's comparable across all three columns:

```
delay_ns  = paper_target_delay_ns − WNS_ns           # = 0.1 − WNS_ns
ADP       = delay_ns × area_um2                       # units: μm²·ns
ΔWNS      = (|ours_wns|  − |base_wns|)  / |base_wns|  × 100
ΔArea     = ( ours_area  −  base_area)  /  base_area  × 100
ΔADP      = ( ours_adp   −  base_adp )  /  base_adp   × 100
```

The same `(target_delay − WNS)` derivation is applied to **all three** columns
(ours / paper-base / paper-Dr.RTL), so the ~30 ps setup-time under-estimate
is a constant offset across each row and cancels in the ratio. This differs
slightly from `eval_nangate45_ppa.json:delay_ps` (which is the actual STA
arrival time including library setup) — same shape, ~30 ps shifted.

| Case | Module | WNS ours (ns) | WNS base (ns) | WNS Dr.RTL (ns) | ΔWNS | Area ours (μm²) | Area base | Area Dr.RTL | ΔArea | ADP ours (μm²·ns) | ADP base | ADP Dr.RTL | ΔADP |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `ticket`      | `ticket_machine`                  | -0.02 | -0.23 | -0.09 |   -91.3% |    55.6 |    78 |    45 |  -28.7% |     6.7 |    25.7 |     8.6 |   -74.1% |
| `controller`  | `control_unit`                    | -0.16 | -0.38 | -0.33 |   -57.9% |   253.2 |   235 |   277 |   +7.8% |    65.8 |   112.8 |   119.1 |   -41.6% |
| `lstm`        | `lstm_cell`                       | -4.28 | -6.51 | -4.86 |   -34.3% | 18034.3 | 14828 |  4753 |  +21.6% |  78,990 |  98,013 |  23,575 |   -19.4% |
| `cpu_fsm`     | `mini_cpu`                        | -0.40 | -0.82 | -0.61 |   -51.2% | 35302.7 | 32268 | 32157 |   +9.4% |  17,651 |  29,687 |  22,831 |   -40.5% |
| `dsp`         | `DSP`                             | -1.62 | -2.61 | -2.59 |   -37.9% |  5580.9 |  4755 |  4751 |  +17.4% |   9,599 |  12,886 |  12,780 |   -25.5% |
| `datapath`    | `datapath`                        | -1.14 | -0.88 | -0.87 |   +29.5% | 11845.0 | 12137 | 12137 |   -2.4% |  14,688 |  11,894 |  11,773 |   +23.5% |
| `vending`     | `vending_machine`                 | -7.12 | -0.27 | -0.09 | +2537.0% | 17824.4 | 20488 | 20533 |  -13.0% | 128,692 |   7,581 |   3,901 | +1597.7% |
| `uart`        | `uart_top_design`                 |   N/A | -0.38 | -0.34 |      N/A |     N/A |  1272 |  1107 |     N/A |     N/A |   610.6 |   487.1 |      N/A |
| `spi1`        | `simple_spi_top`                  | -0.31 | -0.32 | -0.29 |    -3.1% |  1184.2 |  1208 |  1276 |   -2.0% |   485.5 |   507.4 |   497.6 |    -4.3% |
| `spi2`        | `spi`                             |   N/A | -0.26 | -0.25 |      N/A |     N/A |  1748 |  1826 |     N/A |     N/A |   629.3 |   639.1 |      N/A |
| `communicate` | `sync_serial_communication_tx_rx` | -0.20 | -0.40 | -0.26 |   -50.0% |  2197.2 |  2092 |  2446 |   +5.0% |   659.1 |   1,046 |   880.6 |   -37.0% |
| `router`      | `router_top`                      | -0.36 | -0.53 | -0.46 |   -32.1% |  5444.2 |  5479 |  5575 |   -0.6% |   2,504 |   3,452 |   3,122 |   -27.4% |
| `pcie`        | `top`                             | -0.23 | -0.79 | -0.44 |   -70.9% |  1344.4 |  2156 |  1426 |  -37.6% |   443.6 |   1,919 |   770.0 |   -76.9% |
| `fifo`        | `fifo`                            |   N/A | -0.54 | -0.43 |      N/A |     N/A | 36061 | 36310 |     N/A |     N/A |  23,079 |  19,244 |      N/A |
| `aes`         | `key_expansion_128aes`            | -0.17 | -0.70 | -0.67 |   -75.7% | 32350.9 | 33755 | 33975 |   -4.2% |   8,735 |  27,004 |  26,161 |   -67.7% |
| `i2c`         | `i2c_master_top`                  | -0.33 | -0.36 | -0.35 |    -8.3% |  1334.0 |  1290 |  1275 |   +3.4% |   573.6 |   593.4 |   573.8 |    -3.3% |
| `cpu_pipe`    | `dcpu16_cpu`                      | -0.69 | -0.38 | -0.11 |   +81.6% |  6121.5 |  2622 |  2313 | +133.5% |   4,836 |   1,259 |   485.7 |  +284.2% |
| `tv80`        | `tv80_core`                       | -0.67 | -1.31 | -1.22 |   -48.9% |  6941.8 |  6044 |  6200 |  +14.9% |   5,345 |   8,522 |   8,184 |   -37.3% |
| `arm_cpu1`    | `arm9_compatiable_code`           | -3.21 | -5.24 | -5.19 |   -38.7% | 28571.1 | 22172 | 22257 |  +28.9% |  94,570 | 118,398 | 117,740 |   -20.1% |
| `arm_cpu2`    | `risclite_mx`                     | -0.95 | -1.01 | -0.92 |    -5.9% | 11871.3 | 10688 | 10995 |  +11.1% |  12,465 |  11,864 |  11,215 |    +5.1% |

**What this comparison is and isn't.** The cell library is identical
(NangateOpenCellLibrary at the typical corner) and the synthesis constraint
envelope is identical (0.1 ns). The synthesis engine is different — yosys + abc
vs Synopsys DC — so this is **not** a measurement of "Dr. RTL did N% better than
us". It's a measurement of "this is how the same constraints land under two
different synth engines on the same baseline RTL". A few interpretive notes:

- **ours beats paper-base on ADP for 13 of 17 measured designs** (ticket -74%,
  pcie -77%, aes -68%, controller -42%, cpu_fsm -41%, communicate -37%,
  tv80 -37%, router -27%, dsp -26%, arm_cpu1 -20%, lstm -19%, spi1 -4%,
  i2c -3%). yosys + abc at a tight 100 ps target maps aggressively.
- **ours regresses badly on the wide-arithmetic designs** — `vending` is the
  headline (+1598% ADP) because of 1024-bit adder restructuring; DC's
  carry-tree generation is far ahead of yosys's. `cpu_pipe` (+284% ADP),
  `datapath` (+23%), `arm_cpu2` (+5%) are similar shapes — yosys doesn't share
  submodule logic the way DC does.
- **Area mostly tracks within ±30%** — the library is the same, so cell counts
  end up close on most designs. The big outliers (`cpu_pipe` +133.5%,
  `arm_cpu1` +29%, `lstm` +21.6%) are again where yosys's structural sharing
  falls behind DC's.
- **Dr.RTL's own optimization** sits between paper-base and our numbers on
  most designs. On ADP, Dr.RTL beats paper-base on every design (the paper's
  whole claim), and our flow beats Dr.RTL on 12 of 17 — except on the
  wide-arithmetic designs where DC's superior synthesis dominates.

**Flow column** — every "ours" row above is generated by
`benchmarks/dr_rtl/scripts/dr_rtl_nangate45_ppa.py`. 16 designs run through stock
`tech_eval.get_ppa(..., technology="nangate45")`; `pcie` runs through a
fallback that re-runs yosys with `synth -flatten` + `clean -purge` +
`write_verilog -noattr -simple-lhs` and post-processes the netlist to drop
yosys-emitted `wire`/`reg` declarations that duplicate port decls and rewrite
remaining module-level `reg X;` as `wire X;` (OpenROAD's structural
`read_verilog` rejects both quirks). 3 designs (uart, spi2, fifo) don't
characterize at all — see below.

### Designs that don't characterize under this flow

- **`uart`, `spi2`** — both have `always @* if (re) read_data = data;` style
  register-mapped read paths with no `else` clause → yosys infers transparent
  latches (`$_DLATCH_*` cells). **Nangate45 has no transparent-latch cell**
  for `dfflibmap` to map them to, so the netlist retains an `always` block
  that OpenROAD's `read_verilog` (structural-only) rejects. A DC-based flow
  (what DR_RTL itself uses) does support latches and would characterize these
  cleanly. To make them work under this flow you'd need to either patch the
  source to add an `else` (turn the latch into a mux — changes behavior) or
  add a latch cell to the synthesis library.
- **`fifo`** — `output reg [31:0] dataOut` is driven by an
  `always @(posedge clk_out, negedge rst)` block whose reset branch loads
  from a memory array (`dataOut <= mem_uut.FIFO[0][0]`). Nangate45 DFFs
  reset/set to a constant (0 or 1) only; yosys can't decompose a
  memory-driven reset into Nangate cells, so the flop emits as a behavioral
  always block. Same OpenROAD parser limitation as above.

All three are **fully usable** with the `yosys_cells` / `yosys_wires` /
`transistors` metrics in the status table above — they only fail under
the nangate45 LEF+lib STA flow.

## Regenerating tb.sv + vectors.dat + metadata.json

```bash
python benchmarks/dr_rtl/scripts/dr_rtl_tb_gen.py --case <name>
python benchmarks/dr_rtl/scripts/dr_rtl_tb_gen.py --list           # show known cases
python benchmarks/dr_rtl/scripts/dr_rtl_tb_gen.py                  # regenerate everything
```

The generator fetches each baseline from `raw.githubusercontent.com` into
`context/starting_point.{v,sv}` (no-op if already present), then:

1. Builds a probe tb that drives 2000 LFSR-seeded random stimuli (plus corners
   for combinational designs) into the golden DUT and captures its outputs.
2. Writes `vectors.dat` from the captured stdout.
3. Emits a data-driven `tb.sv` that re-runs the same vectors against the
   student DUT and asserts each output matches.

Sequential designs hold reset for 3 cycles then deassert, matching the
`rtl_rewriter` generator's protocol. The `reset_active_low` field flips the
asserted/deasserted polarity.

## Verifying a benchmark by hand

```bash
mkdir -p /tmp/dr_rtl_<name>_smoke
cp benchmarks/dr_rtl/<name>/context/starting_point.v /tmp/dr_rtl_<name>_smoke/
python run_eval.py \
    /tmp/dr_rtl_<name>_smoke/starting_point.v \
    --benchmark benchmarks/dr_rtl/<name> \
    --language verilog --cost-metric yosys_cells
```

Expected: `Correctness: PASS, 2000/2000` (or 2002/2002 for combinational) with
finite `yosys_cells`.

## Running the agent on one design

```bash
python run_benchmark.py \
    --benchmark dr_rtl/<name> \
    --language verilog --cost-metric yosys_cells \
    --model claude:claude-opus-4-7 \
    --max-steps 20
```

A multi-run / two-phase pipeline parallel to
`experiments/rtl_rewriter_multirun.py` is not yet wired up for this benchmark
family — track that work in a follow-on plan.

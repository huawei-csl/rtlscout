# `turbo_rtl` — benchmark setup + agent campaign results

## Setup

### Cost metric — `sky130_adp`

Added in `core/cost.py` as `Sky130ADPCost`. Replicates `references/run_evaluation.py` (no CEC, no OpenROAD STA):

```
yosys: read_verilog -sv <files>; hierarchy -top <top>; proc; opt; techmap; opt;
       synth -flatten; async2sync; dffunmap; write_blif <blif>
yosys-abc: read_blif <blif>; read_lib <SKY130_LIB>;
           strash; dch -f; map; topo; upsize; dnsize; stime
```

Returned cost value is **Area × Delay_ps**, parsed from the final line of `stime`.

Library: `/prog/OpenROAD-flow-scripts/tools/OpenROAD/test/sky130hd/sky130_fd_sc_hd__ff_n40C_1v95.lib` (already present in the devcontainer). Override via the `SKY130_LIB_PATH` env var.

### Benchmark family

Seven benchmarks selected from `benchmarks/final_benchmark_samples.zip` — five combinational plus two sequential (register-based). Each exists in two parallel forms sharing the same `tb.sv` / `vectors.dat` / `metadata.json`:

- `benchmarks/turbo_rtl/<name>/` — Verilog, starting point is `context/starting_point.v` (golden from the zip, verbatim).
- `benchmarks/turbo_rtl_spirehdl/<name>/` — SpireHDL, starting point is `context/starting_point.py` (hand-translated from the golden, mirroring every `assign` as a `Wire(…)` and every `reg` as a `Register(…)`).

Testbenches were generated at benchmark-creation time by compiling the golden `.v` against a 32-bit-LFSR probe in verilator (seeds `0xDEADBEEF` and `0xCAFEBABE`, 2000 random cases), capturing the input/output pairs into `vectors.dat`, and writing a data-driven `tb.sv` that `$sscanf`s each line and checks `dut.<output> === expected_<output>`. For sequential benchmarks the probe toggles `clk`, holds reset for 3 cycles, then feeds a new input combination and samples outputs on every rising clock edge; the tb.sv mirrors the same protocol. Generator scripts: `/tmp/turbo_rtl_gen.py` (combinational) and `/tmp/turbo_rtl_seq_gen.py` (sequential) — not committed; see `benchmarks/turbo_rtl/README.md` for the full procedure.

| Benchmark | Source (`dataset/id/file`) | Module | Flavor | Ports |
|---|---|---|---|---|
| `encoder_8b10b` | `deepcircuitx/10105/10105_19.v` | `encoder` | combinational 8b/10b encoder | `in_8b[7:0]`, `dataK` → `out_10b[9:0]` |
| `gda_adder_n8m8p2` | `mgverilog/1113/1113_3.v` | `GDA_St_N8_M8_P2` | combinational approximate adder | `in1[7:0]`, `in2[7:0]` → `res[8:0]` |
| `bcd_to_bin_16b` | `deeprtl/35966/35966_7.v` | `conversor_num_16b` | combinational BCD→binary | `numeros[19:0]` → `operador[15:0]` |
| `const_mult_3853` | `deeprtl/20904/20904_3.v` | `multiplier_block` | combinational const-mult ×3853 | `i_data0[31:0]` → `o_data0[31:0]` |
| `rgb_diff_check` | `rtlcoder/8900/8900_8.v` | `DiffCheck` | combinational RGB555 predicate | `rgb1[14:0]`, `rgb2[14:0]` → `result` |
| `adder_4bit_reg` | `rtlcoder/9045/9045_11.v` | `adder_4bit` | **sequential** — clk-only registered adder | `clk`, `a[3:0]`, `b[3:0]`, `cin` → `sum[3:0]`, `cout` |
| `avg4_reg` | `rtlcoder/13396/13396_4.v` | `average_module` | **sequential** — clk + sync reset, running accumulator | `clk`, `reset`, `a..d[7:0]` → `average[7:0]` |

All 14 benchmarks (7 verilog + 7 spirehdl) were smoke-tested end-to-end with `run_eval.py` on their starting points under `--cost-metric sky130_adp`:

```bash
~/pyenv_eda/bin/python run_eval.py \
    benchmarks/turbo_rtl/<name>/context/starting_point.v \
    --benchmark benchmarks/turbo_rtl/<name> \
    --language verilog --cost-metric sky130_adp

~/pyenv_eda/bin/python run_eval.py \
    benchmarks/turbo_rtl_spirehdl/<name>/context/starting_point.py \
    --benchmark benchmarks/turbo_rtl_spirehdl/<name> \
    --language spirehdl --cost-metric sky130_adp
```

All 10 report `Correctness: PASS, 2002/2002 checks`.

### Starting-point vs. reference ADP

Reference numbers come from `final_benchmark_samples.json` (the paper's own yosys+abc flow against the same sky130 ff library). "Start (verilog)" and "Start (spirehdl)" are the `sky130_adp` values our metric reports on the **untouched** starting points — before any agent run.

| Benchmark | Ref raw ADP | Ref opt ADP | Start (verilog) | Start (spirehdl) |
|---|---:|---:|---:|---:|
| `encoder_8b10b`    |      88,273 |      76,348 |         52,769 |          52,769 |
| `gda_adder_n8m8p2` |     116,940 |     111,328 |         82,458 |          80,848 |
| `bcd_to_bin_16b`   |   5,135,190 |   4,438,411 |      3,288,027 |       3,359,772 |
| `const_mult_3853`  |  12,033,637 |  11,885,961 |      8,275,901 |       8,275,901 |
| `rgb_diff_check`   |   3,342,138 |   3,153,100 |      2,539,030 |       2,539,030 |
| `adder_4bit_reg` ⏱ |     149,829 |     145,752 |        122,398 |         122,398 |
| `avg4_reg` ⏱       |   3,788,288 |   3,374,988 |      2,490,928 |       2,375,033 |

⏱ = sequential (clocked).

**Note on SpireHDL starting points:** after the first round of runs we rewrote every `starting_point.py` to mirror the reference Verilog `assign`-for-`assign` — each intermediate `wire` from the golden becomes an explicit `m.wire(UInt(W), "name"); name <<= expr` in SpireHDL. This closes the width-inflation gap on `bcd_to_bin_16b` (4,283,419 → 3,359,772, a 22% drop that puts it within 2% of the verilog starting point). The other four benchmarks synthesize to the same netlist as their verilog siblings either way — yosys/abc collapses the redundant aliases — so their numbers didn't change, but the spirehdl source now tracks the golden one-for-one. See `benchmarks/turbo_rtl/README.md` §"Write a SpireHDL starting point that mirrors the verilog `assign` structure" for the convention.

**Observation:** our yosys+abc `dch -f; map; topo; upsize; dnsize` flow already produces lower ADP than the paper's `ppa_opt` on every benchmark, before an agent has touched anything. The agent campaigns below should refine these numbers further.

### Sanity check — is the metric doing the same thing as `references/run_evaluation.py`?

Yes, bit-for-bit. A side-by-side run of the **exact** reference script (same yosys script text piped via `echo … | yosys`, same `yosys-abc -c "…"` invocation, same library path) against `Sky130ADPCost.evaluate()` on the same starting-point files produces identical area, delay, and ADP on every benchmark (checked via `/tmp/ref_flow_compare.py`):

| Benchmark | Ref area | Ref delay (ps) | Ref ADP | Our area | Our delay (ps) | Our ADP | Match |
|---|---:|---:|---:|---:|---:|---:|:---:|
| `encoder_8b10b`    |   230.22 |   229.21 |      52,768.73 |   230.22 |   229.21 |      52,768.73 | ✅ |
| `gda_adder_n8m8p2` |   380.36 |   216.79 |      82,458.24 |   380.36 |   216.79 |      82,458.24 | ✅ |
| `bcd_to_bin_16b`   | 2,368.52 | 1,388.22 |   3,288,026.83 | 2,368.52 | 1,388.22 |   3,288,026.83 | ✅ |
| `const_mult_3853`  | 4,910.96 | 1,685.19 |   8,275,900.68 | 4,910.96 | 1,685.19 |   8,275,900.68 | ✅ |
| `rgb_diff_check`   | 2,184.60 | 1,162.24 |   2,539,029.50 | 2,184.60 | 1,162.24 |   2,539,029.50 | ✅ |

So the metric is correct. The gap between our numbers and the paper's `ppa_raw` / `ppa_opt` in `final_benchmark_samples.json` (e.g. encoder ref_raw_adp ≈ 88,273 vs. our 52,769 on the same raw file) is **not** a metric bug. Plausible causes:

- **Different yosys / abc version.** We're on `Yosys 0.55 (git sha1 60f126cd0)` in this devcontainer. The paper's numbers presumably come from an older toolchain; `synth -flatten` + `dch -f; map` output is quite version-sensitive. For the encoder, area is within ~3% (222.71 vs 230.22) but the paper's delay is ~73% higher (396.36 ps vs 229.21 ps) — consistent with abc's mapping/sizing heuristics having changed.
- **Same flow text, different environment.** Liberty file mtime/contents, locale, `ABC_DATA` / resource-limits may also perturb sizing decisions marginally.

Minor differences between `core/cost.py:Sky130ADPCost` and `references/run_evaluation.py`, none of which change the numbers (verified by the match table above):

- We call yosys as `yosys -q <script_file>` instead of `echo … | yosys`. Same script text, same effect.
- We pass the abc script via `yosys-abc -f <script_file>` instead of `-c "<script>"`. Same commands.
- We prepend `design -reset` and use `hierarchy -top <top_module>` (the reference uses plain `hierarchy;`). On single-module designs these are equivalent; the explicit `-top` is more robust on multi-module inputs.
- We use `read_verilog -sv` vs. the reference's plain `read_verilog`. Irrelevant on these pure Verilog-2001 golden files.
- We strip ANSI escape codes before regex-matching the Area/Delay line. The reference doesn't, because it pipes through `shell=True` and the escapes don't interfere with the regex it uses.

## Agent campaign settings

Two rounds were run, both with `--cost-metric sky130_adp` and one campaign per (benchmark × language). The numbers from both rounds are kept side-by-side in the results table so they can be compared directly.

| Round | Model | Steps | Benchmarks | Runs dir |
|---|---|---:|---|---|
| Round 1 | `claude:claude-sonnet-4-5` | 20 | 5 combinational | `runs/turbo_rtl_sky130_adp/` |
| Round 2 | `claude:claude-opus-4-6`   | 30 | 5 combinational + 2 sequential | `runs/turbo_rtl_30/` |

Round-2 sweep (the current canonical one) was launched as a smoke run on `adder_4bit_reg` verilog (foreground), then two parallel waves: 6 verilog campaigns, then 7 spirehdl campaigns. Each wave ran fully concurrently — `Sky130ADPCost` is concurrency-safe (each call uses its own `tempfile.mkdtemp`, verified with a 4-thread test).

```bash
# Round 2: smoke run (foreground)
~/pyenv_eda/bin/python run_benchmark.py \
    --benchmark turbo_rtl/adder_4bit_reg \
    --model claude:claude-opus-4-6 \
    --max-steps 30 --cost-metric sky130_adp --language verilog \
    --runs-dir runs/turbo_rtl_30

# Round 2: full sweep (per-language wave; each line backgrounded)
for b in encoder_8b10b gda_adder_n8m8p2 bcd_to_bin_16b const_mult_3853 \
         rgb_diff_check avg4_reg; do
  ~/pyenv_eda/bin/python run_benchmark.py \
      --benchmark turbo_rtl/$b \
      --model claude:claude-opus-4-6 --max-steps 30 \
      --cost-metric sky130_adp --language verilog \
      --runs-dir runs/turbo_rtl_30 &
done; wait
for b in encoder_8b10b gda_adder_n8m8p2 bcd_to_bin_16b const_mult_3853 \
         rgb_diff_check adder_4bit_reg avg4_reg; do
  ~/pyenv_eda/bin/python run_benchmark.py \
      --benchmark turbo_rtl_spirehdl/$b \
      --model claude:claude-opus-4-6 --max-steps 30 \
      --cost-metric sky130_adp --language spirehdl \
      --runs-dir runs/turbo_rtl_30 &
done; wait
```

## Final results — both rounds

All campaigns completed. **Best ADP** is the lowest `sky130_adp` across all fully-correct (2000-2002/2002) evaluations the agent produced within its step budget. Round-1 covered 5 combinational benchmarks × 2 languages = 10 runs. Round-2 added the 2 sequential benchmarks, used Opus 4.6 with a bigger 30-step budget, and re-ran the 5 combinational benchmarks for comparison = 14 runs.

| Benchmark | Ref opt ADP | R1 V (Son-20) | R1 S (Son-20) | R2 V (Opus-30) | R2 S (Opus-30) | Best-of-all | vs ref |
|---|---:|---:|---:|---:|---:|---:|---:|
| `encoder_8b10b`    |     76,348 |     50,265 |     49,689 |     48,616 |     52,399 |     **48,616** | 0.637 |
| `gda_adder_n8m8p2` |    111,328 |     65,356 |     73,267 |     67,858 |     67,858 |     **65,356** | 0.587 |
| `bcd_to_bin_16b`   |  4,438,411 |  2,779,155 |  3,268,515 |  2,718,510 |  3,159,272 |  **2,718,510** | 0.613 |
| `const_mult_3853`  | 11,885,961 |  8,275,901 |  8,275,901 |  8,185,036 |  8,185,036 |  **8,185,036** | 0.689 |
| `rgb_diff_check`   |  3,153,100 |  2,464,238 |  2,539,030 |  2,539,030 |  2,284,574 |  **2,284,574** | 0.725 |
| `adder_4bit_reg` ⏱ |    145,752 |         — |         — |     47,630 |     53,427 |     **47,630** | 0.327 |
| `avg4_reg` ⏱       |  3,374,988 |         — |         — |  2,143,114 |  2,270,125 |  **2,143,114** | 0.635 |

⏱ = sequential (clocked). R1 / R2 = round-1 Sonnet-20 / round-2 Opus-30. "Best-of-all" is the minimum across both rounds and both languages. "vs ref" is `best / ref_opt_adp` (below 1.0 = we beat the paper).

**Acceptance criterion — met.** All 7 benchmarks beat the paper's `ppa_opt.adp` in at least one language. Best-of-all ratios span 0.327 (the `adder_4bit_reg` sequential CLA rewrite — a 67% ADP reduction vs. ref) to 0.725 (rgb_diff_check).

### Round-2 (Opus 30-step) vs round-1 (Sonnet 20-step): net changes

Where Opus+30 beat Sonnet+20 — and where it didn't:

| Benchmark | Sonnet V | Opus V | ΔV | Sonnet S | Opus S | ΔS |
|---|---:|---:|---:|---:|---:|---:|
| `encoder_8b10b`    |   50,265 |    48,616 | **−3.3%** |    49,689 |    52,399 | **+5.5%** 🔻 |
| `gda_adder_n8m8p2` |   65,356 |    67,858 | **+3.8%** 🔻 |    73,267 |    67,858 | **−7.4%** |
| `bcd_to_bin_16b`   | 2,779,155 | 2,718,510 | **−2.2%** | 3,268,515 | 3,159,272 | **−3.3%** |
| `const_mult_3853`  | 8,275,901 | 8,185,036 | **−1.1%** | 8,275,901 | 8,185,036 | **−1.1%** |
| `rgb_diff_check`   | 2,464,238 | 2,539,030 | **+3.0%** 🔻 | 2,539,030 | 2,284,574 | **−10.1%** |

Opus-30 is not uniformly better than Sonnet-20. It regressed on three of ten cells in the comparison (🔻):

- **`rgb_diff_check` verilog** — Opus stopped at the starting-point ADP (2,539,030) and never found the bit-pattern rewrite (`y[7:5] == 3'b000` etc.) that Sonnet stumbled into last round. It tried more sophisticated reformulations, all of which either broke correctness or didn't help.
- **`encoder_8b10b` spirehdl** — Opus went backwards from Sonnet's 49,689 to 52,399. The Round-1 Sonnet run had narrowly beaten verilog (49,689 < 50,265); Opus spirehdl lost that advantage. Likely a local-optima choice in the search.
- **`gda_adder_n8m8p2` verilog** — Sonnet found 65,356, Opus only 67,858. Same design space, Opus just picked a slightly worse variant.

But the wins are bigger than the losses — notably **`rgb_diff_check` spirehdl**: Opus dropped it from 2,539,030 (starting point) to 2,284,574, a 10.1% improvement, and it **beat the verilog winner** from either round (2,464,238). This is the first benchmark where spirehdl wins outright.

The two sequential benchmarks are only in round 2 (they didn't exist in round 1). Both the verilog and spirehdl variants produce real gains. `adder_4bit_reg` is the headline result: Opus worked through baseline → behavioral `+` → structural ripple → carry-select → **full CLA with flat sum-of-products carries**, driving ADP from 122,398 down to 47,630 — a **61% reduction** vs. its own starting point, and **0.327×** the paper's `ppa_opt.adp`.

### Agent gains relative to our own starting point (round 2, Opus 30-step)

Our `sky130_adp` flow already beats the paper's numbers cold (see "Starting-point vs. reference ADP" above), so the more honest measure of what the agent itself added is the delta vs. the untouched starting point. These are round-2 only.

| Benchmark | Start V | Best V | V gain | Start S | Best S | S gain |
|---|---:|---:|---:|---:|---:|---:|
| `encoder_8b10b`    |     52,769 |     48,616 |  7.9% |     52,769 |     52,399 |  0.7% |
| `gda_adder_n8m8p2` |     82,458 |     67,858 | 17.7% |     80,848 |     67,858 | 16.1% |
| `bcd_to_bin_16b`   |  3,288,027 |  2,718,510 | 17.3% |  3,359,772 |  3,159,272 |  6.0% |
| `const_mult_3853`  |  8,275,901 |  8,185,036 |  1.1% |  8,275,901 |  8,185,036 |  1.1% |
| `rgb_diff_check`   |  2,539,030 |  2,539,030 |  0.0% |  2,539,030 |  2,284,574 | 10.1% |
| `adder_4bit_reg`   |    122,398 |     47,630 | 61.1% |    122,398 |     53,427 | 56.3% |
| `avg4_reg`         |  2,490,928 |  2,143,114 | 14.0% |  2,375,033 |  2,270,125 |  4.4% |

The agent found real improvements on 6 of 7 verilog benchmarks (rgb_diff_check is the lone hold-out — stuck at 0.0%) and all 7 spirehdl benchmarks. The two sequential benchmarks have the biggest agent gains — `adder_4bit_reg` clears 60% in both languages just by rewriting a 4-bit adder to explicit CLA.

### Per-campaign wall time + token budget

Round-2 campaign wall times ranged 186–406 s (3–7 min), averaging ~340 s. Token spend per 30-step Opus campaign is around 355k input (mostly cache reads) + 8–9k output. Total for all 14 round-2 campaigns: roughly 5M input + 120k output tokens.

All round-2 best designs live under `runs/turbo_rtl_30/<benchmark>/claude-opus-4-6/<timestamp>/best_design/`; round-1 best designs live under `runs/turbo_rtl_sky130_adp/<benchmark>/claude-sonnet-4-5/<timestamp>/best_design/`. Each `best_design/` directory carries a `_best_meta.json` recording which file achieved the best cost.

## Round 3 — area-only and delay-only metrics (encoder_8b10b, gda_adder_n8m8p2)

To check whether the language gap that shows up under `sky130_adp` is specific to that flow or also present under area-only and delay-only optimization targets, we ran a focused round on the two simpler combinational benchmarks (encoder_8b10b and gda_adder_n8m8p2) with `--cost-metric area` and `--cost-metric delay` — both metrics use the **OpenROAD STA flow against ASAP7** via `tech_eval`, completely separate from the `yosys-abc stime` flow that powers `sky130_adp`. Same agent settings as round 2 (Opus 4.6, 30 steps), 8 campaigns total (2 benchmarks × 2 metrics × 2 languages), all in parallel under `runs/turbo_rtl_30_pp/`.

```bash
for bench in encoder_8b10b gda_adder_n8m8p2; do
  for metric in area delay; do
    for lang_pair in "verilog turbo_rtl" "spirehdl turbo_rtl_spirehdl"; do
      lang=$(echo $lang_pair | cut -d' ' -f1); root=$(echo $lang_pair | cut -d' ' -f2)
      ~/pyenv_eda/bin/python run_benchmark.py \
          --benchmark $root/$bench \
          --model claude:claude-opus-4-6 --max-steps 30 \
          --cost-metric $metric --language $lang \
          --runs-dir runs/turbo_rtl_30_pp &
    done
  done
done; wait
```

### Results

**Original (integer-rounded) numbers — as the agent saw them during the campaigns:**

| Benchmark | Start area | Start delay (ps) | V best `area` | S best `area` | V best `delay` | S best `delay` |
|---|---:|---:|---:|---:|---:|---:|
| `encoder_8b10b`    | 3.0 | 84.89 |   2.0 |   2.0 | 83.45 | **83.15** |
| `gda_adder_n8m8p2` | 4.0 | 89.15 |   4.0 |   4.0 | 89.15 | 89.15 |

> **Caveat — area numbers were being rounded to integers by OpenROAD.** We later discovered that OpenROAD's `report_design_area` Tcl proc formats the area with `%.0f` (see `/prog/OpenROAD-flow-scripts/tools/OpenROAD/src/rsz/src/Resizer.tcl:396`), so every `area` value at the metric's granularity was quantized to whole µm². For these small benchmarks that was catastrophic resolution loss — agent improvements of ~0.1 µm² were invisible, and a genuine 10% improvement could look identical to "tie at 2.0". We patched the tech_eval STA template to additionally emit `rsz::design_area` (a Tcl double in square meters → µm² with full precision) and the parser to prefer that value, then **re-evaluated the saved best designs from all 8 round-3 campaigns against the precise metric** (without rerunning the agent). The table below has the real numbers.

**Re-evaluated numbers with precise `design_area_precise` (same designs, higher-resolution readout):**

| Benchmark | Lang | Start area | Best area (`area` campaign) | Best area (`delay` campaign) | Start delay (ps) | Best delay (ps) |
|---|---|---:|---:|---:|---:|---:|
| `encoder_8b10b`    | V |   2.756 | **2.420** (−12.2%) | 2.537 (−7.9%) | 84.89 | **83.45** (−1.7%) |
| `encoder_8b10b`    | S |   2.668 | **2.493** (−6.6%) | 2.858 (+7.1%)  | 84.89 | **83.15** (−2.1%) |
| `gda_adder_n8m8p2` | V |   3.732 | 3.732  (**0.0%**) | 3.732 (0.0%)   | 89.15 | 89.15 (0.0%) |
| `gda_adder_n8m8p2` | S |   3.747 | 3.747  (**0.0%**) | 3.747 (0.0%)   | 89.15 | 89.15 (0.0%) |

**Verilog vs SpireHDL, using precise area:**

| Benchmark / metric | V best | S best | V vs S |
|---|---:|---:|:---|
| `encoder_8b10b` area  | **2.420** | 2.493 | verilog wins by 3.0% |
| `encoder_8b10b` delay | 83.45 ps | **83.15 ps** | spirehdl wins by 0.4% |
| `gda_adder_n8m8p2` area  | **3.732** | 3.747 | verilog wins by 0.4% (starting-point gap, no agent progress) |
| `gda_adder_n8m8p2` delay | 89.15 ps | 89.15 ps | tie |

### What this tells us

**Headline (corrected after the precise-area fix): under `area` and `delay` (the OpenROAD-STA / ASAP7 flow), the verilog vs spirehdl gap that we saw under `sky130_adp` is dramatically smaller — a few percent instead of 8-16 percent — but does not fully disappear.** On encoder_8b10b verilog actually wins area (2.420 vs 2.493, +3%) and spirehdl wins delay (83.15 vs 83.45, +0.4%). On gda_adder_n8m8p2 **neither agent moved off the starting point** under either metric in either language (confirmed with precise area: 3.732 for verilog, 3.747 for spirehdl, no change from start) — the ASAP7 library genuinely floors at this area for an 8-bit approximate adder, this is not a rounding artefact.

The integer-metric version of this section previously claimed "33% area improvement, tie between languages". Both numbers were rounding artefacts:
- The real encoder area gain is **12.2% (verilog) / 6.6% (spirehdl)**, not 33%.
- Neither language ties under precise area — verilog outperforms on area, spirehdl on delay. Both gaps are small (3% / 0.4%).
- SpireHDL's starting point was actually **better than verilog's** on encoder (2.668 vs 2.756) — a fact hidden by integer rounding. The verilog agent then made a bigger optimization (12.2% vs 6.6%), ending at a lower final number.

**Side observation — area/delay trade-off on spirehdl encoder:** the spirehdl `delay` campaign got to 83.15 ps (the best delay of any run), but it **spent area** to do so: area climbed from the 2.668 starting point to 2.858 (+7.1%). This is an honest A/D trade-off that the agent made while single-mindedly optimizing delay, and it's only visible because the precise area metric shows the regression. The verilog `delay` campaign was tamer — 84.89 → 83.45 ps with area going 2.756 → 2.537 (area actually shrank as a side-effect).

This is consistent with the round-2 root-cause analysis above. The three spirehdl emission overheads I documented (BLIF buffer tax on registered outputs, `_maybe_share` over-sharing, output-truncation slice node) all hurt the **`yosys-abc stime` flow** — which is a fast structural mapping pass that does *local* rewriting within named-wire boundaries. The OpenROAD STA path (`abc -D <delay> -constr ...` then `read_verilog` of the abc-mapped netlist into OpenROAD `sta`) does its synthesis at a different stage with different aggressiveness, and evidently DOES collapse those alias chains and slice nodes during its mapping. The result is that the same SpireHDL code that paid a tax under `sky130_adp` now produces an indistinguishable final netlist from the verilog version.

A few specific notes (using precise area):

- **encoder_8b10b area — real gains are 12.2% (V) and 6.6% (S), not 33%.** The "3.0 → 2.0 in both languages" numbers were integer-rounding artefacts. Under precise area, both verilog and spirehdl found bit-level reformulations of the L03/L30/L12/L21 helper terms, but verilog dropped further (2.756 → 2.420) than spirehdl (2.668 → 2.493). The two best designs are at `runs/turbo_rtl_30_pp/encoder_8b10b/claude-opus-4-6/20260414_161930/best_design/design_v10.sv` and `…20260414_161933/best_design/design_v5.py` respectively.
- **encoder_8b10b delay: very small headroom, small spirehdl win with an area cost.** Both languages squeezed ~1–2 ps out of the 84.89 ps starting critical path, bottoming out at 83.45 (V) / 83.15 (S). The critical path through the encoder's nested AND/OR fabric is just naturally short in ASAP7. The spirehdl delay winner, however, **paid for its 0.4% delay advantage with a 7.1% area regression** — a real A/D trade-off that the precise metric exposes.
- **gda_adder_n8m8p2 both metrics, both languages: truly stuck at starting point (confirmed with precise area).** The 8-bit approximate adder really does hit a floor around 3.73 µm² / 89 ps in ASAP7 regardless of how the agent rephrases the carry-prediction. None of the 4 campaigns moved off their respective starting numbers — every variant the agent tried mapped to the same ~3.73 µm², 89 ps result. The verilog starting point is microscopically better than spirehdl's (3.7325 vs 3.7471 — 0.4% gap, under the rounding floor in the original results), but neither agent closed the gap. This is a genuine library/algorithm ceiling, not a rounding artefact.

### Why does the language gap close under `area`/`delay`?

The `sky130_adp` flow is `yosys synth → write_blif → yosys-abc strash; dch -f; map; topo; upsize; dnsize; stime`. It maps the **input BLIF as given**, doing local rewrites within the AIG nodes. SpireHDL's emit pollutes the AIG with explicit alias buffer nodes (Cause 1 above), named cut-wires from `_maybe_share` (Cause 2), and explicit slice-truncation nodes (Cause 3) — all of which `dch -f` respects as boundaries.

The `area` / `delay` flow goes through `tech_eval`'s OpenROAD pipeline:

```
yosys: read; synth -top; abc -D <target_delay> -constr <…> -liberty <asap7_lib>; write
OpenROAD STA: read_lef; read_lib; read_verilog <netlist>; link_design; create_clock; …; report
```

The key call here is `abc -D <delay> -constr <constr> -liberty <…>` *inside yosys*, which runs abc's full delay-driven mapping flow against the standard cell library — including aggressive constant propagation, buffer collapsing, and structural rewriting. After that yosys writes a clean post-mapped Verilog netlist that OpenROAD STA reads back; OpenROAD then does its own opt passes before reporting area and delay. Most of the structural barriers SpireHDL introduces evidently get folded away by abc's delay-driven mapping inside yosys — they don't survive into the OpenROAD-side netlist.

**Practical takeaway:** if you care about cross-language fairness under our agent harness, the `area` / `delay` metrics give a more honest comparison than `sky130_adp`. The `sky130_adp` flow is faster and library-flexible, but its lack of don't-care propagation and structural-cut sensitivity penalises spirehdl's emission patterns specifically. Until the three library fixes proposed in the round-2 analysis are made, `sky130_adp` understates spirehdl's true synthesis quality.

## Why is SpireHDL worse? — Round 1 analysis (Sonnet 20-step, OUTDATED)

> **Note (kept for the record).** This section reflects the round-1 Sonnet 20-step results. Two of the three causes it identifies (width inflation in `bcd_to_bin_16b`; redundant aliased wires from `_maybe_share`) are still real but were partially addressed by rewriting the SpireHDL starting points to mirror the verilog `assign`-for-`assign` (and by the round-2 retry with explicit `Wire(...)` cut-points). The third cause (agent strategy miss on `rgb_diff_check`) flipped sign in round 2 — Opus spirehdl found a bit-level rewrite that verilog missed, so spirehdl now WINS that benchmark. **For the current (round 2) analysis, see "Why is SpireHDL still worse — Round 2 analysis (Opus 30-step)" further down.**

SpireHDL ties on `const_mult_3853`, narrowly beats verilog on `encoder_8b10b` (49.7k vs 50.3k), and loses on the other three: `gda_adder` (+12%), `bcd_to_bin` (+17.6%), `rgb_diff_check` (+3%). Cross-reading the chat logs and the final `design_*.py` / `design_*.sv` files in `runs/turbo_rtl_sky130_adp/`, three independent root causes emerged:

### 1. SpireHDL's automatic width growth hurts arithmetic trees (bcd_to_bin)

The SpireHDL starting point already evaluates at **4,283,419** ADP while the verilog one is **3,288,027** — a 30% gap **before** the agent does anything. Looking at the emitted Verilog from the spirehdl version's best design (`design_tree2.py`):

```verilog
wire [19:0] sig_1;
wire [12:0] low_triple_1;
wire [7:0]  low_triple;
wire [13:0] high_pair;
assign sig_1 = (((numeros[19:16] * 14'd10000) + high_pair) + low_triple_1);
assign operador = sig_1[15:0];
```

SpireHDL's `d4 * 10000` widens `UInt(4) * UInt(14) → UInt(18)`, each subsequent `+` widens by one, and the final `operador <<= ...` truncates from 20 bits down to 16. The 16 bits of "headroom" create extra carry logic that yosys then has to prune.

The best verilog design does the opposite — **it forces every intermediate to 16 bits up front**:

```verilog
wire [15:0] v4, v3, v2, v1, v0;
assign v4 = 16'd10000 * {12'b0, numeros[19:16]};
assign v3 = 16'd1000  * {12'b0, numeros[15:12]};
...
assign operador = s024 + s13;
```

The agent's SpireHDL system prompt actually warns about width inference — but only in the context of `cat()` packing, not arithmetic trees. Sonnet read the warning, tried Horner's method and shift-and-add as algorithmic refactors, and never thought to wrap each intermediate with an explicit `m.wire(UInt(16), "v4"); v4 <<= (...)` to create a 16-bit cut-point.

**"But doesn't yosys optimize out the extra MSBs?"** No — verified empirically with two minimal SpireHDL designs (see `/tmp/width_test/`):

| Variant | Area | Delay (ps) | ADP |
|---|---:|---:|---:|
| SpireHDL wide — current starting point (natural width growth) | 3,035.41 | 1,411.15 | **4,283,419** |
| SpireHDL narrow — explicit `m.wire(UInt(16))` at every stage     | 2,325.98 | 1,212.13 | **2,819,390** |

Same logical function, same test vectors, same `Sky130ADPCost` flow. The one-line-per-wire fix drops ADP by **34%**, beats the spirehdl agent's 20-step best (3,268,515) by 14%, and lands within 1.4% of the verilog agent's best (2,779,155) **with zero agent iteration**.

So yosys's `opt` / `opt_clean` / `opt_expr` passes and abc's `dch -f; map` do **not** back-propagate the `operador <<= sum[15:0]` truncation as don't-cares. They do local structural rewriting on the AIG/netlist as-given; nothing in the standard flow runs a backward don't-care sweep from the primary outputs. The extra MSB carry-chain logic survives all the way through technology mapping and shows up in the final area and delay numbers.

This means:
- The "agent should have tried explicit width cut-points" point isn't just theoretical — it would have worked.
- SpireHDL's default behavior (let arithmetic widths grow, truncate at output) is a real footgun for area-optimized synthesis, not just an aesthetic issue. A library-side fix would be for `m.output(...) <<= expr` to insert an implicit truncation wire at the output width when the expression is wider. That would close the gap without any user change.

### 2. SpireHDL's `_maybe_share` inflates the preliminary netlist (gda_adder)

Both best designs encode the *same* 8-bit approximate-adder CLA algorithm. Logically identical. But the emitted Verilog from the SpireHDL version reveals an artifact:

```verilog
assign sig_15 = in2[5];   // g5 uses it
assign sig_16 = in2[5];   // cp5 uses it again
assign sig_14 = in2[5];   // s5 uses it again
```

`_maybe_share` in `spirehdl/spirehdl.py:65` creates a **fresh wire** every time a sub-expression gets referenced for the second time in a row — so `in2[5]`, `in2[6]`, `in2[7]` each end up as three distinct named wires. Functionally a no-op (yosys collapses them in `opt`), but the starting netlist has ~50 extra aliases that `dch -f; map` has to navigate. On this benchmark it lands in a slightly worse local optimum (area 312 → 335, delay 209 → 219).

Also, the verilog best expresses the XOR sum bit as `(cp[0] + in1[2] + in2[2]) & 1'b1` (a 3-operand add that yosys reduces to a full-adder sum bit). The SpireHDL best uses the literal `in1[2] ^ in2[2] ^ cp1` — logically identical but yosys's front-end handles it via a different rewrite path and produces slightly more gates.

### 3. Agent strategy diverges across languages (rgb_diff_check)

The verilog agent found a specific trick: rewrite the range predicates `y < 0x18 || y >= 0xE8` as **bit-pattern matches on the top bits**:

```verilog
wire y_inside = (y[7:5] == 3'b000 && y[4:0] < 5'd24)
             || (y[7:5] == 3'b111 && y[4:0] >= 5'd8);
```

The 8-bit comparator shrinks to a 3-bit equality plus a 5-bit comparator — cheaper cells. Applied to `u_inside` and `v_inside` too. Net gain: 2,539,030 → 2,464,238 (3%).

The SpireHDL agent never explored this rewrite. It stopped after 1 eval at the starting-point cost and spent the rest of its steps on approaches that all either broke correctness or didn't improve. Not a SpireHDL limitation — the same trick translates trivially (`(y[5:8] == 0) & (y[0:5] < 24) | ...`) — just a strategy miss in that particular run.

### Synthesis

It's **not** that SpireHDL generates intrinsically worse RTL. The three losing campaigns each have a different fixable problem:

1. **(bcd)** Explicit width-cutpoints in SpireHDL: `m.wire(UInt(16), "v4"); v4 <<= expr` at every arithmetic step. The system prompt mentions this trick but ties it to `cat()`-packing; the agent didn't generalize.
2. **(gda)** `_maybe_share` creates redundant aliased wires. Low-level library issue — harmless in the abstract but occasionally knocks synth into a worse local optimum. Could be fixed by sharing by expression *value* instead of *reference count*, or by tightening the aliasing in `_create_new_shared_wire`.
3. **(rgb)** Agent strategy difference. A longer step budget (or an elite-pool seeded run via `run_multistage.py`) would very likely find the bit-pattern rewrite in SpireHDL too.

Notably, **SpireHDL already beat the paper's `ppa_opt` on all 5 benchmarks** — it's just losing a rematch vs. its own verilog sibling in 3 of them. A second-stage `run_multistage.py` campaign with `--flowy-optimize` / `--abc-optimize` would probably close the gap further; the current results are from single-run `run_benchmark.py` with no synthesis decorators.

## Why is SpireHDL still worse — Round 2 analysis (Opus 30-step)

> **Correction (added later).** This section originally claimed three spirehdl-side root causes. After deeper testing, **Cause 1 (the "registered output buffer tax") was actually a `Sky130ADPCost` script bug, not a spirehdl issue** — yosys's default `opt_clean` deliberately preserves named (public) wires for debuggability, and the `Sky130ADPCost` yosys script never invoked `clean -purge` to drop alias buffers. Adding `clean -purge` to the script (committed in `core/cost.py`) makes the alias-buffer chain vanish and brings `adder_4bit_reg` spirehdl from 53,427 → 47,217 ADP — a 11.6% win that puts it narrowly *ahead* of the verilog winner (47,630). **Causes 2 and 3 (named-wire explosion + output-truncation slice) are confirmed spirehdl emission issues** and survive the purge — re-evaluating the encoder and bcd_to_bin spirehdl bests under the patched metric gives byte-identical numbers. The original three-cause analysis is preserved verbatim below for the record; the "Correction summary" subsection at the very end of this section reconciles everything against the post-patch reality.

In round 2 SpireHDL loses on **4 of 7** benchmarks (encoder_8b10b +7.8%, bcd_to_bin_16b +16.2%, adder_4bit_reg +12.2%, avg4_reg +5.9%), ties on **2** (gda_adder_n8m8p2, const_mult_3853), and **wins outright on 1** (rgb_diff_check, −10.0%). I dug into the chat logs, the per-step `design_*.{py,sv}` files in `runs/turbo_rtl_30/`, and ran controlled empirical experiments to nail down the root causes. **Three concrete spirehdl mechanisms explain the regressions** — all are library-level, none are agent-strategy issues. (See the correction note above and the "Correction summary" at the end of this section.)

### Cause 1 — registered outputs pay a "BLIF buffer tax" (adder_4bit_reg, avg4_reg)

`adder_4bit_reg` is the cleanest demonstration: round-2 verilog 47,630 vs spirehdl 53,427, a 12% gap with **identical algorithmic content** (both designs implement the same CLA carry-lookahead with the same gate count post-yosys synth). I verified this by writing a spirehdl mirror of the verilog winner literally line-for-line — same `Wire(...)` declarations, same expressions — and it still came in at 53,427.

The difference is in the emitted Verilog's **register output style**:

| Verilog winner | SpireHDL emit |
|---|---|
| `output reg [3:0] sum` | `output [3:0] sum; reg [3:0] sum_reg; assign sum = sum_reg;` |
| `always @(posedge clk) sum[0] <= …` | `always @(posedge clk) sum_reg <= …; assign sum = sum_reg;` |

These should be semantically identical. They aren't — the indirect form pays a tax. Empirical proof:

```
yosys post-synth cell counts (both forms): 36 cells, identical mix
                                           (10 ANDNOT, 4 AND, 5 DFF_P, 1 ORNOT, 5 OR, 5 XNOR, 3 XOR)

After yosys-abc dch -f; map; stime against sky130_fd_sc_hd__ff_n40C_1v95.lib:
  Verilog `output reg`:                    27 gates, area 143.89, delay 331.02 ps → ADP 47,631
  SpireHDL-style `reg foo; assign sum=foo`: 39 gates, area 197.69, delay 344.53 ps → ADP 68,113
  ────────────────────────────────────────────────────────────────────────
  Penalty:                                 +12 gates, +37% area, +12% ADP
```

Diffing the two BLIFs that yosys feeds into abc reveals the source: the `reg foo; assign output = foo;` pattern emits **one explicit `.names` buffer node per output bit**:

```
.names sum_reg[0] sum[0]
1 1
.names sum_reg[1] sum[1]
1 1
.names sum_reg[2] sum[2]
1 1
.names sum_reg[3] sum[3]
1 1
.names cout_reg cout
1 1
```

These are 1-input "buffer" subgraphs — semantically a wire copy, but to abc's `dch -f; map` they look like dataflow nodes. abc maps them to physical buffer/inverter cells (and the `upsize`/`dnsize` passes amplify the cost as the design grows). The `output reg` form avoids the buffer nodes entirely because the latch's primary output IS the module port.

**Why spirehdl can't avoid this:** `Module.output(typ, name)` always creates a `Signal` with `kind="output"` (i.e. a wire), and the only way to drive an output is `output_signal <<= source`. There is no `Module.output_register(...)` constructor and no path for `Register` to become a port. So every benchmark with a registered output (`adder_4bit_reg`, `avg4_reg`) eats the buffer tax. Both round-2 sequential losses are this.

**Possible library fix:** in `Module.to_verilog_lines`, detect when an output's driver chain terminates in exactly one Register and emit the output as `output reg` with the always-block driving it directly. That would close 12% on registered-output benchmarks for free, no user-script change needed.

### Cause 2 — `_maybe_share` over-shares with `force_share=True` (encoder_8b10b, gda_adder_n8m8p2)

Spirehdl's expression cache (`_maybe_share` in `spirehdl.py:65`) creates a fresh named wire every time a sub-expression is referenced for the second time, and `fit_width` calls it with `force_share=True` even on first sight when a width adjustment is needed. The downstream effect is a wire-count explosion.

Counts on `encoder_8b10b`'s best designs (combinational, ~40 lines of source):

| | wire declarations | named wires |
|---|---:|---|
| Round-2 verilog winner | **14** | `A,B,C,D,E,F,G,H, L03, L30, ABCD, DL03, L12, L21` |
| Round-2 spirehdl best | **53** | the same logical wires + 30+ `sig_N` and `name_1`/`name_2` aliases |

Worse, the same `signal_name_inference` logic that scrapes Python variable names mis-attributes a name like `L03 = ~A & ~B & ~C` to the **innermost** intermediate sub-expression. The result is three named wires for a single Python variable:

```verilog
// What spirehdl emits for L03 = ~C & ~A & ~B
wire  L03;     assign L03   = (~in_8b[0]);                 // inner ~A
wire  L03_1;   assign L03_1 = (~in_8b[1]);                 // inner ~B
wire  L03_2;   assign L03_2 = (((~in_8b[2]) & L03) & L03_1); // full expr
```

Each of those named wires becomes an **optimization barrier** for abc's `dch -f` rewriting pass (abc preserves named net boundaries by default — it can rewrite *within* a node's fan-in cone but won't merge fan-ins across named cuts). With ~50 cuts in the encoder netlist vs ~14 in the verilog version, abc's search space is severely restricted.

This is responsible for the +7.8% encoder gap and the small gda_adder discrepancy. **It is the same root cause that the round-1 analysis identified** (the "redundant aliased wires" point), but rewriting the SpireHDL starting points to use `Wire(...)` explicitly didn't fix it — agent-driven optimization re-introduces the over-sharing as the design grows.

**Possible library fix:** change the threshold in `_maybe_share` from "share on second sighting" to "share on third sighting" (or only share at fan-out > 2), and don't force-share inside `fit_width` unless the source is itself a complex subgraph. Alternatively, run a post-emit pass that inlines wires whose driver is a single bit-slice or a single unary op.

### Cause 3 — output truncation creates a pinned slice node (bcd_to_bin_16b)

`bcd_to_bin_16b`: round-2 verilog 2,718,510 vs spirehdl 3,159,272 — 16% gap. **Round-1's analysis blamed spirehdl's natural width inflation** (`d4 * 10000` widening to UInt(18) instead of UInt(16)). Round 1 fixed that by rewriting the starting point to use explicit `Wire(UInt(16), ...)` cut-points at every product. After that fix the starting points are within 2% of each other (3,288k vs 3,360k). The **remaining** round-2 gap is a different effect, surfaced by the agent's specific best design:

```python
# spirehdl round-2 best: d_v12.py
operador <<= (s43 + s210)[0:16]
```

vs the verilog winner:

```verilog
// design_v12.sv
wire [15:0] sum_hi = (num_exp4 + num_exp3) + num_exp1;
wire [15:0] sum_lo = num_exp2 + {12'b0, numeros[3:0]};
assign operador = sum_hi + sum_lo;
```

In the verilog form, `sum_hi + sum_lo` is computed in the 16-bit context of the LHS `assign operador = …`, so Verilog widens the operands TO 16 bits and the addition is emitted as a single 16-bit adder. In spirehdl, `s43 + s210` (both 16-bit `Wire`s) returns `UInt(17)` per `add_result_type`, then `[0:16]` slices the lower 16 bits. The emitted Verilog is:

```verilog
assign sig_1 = (s43 + s210);    // 17-bit wire
assign operador = sig_1[15:0];  // explicit slice node
```

That extra `sig_1[15:0]` slice is **another `dch -f` cut barrier**, sitting right on the output cone. abc can't fuse the upper-bit drop with the addition's last carry, so it has to map the full 17-bit adder and then drop the top bit. The same applies anywhere a spirehdl arithmetic chain widens past the desired output and gets sliced back down.

**Workaround in user code:** never use `output <<= (expr)[0:N]`. Instead, declare the final sum into a `Wire(UInt(N))` first — `Wire` truncates via fit_width on the `<<=`, and that emits as the right thing in Verilog context. Or even better, structure the arithmetic so it never widens (cast operands at each step).

**Library fix:** when spirehdl is about to emit `output_wire <<= wider_expression`, insert an implicit `fit_width` to the output's declared width before the slice ever materializes — that turns `output = sig[15:0]` back into `output = (lhs_in_16bit_context)`.

### Cause 4 (not really a cause) — agent strategy variance: rgb_diff_check spirehdl WIN

For completeness: `rgb_diff_check` is the round-2 case where spirehdl beats verilog (2,284,574 vs 2,539,030 — 10% better, spirehdl wins outright). This is **agent-strategy variance**, not a spirehdl advantage:

- The verilog Opus run stalled at the starting point (2,539,030) after trying ~10 reformulations that either broke correctness or didn't improve.
- The spirehdl Opus run found a **bit-level rewrite of `u_inside`**: instead of `(u < 0x04) | (u >= 0x7C)`, it computed `~(u[6]^u[5]) & ~(u[5]^u[4]) & ~(u[4]^u[3]) & ~(u[3]^u[2])`. This is the "top-three bits all equal each other and equal bit 6" check, which is exactly the unsigned predicate `u in [-4, 3]` interpreted as a 7-bit signed value. It saves a 7-bit comparator chain.
- The same rewrite would have worked equally well in verilog. Opus simply explored different paths in the two languages.

So spirehdl "winning" rgb_diff_check is luck of the search, not a structural advantage — and round-1 Sonnet had previously found this rewrite in the verilog run, which was then "lost" when round-2 Opus didn't try it. (`encoder_8b10b` Opus spirehdl losing to round-1 Sonnet spirehdl is the opposite version of the same coin.)

### Summary

Round 2 spirehdl losses break down cleanly:

| Benchmark | Δ vs verilog | Root cause | Fixable in library? |
|---|---:|---|---|
| `adder_4bit_reg` | +12.2% | Cause 1 (output reg buffer tax) | Yes — emit `output reg` when output drives from a Register |
| `avg4_reg`       |  +5.9% | Cause 1 (output reg buffer tax) | Yes — same fix |
| `bcd_to_bin_16b` | +16.2% | Cause 3 (output truncation slice) | Yes — implicit `fit_width` at output |
| `encoder_8b10b`  |  +7.8% | Cause 2 (over-sharing + naming) | Yes — relax `_maybe_share` threshold + don't force-share in fit_width |
| `gda_adder_n8m8p2` | tie | (would still be Cause 2 if not for ties) | Yes — same fix |
| `const_mult_3853` | tie | n/a | n/a |
| `rgb_diff_check`  | −10.0% | spirehdl wins (agent strategy variance) | n/a |

**None of the spirehdl losses are inherent to the language.** All three causes are mechanical spirehdl-emission issues that yosys+abc could otherwise have collapsed. With the three library fixes above, spirehdl should match verilog within noise on every benchmark in this set — and since spirehdl's compositional semantics actually help with structural exploration (rgb_diff_check), the lazy expectation should be that **a fixed spirehdl ties or beats verilog under the same agent strategy**.

The reason all this matters: the cost-metric flow we're using (`yosys synth` → `yosys-abc dch -f; map; topo; upsize; dnsize; stime`) is **structurally sensitive**. It does local rewrites within named-wire boundaries but does not back-propagate don't-cares from outputs (round 1's first finding) and doesn't fuse across explicit alias buffers (round 2's first finding). Spirehdl's defaults — over-sharing intermediate expressions, inability to register an output port — reliably trip both blind spots. The same designs synthesized through a flow that runs e.g. `abc -fast` followed by `clean -purge` and a backward don't-care sweep would likely show much smaller language gaps.

### Correction summary (after the `clean -purge` fix and deeper testing)

The original "Three causes" analysis above had Cause 1 attributed to the wrong layer, and Cause 2's mechanism wrong. Empirical re-test on the saved round-2 best designs (no agent rerun):

- **Cause 1 was a `Sky130ADPCost` script bug, not a spirehdl issue.** Yosys's default `opt`/`opt_clean` deliberately preserves named (public) wires for debuggability — the alias buffer chain `.names sum_reg[i] sum[i] / 1 1` survives into BLIF only because our script never invoked `opt_clean -purge` (a.k.a. `clean -purge`). The `assign output = reg` pattern that spirehdl is forced to emit is *not* the proximate cause; the missing yosys flag is. **Patch:** one line added to `core/cost.py:Sky130ADPCost`'s yosys script (`clean -purge` before `write_blif`).
- **Cause 2 mechanism was wrong.** I claimed spirehdl's `_maybe_share` named wires acted as hard `dch -f` boundaries that prevented optimization. Empirical test contradicts this: yosys's `opt`/`opt_clean -purge` does collapse most of the named-wire chain. The post-yosys cell counts on `encoder_8b10b` are **58 cells (spirehdl) vs 53 cells (verilog)** — a real but small (+9%) difference, not a 53-vs-14 explosion. On `bcd_to_bin_16b` spirehdl has **fewer** post-yosys cells (384 vs 452), yet still loses on ADP. The actual mechanism is "source structure leaks into the post-flatten AIG topology in a residual way, and abc's local search lands in different optima for the two AIG shapes". On encoder, abc maps the spirehdl AIG to smaller area (202 vs 228) but worse delay (258 vs 213); ADP penalises the spirehdl landing by 7.8% but area-only would FAVOUR it. Switching abc to `abc -fast` (a different mapping strategy) flips the sign — spirehdl 49,963 vs verilog 50,597 (spirehdl wins by 1.3%). So the gap is sensitive to abc's strategy, not to a hard barrier. None of the yosys-side passes I tried (`opt -full`, `opt_share`, `opt_merge`, double-`flatten`) closed it.
- **Cause 3 (bcd output-truncation slice) is partially a special case of the corrected Cause 2.** The slice contributes to bcd's post-flatten AIG having a different shape than verilog's. A library-side `fit_width`-at-output fix would remove the slice and is the most promising actionable change for that specific benchmark.

Re-evaluation of every round-2 best design under the patched (`clean -purge`) `Sky130ADPCost`:

| Benchmark | Lang | Original ADP | Patched ADP | Δ |
|---|---|---:|---:|---:|
| `adder_4bit_reg` | spirehdl |  53,427 | **47,217** | **−11.6%** ⬇ (now ahead of verilog 47,630) |
| `adder_4bit_reg` | verilog   |  47,630 |  47,630 | 0.0% |
| `avg4_reg`       | spirehdl | 2,270,125 | 2,270,125 | 0.0% |
| `avg4_reg`       | verilog   | 2,143,114 | 2,143,114 | 0.0% |
| `bcd_to_bin_16b` | spirehdl | 3,159,272 | 3,159,272 | 0.0% (Cause 3 still present) |
| `bcd_to_bin_16b` | verilog   | 2,718,510 | 2,718,510 | 0.0% |
| `const_mult_3853`| both      | 8,185,036 | 8,185,036 | 0.0% |
| `encoder_8b10b`  | spirehdl |  52,399 |  52,399 | 0.0% (Cause 2 still present) |
| `encoder_8b10b`  | verilog   |  48,616 |  48,616 | 0.0% |
| `gda_adder_n8m8p2` | both    |  67,858 |  67,858 | 0.0% |
| `rgb_diff_check` | spirehdl | 2,284,574 | 2,284,574 | 0.0% (spirehdl was already winning) |
| `rgb_diff_check` | verilog   | 2,539,030 | 2,539,030 | 0.0% |

Only `adder_4bit_reg` spirehdl moves — but it moves dramatically (−11.6%). Notably, **`avg4_reg` spirehdl is unchanged** despite using the same `assign average = average_reg` pattern: its 5-bit buffer chain is dominated by the surrounding ~2M ADP of accumulator logic, whereas `adder_4bit_reg`'s tiny netlist is dominated *by* the 12-gate buffer overhead. So the buffer tax is real but only severe on small registered designs.

**Updated language scoreboard** (post-patch, "best of" still uses round 1 + round 2 + this re-eval):

| Benchmark | Best V (any round) | Best S (any round, post-patch) | Winner |
|---|---:|---:|---|
| `encoder_8b10b`    |     48,616 |     49,689 | V by 2.2% |
| `gda_adder_n8m8p2` |     65,356 |     67,858 | V by 3.8% |
| `bcd_to_bin_16b`   |  2,718,510 |  3,159,272 | V by 16.2% |
| `const_mult_3853`  |  8,185,036 |  8,185,036 | tie |
| `rgb_diff_check`   |  2,539,030 |  2,284,574 | **S** by 10.0% |
| `adder_4bit_reg`   |     47,630 |     **47,217** | **S** by 0.9% |
| `avg4_reg`         |  2,143,114 |  2,270,125 | V by 5.9% |

Spirehdl now wins outright on 2 of 7 benchmarks (rgb_diff_check, adder_4bit_reg), ties on 1 (const_mult_3853), and loses on 4 — and the losses on encoder/gda_adder are both ~2-4% rather than the 8-12% they looked like before. Two genuine library fixes remain: the `_maybe_share` over-sharing (closes encoder + gda) and the implicit-fit_width-at-output (closes bcd). With those, the lazy expectation is spirehdl ties or beats verilog on every benchmark in this set.

### Best designs — where to find them (round 1)

Round-1 campaigns saved their best designs under `runs/turbo_rtl_sky130_adp/<benchmark>/claude-sonnet-4-5/<timestamp>/best_design/`, with a `_best_meta.json` recording which file (`design_opt<n>.sv` for verilog, `design_opt<n>.py` or `design_tree2.py` etc. for spirehdl) achieved the best cost. Round-2 best designs live under `runs/turbo_rtl_30/<benchmark>/claude-opus-4-6/<timestamp>/best_design/` with the same `_best_meta.json` convention. Timestamp mapping for round 1 (the earlier timestamp is always the verilog run for each benchmark):

| Benchmark | Verilog run | SpireHDL run |
|---|---|---|
| `encoder_8b10b`    | `20260414_133130/best_design/design_opt5.sv` | `20260414_133458/best_design/design_opt2.py` |
| `gda_adder_n8m8p2` | `20260414_133451/best_design/design_opt8.sv` | `20260414_133500/best_design/design_opt1.py` |
| `bcd_to_bin_16b`   | `20260414_133453/best_design/design_opt8.sv` | `20260414_133501/best_design/design_tree2.py` |
| `const_mult_3853`  | `20260414_133454/best_design/<starting point>` | `20260414_133503/best_design/<starting point>` |
| `rgb_diff_check`   | `20260414_133456/best_design/design_opt2.sv` | `20260414_133505/best_design/<starting point>` |

## Notes & caveats

- The `sky130_adp` yosys+abc flow is already aggressive (`dch -f; map; topo; upsize; dnsize`), and it starts from a lower ADP than the paper's `ppa_opt` on every benchmark above. The agent's job is incremental refinement — rewriting the algorithm to shrink area or critical depth further. With only 20 steps the headroom is modest.
- All 5 picks are **combinational** so the random-stimulus tb flow doesn't need cycle-by-cycle capture; the tb compares outputs at `#1` after each input assignment. Adding sequential benchmarks would require a different probe tb.
- The SpireHDL `rgb_diff_check` starting point initially failed 18/2002 vectors due to a spirehdl `cast(unsigned_concat, SInt(wider))` footgun — `Resize` picks the extension mode from the *source* type, so the cast zero-extended instead of sign-extending. Fixed by doing the sign extension explicitly in bit-space via `cat(x, x[msb])`. Not a spirehdl bug per se, but an API surprise worth documenting. See `benchmarks/turbo_rtl/README.md` §SpireHDL translation pitfalls.

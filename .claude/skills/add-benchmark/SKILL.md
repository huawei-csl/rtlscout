---
name: add-benchmark
description: >-
  Add a new RTL design as an RTL Scout benchmark — directory layout, the self-checking
  testbench contract, the add_benchmark.py generators, and porting an existing Verilog or
  Spire design. Use when integrating a new design (or an external benchmark suite) into
  the benchmarks/ folder.
---

# Add a benchmark

This skill is a **router to the authoritative docs** — read them rather than guessing, and
reuse the experience captured from previous ports. A benchmark is a directory under
`benchmarks/` containing `description.txt` + `metadata.json` + `tb.sv` (all three required;
it is only discovered if all three are present, and `_debug/` / `_scratch/` subdirs are ignored
by the loader).

## What you start from

Any of these — adapt accordingly:

1. **A reference design** (`.v` Verilog or a golden model) — use it directly as the correctness
   oracle, and optionally keep it as the `context/` starting point.
2. **Just a description** (no file) — author `description.txt` and a self-checking `tb.sv` from it.
   With no reference, **you must generate the correctness oracle yourself**: compute expected
   outputs inline for derivable logic (e.g. `sum === a + b`), or write a behavioral / Python golden
   model that emits `vectors.dat` (inputs + expected outputs). A vaguer spec → a weaker testbench.
3. **A design in a different language than the target** (e.g. Verilog → Spire benchmark) — the
   original is the oracle; translate it to the target language (see "Decide first" #4).

In every case the user also chooses **whether to ship a `context/` starting point** (see "Decide first" #3).

## Decide first

Pin these down **before** creating any files:

1. **Scope** — a **single design** (`benchmarks/<name>/`) or a **suite of cases** (nested,
   `benchmarks/<suite>/<case>/`, discovered recursively and referenced as `--benchmark <suite>/<case>`).
   `simple_adder` / `fpmul_f16` are single; `dr_rtl` / `rtl_rewriter` are suites. The `add_benchmark.py`
   generators produce a single benchmark per invocation.
2. **Target language** — the language the agent **writes the design in**: `verilog`, `spirehdl`, or
   `amaranth`. Fix this up front; `--language` must match it, and a `context/` starting point (if any)
   must be in that language.
3. **Starting point or not** — either ship a `context/` reference the agent builds on (e.g.
   `starting_point.py` for Spire, or a `.v` for Verilog), **or** omit `context/` so the agent solves
   from the spec alone. If you ship one, it must be in the target language **and** be mentioned in
   `description.txt` — otherwise the agent ignores it and writes from scratch.
4. **Translation / port** — adding an existing design in a *different* language (e.g. you have Verilog
   but want a **Spire** benchmark) means **translating** it to the target language. The original is
   your reference/oracle; the per-design `_debug/DEBUGGING.md` and `NOTES_*` files (section 3) are exactly
   the Verilog→Spire porting experience — read them before starting.

> **The testbench is always Verilog/SystemVerilog** (`tb.sv`), whatever the target language —
> correctness is Verilator simulating the *generated Verilog* against `tb.sv`. A Spire or Amaranth
> benchmark still ships a `.sv` testbench.

## 1. The process — start here

- **`README_add_benchmarks.md`** — the canonical guide: directory layout, the `metadata.json`
  schema, the testbench contract (`<module_name> dut (...)`, `TB_SUMMARY total=N errors=E`, a final
  `PASS` or `$fatal`), the `context/` starting-point convention, and the **Quick check** snippet
  that confirms the benchmark loads and the module name matches the testbench.
- **`add_benchmark.py`** — generators for arithmetic designs (`multiplier`, `adder`, `fpmul`,
  `fpadd`, `mac`, `matmulacc`): emit `tb.sv`, test vectors, the reference `.v`, `metadata.json`,
  and a Spire `context/`. Run `python add_benchmark.py <generator> --help`.

## 2. Worked examples — how real suites were integrated

- **`benchmarks/turbo_rtl/README.md`** (+ `benchmarks/turbo_rtl/RESULTS.md`) — an external suite
  integrated with both Verilog and Spire variants, test-vector generation, and the `sky130_adp`
  metric. The most complete end-to-end example.
- **`benchmarks/dr_rtl/README.md`** and **`benchmarks/dr_rtl_spirehdl/README.md`** — the DR-RTL
  ports, nested as `benchmarks/dr_rtl/<case>` (referenced as `--benchmark dr_rtl/<case>`).
- **`benchmarks/rtl_rewriter/README.md`** — the RTLRewriter cases.

## 3. Experience & gotchas from prior ports — read before a non-trivial design

- **`benchmarks/dr_rtl/NOTES_dr_rtl_scaffolding.md`** and
  **`benchmarks/dr_rtl_spirehdl/NOTES_dr_rtl_spirehdl_porting.md`** — scaffolding and porting notes.
- **`benchmarks/dr_rtl_spirehdl/<case>/_debug/DEBUGGING.md`** — per-design debugging journals (bugs
  found, spire-vs-verilog metric deltas, and the trace methodology used to find them). Cases:
  `router`, `datapath`, `cpu_pipe`, `pcie`, `i2c`. Skim one or two before porting a tricky design.

## 4. Clock and reset naming — MANDATORY for any sequential design

**The top-level clock port must be named exactly `clk`, and the reset `rst`.** This is not a style
preference; a different name silently produces wrong PPA numbers.

The PPA flow's STA script resolves the clock with `get_ports -quiet clk` and, on a miss, falls back
to a **virtual clock** (`create_clock -name VCLK`) attached to no port. A virtual clock leaves every
flip-flop in no clock domain, so **no register-to-register setup check is created at all**. The only
constrained paths left are `set_max_delay -from [all_inputs]` — the input into the first pipeline
stage. You get a plausible-looking delay that silently omits the entire pipeline.

Measured on `pdpu_dot16_pipe` (clock was `clk_i`): reported **745 ps**, true value **956 ps** — a
25% under-report, and the reported worst path was in stage 1 while the real one was in stage 2.
Diagnosing this cost hours; the giveaway is `Path Group: path delay` (or `VCLK`) instead of
`Path Group: clk` in `worst_timing_path`, and a worst path that starts at an input port.

- **Verilog benchmarks**: rename the port in `context/*.v`, `tb.sv` and `description.txt` together.
  A word-boundary rename is safe (`sed -E 's/\bclk_i\b/clk/g; s/\brst_i\b/rst/g'`); check first that
  no bare `clk`/`rst` identifier already exists. Submodule-internal clock ports (e.g. a dual-port
  RAM's `clk0_i`/`clk1_i`) do not matter — only the **top-level** port is bound by STA.
- **Spire benchmarks**: `to_netlist(..., with_clock=True)` already emits `clk` — just don't rename
  it. If the design needs a *data* input called `rst` (a manual sync reset with `with_reset=False`),
  Spire reserves that name, so declare it `rst_i` and rename the emitted port back:

      _net = MyDesign().to_netlist("my_top", with_clock=True, with_reset=False)
      for _p in _net._ports:
          if _p.name == "rst_i":
              _p.name = "rst"

  `benchmarks/jpeg_idct_2d_1r1w_spire` is the reference example.
- **Verilog/Spire pairs must agree**, since the two share one testbench. Spire emits `clk`, so the
  Verilog side is the one that adapts — never rename Spire's clock to match a `_i`-suffixed reference.
- Porting a reference design **verbatim** is not a reason to keep `clk_i`. A port rename changes no
  logic or structure, and correct measurement outranks byte-fidelity to upstream naming.

Verify after any change: run `run_eval.py --cost-metric delay` and confirm `worst_timing_path`
reports `Path Group: clk` with a **register** startpoint, not an input port.

## Checklist

- [ ] Pick `--language` to match the design file: `verilog` (`.v` / `.sv`), `spirehdl` (`.py`), or `amaranth`.
- [ ] `description.txt` is language-neutral; if you ship a `context/` starting point, **say so in it** —
      otherwise the agent ignores the files and writes a design from scratch.
- [ ] `metadata.json` `module_name` must equal what `tb.sv` instantiates as `dut`.
- [ ] **Sequential design?** Top-level clock port named `clk`, reset `rst` — see section 4. Any other
      name silently under-reports delay (no reg-to-reg paths are timed at all).
- [ ] `tb.sv` stimuli are thorough — directed **corner cases** *and* a batch of **randomized inputs**;
      the tb is the only correctness oracle, so weak coverage lets broken designs pass (see
      `README_add_benchmarks.md` → `tb.sv`).
- [ ] Confirm discovery + module match with the **Quick check** snippet in `README_add_benchmarks.md`.
- [ ] Smoke-test **offline** (free, no API key): `python run_benchmark.py --benchmark <name> --model fake:simple_adder_pass`,
      and/or evaluate a reference design with `run_eval.py`.
- [ ] *(optional, strongest check)* a **real agent run** with a live model, e.g.
      `python run_benchmark.py --benchmark <name> --model openrouter:qwen/qwen3.7-max --language <lang>`.
      **This spends API credits — confirm with the user before launching it.**

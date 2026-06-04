# `turbo_rtl` / `turbo_rtl_spirehdl` benchmarks

Benchmarks picked from `benchmarks/final_benchmark_samples.zip` (paired raw + best Verilog designs from the deepcircuitx / deeprtl / mgverilog / rtlcoder datasets). The reference ADP numbers in `ppa_opt.adp` from `final_benchmark_samples.json` are the numbers to beat under `--cost-metric sky130_adp`.

Current picks:

| Benchmark | Source (`dataset/id/file`) | Module | Flavor |
|---|---|---|---|
| `encoder_8b10b` | `deepcircuitx/10105/10105_19.v` | `encoder` | 8b/10b encoder (bit logic) |
| `gda_adder_n8m8p2` | `mgverilog/1113/1113_3.v` | `GDA_St_N8_M8_P2` | approximate 8-bit adder |
| `bcd_to_bin_16b` | `deeprtl/35966/35966_7.v` | `conversor_num_16b` | 5-digit BCD→binary |
| `const_mult_3853` | `deeprtl/20904/20904_3.v` | `multiplier_block` | 32-bit shift-and-add |
| `rgb_diff_check` | `rtlcoder/8900/8900_8.v` | `DiffCheck` | RGB555 proximity predicate |
| `adder_4bit_reg` | `rtlcoder/9045/9045_11.v` | `adder_4bit` | registered 4-bit adder (clk only) |
| `avg4_reg` | `rtlcoder/13396/13396_4.v` | `average_module` | clk + sync reset, running accumulator |

Each benchmark exists in **two** parallel forms that share the same tb / vectors / metadata and differ only in what's in `context/`:

```
benchmarks/turbo_rtl/<name>/              # Verilog starting point
  description.txt                         # spec, points at context/starting_point.v
  metadata.json                           # { name, module_name, tb_module, source{…} }
  tb.sv                                   # self-checking, reads vectors.dat
  vectors.dat                             # random stimulus + expected output
  context/
    starting_point.v                      # golden from the zip, verbatim

benchmarks/turbo_rtl_spirehdl/<name>/    # SpireHDL starting point
  description.txt                         # same spec, points at context/starting_point.py
  metadata.json                           # IDENTICAL module_name as the verilog sibling
  tb.sv                                   # IDENTICAL to verilog sibling
  vectors.dat                             # IDENTICAL to verilog sibling
  context/
    starting_point.py                     # hand-written SpireHDL that writes design.v
```

**Hard invariant:** `metadata.json`, `tb.sv`, and `vectors.dat` must be bit-identical between the Verilog and SpireHDL variants. If they drift, the spirehdl starting point will pass against a different oracle than the verilog one.

### `metadata.json` — include a `source` cross-reference to the zip

Every turbo_rtl benchmark's `metadata.json` carries a `source` block pointing back at the raw `.v` inside `benchmarks/final_benchmark_samples.zip`:

```json
{
  "name": "avg4_reg",
  "module_name": "average_module",
  "tb_module": "tb",
  "source": {
    "zip": "benchmarks/final_benchmark_samples.zip",
    "path": "final_benchmark_samples/rtlcoder_success_20251104/13396/13396_4.v",
    "module_key": "rtlcoder_success_20251104/13396"
  }
}
```

- `zip` — path to the source zip relative to the repo root. All current benchmarks use the same zip; if you ever add one from a different source, update this field.
- `path` — the exact path inside the zip, including the `final_benchmark_samples/` top-level directory that the zip unpacks to.
- `module_key` — the key used in `final_benchmark_samples.json` under `samples[*].module_key`. Use this to look up the paper's `ppa_raw.adp` and `ppa_opt.adp` without having to grep through the whole JSON. Example:

  ```bash
  ~/pyenv_eda/bin/python -c "
  import json
  md  = json.load(open('benchmarks/turbo_rtl/avg4_reg/metadata.json'))
  ref = json.load(open('/tmp/final_benchmark_samples/final_benchmark_samples/final_benchmark_samples.json'))
  mk  = md['source']['module_key']
  hit = next(s for s in ref['samples'] if s['module_key'] == mk)
  print(mk, 'ref_opt_adp =', round(hit['ppa_opt']['adp'], 1))
  "
  ```

**Keep this field in sync between the verilog and spirehdl variants of the same benchmark.** Both generators (`/tmp/turbo_rtl_gen.py` and `/tmp/turbo_rtl_seq_gen.py`) write it automatically from the entry's `src` field, so new benchmarks added through the generators always get it. If you hand-edit an existing benchmark, remember to update **both** `benchmarks/turbo_rtl/<name>/metadata.json` and `benchmarks/turbo_rtl_spirehdl/<name>/metadata.json`.

## Quick smoke test

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

Expected on a freshly-added benchmark: both say `Correctness: PASS, 2002/2002`, the two `sky130_adp` values should be within a few percent of each other (perfectly equal if the spirehdl translation emits the same logical netlist as the golden).

## Important gotcha — don't run starting_point.py in place

`run_eval.py` uses `dirname(<file>)` as the workspace when you don't pass `--workdir`. If you point it at `context/starting_point.py`, it builds `obj_dir/`, `design.v`, and copies `tb.sv` + `vectors.dat` **into `context/`**. Those artifacts then get picked up by later runs and — worse — by `core/runner.py`'s context-copy step, leaking into every future agent workspace.

After any in-place smoke test, clean up:

```bash
rm -rf benchmarks/turbo_rtl_spirehdl/*/context/obj_dir \
       benchmarks/turbo_rtl_spirehdl/*/context/design.v \
       benchmarks/turbo_rtl_spirehdl/*/context/tb.sv \
       benchmarks/turbo_rtl_spirehdl/*/context/vectors.dat \
       benchmarks/turbo_rtl_spirehdl/*/context/__pycache__
rm -rf benchmarks/turbo_rtl/*/context/obj_dir \
       benchmarks/turbo_rtl/*/context/tb.sv \
       benchmarks/turbo_rtl/*/context/vectors.dat
```

Better: copy the starting_point file to `/tmp/...` before running, or pass `--workdir /tmp/foo` explicitly.

---

## How to add a new benchmark from `final_benchmark_samples.zip`

### 1. Unzip once

```bash
mkdir -p /tmp/final_benchmark_samples
unzip -o benchmarks/final_benchmark_samples.zip -d /tmp/final_benchmark_samples
```

Contents: four `*_success_20251104/` dataset directories plus `final_benchmark_samples.json` indexing every (raw, best) pair along with the paper's `ppa_raw`/`ppa_opt` (area, delay_ps, adp) figures.

### 2. Pick a design

Open `/tmp/final_benchmark_samples/final_benchmark_samples/final_benchmark_samples.json` and choose a `module_key` whose source file is:

- **Combinational OR sequential** — both are supported:
  - **Combinational** flow: `/tmp/turbo_rtl_gen.py` compiles the golden, drives random inputs at `#1`, captures outputs, writes a data-driven tb.sv with `#1` sampling.
  - **Sequential** flow: `/tmp/turbo_rtl_seq_gen.py` drives `clk` at 10 ns period, holds `reset` high for `N_RESET=3` cycles, then feeds random inputs **per cycle** and samples outputs at each `@(posedge clk); #1` tick. The tb.sv mirrors the same protocol: reset then per-cycle sample/check loop.
  - Avoid SV-keyword identifiers — verilator in SystemVerilog mode rejects module/port names like `rand`, `type`, `return`, etc. Check with `verilator --lint-only -sv` before committing to a pick.
- **Verilator-clean** — no non-constant bit selects, no real-valued ports. Sanity check by trying to compile the raw `.v` alone with `verilator --lint-only -sv <file>.v`.
- **Small-to-medium** (≤ ~60 LOC works well; very large designs make the spirehdl hand-translation painful).

Look up the reference numbers in the JSON:

```python
python3 -c "
import json
d = json.load(open('/tmp/final_benchmark_samples/final_benchmark_samples/final_benchmark_samples.json'))
for s in d['samples']:
    if s['module_key'] == 'deepcircuitx_success_20251104/10105':
        print(s)"
```

Record `ppa_raw.adp` and `ppa_opt.adp` — these are the baseline and the paper's optimized ADP that the agent needs to beat.

### 3. Generate the Verilog benchmark directory

Two throwaway generators:

- `/tmp/turbo_rtl_gen.py` — combinational designs
- `/tmp/turbo_rtl_seq_gen.py` — clocked designs

Add an entry to the appropriate generator's `BENCHMARKS` list with hard-coded port info — do NOT auto-parse the verilog headers; port parsing is brittle and we only have a handful of benchmarks.

Combinational entry:

```python
{
    "name": "my_bench",           # becomes benchmarks/turbo_rtl/my_bench/
    "module": "my_module",        # MUST equal the raw .v's `module <name>`
    "src":   "deepcircuitx_success_20251104/12345/12345_1.v",
    "inputs":  [("a", 8), ("b", 8)],      # (port_name, width_in_bits)
    "outputs": [("y", 9)],
    "desc": "Human-readable one-paragraph spec that gets spliced into description.txt.",
},
```

Sequential entry — add `clock_port` and `reset_port` (use `None` if the design has no reset):

```python
{
    "name": "my_seq_bench",
    "module": "my_seq_module",
    "src":   "rtlcoder_success_20251104/12345/12345_1.v",
    "clock_port": "clk",          # name of the clock port in the golden
    "reset_port": "reset",        # name of the reset port in the golden, or None
    "inputs":  [("a", 8), ("b", 8)],
    "outputs": [("y", 8)],
    "desc": "One-paragraph spec. Mention the reset semantics (sync vs async, active high/low).",
},
```

Then run the appropriate generator:

```bash
~/pyenv_eda/bin/python /tmp/turbo_rtl_gen.py         # combinational
~/pyenv_eda/bin/python /tmp/turbo_rtl_seq_gen.py     # clocked
```

What it does:

1. Copies the raw `.v` to `benchmarks/turbo_rtl/<name>/context/starting_point.v` unchanged (the agent reads it as a known-correct reference).
2. Writes `metadata.json` with `name`, `module_name`, `tb_module: "tb"`.
3. Writes `description.txt` embedding your `desc` + the port list + the standard "reference starting point" footer.
4. Builds a temporary "probe tb" that instantiates the golden, drives a 32-bit LFSR (seed `0xDEADBEEF` and `0xCAFEBABE`) to generate 2000 random input combinations plus a deterministic all-zero and all-ones case, and `$display`s `<input1_dec> <input2_dec> ... <output1_dec> ...` per line.
5. Compiles `golden.v + probe_tb.sv` with `verilator --binary --timing` and runs the binary.
6. Captures stdout into `vectors.dat` with a `# port1 port2 out1 ...` header.
7. Emits a data-driven `tb.sv` that `$fopen`s `vectors.dat`, `$sscanf`s every line, compares `dut.<output>` against `expected_<output>`, and prints the framework-recognised `TB_SUMMARY total=N errors=E` + `PASS`/`$fatal(1,"FAIL")`.

If verilator rejects the raw `.v` (e.g. non-constant bit selects), swap the pick — don't try to patch the golden.

### 4. Verify the Verilog benchmark passes

```bash
~/pyenv_eda/bin/python -c "
from pathlib import Path
from core.benchmarks import load_benchmark
b = load_benchmark(Path('benchmarks/turbo_rtl/my_bench'))
print(b.name, b.module_name)
"
~/pyenv_eda/bin/python run_eval.py \
    benchmarks/turbo_rtl/my_bench/context/starting_point.v \
    --benchmark benchmarks/turbo_rtl/my_bench \
    --language verilog --cost-metric sky130_adp
```

Must report `Correctness: PASS, 2002/2002` and a finite `sky130_adp`. Then clean up `context/obj_dir`, `context/tb.sv`, `context/vectors.dat`.

### 5. Mirror as a SpireHDL benchmark

```bash
mkdir -p benchmarks/turbo_rtl_spirehdl/my_bench/context
# Copy the three invariants verbatim:
cp benchmarks/turbo_rtl/my_bench/{tb.sv,vectors.dat,metadata.json} \
   benchmarks/turbo_rtl_spirehdl/my_bench/
# Adapt description.txt to point at starting_point.py:
sed 's|context/starting_point.v|context/starting_point.py|' \
    benchmarks/turbo_rtl/my_bench/description.txt \
    > benchmarks/turbo_rtl_spirehdl/my_bench/description.txt
```

Then hand-write `benchmarks/turbo_rtl_spirehdl/my_bench/context/starting_point.py` as a SpireHDL script that emits `design.v` with **the same top-module name** as the Verilog sibling.

#### Convention: mirror the reference Verilog `assign`-for-`assign`

For every `assign <name> = <expr>;` in the golden `.v`, write **one** matching line in the SpireHDL script using the standalone `Wire` class from `spirehdl.spirehdl`:

```python
from spirehdl.spirehdl import UInt, Wire, Register

# Combinational wire — one per `assign <name> = <expr>;` in the golden
w = Wire(UInt(W), name="<name>"); w <<= <expr>

# Register — one per `always @(posedge clk) <name> <= <expr>;` in the golden
r = Register(UInt(W), name="<name>"); r.next <<= <expr>  # see spirehdl Register docs
```

Use `Wire(typ, name=...)` rather than the instance-method `m.wire(typ, name)`. `Wire` is a plain class imported from `spirehdl.spirehdl` — it does not need the `Module` handle, so you can declare wires inside helper functions, loops, list comprehensions, or library modules, and they'll still be picked up by the module via its expression-traversal walk from the primary outputs. Same goes for `Register` — use it in place of `m.reg(...)` for clocked state. If you're ever writing reusable generator functions that produce pieces of a design, `Wire`/`Register` is the idiomatic way to do it because the function stays decoupled from the caller's `Module` object.

Use the **exact width `W`** declared for that wire in the golden — if the golden says `wire [15:0] num_exp4`, use `Wire(UInt(16), name="num_exp4")`; if it says scalar `wire foo`, use `Wire(UInt(1), name="foo")`.

Why this matters: SpireHDL's default behavior is to let arithmetic widths grow (`UInt(N) + UInt(N) → UInt(N+1)`, `UInt(N) * UInt(M) → UInt(N+M)`), and truncate only at the final `output <<=` assignment. Yosys+abc's standard flow does **not** back-propagate the output truncation as don't-cares, so every extra MSB carry-chain gate survives technology mapping and shows up in the area / delay numbers. Forcing an explicit cut-point at each stage collapses the intermediate carries to the right width. Measured on `bcd_to_bin_16b`: 4,283,419 ADP → 3,359,772 ADP (22% drop) just from wire-ifying the same expression tree.

On gate-level / bit-level benchmarks (like the 8b/10b encoder or the GDA adder) the explicit wires often don't change the synthesized netlist — yosys collapses the redundant aliases during `opt`. But write them anyway, because:

1. The source then tracks the verilog golden line-for-line, making review trivial.
2. Agents optimizing from this starting point see named handles to manipulate, not anonymous inlined subexpressions.
3. It removes width inflation as a possible confound when comparing numbers.

Minimal scaffold:

```python
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Wire, cat

m = Module("my_module", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
y = m.output(UInt(9), "y")

# For every `assign <w> = <expr>;` in the golden — one Wire + <<=
sum_ab = Wire(UInt(9), name="sum_ab"); sum_ab <<= a + b

y <<= sum_ab

m.to_verilog_file("design.v")
```

Worked example for a combinational design: compare `benchmarks/turbo_rtl/bcd_to_bin_16b/context/starting_point.v` (golden) and `benchmarks/turbo_rtl_spirehdl/bcd_to_bin_16b/context/starting_point.py` (mirror) — every `assign` in the golden has a corresponding `Wire(UInt(16), name="<same_name>"); <same_name> <<=` in the mirror.

#### Registers and reset

For every `reg` that appears on the LHS of a `<=` inside an `always @(posedge clk …)` block in the golden, declare a `Register(typ, name=...)` in the SpireHDL script. The same `<<=` operator sets the **next-state** expression (not combinational driver):

```python
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Register

m = Module("foo", with_clock=True, with_reset=False)   # clk input auto-created
a = m.input(UInt(8), "a")
y = m.output(UInt(8), "y")

# reg [7:0] acc;  always @(posedge clk) acc <= acc + a;
acc = Register(UInt(8), name="acc")
acc <<= acc + a

y <<= acc
```

**Choosing `with_reset`:**

- **No reset in the golden** (`clk`-only): set `with_reset=False`. No reset port is added.
- **Golden uses `posedge rst` async reset** with reset-value constants: the simplest path is `with_reset=True` (spirehdl auto-creates an `rst` input and emits `always @(posedge clk or posedge rst)`). Declare each register as `Register(typ, init=<reset_value>, name=...)`.
- **Golden uses a port named anything other than `rst`** (e.g. `reset`, `rst_n`) **or** a synchronous reset inside the `always @(posedge clk)` body: set `with_reset=False`, declare the reset signal as a regular `m.input(UInt(1), "reset")`, and implement the reset explicitly as a `mux` on each register's next-state driver:

  ```python
  from spirehdl.spirehdl import mux
  reset = m.input(UInt(1), "reset")
  acc = Register(UInt(8), name="acc")
  next_acc = Wire(UInt(8), name="next_acc"); next_acc <<= acc + a
  acc <<= mux(reset, 0, next_acc)       # sync reset to 0
  ```

  This is also what you want if the golden has an active-low reset (`if (!rst_n)`), or a reset that loads a non-constant value. The `mux` form keeps the emitted Verilog's port names identical to the golden, which is required because `tb.sv` is bit-identical between the verilog and spirehdl variants.

Worked examples:

- Clk-only registered adder — `benchmarks/turbo_rtl_spirehdl/adder_4bit_reg/context/starting_point.py`. Uses `Register(UInt(4), name="sum_reg")` with `with_reset=False`; no reset at all.
- Synchronous-reset accumulator — `benchmarks/turbo_rtl_spirehdl/avg4_reg/context/starting_point.py`. Uses `with_reset=False` + `m.input(UInt(1), "reset")` + `mux(reset, 0, next_val)` to keep the port named `reset` and match the golden's synchronous-reset semantics.

Full SpireHDL API: `deps/spire-hdl/README.md`.

### 6. SpireHDL translation pitfalls (learned the hard way)

When hand-converting a bit-accurate golden to SpireHDL, these are the things that bite:

- **`cat(...)` is LSB-first in argument order.** `cat(b0, b1, ..., b9)` emits Verilog `{b9, ..., b1, b0}`. Easy to get backwards when translating Verilog `{msb, ..., lsb}` concats.

- **Python slicing is half-open, LSB-based.** `x[0:5]` is five bits (0..4) starting at the LSB — equivalent to Verilog `x[4:0]`. Single-bit `x[3]` is bit 3.

- **Operator widening mirrors Verilog but with concrete widths.** `UInt(n) + UInt(n)` returns `UInt(n+1)`. `UInt(n) * UInt(m)` returns `UInt(n+m)`. `UInt(n) & UInt(m)` returns `UInt(max(n,m))` with the narrower side zero-extended. `<<` with a constant shift widens by that constant.

- **Verilog `+` on 1-bit values returns 2 bits, same in spirehdl.** If the golden does `(E + ~D)`, the result is 2-bit and later bitwise/logical ops on it can swallow the carry. Replace with `^` (XOR) when the enclosing expression only cares about the LSB.

- **Verilog `||` is logical (multi-bit → 1-bit reduce-or).** Spirehdl has no reduce-or operator out of the box. If the operands happen to be 1-bit (common after bitwise AND with a 1-bit signal), just use `|`. If a multi-bit value is being logically OR'd, rewrite as `(x != 0) | y`.

- **`cast(expr, TargetType)` does NOT pick extension mode from the target type.** It goes through `fit_width` → `Resize`, and `Resize` sign-extends iff the *source* is signed. Casting an unsigned `Concat` result to `SInt(wider)` **zero-extends**, not sign-extends. If you want sign extension, sign-extend in bit-space first: `cat(x, x[msb])`, then cast.

- **Spirehdl's `SInt` vs. `UInt` affects emitted `wire signed` declarations but not the bit pattern.** Two's-complement addition/subtraction is the same in both, so dropping `$signed(...)` from the Verilog usually still matches bit patterns. The place it matters is (a) sign-extension during width-growth and (b) signed comparators (`<`, `>=`) — in the reference's range-test lines, comparisons are **unsigned** (Verilog's default for unsigned wires against unsigned literals), so compute at unsigned 8-bit and compare unsigned.

- **Intermediate expressions can get auto-named from nearby Python assignments.** When the emitted Verilog has a `wire signed [8:0] v;` where you intended 8 bits, it's spirehdl `_maybe_share` naming an un-cast intermediate after your Python variable. Force truncation by doing the assignment via an explicit `<<=` into a pre-declared wire of the width you want, or reorder so `cast(..., narrower)` runs before the auto-naming scans.

### 7. Verify the SpireHDL benchmark agrees with the Verilog golden

Build both with verilator and compare outputs head-to-head before trusting `run_eval.py`:

```bash
cd /tmp && mkdir -p shdl_cmp && cd shdl_cmp
cp /workspaces/rtl_scout/benchmarks/turbo_rtl_spirehdl/my_bench/context/starting_point.py .
~/pyenv_eda/bin/python starting_point.py     # emits design.v
# Write a probe that instantiates BOTH modules and compares (see /tmp/shdl_test/probe.sv for a template — dup-and-rename the golden module to `<name>_golden` so both compile together)
verilator --binary --top-module probe_tb -Wno-fatal -Wno-WIDTH -j 0 \
    -o probe_exe design.v probe.sv
./obj_dir/probe_exe | grep -E "MISMATCH|total"
```

The rgb_diff_check translation failed 18/2002 vectors on the first try; this probe caught it in seconds and showed the specific failing inputs. Do this before running the full framework eval, especially for designs that use signed arithmetic.

### 8. Run the framework eval on the SpireHDL variant

```bash
~/pyenv_eda/bin/python run_eval.py \
    benchmarks/turbo_rtl_spirehdl/my_bench/context/starting_point.py \
    --benchmark benchmarks/turbo_rtl_spirehdl/my_bench \
    --language spirehdl --cost-metric sky130_adp
```

Must report `PASS, 2002/2002`. Then **clean up** the `context/` dir again (obj_dir, design.v, tb.sv, vectors.dat).

### 9. Register reference numbers

Add the benchmark to the table at the top of this file with a note on the reference `ppa_opt.adp` to beat. That's the number the agent campaign (`run_benchmark.py --cost-metric sky130_adp`) will be compared against.

---

## The `sky130_adp` cost metric

Lives in `core/cost.py` as `Sky130ADPCost`. It replicates `references/run_evaluation.py`:

1. `yosys` synth of the design: `read_verilog -sv`; `hierarchy -top`; `proc; opt; techmap; opt; synth -flatten; async2sync; dffunmap; write_blif`.
2. `yosys-abc`: `read_blif; read_lib <sky130_ff_lib>; strash; dch -f; map; topo; upsize; dnsize; stime`.
3. Regex-parse `Area = <a>` and `Delay = <d> ps` from `stime`, return `area * delay_ps` as the cost.

No CEC, no OpenROAD STA (`references/run_evaluation.py` doesn't run STA either). Correctness is already handled by the testbench under Verilator, so `cec` isn't needed.

Library path defaults to
`/prog/OpenROAD-flow-scripts/tools/OpenROAD/test/sky130hd/sky130_fd_sc_hd__ff_n40C_1v95.lib`,
which is present in this devcontainer. Override with the `SKY130_LIB_PATH` env var.

### Why SpireHDL underperforms Verilog under `sky130_adp` specifically

The `dch -f; map; topo; upsize; dnsize; stime` flow is **structurally sensitive**. yosys preserves named wires and explicit alias nodes as boundaries when it hands the netlist to abc, and abc's `dch -f` only does *local* rewriting within those boundaries — it will not back-propagate don't-cares from primary outputs and it will not fuse across explicit BLIF cut nodes. SpireHDL, by design, names a lot more intermediate signals than handwritten Verilog does, so it trips this structural tax more often. Two concrete mechanisms (and one ex-mechanism that turned out to be a bug in `Sky130ADPCost` itself) explain every spirehdl regression we measured:

1. **Source structure influences post-yosys AIG topology** (encoder_8b10b, gda_adder_n8m8p2, bcd_to_bin_16b). SpireHDL's expression cache (`spire-hdl/src/spirehdl/spirehdl.py:65`) creates a named wire every time a sub-expression is referenced for the second time, and `signal_name_inference` mis-attributes Python variable names to the *innermost* sub-expression (so `L03 = ~A & ~B & ~C` ends up as three named wires `L03` / `L03_1` / `L03_2`). Yosys's `opt`/`opt_clean -purge` does collapse most of this — but the post-flatten AIG that gets handed to abc still differs in topology from the equivalent verilog AIG (on `encoder_8b10b`: 58 cells vs 53; on `bcd_to_bin_16b`: 384 cells vs 452 — spirehdl actually has *fewer* cells here, yet loses on ADP). abc's `dch -f; map; topo; upsize; dnsize` then finds **different local optima** for the two AIGs: on encoder it picks a smaller-area / larger-delay solution for spirehdl and a larger-area / smaller-delay one for verilog, and ADP happens to favour the verilog landing by ~8%. Under `area`-only metric the sign flips; under `abc -fast` (a different abc strategy) the sign also flips on encoder (spirehdl 49,963 vs verilog 50,597). So this is **not** a "named wires are hard barriers" story — it's "source structure leaks into the AIG and biases abc's local search". No yosys-side flag we tested fixes it.
2. **Output truncation creates a pinned slice node** (bcd_to_bin_16b). When spirehdl arithmetic widens past the desired output width and we truncate via slicing — `operador <<= (s43 + s210)[0:16]` — the explicit slice survives into the netlist as `assign sig_1 = (s43 + s210); assign operador = sig_1[15:0];`. abc can't fuse the upper-bit drop with the addition's last carry, so it has to map the full 17-bit adder and then drop the top bit. Survives `clean -purge` because the 17-bit `sig_1` has multiple genuine fan-in operators driving it (not a pure alias). This is partially a special case of (1): the slice biases the post-flatten AIG and contributes to bcd having a different (smaller-cell-count but worse-ADP) shape than the verilog version. A library-side `fit_width`-at-output fix would remove the slice and is the most promising actionable change.

**Ex-cause 3 — registered-output buffer tax (`adder_4bit_reg`, `avg4_reg`).** SpireHDL can't emit `output reg [3:0] sum`, so registered outputs always become `output sum; reg sum_reg; assign sum = sum_reg;`. yosys then writes one explicit `.names sum_reg[i] sum[i] / 1 1` buffer node per output bit into the BLIF, and abc's `dch -f; map` was mapping each one to a physical buffer cell — costing about 12% area on `adder_4bit_reg` (53,427 vs 47,630). **This was actually a `Sky130ADPCost` script bug, not a spirehdl issue:** yosys's default `opt`/`opt_clean` deliberately preserves *public* wires (named, source-visible) for debuggability, and our script never invoked `opt_clean -purge` to drop alias buffers whose only use is a 1-input copy to an output. **Adding `clean -purge` to the yosys script before `write_blif` makes the buffers vanish.** Re-evaluating the unchanged `adder_4bit_reg` spirehdl best design under the patched metric drops it from 53,427 → 47,217 ADP — an 11.6% improvement that puts spirehdl narrowly *ahead* of the verilog winner. Patch is in `core/cost.py:Sky130ADPCost`. Other registered-output benchmarks (`avg4_reg`) don't show movement because their buffer-cell tax is dominated by the surrounding logic.

**Practical implication for benchmark authors:** under `sky130_adp` (now patched), expect spirehdl to land in a different abc local optimum than the equivalent verilog, with a ~5-15% ADP delta in either direction depending on the benchmark and the abc strategy. Registered-output benchmarks are no longer in the danger zone post-patch. **Under `--cost-metric area` and `--cost-metric delay`** (the OpenROAD STA / ASAP7 flow via `tech_eval`) **the gap collapses to a few percent** because the OpenROAD path runs `abc -D <delay> -constr -liberty <…>` *inside* yosys, which is a more aggressive pass that explores wider rewrites during mapping. If you need a fair cross-language comparison and don't care about sky130 specifically, prefer `area`/`delay` over `sky130_adp`.

Things we tried that did NOT close the gap on encoder/bcd:
- `clean -purge` (works for the registered-output buffer tax but not for the AIG-shape difference).
- `opt -full` instead of bare `opt` (no measurable change).
- Adding `opt_share`/`opt_merge` after `opt` (no change).
- A double-`flatten` followed by `opt -full` (no change).

Things that DID change the picture:
- `abc -fast` instead of `dch -f; map; topo; upsize; dnsize` flips the sign on encoder (spirehdl wins 49,963 vs verilog 50,597) but hurts verilog. So a "best of multiple abc strategies" wrapper would close the gap on average, at the cost of more synth time per evaluation.

The two remaining promising fixes:
- **Spirehdl-side:** raise `_maybe_share`'s sharing threshold (don't share until fan-out > 2), and don't `force_share=True` inside `fit_width` for trivial sources (single bit-slices, unary ops). This won't eliminate the AIG-shape difference but should reduce it.
- **Spirehdl-side:** when `output_wire <<= wider_expression`, insert an implicit `fit_width` to the declared output width *before* the slice ever materializes, so the operation is computed in the output's bit-width context (what verilog does natively). This removes the explicit slice node and should bring bcd's AIG shape closer to verilog's.
- **Sky130ADPCost-side (alternative):** run multiple abc strategies and pick the best result. Trades evaluation time for cross-language fairness.

The full empirical write-up — chat-log analysis, controlled experiments, the `clean -purge` correction, and the round-3 OpenROAD-STA cross-check — is in `RESULTS.md` ("Why is SpireHDL still worse — Round 2 analysis" + "Correction").

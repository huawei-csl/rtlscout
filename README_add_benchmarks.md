# Adding a benchmark

How to add your own benchmark to RTL Scout — generated from spire-hdl or authored by hand. For the list of built-in benchmarks see the [main README](README.md#basic-benchmarks).

For a worked example of integrating an external benchmark suite (including Verilog and SpireHDL variants, test-vector generation, and the `sky130_adp` cost metric), see [`benchmarks/turbo_rtl/README.md`](benchmarks/turbo_rtl/README.md).

## Option A: generate from spire-hdl

For benchmarks built on top of spire-hdl's arithmetic generators (multipliers, adders, MACs, FP units, matmuls), use `add_benchmark.py`. It produces test vectors, a data-driven `tb.sv`, the reference `.v`, `metadata.json`, `description.txt`, and a `context/` directory with the spire-hdl source files used to construct the design.

```bash
python add_benchmark.py multiplier --n-bits 8 --encoding unsigned
python add_benchmark.py adder      --n-bits 16 --encoding twos_complement
python add_benchmark.py fpmul      --exponent-width 5 --fraction-width 10 --subnormal-support
python add_benchmark.py fpadd      --exponent-width 5 --fraction-width 10 --subnormal-support
python add_benchmark.py mac        --n-bits 8 --c-bits 16
python add_benchmark.py matmulacc  --dim-m 4 --dim-n 4 --dim-k 4 --a-width 4
```

Run `python add_benchmark.py <generator> --help` for the full set of flags. Add `--name <bench_name>` to override the auto-generated directory name, and `--force` to overwrite an existing benchmark directory.

## Option B: add a benchmark manually

For benchmarks that don't fit the generators (hand-written RTL, sequential circuits, FSMs, etc.), create the directory and files yourself.

### Directory layout

```
benchmarks/<bench_name>/
├── description.txt        # required — natural-language spec, fed to the LLM
├── metadata.json          # required — benchmark id + RTL module name
├── tb.sv                  # required — self-checking SystemVerilog testbench
├── vectors.dat            # optional — test vectors for data-driven testbenches
└── context/               # optional — files copied into the agent workspace
    ├── starting_point.py  #   e.g. a working reference the agent can edit
    └── ...                #   any helper files (Python, Verilog, etc.)
```

Benchmarks can be **nested** in subdirectories for grouping:

```
benchmarks/
├── fp/
│   ├── fpmul_f16/        # --benchmark fp/fpmul_f16  or  --benchmark fpmul_f16
│   └── fpadd_f16/
├── integer/
│   ├── mult8/
│   └── alu8/
└── sequential/
    └── fifo_sync4/
```

`discover_benchmarks()` recursively scans all subdirectories. When specifying `--benchmark`, you can use the leaf directory name (e.g. `fpmul_f16`), the relative path from the benchmarks root (e.g. `fp/fpmul_f16`), or the metadata `name` field. If two nested benchmarks share the same leaf name, use the relative path to disambiguate.

A benchmark is **discovered** only if its directory contains `description.txt`, `metadata.json`, and `tb.sv`. Anything missing one of those three is silently skipped.

### `description.txt`

Plain text. The whole file is embedded verbatim into the LLM system prompt as `## Specification`. Keep it language-neutral — the framework adds language-specific guidance (Verilog / SpireHDL / Amaranth) around it based on `--language`. Include the module name, port widths, and the expected behavior; mention any constraints (e.g. "must support subnormals", "active-low reset"). If you use Verilog/SV literals (`3'b000`, `8'h00`, …) to express behavior, label that section as such (see `benchmarks/alu8/description.txt` for an example).

### `metadata.json`

Minimal schema:

```json
{
  "name": "fpmul_f16",
  "module_name": "my_dut",
  "tb_module": "tb"
}
```

- `name` — benchmark identifier (must equal the directory name).
- `module_name` — the **RTL module under test**. The agent reads this via `Benchmark.module_name` and uses it as `design_top_module`. It must match what `tb.sv` instantiates as `dut`. If the RTL module name happens to equal the benchmark id, set both to the same value.
- `tb_module` — the testbench top (almost always `"tb"`).

Generators may add an extra `"generator": { ... }` block for provenance — that's optional and ignored at runtime.

### `tb.sv`

A self-checking SystemVerilog testbench that:

1. Instantiates the design as `<module_name> dut (...)`. The exact pattern `<name> dut(` is parsed at evaluation time by `batch_eval.py`, so don't rename `dut`.
2. Drives stimuli (either inline patterns or by reading `vectors.dat`).
3. Prints `TB_SUMMARY total=<N> errors=<E>` followed by `PASS` or `$fatal(1, "FAIL")`. The framework greps `TB_SUMMARY` and the final `PASS/FAIL` line to score correctness.

For data-driven testbenches, place the vectors in `vectors.dat` next to `tb.sv` (one test case per line). For self-contained testbenches with hard-coded patterns, `vectors.dat` is unnecessary — see `benchmarks/mult4/tb.sv` for an example.

**Make the stimuli thorough.** The testbench is the agent's *only* **correctness oracle** — the source of truth for *correct* behavior, i.e. the expected outputs each candidate design is checked against. Weak stimuli let a subtly wrong design pass and get rewarded during optimization. Drive a diverse mix of **directed corner cases** (zero, min/max, overflow / carry, all-zeros / all-ones, sign and rounding boundaries, and reset / enable edges for sequential designs) **and** a large batch of **randomized inputs** (typically hundreds to thousands of cases). The more your vectors distinguish correct from incorrect behavior, the more reliable the PASS/FAIL signal — and the harder it is for the agent to "pass" with a broken simplification.

**Where the expected values come from.** A self-checking testbench needs a known-correct oracle. If you have a reference design, use it directly (instantiate it alongside `dut` and compare, or pre-compute outputs from it). If you're starting from only a *specification*, derive the golden behavior yourself: compute it inline for simple/derivable logic, or write a behavioral / Python reference model that emits `vectors.dat` (inputs + expected outputs). No reference is required to author a benchmark — but the expected behavior must come from *somewhere* trustworthy.

Anything in `context/` is copied into the agent's workspace at the start of a run (see `core/runner.py`). Typical contents:

- `starting_point.py` — a known-correct reference design the agent can read and incrementally modify (used by the `fpmul_f16` / `fpadd_f16` benchmarks).
- Helper modules (Python or Verilog) that the reference depends on.
- Subfolders are copied recursively.

Omit the `context/` directory entirely if the benchmark is meant to be solved from scratch with no starting code.

**Important:** if you ship a `context/` directory, mention it explicitly in `description.txt`. The agent does not list its workspace by default — if the spec doesn't tell it the files exist, it will write a fresh design from scratch and ignore them. Append a note like:

> A working starting point is provided: run `starting_point.py` (SpireHDL mode) to generate a correct reference design (`design.v`). Study the context files in your workspace for implementation details, then optimize from there.

Adapt the wording to whatever entry-point and language make sense for your benchmark (`add_benchmark.py` does this automatically when its generators ship context files — see `benchmarks/fpmul_f16/description.txt` for an example).

### Quick check

After creating the files, confirm the benchmark loads and the module name matches the testbench:

```bash
~/pyenv_eda/bin/python -c "
import re
from pathlib import Path
from core.benchmarks import load_benchmark
b = load_benchmark(Path('benchmarks/<bench_name>'))
tb_dut = re.search(r'(\w+)\s+dut\s*\(', b.testbench.read_text()).group(1)
print('module_name:', b.module_name, '| tb dut:', tb_dut, '| match:', b.module_name == tb_dut)
"
```

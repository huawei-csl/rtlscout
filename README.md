<div align="center">
  <img src="imgs/rtlscout_logo_white_800.png" alt="RTL Scout" width="600">
</div>

<br>

# RTL Scout

An RTL design agent powered by pluggable LLM backends (DeepInfra, Claude) with tool use. The agent iteratively creates and optimizes Verilog/SystemVerilog designs, targeting **correctness first, then minimal cost** under a configurable cost metric.

## Getting Started

### Option A: VS Code Dev Container (recommended)

1. Clone this repo with submodules:
   ```bash
   git clone --recurse-submodules <REMOTE>/rtlscout.git
   ```
2. Open the `rtlscout` folder in VS Code.
3. When prompted, click **"Reopen in Container"** (or run the command *Dev Containers: Reopen in Container*).
4. Once the container is up, make sure the VS Code Python interpreter to `~/pyenv_eda/bin/python` (*Python: Select Interpreter* → enter that path).

The Dev Container extension will build the Docker image and start the environment. Edit `.env` with your API keys once inside:
```bash
cp .env.template .env && code .env
```

### Option B: Manual setup

```bash
# 1. Clone this repo with submodules (replace <REMOTE> with your Git remote)
git clone --recurse-submodules <REMOTE>/rtlscout.git
cd rtlscout

# 2. Initialize the spire-hdl submodule
bash .devcontainer/setup_workspace.sh

# 3. Edit .env with your API keys (ANTHROPIC_API_KEY, OPENROUTER_API_KEY, etc.)
cp .env.template .env
vi .env

# 4. Build the Docker image (one-time, takes a while)
bash .devcontainer/build_image.sh

# 5. Start the container (mounts repo, installs packages, drops into shell)
bash .devcontainer/start_container.sh
```

Once inside the container:
```bash
python run_eval.py benchmarks/fpmul_f16/context/starting_point.py \
    --benchmark benchmarks/fpmul_f16 --language spirehdl \
    --cost-metric area --target-delay 500
```

See the [Usage](#usage) section for further commands to run.

### Docker image: full build, slim build, or prebuilt pull

The base EDA image (OpenROAD, Yosys, Verilator, OpenSTA, sv2v, …) is large. Three ways to get it:

- **Full build** (default) — `bash .devcontainer/build_image.sh`. Builds everything from source (~1–2 h the first time; ~54 GB image).
- **Slim build** — `BUILD_SLIM=1 bash .devcontainer/build_image.sh`. Same toolchain, but the final image drops the OpenROAD build tree and the PDK data the flow never reads — **~3 GB instead of ~54 GB** (uses `deps/tech_eval/.devcontainer/Dockerfile.slim`; shares the full build's compile cache).
- **Prebuilt image** (no build) — pull the slim image from GitHub Container Registry:
  ```bash
  docker pull ghcr.io/huawei-csl/rtlscout:slim
  docker tag  ghcr.io/huawei-csl/rtlscout:slim rtlscout:latest   # start_container.sh / the devcontainer expect this tag
  bash .devcontainer/setup_workspace.sh                          # still need the spire-hdl submodule
  bash .devcontainer/start_container.sh
  ```

## Paper Experiments

Step-by-step walkthrough of the FP16 multiplier experiment from the paper:

- [README_fpmul.md](README_fpmul.md) -- FP16 multiplier (fpmul_f16)

## Evaluating a new benchmark (recommended workflow, for SpireHDL)

The multi-stage pipeline with elite-pool seeding consistently produces the best results. Here is a recommended workflow for evaluating a new benchmark, using `my_bench` as an example (replace with your benchmark name, model, and cost metric).

### Step 1: Multi-run agent campaign (no synthesis decorators)

Start with a plain agent campaign — no `@abc_optimized`. Synthesis decorators add complexity that can distract the agent before it has found a good algorithmic baseline. Enable `--arith-autoconfig` so the agent can use `replace_arithmetic_ops()` for automatic arithmetic unit selection. Use `--dont-touch-main-arith` if the benchmark has configurable arithmetic components (MultiplierConfig, AdderConfig) that will be swept in a later stage.

```bash
python run_multistage.py \
    --benchmark my_bench \
    --model claude:claude-opus-4-6 \
    --total-runs 10 --max-concurrent 2 --max-steps 30 \
    --cost-metric area --target-delay 500 \
    --language spirehdl \
    --arith-autoconfig \
    --elite-size 3 --fresh-first 3 \
    --save-workspaces \
    --runs-root runs/my_bench_stage1
```

Key flags:
- `--total-runs 10`: 10 independent agent runs with elite-pool seeding.
- `--fresh-first 3`: the first 3 runs start from scratch (no seed), the rest sample from the elite pool of best-so-far designs.
- `--save-workspaces`: saves a snapshot of the workspace after each evaluation step (needed for `extract_pareto.py` later).
- Omit `--dont-touch-main-arith` if you want the agent to freely explore all design parameters.

### Step 2: Seeded campaign with synthesis optimization

Seed from the best designs of Step 1, now with `@abc_optimized` enabled. Fewer runs are needed since the agent starts from a strong baseline.

```bash
python run_multistage.py \
    --benchmark my_bench \
    --model claude:claude-opus-4-6 \
    --total-runs 6 --max-concurrent 1 --max-steps 30 \
    --cost-metric area --target-delay 500 \
    --language spirehdl \
    --arith-autoconfig \
    --abc-optimize \
    --elite-size 3 \
    --seed-from runs/my_bench_stage1 \
    --save-workspaces \
    --runs-root runs/my_bench_stage2
```

Key differences from Step 1:
- `--seed-from runs/my_bench_stage1`: seeds the elite pool from the best designs of the first campaign.
- `--abc-optimize`: the agent now has access to synthesis optimization decorators.
- `--max-concurrent 1`: Synthesis optimization runs are heavier; sequential execution avoids resource contention.
- Fewer runs (`--total-runs 6`) since we're refining, not exploring from scratch.

### Step 3: Extract Pareto front and plot results

**Plot per-run cost evolution** (one chart per campaign):

```bash
python plot_results.py --input runs/my_bench_stage1
python plot_results.py --input runs/my_bench_stage2
```

**Extract Pareto-optimal designs** (area vs delay) from both campaigns:

```bash
python extract_pareto.py \
    runs/my_bench_stage1 runs/my_bench_stage2 \
    -o pareto_fronts/my_bench \
    --separate-dirs -n 20
```

This aggregates all evaluations from both campaigns, computes the Pareto front, and extracts up to 20 designs (Pareto-optimal first, then best-scored non-Pareto designs).

**Plot the Pareto front** (paper-quality area vs delay scatter):

```bash
python plot_pareto_paper.py \
    --compare pareto_fronts/my_bench runs/my_bench_stage1 \
    -o plots/my_bench/ \
    --label-a "With ABC" --label-b "Without"
```

Or plot a single campaign's multistage evolution:

```bash
python plot_pareto_paper.py runs/my_bench_stage1 -o plots/my_bench/
```

### Tips

- **Cost metric choice**: `area` is the most common objective. Use `delay` for timing-critical designs, or run both and combine with `extract_pareto.py`.
- **Target delay**: affects the synthesis timing constraint. Lower values push the synthesizer toward faster logic (often at the cost of area). Experiment with different values (200–2000 ps).
- **Model choice**: Claude Opus produces the best results but is slower and more expensive. Claude Sonnet is a good alternative for initial exploration or larger run counts.
- **Step budget**: `--max-steps 30` gives the agent enough room to iterate. For simpler benchmarks (e.g. 8-bit multipliers), `--max-steps 15-20` may suffice.

## Agent flow

```
                        ┌──────────────────────┐
                        │   System prompt      │
                        │  (spec + cost metric │
                        │   + tool docs)       │
                        └─────────┬────────────┘
                                  │
                                  v
                   ┌──────────────────────────────┐
                   │         LLM generates        │
                   │    response + tool calls     │
                   └──────────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              v                   v                   v
     ┌────────────────┐  ┌───────────────┐  ┌────────────────┐
     │  File tools    │  │ run_evaluation│  │     done       │
     │  create_file   │  │               │  │  (final eval)  │
     │  replace_file  │  │  ┌─────────┐  │  └───────┬────────┘
     │  apply_diff    │  │  │SpireHDL │  │          │
     │  read_file     │  │  │compile  │  │          │
     │  ls            │  │  │(if flag)│  │          v
     └────────┬───────┘  │  └────┬────┘  │    ┌───────────┐
              │          │       v       │    │  Result   │
              │          │  ┌─────────┐  │    │ best_cost │
              │          │  │Verilator│  │    │ best_eval │
              │          │  │lint+sim │  │    └───────────┘
              │          │  └────┬────┘  │
              │          │       v       │
              │          │  ┌─────────┐  │
              │          │  │  Yosys  │  │
              │          │  │  cost   │  │
              │          │  └────┬────┘  │
              │          │       v       │
              │          │  Summary:     │
              │          │  pass/fail +  │
              │          │  cost value   │
              │          └───────┬───────┘
              │                  │
              └─────────┬────────┘
                        │
                        v
               ┌────────────────┐    100% correct     ┌──────────────┐
               │ Tool result    │───& lower cost? ───>│ Track best   │
               │ fed back to LLM│                     │ best_design/ │
               └────────┬───────┘                     └──────────────┘
                        │
                        v
                 ┌────────────────┐
                 │ Next step      │──── until done or max_steps
                 └────────────────┘
```

**Strategy**: the LLM is instructed to (1) build a simple correct design first, (2) run evaluation, (3) once 100% correct, iteratively optimize to reduce the cost metric, reverting if correctness breaks.

## Architecture

```
core/
├── prompts.py       # System prompt builders (Verilog + SpireHDL)
├── correctness.py   # Verilator lint + simulation
├── cost.py          # Pluggable cost metrics (transistors, PPA delay/area/power)
├── evaluation.py    # Combines correctness + cost
├── agent.py         # Tool-use agent (7 tools)
├── llm_client.py    # LLM backends (DeepInfra, Claude)
├── benchmarks.py    # Benchmark loading
└── runner.py        # Orchestration (model x benchmark)

benchmarks/          # benchmark suite (one dir per benchmark)
run_benchmark.py     # CLI: single benchmark + model
run_model.py         # CLI: all benchmarks for one model
run_sweep.py         # CLI: multiple models x benchmarks
run_multistage.py    # CLI: async elite-pool multi-stage optimisation
run_eval.py          # CLI: re-evaluate a design file
plot_results.py      # CLI: plotting at any level
```

### Agent tools

| Tool | Description |
|------|-------------|
| `create_file` | Create a new file |
| `replace_file` | Overwrite an existing file |
| `apply_diff` | Apply a unified diff patch |
| `ls` | List files in working directory |
| `read_file` | Read file contents |
| `run_evaluation` | Run correctness (Verilator) + cost evaluation |
| `done` | Signal completion |

### Evaluation

The `run_evaluation` tool returns both:
- **Correctness**: Verilator lint + simulation against a self-checking testbench (pass/fail per TB_CASE)
- **Cost**: Pluggable metric (see below)

The agent is instructed to get 100% correctness first with a simple design, then iterate to reduce cost. The **best result** is the lowest cost among fully correct designs. The best design's workspace is automatically saved to `best_design/` for later use.

## Cost metrics

The cost metric is configurable via `--cost-metric`. All metrics follow the same interface (`CostMetric` ABC) and the metric name propagates automatically into system prompts, JSON output, and plot labels.

| Metric | `--cost-metric` | Tool chain | Description |
|--------|-----------------|------------|-------------|
| Transistors | `transistors` (default) | Yosys + ABC | Estimated transistor count via `stat -tech cmos` |
| Yosys cells | `yosys_cells` | Yosys | Cell count after `synth; clean -purge; stat` (technology-independent) |
| Yosys wires | `yosys_wires` | Yosys | Wire count after `synth; clean -purge; stat` (technology-independent) |
| Yosys transistors | `yosys_transistors` | Yosys | Transistor count from the same `synth; clean -purge; stat` pipeline (hierarchy-correct; matches `yosys_cells`/`yosys_wires` on multi-module designs) |
| Delay | `delay` | Yosys + OpenROAD STA | Critical-path delay (ns) |
| Area | `area` | Yosys + OpenROAD STA | Design area (um²) |
| Power | `power` | Yosys + OpenROAD STA | Total power (W) |
| AIG count | `aig_count` | Yosys + spirehdl/aigverse | Post-optimization AIG AND-node count (`aig.size()`), combinational designs only |
| AIG depth | `aig_depth` | Yosys + spirehdl/aigverse | Post-optimization AIG logic depth (`DepthAig.num_levels()`), combinational designs only |

**Transistors / yosys_cells / yosys_wires / yosys_transistors** use fast Yosys-only flows (technology-independent). The `yosys_cells` / `yosys_wires` / `yosys_transistors` variants skip ABC and instead run `synth; clean -purge; stat` — `clean -purge` drops public-alias buffers that `opt_clean` preserves for debuggability, giving counts that more faithfully reflect the netlist. **Delay/area/power** use the `tech_eval` package which synthesizes against a standard cell library (nangate45) and runs OpenROAD static timing analysis. PPA metrics require designs with a `clk` port. **aig_count / aig_depth** measure the And-Inverter Graph after spirehdl's aigverse optimization (yosys `aigmap` → aigverse); combinational designs only.

For PPA metrics, the `--target-delay` flag (in ps) controls the synthesis timing constraint. Lower values push for faster designs at the expense of area/power.

## Usage

### Run a single benchmark

```bash
# Default: transistor cost, DeepInfra provider
python run_benchmark.py --benchmark simple_adder

# With explicit options
python run_benchmark.py \
  --benchmark alu8 \
  --model meta-llama/Llama-3.3-70B-Instruct-Turbo \
  --max-steps 15 \
  --runs-dir runs
```

### Using different cost metrics

```bash
# Optimize for area (PPA)
python run_benchmark.py \
  --benchmark fifo_sync4 \
  --cost-metric area \
  --target-delay 500

# Optimize for delay (PPA)
python run_benchmark.py \
  --benchmark alu8 \
  --cost-metric delay \
  --target-delay 300

# Optimize for power (PPA)
python run_benchmark.py \
  --benchmark seq_detector \
  --cost-metric power \
  --target-delay 500
```

### Using SpireHDL

The `--language spirehdl` flag switches the agent from writing Verilog directly to writing Python scripts using the SpireHDL embedded DSL. The framework runs the `.py` file; the script writes Verilog directly via `m.to_verilog_file("design.v")`, and the resulting file is evaluated as usual.

The agent's working directory is on the Python path, so the agent can split logic across multiple `.py` files and use plain imports (e.g. `from helper import build_adder`). The main entry point passed to `run_evaluation` (e.g. `design.py`) is the only file that gets executed by the framework.

```bash
python run_benchmark.py \
  --model deepinfra:deepseek-ai/DeepSeek-V3.2 \
  --benchmark mult8 \
  --language spirehdl \
  --max-steps 65 \
  --cost-metric delay
```

### SpireHDL optimize cache propagation

 `@abc_optimized` populates a content-addressed disk cache at `<workspace>/.spirehdl_cache/` (SHA of AIG + decorator kwargs). Cache reuse across the various execution seams is:

| Seam | Cached? |
|:---|:---:|
| Step → step (same agent) | ✓ |
| Seeded agent ← earlier elite best (inside one `run_multistage`) | ✓ |
| Phase 1 → phase 2 (`rtl_rewriter_multirun.py`'s chained phases) | ✓ |
| Multirun → multirun via `--seed-from <multistage_summary.json>` | ✓ |
| Fresh agent (empty elite pool, or `p_fresh` coin flip) | ✗ |
| Multirun → multirun via `--seed-from <pareto_front.json>` (extract format) | ✗ |

The propagation lives in `core.multistage.build_seed_context`, which whitelists `.spirehdl_cache/` when copying a seeding predecessor's `best_design/` into the seeded agent's context.

**Fresh agents don't inherit any cache** — by design. `core.multistage._make_task` (the fresh/seeded dispatch) skips `build_seed_context` entirely when the pool is empty or the `p_fresh` coin flip fires, so a fresh agent always starts from the benchmark's raw `context/` folder with a cold cache. This is intentional: fresh agents are the exploration arm and should not be biased by prior exploitation work.

**Extract-format seeds don't carry a cache.** `_prepare_extract_seed_dir` (`core/multistage.py:207`) only copies the single extracted `.v`/`.py` file referenced by a `pareto_front.json` / `best_designs.json` entry — it never looks at a sibling `.spirehdl_cache/`. Matters only if you ever run `run_multistage.py --seed-from <pareto_front.json>` (the extract-format seed path). Workaround: convert to `multistage_summary.json` format, or pre-warm by setting `SPIREHDL_CACHE_DIR` via env to a shared location before the run.

### Saving evaluation snapshots

Use `--save-workspaces` to save the workspace, evaluation result, and summary after each evaluation. Snapshots are stored as `eval_1/`, `eval_2/`, etc. alongside the run's `best_design/` and `result.json`. Each `eval_{i}/` contains:
- `workspace/` — copy of the design files at that step
- `result.json` — full evaluation result (correctness, cost, pass rate)
- `summary.txt` — human-readable evaluation summary

```bash
python run_benchmark.py \
  --model deepinfra:deepseek-ai/DeepSeek-V3.2 \
  --benchmark mult8 \
  --language spirehdl \
  --max-steps 65 \
  --cost-metric delay \
  --save-workspaces
```

### Using different LLM providers

```bash
# Claude
python run_benchmark.py \
  --benchmark alu8 \
  --model claude:claude-sonnet-4-5-20250929

# DeepInfra (default)
python run_benchmark.py \
  --benchmark alu8 \
  --model meta-llama/Llama-3.3-70B-Instruct-Turbo

# Mixed providers in a sweep
python run_sweep.py \
  --models claude:claude-sonnet-4-5-20250929 meta-llama/Llama-3.3-70B-Instruct-Turbo
```

### Run all benchmarks for a model

```bash
python run_model.py --model meta-llama/Llama-3.3-70B-Instruct-Turbo
```

Run a subset of benchmarks:

```bash
python run_model.py \
  --model Qwen/Qwen2.5-72B-Instruct \
  --benchmarks simple_adder simple_mux alu8
```

### Sweep across models and benchmarks

```bash
# Sweep with default transistor cost
python run_sweep.py \
  --models meta-llama/Llama-3.3-70B-Instruct-Turbo Qwen/Qwen2.5-72B-Instruct \
  --benchmarks simple_adder simple_mux

# Sweep with area cost
python run_sweep.py \
  --models meta-llama/Llama-3.3-70B-Instruct-Turbo Qwen/Qwen2.5-72B-Instruct \
  --cost-metric area \
  --target-delay 500 \
  --max-steps 20
```

### Multi-stage optimisation

Run multiple agents in parallel with an evolving elite pool of best designs. See [README_multistage.md](README_multistage.md) for full documentation.

```bash
python run_multistage.py \
    --benchmark fpmul_f16 \
    --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
    --total-runs 10 --max-concurrent 4 --max-steps 30 \
    --cost-metric delay --language spirehdl
```

### Re-evaluate a design

Use `run_eval.py` to re-run the evaluation pipeline on an existing design file (e.g. from a previous run). Useful for testing with updated testbenches or different cost metrics.

```bash
# Basic: evaluate a SpireHDL design (language auto-detected from .py extension)
python run_eval.py runs/fpmul_f16/claude-opus-4-6/20260311_140923/best_design/workspace/design.py

# Explicit language + cost metric
python run_eval.py runs/.../workspace/design.py --cost-metric delay --target-delay 500

# Use testbench from the original benchmark directory (e.g. after regenerating test vectors)
python run_eval.py runs/.../best_design/workspace/design.py --benchmark benchmarks/fpmul_f16

# Output as JSON
python run_eval.py runs/.../workspace/design.py --json

Flags:
- `--language` — `verilog`, `spirehdl`, or `amaranth` (default: auto-detect from extension)
- `--cost-metric` — any registered metric (`transistors`, `delay`, `area`, `power`)
- `--target-delay` — synthesis timing constraint in ps (default: 500)
- `--top-module` — override top module name (default: auto-detect from `design.v`)
- `--workdir` — override workspace directory (default: parent of design file)
- `--benchmark` — copy `tb.sv` and `vectors.dat` from this benchmark directory into the workspace before evaluation
- `--json` — print result as JSON instead of human-readable summary

### Extract best designs

Extract the top N passing designs from any run directory (multistage or single benchmark), sorted by a chosen metric.

```bash
# Top 5 by cost (default)
python extract_best_designs.py runs/multistage_20260316_143944 -n 5 -o best_5/

# Top 3 sorted by delay
python extract_best_designs.py runs/mult8 -n 3 --sort-by delay -o best_delay/
```

Flags:
- `-n` / `--top` — number of designs to extract (default: 5)
- `-o` / `--output` — output directory (default: `<run_dir>/best_extracted`)
- `--sort-by` — metric to sort by: `cost` (default), `area`, `delay`, `power`

Output includes the design files and a `best_designs.json` manifest linking each file back to its original eval.

### Extract Pareto-optimal designs

Extract designs on the area-vs-delay Pareto front. A design is Pareto-optimal if no other design is strictly better in both area and delay.

```bash
python extract_pareto.py runs/multistage_20260316_143944 -o pareto_front/
```

Flags:
- `-o` / `--output` — output directory (default: `<run_dir>/pareto_front`)

Output includes the design files and a `pareto_front.json` manifest with full PPA metrics.

### Plot results

The plotting script auto-detects the level from the JSON structure. Axis labels and titles adapt to whichever cost metric was used.

```bash
# Benchmark level (step-by-step cost + pass rate)
python plot_results.py --input runs/<benchmark>/<model>/<timestamp>/result.json

# Model level (pass/fail + cost per benchmark)
python plot_results.py --input runs/<dir>/summary_<model>.json

# Sweep level (pass rate heatmap + cost comparison across models)
python plot_results.py --input runs/<dir>/all_results.json
```

Use `--no-accuracy` to hide the pass-rate secondary axis in benchmark plots. Pass rate is instead encoded in bar color (green = 100% correct, yellow = partial, orange = failed), with cross markers and percentage labels for non-passing evaluations:

```bash
python plot_results.py --input runs/.../result.json --no-accuracy
```

Override output directory:

```bash
python plot_results.py --input runs/sweep/all_results.json --output-dir my_plots/
```

## Benchmarks

| Benchmark | Module | Description |
|-----------|--------|-------------|
| `simple_adder` | `adder` | 8-bit addition (mod 256) |
| `simple_mux` | `mux2` | 2-to-1 8-bit multiplexer |
| `parity_even` | `parity8` | Even parity detection |
| `alu8` | `alu8` | 8-bit ALU with 8 operations |
| `register_enable` | `reg_en` | 8-bit register with enable + sync reset |
| `seq_detector` | `seq_det` | 1011 sequence detector |
| `fifo_sync4` | `fifo_sync4` | 4-entry synchronous FIFO |

Each benchmark lives in `benchmarks/<name>/` and has the files described in the next section.

## Adding a benchmark

For a worked example of integrating an external benchmark suite (including Verilog and SpireHDL variants, test-vector generation, and the `sky130_adp` cost metric), see [`benchmarks/turbo_rtl/README.md`](benchmarks/turbo_rtl/README.md).

### Option A: generate from spire-hdl

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

### Option B: add a benchmark manually

For benchmarks that don't fit the generators (hand-written RTL, sequential circuits, FSMs, etc.), create the directory and files yourself.

#### Directory layout

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

#### `description.txt`

Plain text. The whole file is embedded verbatim into the LLM system prompt as `## Specification`. Keep it language-neutral — the framework adds language-specific guidance (Verilog / SpireHDL / Amaranth) around it based on `--language`. Include the module name, port widths, and the expected behavior; mention any constraints (e.g. "must support subnormals", "active-low reset"). If you use Verilog/SV literals (`3'b000`, `8'h00`, …) to express behavior, label that section as such (see `benchmarks/alu8/description.txt` for an example).

#### `metadata.json`

Minimal schema:

```json
{
  "name": "my_bench",
  "module_name": "my_dut",
  "tb_module": "tb"
}
```

- `name` — benchmark identifier (must equal the directory name).
- `module_name` — the **RTL module under test**. The agent reads this via `Benchmark.module_name` and uses it as `design_top_module`. It must match what `tb.sv` instantiates as `dut`. If the RTL module name happens to equal the benchmark id, set both to the same value.
- `tb_module` — the testbench top (almost always `"tb"`).

Generators may add an extra `"generator": { ... }` block for provenance — that's optional and ignored at runtime.

#### `tb.sv`

A self-checking SystemVerilog testbench that:

1. Instantiates the design as `<module_name> dut (...)`. The exact pattern `<name> dut(` is parsed at evaluation time by `batch_eval.py`, so don't rename `dut`.
2. Drives stimuli (either inline patterns or by reading `vectors.dat`).
3. Prints `TB_SUMMARY total=<N> errors=<E>` followed by `PASS` or `$fatal(1, "FAIL")`. The framework greps `TB_SUMMARY` and the final `PASS/FAIL` line to score correctness.

For data-driven testbenches, place the vectors in `vectors.dat` next to `tb.sv` (one test case per line). For self-contained testbenches with hard-coded patterns, `vectors.dat` is unnecessary — see `benchmarks/mult4/tb.sv` for an example.

#### `context/` (optional)

Anything in `context/` is copied into the agent's workspace at the start of a run (see `core/runner.py`). Typical contents:

- `starting_point.py` — a known-correct reference design the agent can read and incrementally modify (used by the `fpmul_f16` / `fpadd_f16` benchmarks).
- Helper modules (Python or Verilog) that the reference depends on.
- Subfolders are copied recursively.

Omit the `context/` directory entirely if the benchmark is meant to be solved from scratch with no starting code.

**Important:** if you ship a `context/` directory, mention it explicitly in `description.txt`. The agent does not list its workspace by default — if the spec doesn't tell it the files exist, it will write a fresh design from scratch and ignore them. Append a note like:

> A working starting point is provided: run `starting_point.py` (SpireHDL mode) to generate a correct reference design (`design.v`). Study the context files in your workspace for implementation details, then optimize from there.

Adapt the wording to whatever entry-point and language make sense for your benchmark (`add_benchmark.py` does this automatically when its generators ship context files — see `benchmarks/fpmul_f16/description.txt` for an example).

#### Quick check

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

## Output format

Results are stored as JSON in the `runs/` directory:

- **Benchmark level** (`result.json`): per-step evaluation results, best cost, cost metric name, pass/fail
- **Model level** (`summary_<model>.json`): per-benchmark pass/fail + cost values
- **Sweep level** (`all_results.json`): all model results combined

The best design from each benchmark run is saved in `best_design/` within the run directory, with a `_best_meta.json` file recording the step, cost value, and metric used.

## Adding a custom cost metric

Subclass `CostMetric` in `cost.py`:

```python
from core.cost import CostMetric, CostResult

class MyCost(CostMetric):
    @property
    def metric_name(self) -> str:
        return "my_metric"

    def evaluate(self, workdir, top_module=None) -> CostResult:
        # Your evaluation logic here
        return CostResult(ok=True, value=42.0, stats={})
```

Then register it in `COST_METRICS` and `make_cost_metric()`, or pass it directly to `RTLAgent(cost_metric=MyCost())`.

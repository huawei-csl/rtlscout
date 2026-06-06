# FP16 Multiplier (`fpmul_f16`) Pipeline

Reproduces the main `fpmul_f16` results from the paper. The full pipeline has four phases
(agentic code optimization → agentic synthesis optimization → arithmetic architecture sweep →
optional high-effort gate-level refinement); the Pareto-optimal designs of each phase seed the next.

**This document covers the two agentic phases** (1 and 2) and **references the architecture sweep**
(Phase 3) via its entry point in `tech_eval`. The optional high-effort refinement (Phase 4) is
omitted here for now.

## Benchmark

- Module: `fp_mul_e5f10` — IEEE-754 FP16 (1 sign, 5 exponent, 10 fraction bits, with subnormals)
- Testbench: `benchmarks/fpmul_f16/tb.sv`
- Starting point: `benchmarks/fpmul_f16/context/starting_point.py`
- Baseline PPA (ASAP7): area ≈ 84 µm², delay ≈ 1458 ps

## Environment

All commands run from the repo root unless noted.

```bash
source ~/pyenv_eda/bin/activate
cd /workspaces/rtl_scout
```

---

## Phase 1: Agentic code optimization (no synthesis backend)

Multiple sequential agent runs with an elite pool: each run starts from the best designs of
previous runs. The agent rewrites the SpireHDL/RTL source (structural and algorithmic changes)
but keeps multiplication and addition as plain `*` and `+` operators — their replacement is
deferred to the Phase 3 architecture sweep. Two campaigns are run, one targeting **area** and one
targeting **delay**, and the resulting Pareto-optimal designs are pooled.

### 1.1 Area campaign

```bash
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model claude:claude-sonnet-4-6 \
    --total-runs 12 --max-concurrent 4 --max-steps 30 \
    --cost-metric area --target-delay 500 \
    --language spirehdl \
    --dont-touch-main-arith \
    --elite-size 2 --fresh-first 4
```

Output: `runs/multirun_<AREA_TS>/` (note the timestamp for later steps).

### 1.2 Delay campaign

```bash
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model claude:claude-opus-4-6 \
    --total-runs 6 --max-concurrent 2 --max-steps 30 \
    --cost-metric delay --target-delay 500 \
    --language spirehdl \
    --dont-touch-main-arith \
    --elite-size 2 --fresh-first 3
```

Output: `runs/multirun_<DELAY_TS>/`.

### 1.3 Plot cost evolution + Pareto scatter

```bash
python plot_pareto_paper.py runs/multirun_<AREA_TS> -o images/
python plot_pareto_paper.py --side-by-side-combined \
    runs/multirun_<AREA_TS> runs/multirun_<DELAY_TS> \
    --label-a "Area target" --label-b "Delay target" -o images/
```

### 1.4 Extract the Phase 1 Pareto front (ablation baseline)

```bash
python extract_pareto.py \
    runs/multirun_<AREA_TS> \
    runs/multirun_<DELAY_TS> \
    --benchmark fpmul_f16 --no-flowy \
    -o pareto_fronts/fpmul_f16 --separate-dirs
```

Output: `pareto_fronts/fpmul_f16/pareto_front.json` + `design_000/`, `design_001/`, …

---

## Phase 2: Agentic synthesis optimization (`@abc_optimized` / `@flowy_optimized`)

Extends Phase 1: the agent additionally annotates logic subcircuits with a synthesis-optimization
decorator that triggers compile-time AIG rewriting, reaching locally-optimal Boolean forms that
source-level changes cannot. Runs are **seeded from the Phase 1 elite pool** and use fewer total
runs (synthesis optimization adds per-compile overhead).

Two backends are available:

| Decorator | Flag | Backend | Available here? |
|-----------|------|---------|-----------------|
| `@abc_optimized` | `--abc-optimize` | ABC `&deepsyn`, run **through Yosys** (decorator lives in spire-hdl) | ✅ **yes** — only Yosys is needed (in the base image) |
| `@flowy_optimized` | `--flowy-optimize` | Mockturtle MIG synthesis explorer (the paper's `@mockturtle_optimized`) | ⚠️ requires the Mockturtle/Flowy backend + `flowy_config.json`, **not bundled in this release** |

The commands below use **`--abc-optimize`**, which runs out-of-the-box in this release. To
reproduce the paper's Mockturtle results, swap `--abc-optimize` → `--flowy-optimize` once the
Flowy/Mockturtle backend is installed (see the paper for parameters; default 50 chains × 30 steps).

### 2.1 Area + synthesis-optimization campaign

```bash
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model claude:claude-opus-4-6 \
    --total-runs 6 --max-concurrent 2 --max-steps 30 \
    --cost-metric area --target-delay 500 \
    --language spirehdl \
    --abc-optimize \
    --dont-touch-main-arith \
    --elite-size 2 --fresh-first 3 \
    --seed-from runs/multirun_<AREA_TS>
```

Output: `runs/multirun_<ABC_AREA_TS>/`.

### 2.2 Delay + synthesis-optimization campaign

```bash
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model claude:claude-opus-4-6 \
    --total-runs 4 --max-concurrent 1 --max-steps 30 \
    --cost-metric delay --target-delay 500 \
    --language spirehdl \
    --abc-optimize \
    --dont-touch-main-arith \
    --elite-size 2 \
    --seed-from runs/multirun_<DELAY_TS>
```

Output: `runs/multirun_<ABC_DELAY_TS>/`.

### 2.3 Extract combined Pareto front (Phase 1 + Phase 2)

```bash
python extract_pareto.py \
    runs/multirun_<AREA_TS> \
    runs/multirun_<DELAY_TS> \
    runs/multirun_<ABC_AREA_TS> \
    runs/multirun_<ABC_DELAY_TS> \
    -o pareto_fronts/fpmul_f16_phase2 --separate-dirs
```

Output: `pareto_fronts/fpmul_f16_phase2/pareto_front.json` + design directories. This Pareto front
is the input to the Phase 3 architecture sweep.

---

## Phase 3: Arithmetic architecture sweep (reference)

Phase 3 replaces the core mantissa multiplier and exponent adder with structurally decomposed
arithmetic units from a library — sweeping partial-product accumulation trees (Wallace, Dadda, …)
× prefix adders (Kogge–Stone, Brent–Kung, Sklansky, ripple-carry, sparse Kogge–Stone) × target
delays over the Pareto designs from Phase 2.

The sweep is implemented in `tech_eval`; run it via its entry point rather than from this repo:

- **Script:** [`deps/tech_eval/src/tech_eval/ppa_extract/sweeps/fpmul/fpmul_sweep_mp.py`](deps/tech_eval/src/tech_eval/ppa_extract/sweeps/fpmul/fpmul_sweep_mp.py)

```bash
cd deps/tech_eval

# Point the sweep at the Phase 2 Pareto designs (folders matching pareto_*/design_NNN/):
python -m tech_eval.ppa_extract.sweeps.fpmul.fpmul_sweep_mp \
    --references-dir /workspaces/rtl_scout/pareto_fronts
```

Output: `deps/tech_eval/results/ppa/FpMul_e5f10_results.json` (one entry per design × arithmetic
configuration × target delay).

---

*Phase 4 (optional high-effort gate-level refinement of the sweep Pareto designs) is omitted from
this document for now.*

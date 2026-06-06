# Multi-Run Parallel Optimisation

An async elite-pool optimisation loop on top of the single-run agent. Multiple agents run in parallel on the same benchmark. An **elite pool** of the best designs evolves continuously — when an agent finishes, the pool is updated and a new agent is immediately spawned, either seeded from the pool (exploitation) or starting fresh (exploration).

```
                    ┌─────────────┐
                    │  Elite Pool │  (top-K designs, sorted by cost)
                    │  + summaries│
                    └──────┬──────┘
                           │ sample (softmax) or fresh start
              ┌────────────┼────────────┐
              v            v            v
         ┌─────────┐ ┌─────────┐ ┌─────────┐
         │ Agent 0 │ │ Agent 1 │ │ Agent 2 │  ... up to W workers
         └────┬────┘ └────┬────┘ └────┬────┘
              │            │            │
              v            v            v
         on completion: update elite pool, spawn next agent
         until total_runs budget exhausted
```

No rounds, no idle time. Agents that finish fast immediately feed the pool and free a slot for the next agent.

## Quick start

```bash
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
    --total-runs 10 --max-concurrent 4 --max-steps 30 \
    --cost-metric delay --language spirehdl
```

## How it works

### 1. Elite pool

The pool holds at most K (default 5) passing designs, sorted by cost. When an agent finishes with a 100%-correct design whose cost is lower than the worst entry in the pool, it replaces that entry. Each entry stores:

- The cost value and metric
- Path to the `best_design/` directory (the design files)
- The agent's `summary.txt` (lessons learned, truncated to 500 chars)

### 2. Seeding

When a new agent is spawned and the pool is non-empty, it can be **seeded** with a design sampled from the pool. The seed design files are copied into the agent's workspace (prefixed `seed_*`), and the system prompt tells the agent:

> *A verified correct design has been placed in your workspace as `seed_design.py` with cost 1618 delay. Start by reading this design and evaluating it, then try to improve it.*

All pool entries' summaries are also injected, so the agent knows what approaches worked and what didn't.

### 3. Softmax sampling (z-score normalised)

When sampling from the pool, costs are normalised to z-scores before applying the softmax temperature. This makes the temperature parameter **scale-independent** — it works the same whether costs are in ps (1618) or transistors (2688).

```
z_i = (cost_i - mean) / std
p_i = exp(-z_i / T) / Σ exp(-z_j / T)
```

Lower cost → higher probability. The temperature T controls the exploration/exploitation trade-off:

**Example**: pool with costs [1618, 1620, 1650]

| Temperature | P(1618) | P(1620) | P(1650) | Behaviour |
|-------------|---------|---------|---------|-----------|
| 0.5         | 56.4%   | 42.9%   | 0.7%    | Greedy — almost always picks the best |
| 1.0         | 50.4%   | 44.0%   | 5.7%    | Balanced (default) |
| 2.0         | 44.1%   | 41.2%   | 14.8%   | Exploratory — gives worse designs a chance |

These probabilities are identical for costs [2688, 2700, 3000] (transistor scale) because the z-score normalisation removes the absolute scale. When all costs are equal, sampling is uniform regardless of temperature.

### 4. Fresh start probability (exploration decay)

Each time a new agent is spawned, it starts fresh (no seed) with probability:

```
p_fresh = max(fresh_min, fresh_base * (1 - completed / total_runs))
```

When the elite pool is empty (no passing designs yet), agents always start fresh.

**Example**: defaults `fresh_base=0.5`, `fresh_min=0.1`, `total_runs=10`

| Completed | p_fresh | Interpretation |
|-----------|---------|----------------|
| 0         | 0.50    | First agents: coin flip between fresh and seeded |
| 1         | 0.45    | |
| 2         | 0.40    | |
| 3         | 0.35    | Shifting toward exploitation |
| 4         | 0.30    | |
| 5         | 0.25    | |
| 6         | 0.20    | |
| 7         | 0.15    | Mostly seeded now |
| 8         | 0.10    | Floor reached |
| 9         | 0.10    | 10% exploration maintained until the end |

Fresh agents still receive the pool summaries (what worked / what failed) but don't get a seed design file. They're instructed to try a different approach.

### 5. Numerical walk-through

Suppose `total_runs=10`, `max_concurrent=3`, `elite_size=3`, defaults otherwise:

| Event | Pool state | Action |
|-------|-----------|--------|
| Start | empty | Submit agents 0, 1, 2 — all fresh (pool empty) |
| Agent 0 finishes: PASS, cost=1618 | [1618] | Pool updated. Submit agent 3: p_fresh=0.35, pool has 1 entry → likely seeded from 1618 |
| Agent 2 finishes: FAIL | [1618] | No pool change. Submit agent 4: p_fresh=0.30 |
| Agent 1 finishes: PASS, cost=1600 | [1600, 1618] | Pool updated, new best! Submit agent 5: p_fresh=0.25, softmax samples from {1600, 1618} |
| Agent 3 finishes: PASS, cost=1580 | [1580, 1600, 1618] | Pool full (3 entries). Submit agent 6: p_fresh=0.20 |
| Agent 5 finishes: PASS, cost=1550 | [1550, 1580, 1600] | Replaces worst (1618). Submit agent 7: p_fresh=0.15 |
| Agent 4 finishes: PASS, cost=1590 | [1550, 1580, 1590] | Replaces worst (1600). Submit agent 8: p_fresh=0.10 |
| Agent 6 finishes: PASS, cost=1560 | [1550, 1560, 1580] | Replaces worst (1590). Submit agent 9: p_fresh=0.10 |
| Agents 7, 8, 9 finish | ... | Pool keeps evolving. No new agents (budget exhausted). |

The pool converges toward better designs. Agents that start fresh occasionally find novel approaches that break out of local minima.

## CLI reference

```
python run_multirun.py [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--benchmark` | (required) | Benchmark name |
| `--model` | (required) | Provider:model spec (e.g. `deepinfra:MiniMaxAI/MiniMax-M2.5`) |
| `--total-runs` | 10 | Total agent runs to complete |
| `--max-concurrent` | 4 | Max parallel agents |
| `--max-steps` | 30 | Max steps per agent |
| `--elite-size` | 5 | Max designs in elite pool |
| `--temperature` | 1.0 | Softmax temperature (higher = more exploratory) |
| `--fresh-base` | 0.5 | Initial fresh-start probability |
| `--fresh-min` | 0.1 | Minimum fresh-start probability |
| `--fresh-first` | 0 | Force the first N runs to start fresh (ignores pool and `p_fresh`). After N runs, the normal probability formula kicks in |
| `--cost-metric` | transistors | Cost metric (`transistors`, `delay`, `area`, `power`) |
| `--target-delay` | 500 | PPA synthesis target delay (ps) |
| `--language` | verilog | `verilog`, `spirehdl`, or `amaranth` |
| `--runs-root` | auto | Output directory (default: `runs/multirun_<timestamp>`) |
| `--seed-from` | none | Path to a previous `multirun_summary.json` or its directory to seed the elite pool |
| `--flowy-optimize` | off | Enable `@flowy_optimized` decorator guidance in system prompt (SpireHDL only). Requires Flowy/Mockturtle/ABC installed — see `docs/flowy_setup.md` |

## Resuming from a previous run

Use `--seed-from` to pre-populate the elite pool with passing designs from a prior multirun run. The new run starts with a warm pool, so agents can be seeded immediately instead of all starting fresh.

```bash
# Point at the summary JSON
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
    --total-runs 10 --max-concurrent 4 --max-steps 30 \
    --cost-metric delay --language spirehdl \
    --seed-from runs/multirun_20260312_163540/multirun_summary.json

# Or point at the directory (auto-finds multirun_summary.json)
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
    --total-runs 10 --max-concurrent 4 --max-steps 30 \
    --cost-metric delay --language spirehdl \
    --seed-from runs/multirun_20260312_163540/
```

You can also seed from the output of `extract_pareto.py` or `extract_best_designs.py`:

```bash
# Seed from Pareto-optimal designs
python run_multirun.py \
    --benchmark fpmul_f16 \
    --model deepinfra:MiniMaxAI/MiniMax-M2.5 \
    --total-runs 10 --max-concurrent 4 --max-steps 30 \
    --cost-metric area --language spirehdl \
    --seed-from pareto_front/
```

When pointing at a directory, `--seed-from` auto-detects the format by looking for `pareto_front.json`, `best_designs.json`, or `multirun_summary.json` (in that order).

How it works:

1. The seed file is loaded and its format is auto-detected (multirun summary vs extract manifest).
2. Each passing entry with a valid cost is converted to an elite pool entry.
3. Entries are inserted into the new pool via the normal `update()` path, respecting `--elite-size`.
4. The `seed_from` path is saved in `config.json` for traceability.

> **Note:** The previous run's workdirs must still exist on disk — the pool entries reference design files by path.

## Output structure

```
runs/multirun_<timestamp>/
  config.json                        # full run configuration
  run_000/<bench>/<model>/<ts>/      # standard run layout per agent
    workspace/
    best_design/
    result.json
    chat_log.txt
    summary.txt
  run_001/...
  ...
  multirun_summary.json            # global results
  best_design/                       # copy of the globally best design
```

### multirun_summary.json

```json
{
  "benchmark": "fpmul_f16",
  "model": "deepinfra:MiniMaxAI/MiniMax-M2.5",
  "total_runs": 10,
  "max_concurrent": 4,
  "elite_size": 5,
  "temperature": 1.0,
  "cost_metric": "delay",
  "total_duration_s": 3200.0,
  "global_best_cost": 1550.0,
  "global_best_workdir": "run_005/.../best_design",
  "elite_pool_final": [
    {"cost": 1550.0, "run_index": 5, "design_file": "design.py"},
    {"cost": 1560.0, "run_index": 6, "design_file": "design.py"},
    {"cost": 1580.0, "run_index": 3, "design_file": "design.py"}
  ],
  "cost_progression": [
    {"run_completed": 1, "run_index": 0, "best_cost": 1618.0},
    {"run_completed": 2, "run_index": 2, "best_cost": 1618.0},
    {"run_completed": 3, "run_index": 1, "best_cost": 1600.0},
    {"run_completed": 4, "run_index": 3, "best_cost": 1580.0}
  ],
  "runs": [
    {"run_index": 0, "is_fresh": true, "passed": true, "best_cost": 1618.0, "duration_s": 615},
    {"run_index": 1, "is_fresh": true, "passed": true, "best_cost": 1600.0, "duration_s": 658},
    {"run_index": 2, "is_fresh": true, "passed": false, "best_cost": null, "duration_s": 342},
    {"run_index": 3, "is_fresh": false, "seed_cost": 1618.0, "passed": true, "best_cost": 1580.0, "duration_s": 422}
  ]
}
```

## Plotting results

Use `plot_multirun.py` to visualise how cost evolves across agent runs.

```bash
# Point at the summary JSON directly
python plot_multirun.py --input runs/multirun_20260312_163540/multirun_summary.json

# Or point at the run directory (auto-finds multirun_summary.json)
python plot_multirun.py --input runs/multirun_20260312_163540/

# Custom output directory
python plot_multirun.py --input runs/multirun_20260312_163540/ --output-dir ./my_plots
```

Output is saved to `<input_dir>/plots/multirun_cost_evolution.png` by default.

### What the plot shows

A single figure with cost on the y-axis and agent run index on the x-axis:

- **Green circles** — fresh-start runs that passed (correct design)
- **Green diamonds** (black edge) — seeded runs that passed
- **Orange crosses** — failed runs (no valid cost; placed at the bottom)
- **Black step line** — elite pool's best cost after each agent completion (`cost_progression`)

Title shows the benchmark, model, and global best cost. A subtitle shows the configuration (`total_runs`, `elite_size`, `temperature`).

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | (required) | Path to `multirun_summary.json` or its parent directory |
| `--output-dir` | `<input_dir>/plots` | Output directory for plot PNGs |

## Implementation

The multirun system is built entirely on top of existing infrastructure with no modifications to core files:

- **`core/multirun.py`** — `ElitePool` class, selection logic, seed context builder, async orchestration loop
- **`run_multirun.py`** — CLI entry point

It reuses `run_agent_on_benchmark()` from `runner.py` by constructing augmented `Benchmark` objects with temporary context directories containing seed design files.

# `rtl_rewriter` experiment scripts

Four scripts that drive the `benchmarks/rtl_rewriter/` + `benchmarks/rtl_rewriter_spirehdl/` suite through the agent and produce side-by-side comparison tables.

**Single-run-per-benchmark pipeline:**

- [`run_rtl_rewriter.py`](run_rtl_rewriter.py) — parallel agent runner; emits `summary.json`.
- [`table_rtl_rewriter.py`](table_rtl_rewriter.py) — renders a markdown table from that `summary.json`.

**Multi-run + two-phase pipeline** (see [Multirun pipeline](#multirun-pipeline) below):

- [`rtl_rewriter_multirun.py`](rtl_rewriter_multirun.py) — drives `core.multirun.run_multirun` with an optional phase-2 pass seeded from phase 1.
- [`table_rtl_rewriter_multirun.py`](table_rtl_rewriter_multirun.py) — renders two tables per metric: best per phase, then a distribution (min / max / mean / n) per phase.
- [`plot_rtl_rewriter_multirun.py`](plot_rtl_rewriter_multirun.py) — grid of per-case subplots; both languages overlaid, each phase column shows all per-run costs with the best highlighted, language-coloured baseline and RTLR-target horizontal reference lines.

## `run_rtl_rewriter.py`

Launches `core.runner.run_agent_on_benchmark` for each `(case × language)` combination in a `ProcessPoolExecutor`. Both the verilog sibling (`benchmarks/rtl_rewriter/case<N>/`) and the spirehdl sibling (`benchmarks/rtl_rewriter_spirehdl/case<N>/`) are run by default; use `--languages verilog` or `--languages spirehdl` to restrict to one.

### Arguments

| Flag | Default | Meaning |
|:---|:---|:---|
| `--cases N [N ...]` | all 10 | Integer case numbers, subset of `[1, 2, 3, 4, 6, 7, 9, 10, 11, 13]`. Rejects unknown numbers with an explicit message. |
| `--languages {verilog,spirehdl}` | both | Which variants to run. |
| `--workers N` | `8` | Max parallel workers in the process pool. |
| `--model SPEC` | `anthropic:claude-opus-4-6` | Model spec as accepted by `core.runner.parse_model_spec`, e.g. `anthropic:claude-opus-4-6`, `deepinfra:moonshotai/Kimi-K2.5`. |
| `--cost-metric NAME` | `yosys_cells` | Cost metric the agent is told to optimise. Any name registered in `core.cost.COST_METRICS` works (`yosys_cells`, `yosys_wires`, `area`, `delay`, `sky130_adp`, …). |
| `--max-steps N` | `20` | Agent budget per task. |
| `--runs-root PATH` | `runs/rtl_rewriter_<timestamp>` | Output directory. |
| `--summary-out PATH` | `<runs-root>/summary.json` | Where to write the summary JSON. |

### Output layout

```
<runs-root>/
    verilog/
        case<N>/<model-slug>/<ts>/
            result.json
            chat_log.txt
            best_design/
                design.v
                _best_meta.json
                ...
    spirehdl/
        case<N>/<model-slug>/<ts>/
            ...
    summary.json
```

The two language sub-roots keep `caseN` from colliding between variants.

### `summary.json` schema

```jsonc
{
  "timestamp": "20260421_120000",
  "model": "anthropic:claude-opus-4-6",
  "cost_metric": "yosys_cells",
  "max_steps": 20,
  "workers": 8,
  "cases": [1, 7, 13],
  "languages": ["verilog", "spirehdl"],
  "total_tasks": 6,
  "total_duration_s": 432.1,
  "runs_root": "runs/rtl_rewriter_20260421_120000",
  "results": {
    "case1": {
      "verilog":   { /* per-run record, see below */ },
      "spirehdl": { /* ... */ }
    },
    "case7": { ... },
    "case13": { ... }
  }
}
```

Each per-run record carries:

| Field | Meaning |
|:---|:---|
| `case_num`, `case_id`, `language` | Identifiers. |
| `benchmark_path` | Relative path to the benchmark dir under the repo root. |
| `workdir` | Timestamped run directory (absolute or `runs/...` relative). |
| `best_design_dir` | `<workdir>/best_design/` (or `null` if the agent never saved one). |
| `passed`, `pass_rate` | Correctness from the random-stimulus `tb.sv`. |
| `best_cost`, `cost_metric`, `cost_metric_requested` | The agent's headline optimisation result, plus which metric was being minimised. |
| `best_wires`, `best_cells` | Re-measured by running `yosys_wires` + `yosys_cells` on `best_design/design.v` after the run. |
| `baseline_wires`, `baseline_cells` | Starting-point numbers pulled from the language's `eval_verify.json`. |
| `delta_wires_pct`, `delta_cells_pct` | `(best − baseline) / baseline · 100` — negative is an improvement. |
| `duration_s`, `num_steps`, `token_usage`, `error` | Agent stats. |
| `status` | `"ok"` or `"error"`. |

### Baseline source

The `baseline_*` numbers come from `benchmarks/rtl_rewriter{,_spirehdl}/eval_verify.json`, produced by `/tmp/rtl_rewriter_verify.py` and `/tmp/rtl_rewriter_spirehdl_verify.py` respectively. If you regenerate those (e.g. after patching a baseline or swapping the spirehdl starting point), rerun the corresponding `_verify.py` before re-running this experiment so the deltas stay honest.

### Example

```bash
# Full sweep, both languages, 6 workers, default model.
python experiments/run_rtl_rewriter.py --workers 6

# Only three cases, spirehdl only, different model.
python experiments/run_rtl_rewriter.py \
    --cases 1 7 13 --languages spirehdl \
    --model deepinfra:moonshotai/Kimi-K2.5 \
    --workers 4

# Optimise for wires instead of cells.
python experiments/run_rtl_rewriter.py --cost-metric yosys_wires
```

## `table_rtl_rewriter.py`

Renders a markdown table from any `summary.json` produced above. Pure read — can be rerun as often as wanted, doesn't touch the run directories.

### Arguments

| Flag | Default | Meaning |
|:---|:---|:---|
| `summary_json` (positional) | — | Path to the `summary.json`. |
| `--show-wires` | off | Also include the wires quadruplet (`Vstart w · Vopt w · Δ V w · Sstart w · Sopt w · Δ S w`). Without it you just get cells. |
| `--out PATH` | stdout | Write the table to a file instead of stdout. |

### Columns

For each case, one row with:

- `Case` — e.g. `case7`.
- `Module` — the DUT's top module name.
- `Vstart c` / `Vopt c` / `Δ V c` — verilog baseline, agent's best, signed delta %.
- `Sstart c` / `Sopt c` / `Δ S c` — same for spirehdl.
- `V` / `S` — correctness flag for each language: `✓` passed, `✗` finished but failed, `err` the agent crashed.

With `--show-wires` the same four V/S columns are duplicated for wire counts, inserted before the cells columns.

A `**sum**` row totals the starts and opts across *passed* runs only (failed / errored rows don't pollute the delta), and a "Run directories" sub-table lists the `workdir` for each language so you can jump into `chat_log.txt` or `best_design/` for any case.

Cells in the raw data that are `null` (failed run, missing baseline) render as `—` and are skipped in deltas and sums.

### Example

```bash
python experiments/table_rtl_rewriter.py \
    runs/rtl_rewriter_20260421_120000/summary.json

python experiments/table_rtl_rewriter.py \
    runs/rtl_rewriter_20260421_120000/summary.json \
    --show-wires --out /tmp/rtl_rewriter.md
```

## Typical end-to-end

```bash
python experiments/run_rtl_rewriter.py --cases 1 7 13 --workers 6
python experiments/table_rtl_rewriter.py \
    runs/rtl_rewriter_<ts>/summary.json
```

The runner prints the exact `python experiments/table_rtl_rewriter.py <path>` invocation on exit, so the second step is usually just a copy-paste. The table script always renders **both** cells and wires tables, primary (= optimised) metric first.

## Multirun pipeline

The multirun variant runs N agents per case per language (via `core.multirun.run_multirun`) and optionally chains two phases, where phase 2 seeds from phase 1's elite pool. For spirehdl only, the prompt-feature flags differ by phase:

| Phase | `--arith-autoconfig` | `--flowy-optimize` | `--abc-optimize` |
|:---|:-:|:-:|:-:|
| phase 1 | ✓ | | |
| phase 2 | ✓ | ✓ | ✓ |

Verilog runs carry none of those spirehdl-only flags; for verilog, phase 2 is effectively "restart with phase-1's best designs seeded into the elite pool", which still often improves a bit.

**Phase-2 is pure exploitation.** `rtl_rewriter_multirun.py` overrides `core.multirun`'s default fresh-agent schedule (`fresh_base=0.5 → fresh_min=0.1`) by pinning `fresh_base=0, fresh_min=0, fresh_first=0` on the phase-2 call, so every phase-2 agent seeds from the pool that was pre-populated from phase 1's summary. This is reflected in the summary's `phase_exploration` block. Phase 1 keeps the default schedule — exploration still matters when the pool is cold.

### `rtl_rewriter_multirun.py` arguments

| Flag | Default | Meaning |
|:---|:---|:---|
| `--cases N [N ...]` | all 10 | Same subset convention as `run_rtl_rewriter.py`. |
| `--languages {verilog,spirehdl}` | both | |
| `--phases {1,2}` | `2` | `1` skips phase 2; `2` runs both with phase 2 seeded from phase 1. |
| `--model SPEC` | `anthropic:claude-opus-4-6` | |
| `--cost-metric NAME` | `yosys_cells` | |
| `--total-runs N` | `6` | Agents inside **each** phase. |
| `--max-concurrent N` | `2` | Parallel agents inside one `run_multirun` call. |
| `--max-steps N` | `20` | Agent budget per run. |
| `--elite-size N` | `5` | Elite pool size per phase. |
| `--workers N` | `4` | Outer parallelism — parallel `(case × language)` pairs. |
| `--runs-root PATH` | `runs/rtl_rewriter_multirun_<ts>` | |
| `--summary-out PATH` | `<runs-root>/summary.json` | |
| `--backfill PATH` | — | Re-read each phase's `multirun_summary.json` and rewrite the given summary in place (for when a previous run was interrupted or the script evolved). |

Concurrent agent cap = `outer_workers × max_concurrent`. The defaults (4 × 2) cap at 8 agents; bump to taste.

### Output layout

```
<runs-root>/
    phase1/
        verilog/case<N>/     ← multirun runs_root
            run_000/ run_001/ ...    ← one per agent
            best_design/             ← global-best from this phase
            multirun_summary.json
        spirehdl/case<N>/   ← idem
    phase2/
        verilog/case<N>/     ← seeded from phase1's multirun_summary.json
        spirehdl/case<N>/
    summary.json
```

### `summary.json` structure

Same top-level `results: {case_id: {language: rec}}` shape as the single-run variant, but each per-lang record contains per-phase sub-records:

```jsonc
{
  "results": {
    "case1": {
      "verilog": {
        "baseline_wires": 28, "baseline_cells": 18,
        "phase1": {
          "runs_root": "<runs-root>/phase1/verilog/case1",
          "multirun_summary_path": ".../multirun_summary.json",
          "flags": {},                       // empty for verilog
          "stats": {
            "cells": {"min": 14, "max": 17, "mean": 15.5, "count": 4},
            "wires": {"min": 22, "max": 25, "mean": 23.5, "count": 4}
          },
          "runs": [
            {"run_index": 0, "passed": true, "best_cost": 14,
             "best_wires": 22, "best_cells": 14,
             "workdir": ".../run_000/case1/...", ...},
            ...
          ],
          "status": "ok"
        },
        "phase2": { /* same shape, plus `seed_from` pointing at phase1 */ }
      },
      "spirehdl": { /* same shape; phase1.flags has arith_autoconfig=true etc. */ }
    }
  }
}
```

### `table_rtl_rewriter_multirun.py`

Renders four sub-tables from the summary, in this order:

1. **Best per phase — <primary metric>** — one row per case, columns `Vbase · P1 V best · P2 V best · Δ 1→2 V · Sbase · P1 S best · P2 S best · Δ 1→2 S · Δ S/V-ref`.
2. **Best per phase — <secondary metric>** — same shape for the other metric.
3. **Distribution across runs — <primary>** — `min / max / mean / n` for each `(phase × language)` slot, so you can see how tight the multirun landed.
4. **Distribution across runs — <secondary>** — idem.

Same column conventions as `table_rtl_rewriter.py`: `Δ S/V-ref` compares spirehdl's phase-2 *best* vs. the *verilog* reference baseline (the honest cross-language metric — in-language Δ columns compare each language against its own baseline).

### Typical end-to-end

```bash
# Both phases, both languages, 3 cases, defaults elsewhere.
python experiments/rtl_rewriter_multirun.py --cases 1 7 13

# Single phase only (skip the seeded refinement).
python experiments/rtl_rewriter_multirun.py --phases 1 --cases 1 7

# Render the tables.
python experiments/table_rtl_rewriter_multirun.py \
    runs/rtl_rewriter_multirun_<ts>/summary.json

# If the script lost the phase1/phase2 fields (e.g. it evolved since the
# run): re-read disk and rewrite the summary in place.
python experiments/rtl_rewriter_multirun.py \
    --backfill runs/rtl_rewriter_multirun_<ts>/summary.json
```

### Plot — `plot_rtl_rewriter_multirun.py`

Renders a grid of per-case subplots from the same `summary.json`. Each subplot puts the two languages side-by-side on each phase column, with:

- Small dots for per-run best costs (slight jitter so identical values don't stack).
- Larger marker for the best of each phase × language; a line connects those bests across phases so phase-to-phase improvement is a visible downward slope.
- Language-coloured dashed horizontal lines for each language's starting-point baseline.
- A single black dash-dot horizontal line for the RTLRewriter paper target.

Phases are discovered dynamically from the summary (any `phaseN` key), so a future three-phase variant works with no code change. The metric defaults to the optimised one in the summary (`cost_metric` → `yosys_cells` → `cells`) and can be overridden with `--metric wires`.

```bash
python experiments/plot_rtl_rewriter_multirun.py \
    runs/rtl_rewriter_multirun_<ts>/summary.json                 # cells PNG
python experiments/plot_rtl_rewriter_multirun.py \
    runs/rtl_rewriter_multirun_<ts>/summary.json --metric wires  # wires PNG
python experiments/plot_rtl_rewriter_multirun.py \
    runs/rtl_rewriter_multirun_<ts>/summary.json --format both   # PNG + SVG
```

| Flag | Default | Meaning |
|:---|:---|:---|
| `summary_json` (positional) | — | Summary JSON from `rtl_rewriter_multirun.py`. |
| `--metric {wires,cells}` | derived from `cost_metric` | Which y-axis to plot. |
| `--out PATH` | `<summary-dir>/multirun_<metric>.png` | Output file stem (with `--format both` the extension is replaced per format). |
| `--cols N` | auto (1/2/3 by case count) | Grid column count. |
| `--format {png,svg,both}` | `png` | Output format(s). |

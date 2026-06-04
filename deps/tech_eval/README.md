# tech_eval

PPA (Power, Performance, Area) evaluation workflows for arithmetic blocks and MMAC cores, built on top of `spire-hdl`, `yosys`, `openroad`, and `verilator`.

---

## Table of Contents

1. [Setup](#setup)
2. [Project layout](#project-layout)
3. [Quick start: PPA from a spire-hdl component](#quick-start-ppa-from-a-spire-hdl-component)
4. [PPA from any Verilog file](#ppa-from-any-verilog-file)
5. [PPA from ELAU designs](#ppa-from-elau-designs)
6. [Test / example scripts](#test--example-scripts)
7. [Sweep scripts](#sweep-scripts)
8. [Common plotting tool](#common-plotting-tool)
9. [Runtime tuning](#runtime-tuning)
10. [File organisation suggestions](#file-organisation-suggestions)

---

## Setup

### 1. Python dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

If you develop with a local `spire-hdl` checkout, install it first (as done in `.devcontainer/start_interactive_container_custom.sh`):

```bash
pip install ../spire-hdl
```

Without editable install, prefix every command with `PYTHONPATH=src`.

### 2. External EDA tools (must be on `PATH`)

| Tool | Purpose |
|---|---|
| `yosys` | Synthesis |
| `openroad` | STA and power analysis |
| `verilator` | RTL simulation for activity-based power |

### 3. Technology library paths

Default library and LEF paths are configured in `src/tech_eval/ppa_extract/core/template.py`.
The default technology is **ASAP7** and expects libraries under `/prog/OpenROAD-flow-scripts/...`.

---

## Project layout

```
src/tech_eval/
├── int_tb_sim.py                   # vector generation + testbench simulation helper
├── recompose_total_power.py        # post-processing utility for power breakdown
└── ppa_extract/
    ├── core/
    │   ├── ppa_extraction.py       # get_ppa() — the main end-to-end flow
    │   ├── ppa_extraction_specific.py  # run_configs() — multiprocess runner
    │   ├── ppa_configs.py          # InstanceConfig / JsonExportConfig dataclasses
    │   └── template.py             # Yosys/OpenROAD script templates + library paths
    ├── tests/
    │   ├── ppa_extraction_test.py          # single multiplier — spire-hdl component
    │   ├── ppa_extraction_test_verilog_file.py  # spire-hdl component + static .sv files
    │   ├── ppa_extraction_test_elau_mul16.py    # ELAU multiplier (multi-file RTL)
    │   ├── mmac_core_test.py               # single MMAC core (unsigned)
    │   ├── mmac_core_sign_magnitude_test.py # single MMAC core (sign-magnitude)
    │   ├── mp_plot_test.py                 # multiprocess PPA + basic delay-vs-area plot
    │   ├── mul_verilog_test.py             # scratch / verilog multiplier experiments
    │   ├── test.py                         # scratch / misc experiments
    │   └── files/                          # static RTL files (adders, multipliers)
    └── sweeps/
        ├── plot_saved_results.py           # universal CLI re-plotter (all sweeps)
        ├── plotting2.py                    # shared plotting functions
        ├── mmac/
        │   ├── mmac_cores_mp.py            # MMAC core family sweep
        │   └── mmac_cores_mp_optim.py      # MMAC sweep with optimised multiplier blocks
        └── multipliers/
            ├── sigma_sweep_all_multipliers_encoders2_mp.py  # sigma sweep (no common plotting)
            ├── sigma_sweep.py                               # minimal single-case sigma sweep
            └── mul_add_sweep_mp.py                          # adder + multiplier sweep
```

---

## Quick start: PPA from a spire-hdl component

The typical flow is:

1. Build a `spire-hdl` component.
2. Generate test vectors.
3. Simulate with `run_component_with_vectors` — this writes the RTL and testbench.
4. Call `get_ppa` to run synthesis + STA + optional power.

```python
from tech_eval.int_tb_sim import TwInputArit, generate_vectors, run_component_with_vectors
from tech_eval.ppa_extract.core.ppa_extraction import get_ppa

from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    Encoding, FSAOption, PPAOption, PPGOption, TwoInputAritEncodings, MultiplierTestVectors,
)
from spirehdl.arithmetic.int_multipliers.multipliers.multiplier_stage_core import StageBasedMultiplierBasic

n_bits = 16
mult = StageBasedMultiplierBasic(
    a_w=n_bits, b_w=n_bits,
    signed_a=False, signed_b=False,
    optim_type="speed",
    ppg_cls=PPGOption.BOOTH_OPTIMISED.value,
    ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
    fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
)

vectors = generate_vectors(
    vec_cls=MultiplierTestVectors,
    encodings=TwoInputAritEncodings.with_enc(Encoding.unsigned),
    sigma=3,
    widths=TwInputArit(a_w=n_bits, b_w=n_bits),
    num_vectors=1000,
    y_w=mult.io.y.typ.width,
)

sim_result = run_component_with_vectors(
    mult, vectors,
    module_name=f"Mul{n_bits}",
    tb_from_data=True,
    worker_path="worker_my_design",
)

ppa = get_ppa(
    rtl_path=sim_result["verilog_filename"],
    target_delay=1200,          # ps (ASAP7 default)
    worker_path="worker_my_design",
    top_module_name=sim_result["module_name"],
    run_verilator=True,
    tb_filename=sim_result["tb_filename"],
    tb_name=sim_result["tb_name"],
    use_vcd_for_power=True,
    save_vcd=True,
)
print(ppa)
```

See `src/tech_eval/ppa_extract/tests/ppa_extraction_test.py` for a runnable version.

---

## PPA from any Verilog file

If you already have a Verilog/SystemVerilog file and just need PPA, skip the vector/simulation steps and pass the file path directly to `get_ppa`.
`rtl_path` accepts either a single path string or a **list of paths** for multi-file designs.

```python
from tech_eval.ppa_extract.core.ppa_extraction import get_ppa

ppa = get_ppa(
    rtl_path="path/to/my_design.sv",   # or a list of paths
    target_delay=1200,                  # ps
    worker_path="worker_my_design",
    top_module_name="MyTopModule",
    run_verilator=False,                # no testbench needed
    use_fa_ha_inference=False,
)
print(ppa)
```

Static RTL files for quick tests are in `src/tech_eval/ppa_extract/tests/files/`
(e.g. `mult16.sv`, `add32.sv`, `mult32_karatsuba.v`).

A complete example that first runs a spire-hdl multiplier and then evaluates a static `.sv` file in the same script is in:

```bash
python -m tech_eval.ppa_extract.tests.ppa_extraction_test_verilog_file
```

---

## PPA from ELAU designs

[ELAU](https://github.com/pulp-platform/ELAU) uses multi-file SystemVerilog.
`get_ppa` accepts a list of source paths so you can evaluate these designs directly — no wrapper generation needed beyond an optional thin module to fix the port names/parameters.

The script `src/tech_eval/ppa_extract/tests/ppa_extraction_test_elau_mul16.py` shows the full pattern:

- Resolves sources from `$ELAU_ROOT/src/`.
- Generates a thin wrapper module to expose fixed-width ports.
- Calls `get_ppa` with the source list and the wrapper.

**Prerequisite:** clone ELAU to `/prog/ELAU` (or change `ELAU_ROOT` in the script).

```bash
python -m tech_eval.ppa_extract.tests.ppa_extraction_test_elau_mul16
```

---

## Test / example scripts

All scripts under `src/tech_eval/ppa_extract/tests/` can be run as modules from the repo root.

| Script | What it demonstrates |
|---|---|
| `ppa_extraction_test` | Single spire-hdl multiplier (32-bit, two's complement) |
| `ppa_extraction_test_verilog_file` | spire-hdl multiplier + static `.sv` file in one script |
| `ppa_extraction_test_elau_mul16` | Multi-source ELAU design (`MulUns16`, `MulPPGenUns16`) |
| `mmac_core_test` | 4×4×4 MMAC core (unsigned), with spire-hdl simulator check |
| `mmac_core_sign_magnitude_test` | 8×8×8 MMAC core (sign-magnitude / symmetric two's complement), saves `ppa_results.json` |
| `mp_plot_test` | Multiprocess PPA over a delay sweep + simple area-vs-delay scatter plot |

Run any of them with:

```bash
python -m tech_eval.ppa_extract.tests.<script_name>
```

The `tests/unit/` subdirectory contains lightweight unit tests (`pytest`) that do not require EDA tools.

---

## Sweep scripts

### MMAC core sweep

**Script:** `src/tech_eval/ppa_extract/sweeps/mmac/mmac_cores_mp.py`

```bash
python -m tech_eval.ppa_extract.sweeps.mmac.mmac_cores_mp
```

Sweeps four MMAC core families across multiple architecture options and target delays using multiprocessing:

- Base (two's complement)
- Fused (two's complement)
- Sign-magnitude encoded
- Sign-magnitude without dedicated encoder

**Outputs (auto-generated after the sweep):**

- `results/ppa/MMAC_m4_a4_results.json` — all raw PPA data
- Six plots per run in `results/ppa/`:
  - `*_area_vs_delay.png`
  - `*_area_vs_power.png`
  - `*_area_vs_switch_count.png`
  - `*_area_vs_estimated_num_transistors.png`
  - `*_delay_vs_power.png`
  - `*_delay_vs_switch_count.png`

**Optimised variant** (uses optimised multiplier blocks):

```bash
python -m tech_eval.ppa_extract.sweeps.mmac.mmac_cores_mp_optim
```

---

### Multiplier + adder sweep

**Script:** `src/tech_eval/ppa_extract/sweeps/multipliers/mul_add_sweep_mp.py`

```bash
python -m tech_eval.ppa_extract.sweeps.multipliers.mul_add_sweep_mp
```

Sweeps standalone adder and multiplier configurations across delay targets.
Saves results to JSON and generates plots using the shared `plotting2` module (same six plot types as the MMAC sweep). Re-grouping helpers (`regroup_by_fsa`, `regroup_by_ppa`, `regroup_by_target_delay`) are available for custom plots.

---

### Sigma sweeps (multipliers + encoders)

These sweeps vary the input distribution spread (σ) to study how power changes with different input statistics.

> **Note:** Unlike the MMAC and multiplier sweeps above, sigma sweeps do **not** use the common `plotting2`/`plot_saved_results` infrastructure — they produce their own inline plots.

| Script | Description |
|---|---|
| `sigma_sweep_all_multipliers_encoders2_mp.py` | Main sigma sweep — multiprocess, covers multiplier variants and encoder cases |
| `sigma_sweep.py` | Minimal single-case sigma sweep |

Run the current main sigma sweep:

```bash
python -m tech_eval.ppa_extract.sweeps.multipliers.sigma_sweep_all_multipliers_encoders2_mp
```

Outputs (written to `worker_sigma/`):
- `power_vs_sigma.png`
- `area_at_target_delay.png`
- `delay_at_target_delay.png`

---

## Common plotting tool

All sweeps that save JSON results can be re-plotted or filtered without re-running the sweep:

```bash
python -m tech_eval.ppa_extract.sweeps.plot_saved_results \
  --results results/ppa/MMAC_m4_a4_results.json
```

**Options:**

| Flag | Description |
|---|---|
| `--list-cases` | Print available case labels and exit |
| `--cases <label> ...` | Plot only the specified cases (space or comma-separated) |
| `--delay-threshold <ps>` | Filter out points slower than this value |
| `--area-threshold <um2>` | Filter out points larger than this value |
| `--power-threshold <W>` | Filter out points above this power |
| `--out-dir <path>` | Output directory (defaults to results file directory) |
| `--design-prefix <str>` | Override filename prefix |
| `--title-label <str>` | Override plot title label |
| `--suffix <str>` | Override filename suffix |
| `--no-legend` | Disable legend |

Produces the same six plot types as the sweep itself.

---

## Runtime tuning

- Sweep scripts hard-code parameters (`n_processes`, bit widths, target delays, etc.) near the top of each file — edit them there.
- `n_processes=80` is aggressive; reduce it for machines with fewer cores or limited RAM.
- Worker folders are deleted by default in most sweeps (`keep_files=False`). Set to `True` to inspect intermediate files.

---

## File organisation todos

These are suggestions only — no files have been moved:

- **`src/tech_eval/ppa_extract/tests/ppa_extraction_test.py` and `ppa_extraction_test_verilog_file.py`** do very similar things. They could be merged into a single parametrised script or renamed to reflect what they specifically test (e.g. `test_spirehdl_multiplier.py` and `test_static_verilog.py`).

- **`src/tech_eval/ppa_extract/sweeps/plot_saved_results.py`** and **`sweeps/mmac/` formerly had their own `plot_saved_results.py`** — the common one now lives at `sweeps/plot_saved_results.py`, which is correct; the MMAC sweep no longer needs its own copy.

## Python environment

In the docker container activate this python environment: `source  ~/pyenv_eda/bin/activate`

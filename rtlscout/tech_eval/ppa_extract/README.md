# ppa_extract

PPA (Power, Performance, Area) extraction and analysis toolkit for evaluating hardware designs synthesized through Yosys and OpenROAD.

## Subpackages

### `core/`
Foundation modules: the PPA extraction pipeline (Yosys + OpenROAD + Verilator orchestration), configuration dataclasses, and technology/platform definitions (ASAP7, Nangate45, FreePDK45).

### `plotting/`
Plotting utilities for visualizing PPA results: Pareto-front computation, delay-vs-area curves, power-vs-area charts, and a standalone tool for re-plotting saved JSON results.

### `tests/`
Component-level test and demo scripts. Each script exercises a specific design type (multiplier, MMAC core, sign-magnitude MMAC) through the full PPA extraction flow.

### `sweeps/`
Large-scale parameter sweep scripts that run PPA extraction across many configurations (sigma values, multiplier variants, encoding options, MMAC core types) with multiprocessing support.



## Main scripts

int_tb_sim.py
ppa_extraction_test.py
ppa_sigma_sweep.py
ppa_extraction_mp_plot_exended_vecs.py
ppa_extraction_mmac_core_test.py
Makefile


# Main sweeps

1. ppa_sigma_sweep_all_multipliers_encoders2_mp.py
2. ppa_extraction_mmac_cores_mp.py
or
ppa_extract/ppa_extraction_mmac_cores_mp_optim.py (for optimized multipliers)
--> ppa_extract/ppa_extraction_mmac_cores_mp_plot_saved_results.py for plotting





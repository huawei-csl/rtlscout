# ppa_extract.core

Core PPA extraction infrastructure.

## Modules

- **`ppa_extraction.py`** - Main PPA extraction pipeline. Orchestrates Yosys synthesis, OpenROAD STA, and Verilator simulation. Key functions: `get_ppa()`, `get_ppa_multiprocess()`, `get_target_delay()`.
- **`ppa_extraction_specific.py`** - High-level wrapper for running multiple design configurations across delay targets with multiprocessing. Key function: `run_configs()`.
- **`ppa_configs.py`** - Configuration dataclasses: `MultConfig`, `AdderConfig`, `InstanceConfig`, `VecConfig`.
- **`template.py`** - Technology/platform definitions (ASAP7, Nangate45, FreePDK45), library paths, Yosys/STA script templates, Verilator flags.

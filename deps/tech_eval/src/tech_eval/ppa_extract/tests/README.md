# ppa_extract.tests

Component-level test and demo scripts for PPA extraction.

## Modules

- **`ppa_extraction_test.py`** - Single multiplier PPA test using sign-magnitude encoding and stage-based options. Entry point: `test1()`.
- **`mmac_core_test.py`** - Matmul-accumulate (MMAC) core test with twos-complement encoding. Also exports `_build_vectors_encoding()` used by other test/sweep scripts.
- **`mmac_core_sign_magnitude_test.py`** - MMAC core variant using sign-magnitude encoding. Entry point: `test_mmac_core_sign_magnitude_vector_simulation()`.
- **`mp_plot_test.py`** - Simple multiprocess PPA runner with inline plotting for basic multipliers. Entry point: `run_ppa_mp()`.

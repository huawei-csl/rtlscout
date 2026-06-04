# ppa_extract.sweeps

Large-scale parameter sweep scripts for PPA exploration.

## Modules

- **`sigma_sweep.py`** - Sweeps input activity (sigma) for a single multiplier configuration. Entry point: `run_sigma_sweep_and_plot()`.
- **`sigma_sweep_all_multipliers.py`** - Sigma sweep across 5 multiplier variants with encoding options.
- **`sigma_sweep_all_multipliers_encoders1.py`** - Extended sigma sweep adding encoder/decoder PPA analysis alongside multipliers.
- **`sigma_sweep_all_multipliers_encoders2_mp.py`** - Multiprocess version of the sigma sweep with encoder analysis.
- **`mmac_cores_mp.py`** - Full MMAC core sweep: tests base, fused, and sign-magnitude core variants across encodings, optimization types, and delay targets. Entry point: `run_ppa_mmac_core()`.
- **`mmac_cores_mp_optim.py`** - Same as `mmac_cores_mp.py` but uses optimized multiplier blocks instead of stage-based multipliers.

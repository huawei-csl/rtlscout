# fpmul_f16 rerun — ABC / Opus 5

Scripted rerun of the paper's FP16-multiplier pipeline (Phases 0–4) per
[`metadocuments/reruns/inputs/HANDOVER_fpmul_rerun.md`](../../metadocuments/reruns/inputs/HANDOVER_fpmul_rerun.md),
with two deliberate deviations:

- **Model**: `anthropic:claude-opus-5` for *every* agent campaign (the handover
  mirrored the paper: Sonnet for Phase-1 area, Opus 4.6 elsewhere).
- **Optimizer**: ABC (`@abc_optimized` in Phase 2, `&deepsyn` in Phase 4) — no
  flowy/Mockturtle anywhere, as the handover already prescribes.

## Usage

```bash
python run_all.py --new-run                # START a fresh run: data/<tag>_<datetime>
python run_all.py                          # RESUME the latest run of the profile
python run_all.py --profile reduced --new-run   # fresh reduced rehearsal
python run_all.py --smoke                  # cheap smoke of every moving part
python run_all.py --stages 4,5             # subset; done stages are skipped anyway
python run_all.py --report-only            # regenerate the run's REPORT.md
RTLSCOUT_RERUN_RUN=o5_20260730_120000 python run_all.py --report-only  # older run
```

The run timestamp is minted ONCE by `--new-run` and pinned via
`data/.latest_<profile>`, so plain invocations always resume — repeated runs
can never overwrite each other.

Scale lives in `profiles/{full,reduced}.yaml` (run counts, agent steps, sweep
grid, deepsyn budgets, target delays); paths and fixed facts live in
`rerun_config.py`. Every run owns a disjoint `data/<tag>_<datetime>/`
namespace (runs, fronts, sweep, logs, state, figures, manifest, report), so
rehearsals, repeats, and the full run can never contaminate each other.
Stages run standalone honor `RTLSCOUT_RERUN_PROFILE` (default `full`) and
join the pinned run.

`run_all.py` re-execs itself into the `~/pyenv_eda` venv, so plain `python`
works. Everything is resumable: campaigns and stages leave `.done` markers in
`state/<tag>/`; delete a marker (or pass `--force`) to redo a stage. The
report (all generated files + key numbers) is regenerated after every stage.

## Layout

| path | what |
|---|---|
| `rerun_config.py` | fixed facts: paths, benchmark, verification setup |
| `profiles/*.yaml` | scale per profile: run counts, steps, sweep grid, deepsyn budgets |
| `run_all.py` | main entry point |
| `stages/stage0_setup.py` | golden reference, directed subnormal vectors, baseline eval |
| `stages/stage1_agent.py` | Phase-1 campaigns (also hosts the shared campaign runner) |
| `stages/stage2_seeded.py` | Phase-2 seeded + `@abc_optimized` campaigns, front extraction, Stage-V gate |
| `stages/stage3_sweep.py` | patchability gate + architecture sweep + post-sweep fronts |
| `stages/stage4_deepsyn.py` | `&deepsyn` refinement + equal-compute baseline + 800/1800 ps evals |
| `stages/stage5_figures.py` | all figures/tables (each attempted independently) |
| `stages/stagev_verify.py` | Stage V: regression pre-check + **exhaustive 2^32 sim vs golden** (no CEC — user decision; exhaustive sim is complete here) |
| `stages/smoke.py` | smoke suite incl. the buggy-design positive control |
| `report.py` | generates `REPORT.md` from `manifest.json` + state |
| `ported/` | scripts ported from the old repo (`batch_deepsyn.py` gained `--num-runs`) |
| `data/<tag>/` | ALL generated data of a run (runs, fronts, sweep, logs, state, figures, report) |

All generated data of a run lives under **`data/<tag>/`** (2026-07-29
layout): `runs/`, `fronts/`, `sweep/` (results JSON + worker dirs + PNGs),
`logs/`, `state/`, `figures/`, `verify_work/`, `manifest.json`, `REPORT.md`
— archive that one folder and you have the complete experiment. Only the
benchmark mutations (golden, tb, vectors) are global by design. Pre-layout
rehearsal data (`runs/fpmul_o5r*`, `pareto_fronts/fpmul_o5r*`,
artifacts-level state/figures/REPORT files) is grandfathered in place.
Status and decisions live in `STATUS.md`.

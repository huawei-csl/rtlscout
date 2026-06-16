# RTLRewriter best designs — benchmark package

This folder contains the **best RTL designs found by RTLScout** on the 14
[RTLRewriter](https://github.com/yaoxufeng/RTLRewriter-Bench) benchmark cases,
in two source languages (**Verilog** and **SpireHDL**) and for two optimization
objectives (**Yosys cell count** and **Yosys transistor count**).

Each design is shipped together with:

- the **starting point** it must be equivalent to (the benchmark base / spec) —
  `starting_point.v` (verilog: the original RTL; spirehdl: the compiled baseline),
  plus `starting_point.py` for SpireHDL,
- the **testbench** (`tb.sv` + `vectors.dat`) used for correctness,
- a machine-readable **`INFO.json`** (module, phase, metric value, CEC verdict),
- and — for SpireHDL — the **source `.py`** (`best.py`); the authoritative
  compiled netlist is the bundled `best.v` (re-running `best.py` re-synthesises it
  via the `@flowy_optimized` / `@abc_optimized` passes).

Every design has been **formally equivalence-checked** against its reference
(see `cec_results/` and the `cec_status` field in each `INFO.json`). `best.v` /
`best.sv` is the authoritative netlist — the exact file that was synthesised for
the reported count and equivalence-checked.

## Layout

```
README.md                 this file (package description + how to evaluate)
README_cec_results.md     CEC overview + per-design verdict tables
verify.py                 re-run all equivalence checks on the bundled files
cec_engine.py             the check engine that verify.py imports
cec_results/              equivalence-check + number re-check reports (md + json)
designs/
  cells_run/              backs table_rtl_rewriter.tex            (objective: Yosys cells)
    table_rtl_rewriter.tex
    case1/ … case14/
      verilog/            starting_point.v  best.sv  tb.sv  vectors.dat  INFO.json
      spirehdl/           starting_point.py  starting_point.v  best.py  best.v
                          tb.sv  vectors.dat  INFO.json
  transistor_run/         backs table_rtl_rewriter_transistors_v2.tex   (objective: Yosys transistors)
    table_rtl_rewriter_transistors_v2.tex
    case1/ … case14/
      verilog/ …
      spirehdl/ …
```

## Re-evaluating a design (`run_eval.py`)

Evaluation uses the RTLScout repo's debug entry point, `run_eval.py`, which runs
the **full pipeline**: SpireHDL compile (for `.py`) → Verilator correctness
against `tb.sv`/`vectors.dat` → Yosys cost. Because `tb.sv` and `vectors.dat` are
bundled next to each design, you can evaluate in place.

**Prerequisites:** a checkout of the `rtl_scout` repo with its environment
installed (`uv sync`, or `pip install -e .`), plus `yosys` and `verilator` on
`PATH`. SpireHDL designs additionally need the `spirehdl` package (vendored under
`deps/spire-hdl`); re-running `best.py` re-synthesises via the ABC/Flowy passes
(the authoritative compiled netlist `best.v` is bundled either way).

Pick the cost metric matching the run: `yosys_cells` for `cells_run`,
`yosys_transistors` for `transistor_run`. The `--top-module` is in `INFO.json`
(usually `example`).

**Verilog**

```bash
cd designs/transistor_run/case3/verilog
python /path/to/rtl_scout/run_eval.py best.sv \
    --language verilog \
    --cost-metric yosys_transistors \
    --top-module example
```

**SpireHDL** (`best.py` is recompiled to Verilog, then evaluated)

```bash
cd designs/transistor_run/case3/spirehdl
python /path/to/rtl_scout/run_eval.py best.py \
    --language spirehdl \
    --cost-metric yosys_transistors \
    --top-module example
```

Expected: `PASS` (all testbench vectors) and a cost equal to `metric_value` in
the adjacent `INFO.json` (e.g. `3782` for case3 verilog transistors, `3564` for
case3 spirehdl). Add `--json` for machine-readable output.

**Evaluate everything in a run** (bash):

```bash
ROOT=/path/to/rtl_scout
for d in designs/transistor_run/case*/{verilog,spirehdl}; do
  info="$d/INFO.json"
  top=$(python -c "import json,sys;print(json.load(open('$info'))['top_module'])")
  src=$(ls "$d"/best.sv "$d"/best.py 2>/dev/null | head -1)
  lang=$([ "${src##*.}" = py ] && echo spirehdl || echo verilog)
  echo "== $d =="
  (cd "$d" && python "$ROOT/run_eval.py" "$(basename "$src")" \
      --language "$lang" --cost-metric yosys_transistors --top-module "$top")
done
```

## Independently re-checking equivalence (Yosys)

This package is self-verifying. **`verify.py`** (bundled, alongside the check
engine `cec_engine.py`) walks every design, re-runs the same check on the
local `starting_point.*` vs `best.*`, and compares against the recorded verdict —
no repo checkout needed, just `yosys` and `verilator` on `PATH`:

```bash
python verify.py                       # re-verify all 56 designs
python verify.py --only case3          # just the case3 folders
python verify.py --sim-vectors 100000  # faster simulation pass for case2/12
# -> "56/56 reproduce the recorded verdict; 56/56 verify EQUIVALENT."
```

You can also re-derive any single verdict by hand. For a **combinational** case
(e.g. case3):

```bash
cd designs/transistor_run/case3/verilog
yosys -p '
  read_verilog -sv starting_point.v; hierarchy -top example; proc; flatten; opt -full;
    rename example gold; design -stash g
  read_verilog -sv best.sv;          hierarchy -top example; proc; flatten; opt -full;
    rename example gate; design -stash k
  design -copy-from g -as gold gold
  design -copy-from k -as gate gate
  equiv_make gold gate equiv; hierarchy -top equiv; clean -purge;
  equiv_simple; equiv_induct; equiv_status -assert'
# -> "Equivalence successfully proven!"
```

Method notes (full details in `README_cec_results.md`):

- **Combinational** designs: `equiv` flow above, or a `miter`+SAT fallback.
- **Sequential** designs (cases 1, 9, 10 — pipelines / FSMs): reset-anchored
  temporal induction (`sat -tempinduct`), a complete unbounded proof — including
  the 7→4-state re-encoded FSM in case10.
- **case2 / case12**: these contain 32-bit multipliers, so a SAT miter is
  intractable; equivalence was established by **1,000,000 random-vector
  simulation** (Verilator), 0 mismatches.

`IDENTITY` in a verdict means the table's best for that cell was the shipped
baseline, so the design *is* the reference (trivially equivalent).

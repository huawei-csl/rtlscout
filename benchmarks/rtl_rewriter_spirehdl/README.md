# `rtl_rewriter_spirehdl` benchmarks

SpireHDL mirror of [`benchmarks/rtl_rewriter/`](../rtl_rewriter/README.md).
All fourteen RTLRewriter (ICCAD 2024, arXiv:2409.11414) short-bench cases, same
top-module names, same port lists — except the starting point is a
hand-written SpireHDL script (`context/starting_point.py`) that emits
`design.v`. The cost metric is `yosys_wires` / `yosys_cells`; correctness
is guarded by `tb.sv` + `vectors.dat` bit-identical to the verilog
sibling.

See [`../rtl_rewriter/README.md`](../rtl_rewriter/README.md) for the full
story (confidence rubric, paper-target numbers, regeneration tooling,
`source` cross-references). This README covers only what's specific to
the SpireHDL variant.

## Measured starting-point cells / wires

Pulled straight out of [`eval_yosys_stat.json`](eval_yosys_stat.json)
(cost metric on the SpireHDL-emitted `design.v`) and
[`eval_verify.json`](eval_verify.json) (same measurement + correctness
gate via Verilator + the shipped `tb.sv`). The two files are regenerated
by `/tmp/rtl_rewriter_compare.py` and
`/tmp/rtl_rewriter_spirehdl_verify.py` respectively; they agree on
`wires` / `cells` for every case, so re-listing them both here would just
add noise.

| Case    | Module                   | Wires | Cells | tb.sv |
|---------|--------------------------|------:|------:|:-----:|
| case1   | `example`                |    28 |    18 |  PASS |
| case2   | `arithmetic_operations`  | 17927 | 18105 |  PASS |
| case3   | `example`                |  1136 |  1220 |  PASS |
| case4   | `example`                |  1376 |  1462 |  PASS |
| case5   | `example`                |    43 |    49 |  PASS |
| case6   | `example`                |   124 |   129 |  PASS |
| case7   | `example`                |   350 |   351 |  PASS |
| case8   | `inefficient_multiplier` |   360 |   370 |  PASS |
| case9   | `example`                |    55 |    54 |  PASS |
| case10  | `example`                |    31 |    30 |  PASS |
| case11  | `example`                |    21 |    24 |  PASS |
| case12  | `example`                | 19486 | 19664 |  PASS |
| case13  | `mux_tree`               |     3 |     1 |  PASS |
| case14  | `mux_tree`               |     8 |     3 |  PASS |

`tb.sv` column is `PASS` when the SpireHDL-emitted design passes the
mirrored testbench at 100% — 14/14 today.

The yosys script used by `core.cost.YosysWiresCost` / `YosysCellsCost`
appends `clean -purge` after `synth`, which drops public alias buffers
and dangling nets. Cell counts are unchanged way.

### Δ vs verilog sibling

The per-case delta between this variant and `benchmarks/rtl_rewriter/`
lives in [`benchmarks/rtl_rewriter_compare.json`](../rtl_rewriter_compare.json).
Headline: the nested-mux ALU (case7), the FSM-derived case10/case11/case13,
and the flat-emitted mux tree (case14) shrink under the SpireHDL mirror,
while the two large commutativity-sharing designs (case2 +54%, case12
+32%) regress because SpireHDL's per-expression wire naming prevents
yosys from merging shared subterms across the 6 outputs — see
`benchmarks/turbo_rtl/README.md` for the underlying "named-wire topology
bias" mechanism.

## Per-case layout

```
benchmarks/rtl_rewriter_spirehdl/<case_id>/
  description.txt                   # spec (same shape as the verilog sibling, pointer updated to .py)
  metadata.json                     # name, module_name, language=spirehdl, source, tb_mode, …
  tb.sv                             # byte-identical copy of the verilog sibling's tb.sv
  vectors.dat                       # byte-identical copy of the verilog sibling's vectors.dat
  context/
    starting_point.py               # hand-written SpireHDL, emits design.v
```

**Hard invariant:** `tb.sv` and `vectors.dat` are bit-identical between
`benchmarks/rtl_rewriter/<case>/` and
`benchmarks/rtl_rewriter_spirehdl/<case>/`. Same top-module name, same
port list, same expected outputs. If they drift, the SpireHDL starting
point is being compared against a different oracle than the verilog one.

`metadata.json` carries the same `source` block as the verilog sibling
(points back at the upstream RTLRewriter-Bench file), plus:

```jsonc
{
  "language": "spirehdl",
  "starting_point": "context/starting_point.py",
  "tb_mode": "seq" | "comb",
  "clock_port": "clk",       // seq only
  "reset_port": "reset"       // seq only, optional
}
```

## Running one

```bash
~/pyenv_eda/bin/python run_eval.py \
    benchmarks/rtl_rewriter_spirehdl/case1/context/starting_point.py \
    --benchmark benchmarks/rtl_rewriter_spirehdl/case1 \
    --language spirehdl --cost-metric yosys_cells
```

Expected: `Correctness: PASS, 2000/2000` (or 2002/2002 for the six
combinational cases) and the `yosys_cells` / `yosys_wires` value from the
table above. The turbo_rtl in-place-artifact warning applies —
`run_eval.py` will drop `obj_dir/`, `design.v`, and the copied
`tb.sv`/`vectors.dat` into the workspace, so prefer
`--workdir /tmp/foo` over running in `context/`.

Cost-metric-only (skip correctness, run the `.py` manually first):

```bash
python -c "
from pathlib import Path
import json, subprocess, tempfile
from core.cost import make_cost_metric

case = 'case1'
d   = Path(f'benchmarks/rtl_rewriter_spirehdl/{case}')
md  = json.loads((d/'metadata.json').read_text())
sp  = d/'context/starting_point.py'

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp/'starting_point.py').write_text(sp.read_text())
    subprocess.check_call(['python3', 'starting_point.py'], cwd=tmp)
    wires = make_cost_metric('yosys_wires').evaluate(tmp, top_module=md['module_name'], design_file=tmp/'design.v')
    cells = make_cost_metric('yosys_cells').evaluate(tmp, top_module=md['module_name'], design_file=tmp/'design.v')
print(case, 'wires=', int(wires.value), 'cells=', int(cells.value))
"
```

## Correctness semantics

Same protocol as the verilog sibling: random-stimulus `tb.sv` is the first
line of defence; layer a yosys `equiv_make; equiv_induct` check on top
when total-equivalence is required.

Known semantic difference: the three FSM/registered cases that retain an
async-reset port in the golden (case9, case10, and the registered chain
adder case1) use async posedge-reset
(`always @(posedge clk or posedge reset)`). SpireHDL's module
constructor exposes an async-reset path only when the reset port is
named `rst`, so case9 and case10 are translated using the
`with_reset=False` + `mux(reset, initial, next_state)` idiom (the same
pattern turbo_rtl's `avg4_reg` uses). This gives the port the name `reset` expected by the
shared `tb.sv`, at the cost of being **synchronous** rather than async
at the clock boundary. Functionally equivalent once `reset` is released
— `tb.sv` holds reset for 3 cycles before any stimulus, so the initial
state is always pinned before the first sampled cycle — but note this if
you care about cycle-0 reset-edge behaviour specifically.

## Source: `rewriter_cases.json`

The paper-claim / reproduction audit lives in the verilog sibling's
[`rewriter_cases.json`](../rtl_rewriter/rewriter_cases.json); the
SpireHDL mirror inherits the confidence labels and paper targets from
there verbatim (same `metadata.json.reference` block).

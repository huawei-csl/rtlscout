"""Phase-1 integrity tests: advisory shim (core.eval_store.run_eval_and_store) and the
authoritative clean-room re-eval (core.reeval.reeval_run) with its agreement gate.

The crux: a run whose agent fakes correctness (tampered testbench) or fabricates a low
cost must be CORRECTED by the authoritative re-score against the benchmark's own inputs,
and the agreement gate must flag the divergence.
"""

import json
import shutil
from pathlib import Path

from tests.conftest import requires_verilator, requires_yosys

BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"
SIMPLE_ADDER_ROOT = BENCHMARKS_ROOT / "simple_adder"

GOOD_ADDER = "module adder(input [7:0] a, b, output [7:0] sum);\n  assign sum = a + b;\nendmodule\n"
BAD_ADDER = "module adder(input [7:0] a, b, output [7:0] sum);\n  assign sum = a - b;\nendmodule\n"
# A testbench the agent might drop in to fake a pass — reeval must DISCARD this and use
# the benchmark's own tb.sv, so the bad design still fails.
TAMPERED_TB = "// agent-tampered testbench (must be ignored by the judge)\nmodule tb; endmodule\n"


def _make_run(base: Path, bench, design_src: str, advisory_cost, advisory_passed: bool,
              tamper_tb: bool = False) -> Path:
    """Build a finished-run directory (workdir/eval_1/ + result.json) with a fabricated
    advisory claim, mimicking what an agent backend leaves on disk."""
    workdir = base / "wd"
    eval1_ws = workdir / "eval_1" / "workspace"
    eval1_ws.mkdir(parents=True)
    if tamper_tb:
        (eval1_ws / "tb.sv").write_text(TAMPERED_TB)
    else:
        shutil.copy2(bench.testbench, eval1_ws / "tb.sv")
    (eval1_ws / "design.sv").write_text(design_src)

    eval_dict = {
        "passed": advisory_passed, "cost_value": advisory_cost,
        "cost": {"ok": True, "value": advisory_cost, "error": ""},
        "metrics": {}, "cost_metric": "transistors",
        "eval_index": 1, "design_file": "design.sv", "target_delay": None,
    }
    (workdir / "eval_1" / "result.json").write_text(json.dumps(eval_dict, indent=2))

    run_result = {
        "benchmark_name": bench.name, "model": "fake:x",
        "passed": advisory_passed, "best_cost": advisory_cost,
        "cost_metric": "transistors", "best_metrics": {},
        "best_eval": eval_dict, "all_evals": [eval_dict],
        "num_steps": 1, "token_usage": {}, "duration_s": 0.0,
        "error": "", "workdir": str(workdir),
    }
    (workdir / "result.json").write_text(json.dumps(run_result, indent=2))
    return workdir


@requires_verilator
@requires_yosys
def test_run_eval_and_store_tree(tmp_path):
    """The advisory shim emits the standard tree: eval_{i}/, best_design/ + meta, evals.jsonl."""
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric
    from core.eval_store import run_eval_and_store
    from core.runner import provision_workspace

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    workdir = tmp_path / "wd"
    ws, _ = provision_workspace(bench, workdir, language="verilog", run_cec=False)
    (ws / "design.sv").write_text(GOOD_ADDER)
    cm = make_cost_metric("transistors")

    ed = run_eval_and_store(ws, design_top_module=bench.module_name, cost_metric=cm,
                            language="verilog", run_root=workdir, design_file="design.sv",
                            run_cec=False, quiet=True)
    assert ed["passed"] is True
    assert ed["eval_index"] == 1
    assert (workdir / "eval_1" / "result.json").exists()
    assert (workdir / "eval_1" / "workspace" / "design.sv").exists()
    assert (workdir / "evals.jsonl").exists()

    meta = json.loads((workdir / "best_design" / "_best_meta.json").read_text())
    assert meta["eval_index"] == 1
    assert meta["best_cost"] == ed["cost_value"]

    # A second eval increments the index and appends to evals.jsonl.
    ed2 = run_eval_and_store(ws, design_top_module=bench.module_name, cost_metric=cm,
                             language="verilog", run_root=workdir, design_file="design.sv",
                             run_cec=False, quiet=True)
    assert ed2["eval_index"] == 2
    assert len((workdir / "evals.jsonl").read_text().strip().splitlines()) == 2


@requires_verilator
@requires_yosys
def test_reeval_catches_tampered_pass(tmp_path):
    """Agent fakes a pass with a tampered testbench + a wrong design. The authoritative
    re-eval against the benchmark's own tb.sv must DOWNGRADE it to FAIL and flag it."""
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric
    from core.reeval import reeval_run
    from core.sandbox import LocalSandbox

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    workdir = _make_run(tmp_path, bench, BAD_ADDER, advisory_cost=5.0,
                        advisory_passed=True, tamper_tb=True)

    cm = make_cost_metric("transistors")
    report = reeval_run(workdir, bench, LocalSandbox(), cost_metric=cm,
                        language="verilog", run_cec=False)

    assert report["authoritative_passed"] is False
    assert report["diverged"] is True

    e = json.loads((workdir / "eval_1" / "result.json").read_text())
    assert e["authoritative"] is True
    assert e["passed"] is False

    r = json.loads((workdir / "result.json").read_text())
    assert r["passed"] is False
    assert r["best_cost"] is None
    assert r["reeval"]["applied"] is True


@requires_verilator
@requires_yosys
def test_reeval_flags_cost_divergence(tmp_path):
    """Agent reports a (good, passing) design but fabricates an absurdly low cost. The
    authoritative cost is the real one and the gate flags the divergence."""
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric
    from core.reeval import reeval_run
    from core.sandbox import LocalSandbox

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    workdir = _make_run(tmp_path, bench, GOOD_ADDER, advisory_cost=1.0,
                        advisory_passed=True, tamper_tb=False)

    cm = make_cost_metric("transistors")
    report = reeval_run(workdir, bench, LocalSandbox(), cost_metric=cm,
                        language="verilog", run_cec=False)

    assert report["authoritative_passed"] is True
    assert report["authoritative_best_cost"] is not None
    assert report["authoritative_best_cost"] > 1.0   # real transistor count >> fabricated 1.0
    assert report["diverged"] is True


@requires_verilator
@requires_yosys
def test_reeval_honest_run_agrees(tmp_path):
    """An honest run (advisory == authoritative) is NOT flagged, and best_design/ is
    rebuilt from the authoritative numbers. Value-agnostic: round 1 discovers the real
    cost, round 2 uses it as the honest advisory."""
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric
    from core.reeval import reeval_run
    from core.sandbox import LocalSandbox

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    cm = make_cost_metric("transistors")

    wd1 = _make_run(tmp_path / "r1", bench, GOOD_ADDER, advisory_cost=12345.0, advisory_passed=True)
    rep1 = reeval_run(wd1, bench, LocalSandbox(), cost_metric=cm, language="verilog", run_cec=False)
    real_cost = rep1["authoritative_best_cost"]
    assert real_cost is not None and real_cost > 0
    assert rep1["diverged"] is True  # 12345 != real

    wd2 = _make_run(tmp_path / "r2", bench, GOOD_ADDER, advisory_cost=real_cost, advisory_passed=True)
    rep2 = reeval_run(wd2, bench, LocalSandbox(), cost_metric=cm, language="verilog", run_cec=False)
    assert rep2["authoritative_passed"] is True
    assert rep2["diverged"] is False

    meta = json.loads((wd2 / "best_design" / "_best_meta.json").read_text())
    assert meta["best_cost"] == real_cost

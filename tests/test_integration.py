"""Integration tests for run_benchmark, run_multirun, and run_eval."""

import shutil
from pathlib import Path

import pytest

from tests.conftest import requires_verilator, requires_yosys

BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"
SIMPLE_ADDER_ROOT = BENCHMARKS_ROOT / "simple_adder"

SIMPLE_ADDER_VERILOG = """\
module adder(input [7:0] a, b, output [7:0] sum);
  assign sum = a + b;
endmodule
"""


@requires_verilator
@requires_yosys
def test_run_eval_simple_adder(tmp_path):
    """Evaluate a correct simple_adder design directly (no LLM)."""
    from core.evaluation import evaluate

    workdir = tmp_path / "workspace"
    workdir.mkdir()
    shutil.copy2(SIMPLE_ADDER_ROOT / "tb.sv", workdir / "tb.sv")
    (workdir / "design.sv").write_text(SIMPLE_ADDER_VERILOG)

    result = evaluate(
        workdir=workdir,
        design_top_module="adder",
        design_file="design.sv",
    )

    assert result.passed
    assert result.cost_value is not None
    assert result.cost_value > 0
    assert result.correctness.passed
    assert result.correctness.lint_ok
    assert result.correctness.sim_ok
    assert result.correctness.total_checks == 3
    assert result.correctness.passed_checks == 3


@requires_verilator
@requires_yosys
def test_run_benchmark_simple_adder(tmp_path):
    """Run the agent loop on simple_adder with a fake Verilog provider."""
    from core.benchmarks import load_benchmark
    from core.runner import run_agent_on_benchmark

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    result = run_agent_on_benchmark(
        bench,
        model="simple_adder_pass",
        runs_dir=tmp_path / "runs",
        max_steps=10,
        provider="fake",
    )

    assert result.passed
    assert result.best_cost is not None
    assert result.best_cost > 0
    assert result.num_steps == 3
    assert list((tmp_path / "runs").rglob("result.json"))
    assert list((tmp_path / "runs").rglob("best_design"))


@requires_verilator
@requires_yosys
def test_run_benchmark_simple_adder_spirehdl(tmp_path):
    """Run the agent loop on simple_adder with a fake SpireHDL provider."""
    from core.benchmarks import load_benchmark
    from core.runner import run_agent_on_benchmark

    bench = load_benchmark(SIMPLE_ADDER_ROOT)
    result = run_agent_on_benchmark(
        bench,
        model="simple_adder_spirehdl_pass",
        runs_dir=tmp_path / "runs",
        max_steps=10,
        provider="fake",
        language="spirehdl",
    )

    assert result.passed
    assert result.best_cost is not None
    assert result.best_cost > 0
    assert list((tmp_path / "runs").rglob("result.json"))
    assert list((tmp_path / "runs").rglob("best_design"))


@requires_verilator
@requires_yosys
def test_run_multirun_simple_adder(tmp_path):
    """Run multirun on simple_adder with a fake Verilog provider."""
    from core.multirun import run_multirun

    summary = run_multirun(
        benchmark_name="simple_adder",
        model="fake:simple_adder_pass",
        total_runs=2,
        max_concurrent=1,
        max_steps=10,
        elite_size=2,
        cost_metric="transistors",
        runs_root=tmp_path / "ms_runs",
    )

    assert summary["global_best_cost"] is not None
    assert summary["global_best_cost"] > 0
    assert (tmp_path / "ms_runs" / "multirun_summary.json").exists()
    passing = [r for r in summary["runs"] if r.get("passed")]
    assert len(passing) >= 1


@requires_verilator
@requires_yosys
def test_run_multirun_simple_adder_spirehdl(tmp_path):
    """Run multirun on simple_adder with a fake SpireHDL provider."""
    from core.multirun import run_multirun

    summary = run_multirun(
        benchmark_name="simple_adder",
        model="fake:simple_adder_spirehdl_pass",
        total_runs=2,
        max_concurrent=1,
        max_steps=10,
        elite_size=2,
        cost_metric="transistors",
        language="spirehdl",
        runs_root=tmp_path / "ms_runs",
    )

    assert summary["global_best_cost"] is not None
    assert summary["global_best_cost"] > 0
    assert (tmp_path / "ms_runs" / "multirun_summary.json").exists()
    passing = [r for r in summary["runs"] if r.get("passed")]
    assert len(passing) >= 1

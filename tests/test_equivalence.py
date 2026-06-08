"""Tests for combinational equivalence checking (CEC)."""

import shutil
from pathlib import Path

import pytest

from tests.conftest import requires_verilator, requires_yosys, requires_yosys_abc

BENCHMARKS_ROOT = Path(__file__).parent.parent / "benchmarks"
SIMPLE_ADDER_ROOT = BENCHMARKS_ROOT / "simple_adder"

# Both keep module name `adder` and identical port names a,b,sum so ABC's cec
# matches primary inputs/outputs by name.
ADDER_PLUS = """\
module adder(input [7:0] a, b, output [7:0] sum);
  assign sum = a + b;
endmodule
"""

ADDER_MINUS = """\
module adder(input [7:0] a, b, output [7:0] sum);
  assign sum = a - b;
endmodule
"""


# ── unit tests for run_cec ───────────────────────────────────────────────────

@requires_yosys
@requires_yosys_abc
def test_run_cec_equivalent(tmp_path):
    from core.equivalence import run_cec

    (tmp_path / "design.v").write_text(ADDER_PLUS)
    (tmp_path / "golden.v").write_text(ADDER_PLUS)

    r = run_cec(tmp_path / "design.v", tmp_path / "golden.v", tmp_path,
                design_top_module="adder")
    assert r.ran
    assert r.tool_ok, r.error
    assert r.equivalent is True


@requires_yosys
@requires_yosys_abc
def test_run_cec_not_equivalent(tmp_path):
    from core.equivalence import run_cec

    (tmp_path / "design.v").write_text(ADDER_PLUS)
    (tmp_path / "golden.v").write_text(ADDER_MINUS)

    r = run_cec(tmp_path / "design.v", tmp_path / "golden.v", tmp_path,
                design_top_module="adder")
    assert r.ran
    assert r.tool_ok, r.error
    assert r.equivalent is False


@requires_yosys
@requires_yosys_abc
def test_run_cec_missing_reference(tmp_path):
    from core.equivalence import run_cec

    (tmp_path / "design.v").write_text(ADDER_PLUS)
    r = run_cec(tmp_path / "design.v", tmp_path / "nope.v", tmp_path,
                design_top_module="adder")
    assert r.ran
    assert r.tool_ok is False
    assert r.equivalent is None
    assert "not found" in r.error


def test_resolve_golden_reference_verilog(tmp_path):
    from core.equivalence import resolve_golden_reference

    class _Bench:
        root = tmp_path
        golden_reference = (tmp_path / "ref.v")
        golden_reference_language = "verilog"

    (tmp_path / "ref.v").write_text(ADDER_PLUS)
    out = resolve_golden_reference(_Bench(), tmp_path / "_golden")
    assert out == (tmp_path / "ref.v")


# ── integration tests: evaluate() gating ─────────────────────────────────────

def _make_workspace(tmp_path):
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    shutil.copy2(SIMPLE_ADDER_ROOT / "tb.sv", workdir / "tb.sv")
    (workdir / "design.sv").write_text(ADDER_PLUS)
    return workdir


@requires_verilator
@requires_yosys
@requires_yosys_abc
def test_evaluate_cec_gate_fails(tmp_path):
    """Design passes the testbench but differs from golden -> gate fails it."""
    from core.evaluation import evaluate

    workdir = _make_workspace(tmp_path)
    golden = tmp_path / "golden.sv"  # outside workspace/
    golden.write_text(ADDER_MINUS)

    result = evaluate(
        workdir=workdir,
        design_top_module="adder",
        design_file="design.sv",
        run_cec=True,
        cec_reference=golden,
    )

    # Simulation still passes (design is a+b, matching tb).
    assert result.correctness.passed
    # But CEC says the design differs from the golden reference.
    assert result.cec is not None
    assert result.cec.ran
    assert result.cec.equivalent is False
    # ...so the overall result is gated to FAIL.
    assert result.passed is False


@requires_verilator
@requires_yosys
@requires_yosys_abc
def test_evaluate_cec_gate_passes(tmp_path):
    """Design equivalent to golden -> CEC passes and result passes."""
    from core.evaluation import evaluate

    workdir = _make_workspace(tmp_path)
    golden = tmp_path / "golden.sv"
    golden.write_text(ADDER_PLUS)

    result = evaluate(
        workdir=workdir,
        design_top_module="adder",
        design_file="design.sv",
        run_cec=True,
        cec_reference=golden,
    )

    assert result.cec is not None
    assert result.cec.equivalent is True
    assert result.passed is True


@requires_verilator
@requires_yosys
def test_evaluate_skip_cec(tmp_path):
    """run_cec=False skips CEC even when a (mismatched) reference is given."""
    from core.evaluation import evaluate

    workdir = _make_workspace(tmp_path)
    golden = tmp_path / "golden.sv"
    golden.write_text(ADDER_MINUS)  # would fail CEC if it ran

    result = evaluate(
        workdir=workdir,
        design_top_module="adder",
        design_file="design.sv",
        run_cec=False,
        cec_reference=golden,
    )
    assert result.cec is None
    assert result.passed == result.correctness.passed


@requires_verilator
@requires_yosys
def test_evaluate_default_no_reference(tmp_path):
    """Default run_cec=True but no reference -> CEC skipped, cec is None."""
    from core.evaluation import evaluate

    workdir = _make_workspace(tmp_path)
    result = evaluate(
        workdir=workdir,
        design_top_module="adder",
        design_file="design.sv",
    )
    assert result.cec is None
    assert result.passed == result.correctness.passed

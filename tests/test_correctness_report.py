"""A Verilator build failure reaches the agent as its %Error lines, not as a raw stderr tail."""
import pytest

from rtlscout import correctness
from rtlscout.correctness import SimResult, evaluate_correctness, verilator_errors

LOG = """%Warning-WIDTHTRUNC: design.v:10:5: Operator ASSIGN expects 8 bits
   10 |     a = b;
      |     ^
                     ... For warning description see https://verilator.org/warn/WIDTHTRUNC
%Error: design.v:584:47: Can't find definition of variable: 'pipe2_sa'
                                                : ... Suggested alternative: 'pipe1_ma'
  584 |   assign x = pipe2_sa;
      |              ^~~~~~~~
%Warning-VARHIDDEN: tb.sv:1055:17: Declaration of signal hides declaration in upper scope: 'n'
 1055 |   input integer n;
%Error: Exiting due to 1 error(s)
"""


def test_verilator_errors_keeps_error_blocks_and_drops_warnings():
    out = verilator_errors(LOG)
    assert out.startswith("%Error: design.v:584:47")
    assert "Suggested alternative" in out and "584 |" in out      # continuation lines of the error
    assert "%Warning" not in out and "input integer n" not in out
    assert out.endswith("%Error: Exiting due to 1 error(s)")


def test_verilator_errors_falls_back_to_the_whole_log_and_caps_long_output():
    assert verilator_errors("Timeout expired") == "Timeout expired"
    many = "\n".join(f"%Error: e{i}" for i in range(50))
    out = verilator_errors(many, max_lines=40).splitlines()
    assert len(out) == 41 and out[-1] == "... (10 more lines)"


def test_build_failure_is_a_failed_evaluation_with_the_errors(tmp_path, monkeypatch):
    (tmp_path / "design.v").write_text("module tb; endmodule\n")
    (tmp_path / "tb.sv").write_text("")
    monkeypatch.setattr(correctness, "lint", lambda sources, workdir: SimResult(False, "", LOG, 1))
    monkeypatch.setattr(correctness, "simulate",
                        lambda sources, top, workdir: SimResult(False, "", LOG, 1, build_failed=True))
    res = evaluate_correctness(tmp_path, tmp_path / "design.v")
    assert not res.passed and not res.sim_ok and res.total_checks == 0
    assert res.sim_stderr.startswith("Verilator could not build the design with the testbench:\n%Error: design.v:584")
    assert "%Warning" not in res.sim_stderr and "%Warning" not in res.lint_stderr


def test_missing_summary_after_a_successful_build_still_raises(tmp_path, monkeypatch):
    (tmp_path / "design.v").write_text("")
    (tmp_path / "tb.sv").write_text("")
    monkeypatch.setattr(correctness, "lint", lambda sources, workdir: SimResult(True, "", "", 0))
    monkeypatch.setattr(correctness, "simulate", lambda sources, top, workdir: SimResult(False, "no summary", "", 1))
    with pytest.raises(ValueError, match="No TB_SUMMARY"):
        evaluate_correctness(tmp_path, tmp_path / "design.v")

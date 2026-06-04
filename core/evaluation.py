"""Evaluation module combining correctness and cost."""

# Output filename written by SpireHDL/Amaranth scripts.
# Used in evaluation.py (compile step) and prompts.py (canonical pattern).
SPIREHDL_VERILOG_OUTPUT = "design.v"
AMARANTH_VERILOG_OUTPUT = "design.v"

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Timeout (seconds) for SpireHDL/Amaranth compilation subprocesses.
# Override with SPIREHDL_TIMEOUT env var (e.g. for long flowy optimizations).
COMPILE_TIMEOUT = int(os.environ.get("SPIREHDL_TIMEOUT", "60"))

from core.correctness import CorrectnessResult, evaluate_correctness
from core.cost import COST_METRICS, CostMetric, CostResult, YosysTransistorCost


def _is_scalar(v: Any) -> bool:
    """True if *v* is a plain int/float (not bool, not None, not dict/list/str)."""
    if v is None or isinstance(v, bool):
        return False
    return isinstance(v, (int, float))


def _metric_keys(cost_metric_name: str) -> tuple[Optional[str], Optional[str]]:
    """Return (primary_key, tiebreaker_key) for a metric name, or (None, None)."""
    cls = COST_METRICS.get(cost_metric_name)
    if cls is None:
        return None, None
    return getattr(cls, "primary_key", None), getattr(cls, "tiebreaker_key", None)


def _truncate(text: str, limit: int) -> str:
    """Truncate text to *limit* chars, keeping first and last portions."""
    if len(text) <= limit:
        return text
    sep = " .. "
    side = (limit - len(sep)) // 2
    return text[:side] + sep + text[-side:]


@dataclass
class EvaluationResult:
    correctness: CorrectnessResult
    cost: CostResult
    passed: bool
    cost_value: Optional[float]
    cost_metric_name: str
    pass_rate: float

    python_run_output: str = ""

    MAX_OUTPUT_CHARS: int = 400
    MAX_JSON_CHARS: int = 1_000
    MAX_TIMING_PATH_CHARS: int = 3_000  # ~50-60 lines of OpenROAD report_checks

    def metrics(self) -> Dict[str, float]:
        """Return the flat scalar bag (``int``/``float`` only) from ``cost.stats``.

        Non-scalar entries (e.g. ``worst_timing_path``) are surfaced via
        dedicated top-level fields in ``to_dict`` / ``summary_str`` instead.
        """
        return {k: v for k, v in self.cost.stats.items() if _is_scalar(v)}

    def _sorted_metric_items(self) -> list[tuple[str, float]]:
        """Metric items ordered: primary first, tiebreaker second, rest alpha."""
        primary_key, tiebreaker_key = _metric_keys(self.cost_metric_name)
        items = self.metrics()
        head: list[tuple[str, float]] = []
        if primary_key and primary_key in items:
            head.append((primary_key, items[primary_key]))
        if tiebreaker_key and tiebreaker_key in items and tiebreaker_key != primary_key:
            head.append((tiebreaker_key, items[tiebreaker_key]))
        used = {k for k, _ in head}
        return head + sorted((k, v) for k, v in items.items() if k not in used)

    def summary_str(self) -> str:
        limit = self.MAX_OUTPUT_CHARS
        lines = []
        lines.append("=== Evaluation Result ===")
        lines.append(f"Correctness: {'PASS' if self.correctness.passed else 'FAIL'}")
        lines.append(f"  Lint: {'OK' if self.correctness.lint_ok else 'FAIL'}")
        lines.append(f"  Sim:  {'OK' if self.correctness.sim_ok else 'FAIL'}")
        lines.append(f"  Checks (ok/tot): {self.correctness.passed_checks}/{self.correctness.total_checks}")
        if not self.correctness.lint_ok:
            lines.append(f"  Lint errors: {_truncate(self.correctness.lint_stderr, limit)}")
        if not self.correctness.sim_ok:
            sim_err = _truncate(self.correctness.sim_stderr, limit)
            sim_out = _truncate(self.correctness.sim_stdout, limit)
            lines.append(f"  Sim output: {sim_out}")
            if sim_err:
                lines.append(f"  Sim errors: {sim_err}")
        lines.append(f"Cost: {'OK' if self.cost.ok else 'FAIL'}")
        if self.cost.ok:
            lines.append(f"  {self.cost_metric_name}: {self.cost_value}")
            items = self._sorted_metric_items()
            if items:
                lines.append("  Metrics:")
                for k, v in items:
                    lines.append(f"    {k}: {v}")
            worst_slack = self.cost.stats.get("worst_slack")
            if worst_slack is not None and not _is_scalar(worst_slack):
                # Non-numeric slack (unlikely but guard anyway)
                lines.append(f"  Worst slack: {worst_slack}")
            worst_path = self.cost.stats.get("worst_timing_path")
            if worst_path:
                lines.append("  Worst timing path:")
                for path_line in _truncate(worst_path, self.MAX_TIMING_PATH_CHARS).splitlines():
                    lines.append(f"    {path_line}")
        else:
            lines.append(f"  Cost error: {self.cost.error}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        lim = self.MAX_JSON_CHARS
        metrics = self.metrics()
        primary_key, tiebreaker_key = _metric_keys(self.cost_metric_name)
        tiebreaker_value = metrics.get(tiebreaker_key) if tiebreaker_key else None
        worst_path = _truncate(self.cost.stats.get("worst_timing_path") or "", self.MAX_TIMING_PATH_CHARS) or None
        return {
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "cost_value": self.cost_value,
            "cost_metric": self.cost_metric_name,
            "cost_tiebreaker_metric": tiebreaker_key,
            "cost_tiebreaker_value": tiebreaker_value,
            "metrics": metrics,
            "cost_extra": self.cost.extra or None,
            "worst_slack": self.cost.stats.get("worst_slack"),
            "worst_timing_path": worst_path,
            "python_run_output": _truncate(self.python_run_output, lim) if self.python_run_output else None,
            "correctness": {
                "passed": self.correctness.passed,
                "lint_ok": self.correctness.lint_ok,
                "sim_ok": self.correctness.sim_ok,
                "total_checks": self.correctness.total_checks,
                "passed_checks": self.correctness.passed_checks,
                "pass_rate": self.correctness.pass_rate,
                "sim_stdout": _truncate(self.correctness.sim_stdout, lim),
                "sim_stderr": _truncate(self.correctness.sim_stderr, lim),
                "lint_stderr": _truncate(self.correctness.lint_stderr, lim),
            },
            "cost": {"ok": self.cost.ok, "value": self.cost.value, "error": self.cost.error},
        }


def _compile_spirehdl(workdir: Path, design_file: Optional[str] = None) -> tuple:
    """Run .py design files that write Verilog directly via m.to_verilog_file().

    Returns (error: str, output: str) where output combines stdout and stderr.
    On success error is "".

    Args:
        workdir: Working directory containing .py design files.
        design_file: If given, run only this file. Otherwise run all non-tb .py files.
    """
    if design_file:
        py_file = workdir / design_file
        if not py_file.exists():
            return f"Design file not found: {design_file}", ""
        design_pys = [py_file]
    else:
        py_files = sorted(workdir.glob("*.py"))
        design_pys = [f for f in py_files if not f.name.startswith("tb")]
    if not design_pys:
        return ('No Python design files found. Create a .py file that uses SpireHDL '
                f'and writes Verilog via m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}").'), ""

    # Remove stale design.v so a script that runs but doesn't produce
    # output fails instead of silently reusing the old file.
    stale_v = workdir / SPIREHDL_VERILOG_OUTPUT
    if stale_v.exists():
        stale_v.unlink()

    verbose = bool(os.environ.get("SPIREHDL_VERBOSE"))
    all_output = []
    for py_file in design_pys:
        try:
            if verbose:
                # Stream output in real time
                proc = subprocess.Popen(
                    [sys.executable, "-u", py_file.name],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(workdir.resolve()),
                )
                chunks = []
                for line in proc.stdout:
                    print(line, end="", flush=True)
                    chunks.append(line)
                proc.wait(timeout=COMPILE_TIMEOUT)
                output = "".join(chunks)
                all_output.append(output)
                if proc.returncode != 0:
                    return (f"SpireHDL compilation failed ({py_file.name}):\n{output}",
                            "\n".join(all_output))
            else:
                result = subprocess.run(
                    [sys.executable, py_file.name],
                    capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
                    cwd=str(workdir.resolve()),
                )
                if result.stdout:
                    all_output.append(result.stdout)
                if result.stderr:
                    all_output.append(result.stderr)
                if result.returncode != 0:
                    return (f"SpireHDL compilation failed ({py_file.name}):\n{result.stderr}",
                            "\n".join(all_output))
        except (subprocess.TimeoutExpired, TimeoutError):
            # subprocess.TimeoutExpired — what subprocess.run raises on --timeout.
            # Builtin TimeoutError — used by some stdlib code paths and
            # third-party libs (e.g. asyncio). Note: `subprocess.TimeoutError`
            # does NOT exist; referencing it raises AttributeError at lookup
            # time when an exception is actually raised, silently swallowing
            # real timeouts.
            if verbose:
                proc.kill()
            return f"SpireHDL compilation timed out ({py_file.name})", "\n".join(all_output)
    return "", "\n".join(all_output)


def _compile_amaranth(workdir: Path, design_file: Optional[str] = None) -> tuple:
    """Run .py design files that write Verilog via amaranth.back.verilog.convert().

    Returns (error: str, output: str) where output combines stdout and stderr.
    On success error is "".

    Args:
        workdir: Working directory containing .py design files.
        design_file: If given, run only this file. Otherwise run all non-tb .py files.
    """
    if design_file:
        py_file = workdir / design_file
        if not py_file.exists():
            return f"Design file not found: {design_file}", ""
        design_pys = [py_file]
    else:
        py_files = sorted(workdir.glob("*.py"))
        design_pys = [f for f in py_files if not f.name.startswith("tb")]
    if not design_pys:
        return ('No Python design files found. Create a .py file that uses Amaranth HDL '
                f'and writes Verilog to "{AMARANTH_VERILOG_OUTPUT}".'), ""

    # Remove stale design.v so a script that runs but doesn't produce
    # output fails instead of silently reusing the old file.
    stale_v = workdir / AMARANTH_VERILOG_OUTPUT
    if stale_v.exists():
        stale_v.unlink()

    all_output = []
    for py_file in design_pys:
        try:
            result = subprocess.run(
                [sys.executable, py_file.name],
                capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
                cwd=str(workdir.resolve()),
            )
        except subprocess.TimeoutExpired:
            return f"Amaranth compilation timed out ({py_file.name})", "\n".join(all_output)
        if result.stdout:
            all_output.append(result.stdout)
        if result.stderr:
            all_output.append(result.stderr)
        if result.returncode != 0:
            return (f"Amaranth compilation failed ({py_file.name}):\n{result.stderr}",
                    "\n".join(all_output))
    return "", "\n".join(all_output)


def evaluate(
    workdir: Path,
    design_top_module: Optional[str] = None,
    cost_metric: Optional[CostMetric] = None,
    language: str = "verilog",
    design_file: Optional[str] = None,
) -> EvaluationResult:
    """Run full evaluation: correctness (verilator) + cost (pluggable metric).

    Args:
        workdir: Directory containing design .sv/.v files and testbench (tb.sv).
        design_top_module: Top module of the design (for cost extraction).
                          If None, cost extraction will auto-detect.
        cost_metric: Cost metric to use. Defaults to YosysTransistorCost.
        language: Design language ('verilog' or 'spirehdl').
        design_file: Main design file name (e.g. 'design.sv' or 'design.py').
                     For SpireHDL, only this file is compiled. For Verilog,
                     all .sv/.v files are still used for simulation but this
                     identifies the primary design.
    """
    if cost_metric is None:
        cost_metric = YosysTransistorCost()

    python_run_output = ""

    # SpireHDL: run .py -> writes Verilog file(s) directly
    if language == "spirehdl":
        compile_err, python_run_output = _compile_spirehdl(workdir, design_file)
        if compile_err:
            failed_correctness = CorrectnessResult(
                passed=False, lint_ok=False, sim_ok=False,
                lint_stdout="", lint_stderr=compile_err,
                sim_stdout="", sim_stderr="", sim_returncode=-1,
            )
            failed_cost = CostResult(ok=False, value=None, stats={}, error=compile_err)
            return EvaluationResult(
                correctness=failed_correctness,
                cost=failed_cost,
                passed=False,
                cost_value=None,
                cost_metric_name=cost_metric.metric_name,
                pass_rate=0.0,
                python_run_output=python_run_output,
            )
        verilog_file = workdir / SPIREHDL_VERILOG_OUTPUT
    elif language == "amaranth":
        compile_err, python_run_output = _compile_amaranth(workdir, design_file)
        if compile_err:
            failed_correctness = CorrectnessResult(
                passed=False, lint_ok=False, sim_ok=False,
                lint_stdout="", lint_stderr=compile_err,
                sim_stdout="", sim_stderr="", sim_returncode=-1,
            )
            failed_cost = CostResult(ok=False, value=None, stats={}, error=compile_err)
            return EvaluationResult(
                correctness=failed_correctness,
                cost=failed_cost,
                passed=False,
                cost_value=None,
                cost_metric_name=cost_metric.metric_name,
                pass_rate=0.0,
                python_run_output=python_run_output,
            )
        verilog_file = workdir / AMARANTH_VERILOG_OUTPUT
    else:
        verilog_file = (workdir / design_file) if design_file else None

    correctness = evaluate_correctness(workdir, design_file=verilog_file)
    cost = cost_metric.evaluate(workdir, design_top_module, design_file=verilog_file)

    return EvaluationResult(
        correctness=correctness,
        cost=cost,
        passed=correctness.passed,
        cost_value=cost.value if cost.ok else None,
        cost_metric_name=cost_metric.metric_name,
        pass_rate=correctness.pass_rate,
        python_run_output=python_run_output,
    )

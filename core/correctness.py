"""Correctness evaluation via Verilator simulation."""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SimResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


@dataclass
class CorrectnessResult:
    passed: bool
    lint_ok: bool
    sim_ok: bool
    lint_stdout: str
    lint_stderr: str
    sim_stdout: str
    sim_stderr: str
    sim_returncode: int
    testbench_checks: List[Dict[str, Any]] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.passed_checks / self.total_checks


def _run(args: List[str], cwd: Path, timeout: int = 30) -> SimResult:
    try:
        proc = subprocess.run(
            args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        return SimResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return SimResult(ok=False, stdout="", stderr="Timeout expired", returncode=-1)
    except Exception as e:
        return SimResult(ok=False, stdout="", stderr=str(e), returncode=-1)
    

verilator_common_flags = [
    "-Wall",
    "-Wno-DECLFILENAME",
    "-Wno-WIDTHEXPAND",
    "-Wno-UNUSEDSIGNAL",
    "--Wno-EOFNEWLINE",
    "-Wno-BLKSEQ",
    "-Wno-fatal",
    "--timescale",
    "1ns/10ps",
]


def lint(sources: List[Path], workdir: Path) -> SimResult:
    if shutil.which("verilator") is None:
        return SimResult(False, "", "verilator not found", 127)
    args = ["verilator", "--lint-only", "--timing", "--sv"] + verilator_common_flags + [str(s.resolve()) for s in sources]
    return _run(args, workdir.resolve())


def simulate(sources: List[Path], top_module: str, workdir: Path, build_timeout: int = 180) -> SimResult:
    if shutil.which("verilator") is None:
        return SimResult(False, "", "verilator not found", 127)
    abs_workdir = workdir.resolve()
    obj_dir = abs_workdir / "obj_dir"
    obj_dir.mkdir(exist_ok=True)
    build_args = [
        "verilator", "--binary", "--sv", "--top-module", top_module,
        "-o", "simv",
    ] + verilator_common_flags + [str(s.resolve()) for s in sources]
    build = _run(build_args, abs_workdir, timeout=build_timeout)
    if not build.ok:
        return SimResult(
            ok=False,
            stdout=build.stdout,
            stderr=build.stderr,
            returncode=build.returncode,
        )
    return _run([str(obj_dir / "simv")], abs_workdir)


def parse_testbench_checks(sim_stdout: str, sim_stderr: str) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    lines = (sim_stdout + "\n" + sim_stderr).splitlines()

    # New format: TB_SUMMARY total=N errors=M  (emitted at end of testbench)
    for line in lines:
        if "TB_SUMMARY" not in line:
            continue
        kv = {k: v for tok in line.split() if "=" in tok for k, v in [tok.split("=", 1)]}
        total  = int(kv.get("total",  0))
        errors = int(kv.get("errors", 0))
        passed = total - errors
        # Emit one record per check so that len(checks)==total and
        # sum(c["passed"]) == passed, matching the existing accounting.
        for _ in range(errors):
            checks.append({"passed": False})
        for _ in range(passed):
            checks.append({"passed": True})
        return checks
    last_1000_characters_stdout = sim_stdout[-1000:] if len(sim_stdout) > 1000 else sim_stdout
    last_1000_characters_stderr = sim_stderr[-1000:] if len(sim_stderr) > 1000 else sim_stderr
    raise ValueError("No TB_SUMMARY line found in simulation output" +
                     f"\nLast 1000 characters of stdout:\n{last_1000_characters_stdout}" +
                     f"\nLast 1000 characters of stderr:\n{last_1000_characters_stderr}")


def evaluate_correctness(workdir: Path, design_file: Optional[Path] = None) -> CorrectnessResult:
    """Run verilator lint + simulation for a design + testbench.

    If design_file is given, sources are [design_file, tb.sv].
    Otherwise all .sv/.v files in workdir are used (fallback).

    Returns a CorrectnessResult with pass/fail and detailed check info.
    """
    workdir = workdir.resolve()
    if design_file is not None:
        sources = [design_file.resolve(), (workdir / "tb.sv").resolve()]
    else:
        sources = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
    if not sources:
        return CorrectnessResult(
            passed=False, lint_ok=False, sim_ok=False,
            lint_stdout="", lint_stderr="No source files found",
            sim_stdout="", sim_stderr="No source files found",
            sim_returncode=-1,
        )

    lint_result = lint(sources, workdir)
    sim_result = simulate(sources, "tb", workdir)
    checks = parse_testbench_checks(sim_result.stdout, sim_result.stderr)
    total = len(checks)
    passed_checks = sum(1 for c in checks if c.get("passed"))
    all_passed = sim_result.ok and lint_result.ok

    return CorrectnessResult(
        passed=all_passed,
        lint_ok=lint_result.ok,
        sim_ok=sim_result.ok,
        lint_stdout=lint_result.stdout,
        lint_stderr=lint_result.stderr,
        sim_stdout=sim_result.stdout,
        sim_stderr=sim_result.stderr,
        sim_returncode=sim_result.returncode,
        testbench_checks=checks,
        total_checks=total,
        passed_checks=passed_checks,
    )

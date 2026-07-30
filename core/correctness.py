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
    # Optional scalar statistics scraped from the simulation (e.g. {"cycles": C}
    # from a TB_CYCLES line). Empty for testbenches that don't emit them.
    sim_stats: Dict[str, Any] = field(default_factory=dict)

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


# X/Z is banned in designs (tb.sv exempt): 2-state sim folds X to a constant while
# synthesis treats it as don't-care, so a design can pass every vector yet synthesize wrong.
_XZ_LITERAL_RE = re.compile(
    r"'\s*[sS]?[bodhBODH]\s*[0-9a-fA-F_xXzZ?]*[xXzZ?]|'[xXzZ]\b|\bcase[xz]\b")


def _xz_dontcare_hits(source: Path) -> List[str]:
    """Return 'line N: <text>' for each X/Z don't-care use in a design file
    (comments and string literals stripped)."""
    hits = []
    in_block = False
    try:
        text = source.read_text(errors="replace")
    except OSError:
        return hits
    for num, line in enumerate(text.splitlines(), 1):
        if in_block:
            end = line.find("*/")
            if end < 0:
                continue
            line = line[end + 2:]
            in_block = False
        line = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
        line = re.sub(r"/\*.*?\*/", " ", line)
        start = line.find("/*")
        if start >= 0:
            line = line[:start]
            in_block = True
        line = line.split("//")[0]
        if _XZ_LITERAL_RE.search(line):
            hits.append(f"line {num}: {line.strip()}")
    return hits


def lint(sources: List[Path], workdir: Path) -> SimResult:
    xz_report = []
    for s in sources:
        if s.name == "tb.sv":
            continue
        hits = _xz_dontcare_hits(s)
        if hits:
            xz_report.append(f"{s.name}:\n  " + "\n  ".join(hits))
    if xz_report:
        return SimResult(
            False, "",
            "X/Z don't-care lint failed: designs must not use X/Z literals or "
            "casex/casez. 2-state simulation folds X to a constant (so vectors "
            "can still pass) while synthesis treats X as a don't-care and may "
            "implement different hardware. Fully specify every output and "
            "state transition.\n" + "\n".join(xz_report), 1)
    if shutil.which("verilator") is None:
        return SimResult(False, "", "verilator not found", 127)
    args = ["verilator", "--lint-only", "--timing", "--sv"] + verilator_common_flags + [str(s.resolve()) for s in sources]
    return _run(args, workdir.resolve())


def simulate(sources: List[Path], top_module: str, workdir: Path, build_timeout: int = 180,
             sim_timeout: int = 240) -> SimResult:
    if shutil.which("verilator") is None:
        return SimResult(False, "", "verilator not found", 127)
    abs_workdir = workdir.resolve()
    obj_dir = abs_workdir / "obj_dir"
    obj_dir.mkdir(exist_ok=True)
    build_args = [
        "verilator", "--binary", "--sv", "--top-module", top_module,
        "-o", "simv",
    ] + verilator_common_flags + [str(s.resolve()) for s in sources]
    try:
        build = _run(build_args, abs_workdir, timeout=build_timeout)
        if not build.ok:
            return SimResult(
                ok=False,
                stdout=build.stdout,
                stderr=build.stderr,
                returncode=build.returncode,
            )
        # Gate-level netlists (e.g. deepsyn AIGs) simulate ~10x slower than
        # behavioral RTL; the old 30 s default silently killed them.
        return _run([str(obj_dir / "simv")], abs_workdir, timeout=sim_timeout)
    finally:
        # Pure scratch: all diagnostics are captured in the returned SimResult and nothing downstream reads
        # obj_dir, so remove it here — workspaces stay free of build residue by construction.
        shutil.rmtree(obj_dir, ignore_errors=True)


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


def parse_sim_stats(sim_stdout: str, sim_stderr: str) -> Dict[str, Any]:
    """Scrape optional scalar statistics from simulation output.

    Recognizes ``TB_CYCLES total=<C>`` (cycles reset->done), ``TB_READS
    total=<R>`` and ``TB_WRITES total=<W>`` (read/write memory accesses, for the
    data-movement energy metrics). Tolerant by design: returns ``{}`` when no
    such lines are present, so testbenches that don't emit them (every other
    benchmark) are unaffected. The last occurrence of each wins.
    """
    stats: Dict[str, Any] = {}
    tag_to_key = {"TB_CYCLES": "cycles", "TB_READS": "reads", "TB_WRITES": "writes"}
    lines = (sim_stdout + "\n" + sim_stderr).splitlines()
    for line in lines:
        tag = next((t for t in tag_to_key if t in line), None)
        if tag is None:
            continue
        kv = {k: v for tok in line.split() if "=" in tok for k, v in [tok.split("=", 1)]}
        if "total" in kv:
            try:
                stats[tag_to_key[tag]] = int(kv["total"])
            except ValueError:
                pass
    return stats


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
    sim_stats = parse_sim_stats(sim_result.stdout, sim_result.stderr)

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
        sim_stats=sim_stats,
    )

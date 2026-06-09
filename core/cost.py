"""Cost evaluation: abstract metric + implementations.

Implementations:
- YosysTransistorCost: estimated transistor count via Yosys + ABC (fast, no PDK)
- PPADelayCost / PPAAreaCost / PPAPowerCost: PPA via Yosys + OpenROAD STA (requires tech_eval)
"""

import json
import multiprocessing
import os
import queue as _queue
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

from tech_eval.ppa_extract.core.template import target_delay_time_unit


@dataclass
class CostResult:
    ok: bool
    value: Optional[float]  # the cost value (metric-specific), None on failure
    stats: Dict
    error: str = ""
    # Non-scalar / bulky diagnostics kept out of `stats` so downstream metrics stays purely numeric.
    extra: Dict = field(default_factory=dict)


class CostMetric(ABC):
    """Abstract base for cost metrics.

    Subclasses set ``primary_key`` (key in ``stats`` equal to ``value``, invariant
    ``cost.value == cost.stats[cost.primary_key]`` for ``ok=True``) and
    ``tiebreaker_key`` (natural secondary sort key, or ``None`` if no pair — e.g. transistors).
    """

    primary_key: ClassVar[str]
    tiebreaker_key: ClassVar[Optional[str]] = None

    @property
    @abstractmethod
    def metric_name(self) -> str:
        """Human-readable metric name, e.g. 'transistors', 'gates'."""
        ...

    @abstractmethod
    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        """Evaluate cost for design files in workdir.

        If design_file is given it is used directly; otherwise the workdir is
        scanned for .sv/.v files (excluding testbench).
        """
        ...


class YosysTransistorCost(CostMetric):
    """Cost metric: estimated transistor count via Yosys synthesis + ABC."""

    primary_key = "transistors"
    tiebreaker_key = "num_cells"

    @property
    def metric_name(self) -> str:
        return "transistors"

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )
        return self._extract(design_files, top_module)

    def _extract(self, verilog_files: List[Path], top_module: Optional[str] = None) -> CostResult:
        """Extract transistor count from Verilog files using Yosys."""
        fd_stat, stat_tmp_file = tempfile.mkstemp(suffix=".json")
        os.close(fd_stat)

        try:
            cmds = ["design -reset"]
            for vf in verilog_files:
                cmds.append(f"read_verilog -sv {vf}")

            if top_module:
                cmds.append(f"hierarchy -top {top_module}")
            else:
                cmds.append("hierarchy -check")

            cmds.append("proc; opt; fsm; memory; opt")
            cmds.append("techmap; opt; abc -fast; opt")

            top_flag = f"-top {top_module}" if top_module else ""
            cmds.append(f"tee -q -o {stat_tmp_file} stat {top_flag} -tech cmos -json")

            script = "; ".join(cmds)
            result = subprocess.run(
                ["yosys", "-p", script],
                capture_output=True, text=True, timeout=30,
            )

            if not os.path.exists(stat_tmp_file) or os.path.getsize(stat_tmp_file) == 0:
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"Yosys failed: {result.stderr[:500]}",
                )

            with open(stat_tmp_file, "r") as f:
                stats = json.load(f)

            modules = stats.get("modules", {})
            if top_module:
                key = f"\\{top_module}"
                if key not in modules:
                    key = top_module
                if key not in modules:
                    key = next(iter(modules))
            else:
                key = next(iter(modules))

            mod_stats = modules[key]
            raw_transistors = mod_stats.get("estimated_num_transistors", "0")
            if isinstance(raw_transistors, str):
                raw_transistors = int(raw_transistors.replace("+", ""))
            # Flat scalar subset lives in `stats`; the full yosys module dict (with nested
            # `num_cells_by_type`, etc.) goes to `extra`.  Drop None entries.
            flat_stats = {"transistors": int(raw_transistors)}
            for k in ("num_cells", "num_wires", "num_pub_wires"):
                v = mod_stats.get(k)
                if v is not None:
                    flat_stats[k] = v
            return CostResult(ok=True, value=int(raw_transistors), stats=flat_stats,
                              extra={"yosys_module_stats": mod_stats})

        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=str(e),
            )
        finally:
            if os.path.exists(stat_tmp_file):
                os.remove(stat_tmp_file)


# ---------------------------------------------------------------------------
# Sky130 ADP via yosys + yosys-abc stime (no OpenROAD, no STA)
# Mirrors references/run_evaluation.py.
# ---------------------------------------------------------------------------

SKY130_LIB_PATH = os.environ.get(
    "SKY130_LIB_PATH",
    "/prog/OpenROAD-flow-scripts/tools/OpenROAD/test/sky130hd/sky130_fd_sc_hd__ff_n40C_1v95.lib",
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_AREA_DELAY_RE = re.compile(r"Area\s*=\s*([0-9.]+).*?Delay\s*=\s*([0-9.]+)\s*ps", re.DOTALL)


class Sky130ADPCost(CostMetric):
    """Area × Delay against sky130_fd_sc_hd__ff_n40C_1v95 via yosys + yosys-abc."""

    primary_key = "adp"
    tiebreaker_key = "area"

    def __init__(self, lib_path: Optional[str] = None, timeout: int = 120):
        self.lib_path = lib_path or SKY130_LIB_PATH
        self.timeout = timeout

    @property
    def metric_name(self) -> str:
        return "sky130_adp"

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )
        if not os.path.exists(self.lib_path):
            return CostResult(
                ok=False, value=None, stats={},
                error=(f"Sky130 liberty not found: {self.lib_path}. "
                       "Set SKY130_LIB_PATH env var to override."),
            )

        tmp_dir = tempfile.mkdtemp(prefix="sky130_adp_")
        blif_path = os.path.join(tmp_dir, "design.blif")
        try:
            read_cmds = "\n".join(f"read_verilog -sv {vf}" for vf in design_files)
            top_cmd = f"hierarchy -top {top_module}" if top_module else "hierarchy -check"
            yosys_script = (
                f"design -reset\n"
                f"{read_cmds}\n"
                f"{top_cmd}\n"
                "proc\n"
                "opt\n"
                "techmap\n"
                "opt\n"
                "synth -flatten\n"
                "async2sync\n"
                "dffunmap\n"
                f"write_blif {blif_path}\n"
            )
            ys_script_path = os.path.join(tmp_dir, "synth.ys")
            with open(ys_script_path, "w") as f:
                f.write(yosys_script)

            ys_res = subprocess.run(
                ["yosys", "-q", ys_script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            if ys_res.returncode != 0 or not os.path.exists(blif_path):
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"Yosys synth failed: {ys_res.stderr[:500] or ys_res.stdout[:500]}",
                )

            abc_script = (
                f"read_blif {blif_path}\n"
                f"read_lib {self.lib_path}\n"
                "strash\n"
                "dch -f\n"
                "map\n"
                "topo\n"
                "upsize\n"
                "dnsize\n"
                "stime\n"
            )
            abc_script_path = os.path.join(tmp_dir, "abc.script")
            with open(abc_script_path, "w") as f:
                f.write(abc_script)

            abc_res = subprocess.run(
                ["yosys-abc", "-f", abc_script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            abc_out = _ANSI_RE.sub("", abc_res.stdout + "\n" + abc_res.stderr)
            matches = _AREA_DELAY_RE.findall(abc_out)
            if not matches:
                return CostResult(
                    ok=False, value=None, stats={"abc_stdout": abc_res.stdout[-500:]},
                    error="Could not parse Area/Delay from yosys-abc stime output",
                )
            area, delay_ps = matches[-1]
            area = float(area)
            delay_ps = float(delay_ps)
            adp = area * delay_ps
            return CostResult(
                ok=True,
                value=adp,
                stats={"area": area, "delay_ps": delay_ps, "adp": adp},
                extra={"lib_path": self.lib_path},
            )
        except subprocess.TimeoutExpired as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"sky130_adp timed out after {self.timeout}s",
            )
        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"sky130_adp failed: {e}",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class Sky130ADPCostV2(CostMetric):
    """Improved Area × Delay against sky130_fd_sc_hd__ff_n40C_1v95.

    Two improvements over ``Sky130ADPCost``:

    1. Adds ``clean -purge`` to the yosys script before ``write_blif``.
       This removes public-wire alias buffers (``assign output = reg``)
       that yosys's default ``opt_clean`` preserves for debuggability,
       fixing a ~12% ADP tax on small registered-output designs emitted
       by SpireHDL.
    2. Optionally runs both a default and an ``abc -fast``-pre-simplified
       AIG through abc's ``dch -f; map; stime`` flow and returns the
       lower ADP (``try_both_strategies=True``, the default). This
       closes another ~4-6% on benchmarks where abc's local search
       lands in a suboptimal mapping for one AIG shape but not the other.
    """

    primary_key = "adp"
    tiebreaker_key = "area"

    def __init__(self, lib_path: Optional[str] = None, timeout: int = 120,
                 try_both_strategies: bool = True):
        self.lib_path = lib_path or SKY130_LIB_PATH
        self.timeout = timeout
        self.try_both_strategies = try_both_strategies

    @property
    def metric_name(self) -> str:
        return "sky130_adp_v2"

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        if not self.try_both_strategies:
            return self._evaluate_one(workdir, top_module, design_file,
                                      abc_fast=False)
        a = self._evaluate_one(workdir, top_module, design_file, abc_fast=False)
        b = self._evaluate_one(workdir, top_module, design_file, abc_fast=True)
        if not a.ok:
            return b
        if not b.ok:
            return a
        winner = a if a.value <= b.value else b
        winner.extra = dict(winner.extra)
        winner.extra["both_strategies"] = {
            "default":  {"value": a.value, "area": a.stats.get("area"),
                         "delay_ps": a.stats.get("delay_ps")},
            "abc_fast": {"value": b.value, "area": b.stats.get("area"),
                         "delay_ps": b.stats.get("delay_ps")},
            "winner":   "default" if a.value <= b.value else "abc_fast",
        }
        return winner

    def _evaluate_one(self, workdir: Path, top_module: Optional[str],
                      design_file: Optional[Path], abc_fast: bool) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )
        if not os.path.exists(self.lib_path):
            return CostResult(
                ok=False, value=None, stats={},
                error=(f"Sky130 liberty not found: {self.lib_path}. "
                       "Set SKY130_LIB_PATH env var to override."),
            )

        tmp_dir = tempfile.mkdtemp(prefix="sky130_adp_v2_")
        blif_path = os.path.join(tmp_dir, "design.blif")
        try:
            read_cmds = "\n".join(f"read_verilog -sv {vf}" for vf in design_files)
            top_cmd = f"hierarchy -top {top_module}" if top_module else "hierarchy -check"
            abc_fast_line = "abc -fast\n" if abc_fast else ""
            yosys_script = (
                f"design -reset\n"
                f"{read_cmds}\n"
                f"{top_cmd}\n"
                "proc\n"
                "opt\n"
                "techmap\n"
                "opt\n"
                "synth -flatten\n"
                "async2sync\n"
                "dffunmap\n"
                f"{abc_fast_line}"
                "clean -purge\n"
                f"write_blif {blif_path}\n"
            )
            ys_script_path = os.path.join(tmp_dir, "synth.ys")
            with open(ys_script_path, "w") as f:
                f.write(yosys_script)

            ys_res = subprocess.run(
                ["yosys", "-q", ys_script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            if ys_res.returncode != 0 or not os.path.exists(blif_path):
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"Yosys synth failed: {ys_res.stderr[:500] or ys_res.stdout[:500]}",
                )

            abc_script = (
                f"read_blif {blif_path}\n"
                f"read_lib {self.lib_path}\n"
                "strash\n"
                "dch -f\n"
                "map\n"
                "topo\n"
                "upsize\n"
                "dnsize\n"
                "stime\n"
            )
            abc_script_path = os.path.join(tmp_dir, "abc.script")
            with open(abc_script_path, "w") as f:
                f.write(abc_script)

            abc_res = subprocess.run(
                ["yosys-abc", "-f", abc_script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            abc_out = _ANSI_RE.sub("", abc_res.stdout + "\n" + abc_res.stderr)
            matches = _AREA_DELAY_RE.findall(abc_out)
            if not matches:
                return CostResult(
                    ok=False, value=None, stats={"abc_stdout": abc_res.stdout[-500:]},
                    error="Could not parse Area/Delay from yosys-abc stime output",
                )
            area, delay_ps = matches[-1]
            area = float(area)
            delay_ps = float(delay_ps)
            adp = area * delay_ps
            return CostResult(
                ok=True,
                value=adp,
                stats={"area": area, "delay_ps": delay_ps, "adp": adp},
                extra={"lib_path": self.lib_path},
            )
        except subprocess.TimeoutExpired:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"sky130_adp_v2 timed out after {self.timeout}s",
            )
        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"sky130_adp_v2 failed: {e}",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Yosys stat wires / cells (post-synth, tech-independent)
# ---------------------------------------------------------------------------

_WIRES_RE = re.compile(r"Number of wires:\s+(\d+)")
_CELLS_RE = re.compile(r"Number of cells:\s+(\d+)")
_TRANSISTORS_RE = re.compile(r"Estimated number of transistors:\s+(\d+)")

# --- transistor side-stat strategy -----------------------------------------
# Bug this guards against: a design shipped as a module *hierarchy* (the top
# module instantiates submodules) leaves the top module's own gate count at
# zero -- the gates live inside the submodule *instances*. Reading the
# per-module `estimated_num_transistors` straight from `stat -tech cmos -json`
# then yields 0 (e.g. case13/case14 of the RTLRewriter benchmark, whose
# baselines ship `mux_tree` instantiating a `mux2to1` submodule). The wires
# and cells counts are unaffected: they are read from the text `stat`'s
# `=== design hierarchy ===` roll-up block, which recurses into submodules.
#
# Two ways to get a hierarchy-correct transistor count, switchable here:
#   "hierarchy" -- parse the recursive "Estimated number of transistors" line
#                  from the text `stat -tech cmos -top` output. Measures the
#                  exact post-synth netlist that wires/cells are measured on
#                  (no flatten), so it stays internally consistent with them.
#                  This is the default.
#   "flatten"   -- flatten + re-synth the design, then read the cmos JSON
#                  (the original JSON path, corrected). Reports the transistor
#                  count of an equivalent single flat module; can differ from
#                  "hierarchy" when flattening enables cross-module optimisation.
# Either way the wires/cells measurement is left untouched (the flatten runs
# only after the wires/cells stat).
TRANSISTOR_STAT_MODE = "hierarchy"  # "hierarchy" | "flatten"
assert TRANSISTOR_STAT_MODE in ("hierarchy", "flatten"), (
    f"TRANSISTOR_STAT_MODE must be 'hierarchy' or 'flatten', "
    f"got {TRANSISTOR_STAT_MODE!r}")


def _read_text_or_empty(path: str) -> str:
    """Read a file, returning '' if it is missing (e.g. yosys died early)."""
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


class _YosysStatCost(CostMetric):
    """Run ``yosys -p '...; synth; stat'`` and capture both wires and cells.

    Subclasses set ``primary_key`` to "wires" or "cells"; the other is still in
    ``stats`` so callers see both regardless.
    """

    _name: str

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    @property
    def metric_name(self) -> str:
        return self._name

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )

        fd_wc, wc_file = tempfile.mkstemp(suffix=".txt")
        os.close(fd_wc)
        fd_tr, tr_file = tempfile.mkstemp(suffix=".txt")
        os.close(fd_tr)
        try:
            cmds = ["design -reset"]
            for vf in design_files:
                cmds.append(f"read_verilog -sv {vf}")
            if top_module:
                cmds.append(f"hierarchy -top {top_module}")
            else:
                cmds.append("hierarchy -auto-top")
            cmds.append("synth")
            # `clean -purge` drops public alias buffers and other dangling
            # wires that yosys's default opt_clean preserves for debuggability
            # with this command we get more meaningful wire/cell counts that better reflect the actual netlist
            cmds.append("clean -purge")
            top_flag = f" -top {top_module}" if top_module else ""
            # wires/cells from the post-synth netlist, sent to its own file via
            # `tee -q` so neither yosys's chatter nor the transistor pass below
            # can pollute the parse. The `=== design hierarchy ===` roll-up
            # block (last in the file) recurses into submodule instances, so a
            # design shipped as a module hierarchy is still counted correctly.
            cmds.append(f"tee -q -o {wc_file} stat{top_flag}")

            # Transistor side-stat -- hierarchy-correct, see TRANSISTOR_STAT_MODE.
            if TRANSISTOR_STAT_MODE == "flatten":
                # Flatten + re-synth, then read the cmos JSON. Runs *after* the
                # wires/cells stat above, so those counts stay untouched.
                cmds.append("flatten")
                cmds.append(f"synth{top_flag}")
                cmds.append("clean -purge")
                cmds.append(f"tee -q -o {tr_file} stat{top_flag} -tech cmos -json")
            else:  # "hierarchy"
                # Text `stat -tech cmos`: its `=== design hierarchy ===` block
                # sums transistors recursively across submodule instances.
                cmds.append(f"tee -q -o {tr_file} stat{top_flag} -tech cmos")
            script = "; ".join(cmds)

            result = subprocess.run(
                ["yosys", "-p", script],
                capture_output=True, text=True, timeout=self.timeout,
            )

            # Multiple modules print multiple "Number of …" blocks; the last
            # block is the hierarchy roll-up (or the sole module if flat).
            wc_text = _read_text_or_empty(wc_file)
            wires_matches = _WIRES_RE.findall(wc_text)
            cells_matches = _CELLS_RE.findall(wc_text)
            if not wires_matches or not cells_matches:
                combined = result.stdout + "\n" + result.stderr
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"Could not parse wires/cells from yosys stat: {combined[-500:]}",
                )
            wires = int(wires_matches[-1])
            cells = int(cells_matches[-1])
            stats = {"wires": wires, "cells": cells}

            stats["transistors"] = self._parse_transistors(tr_file, top_module)

            return CostResult(ok=True, value=float(stats[self.primary_key]), stats=stats)

        except subprocess.TimeoutExpired:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"yosys stat timed out after {self.timeout}s",
            )
        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"yosys stat failed: {e}",
            )
        finally:
            for f in (wc_file, tr_file):
                if os.path.exists(f):
                    os.remove(f)

    @staticmethod
    def _parse_transistors(tr_file: str, top_module: Optional[str]) -> int:
        """Transistor count from the side-stat file written by ``evaluate``.

        In ``"hierarchy"`` mode the file is text ``stat -tech cmos`` output and
        the last ``Estimated number of transistors`` line is the recursive
        ``=== design hierarchy ===`` roll-up (the sole module's line if the
        design is flat). In ``"flatten"`` mode it is the cmos JSON of the
        flattened + re-synthesised design, whose top module already holds every
        gate. Either way the returned count covers the whole design.
        """
        text = _read_text_or_empty(tr_file)
        if TRANSISTOR_STAT_MODE == "flatten":
            modules = json.loads(text)["modules"]
            if top_module and f"\\{top_module}" in modules:
                key = f"\\{top_module}"
            elif top_module and top_module in modules:
                key = top_module
            else:
                key = next(iter(modules))
            raw_t = modules[key]["estimated_num_transistors"]
            if isinstance(raw_t, str):
                raw_t = raw_t.replace("+", "")
            return int(raw_t)
        # "hierarchy": last match is the design-hierarchy roll-up; the trailing
        # "+" yosys prints on hierarchical estimates is left out of the group.
        matches = _TRANSISTORS_RE.findall(text)
        if not matches:
            raise ValueError(
                f"Could not parse transistor estimate from yosys stat: "
                f"{text[-500:]}")
        return int(matches[-1])


class YosysWiresCost(_YosysStatCost):
    """Cost metric: number of wires after ``yosys ... synth; stat``."""
    _name = "yosys_wires"
    primary_key = "wires"
    tiebreaker_key = "cells"


class YosysCellsCost(_YosysStatCost):
    """Cost metric: number of cells after ``yosys ... synth; stat``."""
    _name = "yosys_cells"
    primary_key = "cells"
    tiebreaker_key = "wires"


class YosysTransistorsCost(_YosysStatCost):
    """Cost metric: estimated transistor count from the same ``synth; stat``
    pipeline used by `YosysWiresCost` / `YosysCellsCost`. The transistor count
    is hierarchy-correct (see TRANSISTOR_STAT_MODE) so it matches the wires/cells
    measurement on multi-module designs. Distinct from the bare `transistors`
    metric (``YosysTransistorCost``), which uses a lighter ``abc -fast``
    pipeline and reads only the top module's transistor estimate."""
    _name = "yosys_transistors"
    primary_key = "transistors"
    tiebreaker_key = "cells"


# ---------------------------------------------------------------------------
# AIG count / depth via yosys aigmap + spirehdl's standard AIG optimization
# ---------------------------------------------------------------------------

class _AigCost(CostMetric):
    """Measure AIG size and depth after spirehdl's standard optimization.

    Pipeline:
      1. ``yosys`` (CLI) synthesises the design, maps to AIG, writes AIGER
         ASCII (``aigmap; write_aiger -ascii``).
      2. spirehdl's ``read_aag_into_aig`` loads the .aag into an
         ``aigverse.Aig``.
      3. ``spirehdl.helpers.optimize_aig_elaborate`` runs two aigverse
         optimization sequences and returns the best AIG (by gate count,
         depth as tiebreaker).
      4. Report ``aig.size()`` and ``DepthAig(aig).num_levels()``.

    Only combinational designs are supported (AIGER latches cannot be
    loaded by the minimal spirehdl reader). ``async2sync; dffunmap`` is
    applied in yosys so edge-triggered logic that survives ``synth`` would
    cause a load-time error.
    """

    _name: str

    def __init__(self, timeout: int = 120,
                 n_iter_optimizations: Optional[int] = None):
        self.timeout = timeout
        self.n_iter_optimizations = n_iter_optimizations

    @property
    def metric_name(self) -> str:
        return self._name

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )

        tmp_dir = tempfile.mkdtemp(prefix="aig_cost_")
        aag_path = os.path.join(tmp_dir, "design.aag")
        try:
            read_cmds = "\n".join(f"read_verilog -sv {vf}" for vf in design_files)
            top_cmd = f"hierarchy -top {top_module}" if top_module else "hierarchy -auto-top"
            yosys_script = (
                f"design -reset\n"
                f"{read_cmds}\n"
                f"{top_cmd}\n"
                "synth -flatten\n"
                "async2sync\n"
                "dffunmap\n"
                "aigmap\n"
                f"write_aiger -ascii -no-startoffset {aag_path}\n"
            )
            ys_script_path = os.path.join(tmp_dir, "synth.ys")
            with open(ys_script_path, "w") as f:
                f.write(yosys_script)

            ys_res = subprocess.run(
                ["yosys", "-q", ys_script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            if ys_res.returncode != 0 or not os.path.exists(aag_path):
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"Yosys aigmap failed: {ys_res.stderr[:500] or ys_res.stdout[:500]}",
                )

            try:
                from aigverse import DepthAig
                from spirehdl.aig.aig_aigerverse import read_aag_into_aig
                from spirehdl.helpers import optimize_aig_elaborate
            except ImportError as e:
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"aigverse/spirehdl not available: {e}",
                )

            aig = read_aag_into_aig(aag_path)
            pre_core = {
                "size": aig.size(),
                "num_gates": len(aig.gates()),
                "depth": DepthAig(aig).num_levels(),
            }

            best_aig, best_stats = optimize_aig_elaborate(
                aig, n_iter_optimizations=self.n_iter_optimizations,
            )
            post_core = {
                "size": best_stats["size"],
                "num_gates": best_stats["num_gates"],
                "depth": best_stats["depth"],
            }

            # optimize_aig_elaborate picks its best iteration by num_gates (depth
            # only as a tiebreaker), so for the depth objective — or any case
            # where the pass trades the scored metric away — the post-opt AIG can
            # be WORSE on (primary, tiebreaker) than its own input. Keep whichever
            # of {pre-opt, post-opt} ranks better (lower is better) so the
            # optimization can never make the reported cost worse than the
            # unoptimized AIG. `pre_opt_used` records which state was scored.
            def _rank(core: dict) -> tuple:
                prim = core[self.primary_key]
                tie = core.get(self.tiebreaker_key) if self.tiebreaker_key else None
                return (prim, tie if tie is not None else 0)

            pre_opt_used = _rank(pre_core) < _rank(post_core)
            chosen = pre_core if pre_opt_used else post_core

            stats = {
                **best_stats,
                **chosen,  # size/num_gates/depth aligned to the scored state
                "size_pre_opt": pre_core["size"],
                "num_gates_pre_opt": pre_core["num_gates"],
                "depth_pre_opt": pre_core["depth"],
                "pre_opt_used": int(pre_opt_used),
            }
            return CostResult(ok=True, value=float(stats[self.primary_key]), stats=stats)

        except subprocess.TimeoutExpired:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"aig cost timed out after {self.timeout}s",
            )
        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"aig cost failed: {e}",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class AigCountCost(_AigCost):
    """Cost metric: post-optimization AIG AND-node count (``len(aig.gates())``).

    Uses ``num_gates`` — the count of AND nodes only — *not* ``aig.size()``,
    which also includes the constant-0 node and the primary-input nodes
    (``size == 1 + num_pis + num_gates``). Those structural I/O nodes are fixed
    by the design's port list and aren't optimizable logic, so counting them
    would only add a constant offset. This also matches the ABC-based family
    (``_AigAbcCost``), whose ``and =`` figure is likewise AND-nodes only.
    """
    _name = "aig_count"
    primary_key = "num_gates"
    tiebreaker_key = "depth"


class AigDepthCost(_AigCost):
    """Cost metric: post-optimization AIG logic depth (``DepthAig.num_levels()``)."""
    _name = "aig_depth"
    primary_key = "depth"
    tiebreaker_key = "num_gates"


# ---------------------------------------------------------------------------
# AIG count / depth via yosys aigmap + ABC (resyn2 or &deepsyn)
# ---------------------------------------------------------------------------

# ABC's `print_stats` line looks like:
#   mult8       : i/o = 16/ 16  lat = 0  and = 409  lev = 39
# (after `&put`; some ABC builds use `nd =` instead of `and =`).
_ABC_STATS_RE = re.compile(r"\b(?:and|nd)\s*=\s*(\d+)\b.*?\blev\s*=\s*(\d+)\b", re.DOTALL)

# `resyn2` is an alias defined in abc.rc; inline its expansion so this
# works without pulling in abc.rc.
_ABC_RESYN2 = ("balance; rewrite; refactor; balance; rewrite; rewrite -z; "
               "balance; refactor -z; rewrite -z; balance")


class _AigAbcCost(CostMetric):
    """Measure AIG size and depth via yosys aigmap + an ABC optimization script.

    Pipeline:
      1. ``yosys`` (CLI): ``synth -flatten; async2sync; dffunmap; aigmap;
         write_aiger -no-startoffset`` (binary .aig).
      2. ``yosys-abc -c 'read_aiger; <abc_script>; print_stats'``.
      3. Parse ``and`` (AND nodes) and ``lev`` (levels) from ``print_stats``.

    Subclasses provide ``_abc_script_fragment`` (the optimization step to insert between
    ``read_aiger`` and ``print_stats``), ``primary_key`` ("size" or "depth"), and ``_name``.
    """

    _name: str
    _abc_prefix = "aig_abc"

    def __init__(self, timeout: int = 180):
        self.timeout = timeout

    @property
    def metric_name(self) -> str:
        return self._name

    def _abc_script_fragment(self, aig_bin: str) -> str:
        raise NotImplementedError

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )

        tmp_dir = tempfile.mkdtemp(prefix=self._abc_prefix + "_")
        aig_bin = os.path.join(tmp_dir, "design.aig")
        try:
            read_cmds = "\n".join(f"read_verilog -sv {vf}" for vf in design_files)
            top_cmd = f"hierarchy -top {top_module}" if top_module else "hierarchy -auto-top"
            yosys_script = (
                f"design -reset\n"
                f"{read_cmds}\n"
                f"{top_cmd}\n"
                "synth -flatten\n"
                "async2sync\n"
                "dffunmap\n"
                "aigmap\n"
                f"write_aiger -no-startoffset {aig_bin}\n"
            )
            ys_script_path = os.path.join(tmp_dir, "synth.ys")
            with open(ys_script_path, "w") as f:
                f.write(yosys_script)

            ys_res = subprocess.run(
                ["yosys", "-q", ys_script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            if ys_res.returncode != 0 or not os.path.exists(aig_bin):
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"Yosys aigmap failed: {ys_res.stderr[:500] or ys_res.stdout[:500]}",
                )

            abc_script = (
                f"read_aiger {aig_bin}; {self._abc_script_fragment(aig_bin)}; "
                f"print_stats"
            )
            abc_res = subprocess.run(
                ["yosys-abc", "-c", abc_script],
                capture_output=True, text=True, timeout=self.timeout,
            )
            out = _ANSI_RE.sub("", abc_res.stdout + "\n" + abc_res.stderr)
            m = _ABC_STATS_RE.search(out)
            if not m:
                return CostResult(
                    ok=False, value=None, stats={"abc_stdout": abc_res.stdout[-500:]},
                    error="Could not parse and/lev from yosys-abc print_stats",
                )
            stats = {"size": int(m.group(1)), "depth": int(m.group(2))}
            return CostResult(ok=True, value=float(stats[self.primary_key]), stats=stats)

        except subprocess.TimeoutExpired:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"{self._name} timed out after {self.timeout}s",
            )
        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"{self._name} failed: {e}",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class _AigDeepsynCost(_AigAbcCost):
    """Backend: ABC ``&deepsyn`` (strong, XOR-aware, slower)."""
    _abc_prefix = "aig_deepsyn"

    def __init__(self, timeout: int = 180, deepsyn_timeout: int = 10):
        super().__init__(timeout=timeout)
        self.deepsyn_timeout = deepsyn_timeout

    def _abc_script_fragment(self, aig_bin: str) -> str:
        return (f"strash; &get -n; &deepsyn -T {self.deepsyn_timeout}; &put")


class _AigResyn2Cost(_AigAbcCost):
    """Backend: ABC's classic ``resyn2`` DAG optimization (cheap, structural)."""
    _abc_prefix = "aig_resyn2"

    def _abc_script_fragment(self, aig_bin: str) -> str:
        return f"strash; {_ABC_RESYN2}"


class AigCountDeepsynCost(_AigDeepsynCost):
    """Cost metric: AIG AND-node count after ABC ``&deepsyn``."""
    _name = "aig_count_deepsyn"
    primary_key = "size"
    tiebreaker_key = "depth"


class AigDepthDeepsynCost(_AigDeepsynCost):
    """Cost metric: AIG logic depth after ABC ``&deepsyn``."""
    _name = "aig_depth_deepsyn"
    primary_key = "depth"
    tiebreaker_key = "size"


class AigCountResyn2Cost(_AigResyn2Cost):
    """Cost metric: AIG AND-node count after ABC ``resyn2``."""
    _name = "aig_count_resyn2"
    primary_key = "size"
    tiebreaker_key = "depth"


class AigDepthResyn2Cost(_AigResyn2Cost):
    """Cost metric: AIG logic depth after ABC ``resyn2``."""
    _name = "aig_depth_resyn2"
    primary_key = "depth"
    tiebreaker_key = "size"


# ---------------------------------------------------------------------------
# PPA cost metrics via tech_eval (Yosys + OpenROAD STA)
# ---------------------------------------------------------------------------

def _tb_output_parser(output: str) -> None:
    """Parse TB_SUMMARY output from our testbenches and raise on failure."""
    from core.correctness import parse_testbench_checks
    checks = parse_testbench_checks(output, "")  # raises ValueError if no TB_SUMMARY
    failed = sum(1 for c in checks if not c.get("passed"))
    if failed:
        raise RuntimeError(
            f"Netlist simulation: {failed}/{len(checks)} check(s) failed"
        )


def _ppa_worker(rtl_paths, target_delay, worker_path, top_module, result_queue,
                tb_path=None, data_files=None, technology="asap7"):
    """Run get_ppa() in a subprocess; put ('ok', ppa) or ('error', msg) in result_queue."""
    try:
        from tech_eval.ppa_extract.core.ppa_extraction import get_ppa
        ppa = get_ppa(
            rtl_path=rtl_paths,
            target_delay=target_delay,
            worker_path=worker_path,
            top_module_name=top_module,
            run_verilator=tb_path is not None,
            tb_filename=tb_path,
            tb_name="tb" if tb_path is not None else None,
            output_parser=_tb_output_parser if tb_path is not None else None,
            data_files=data_files,
            run_in_worker_path=True if data_files is not None else False,
            technology=technology,
        )
        result_queue.put(("ok", ppa))
    except Exception as e:
        result_queue.put(("error", str(e)))


class PPACost(CostMetric):
    """Base class for PPA cost metrics using tech_eval's get_ppa().

    Subclasses set ``_ppa_key`` and ``_name`` to select which PPA dimension
    (delay, area, power) is used as the cost value.
    """

    _ppa_key: str  # key in get_ppa() result dict
    _name: str     # metric_name returned to callers

    def __init__(self, target_delay: float = 500.0, ppa_timeout: int = 180,
                 technology: str = "asap7"):
        self.target_delay = target_delay
        self.ppa_timeout = ppa_timeout
        self.technology = technology

    @property
    def metric_name(self) -> str:
        return self._name

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        workdir = workdir.resolve()
        if design_file is not None:
            design_files = [design_file.resolve()]
        else:
            sv_files = sorted(workdir.glob("*.sv")) + sorted(workdir.glob("*.v"))
            design_files = [f for f in sv_files if f.name not in ("tb.sv", "tb.v")]
        if not design_files:
            return CostResult(
                ok=False, value=None, stats={},
                error="No design files found (excluding testbench)",
            )

        tb_file = workdir / "tb.sv"
        tb_path = str(tb_file) if tb_file.exists() else None

        # Collect auxiliary data files (e.g. vectors.dat) for data-driven testbenches
        data_files = [str(f) for f in workdir.glob("*.dat")]

        worker_path = tempfile.mkdtemp(prefix="ppa_worker_")
        try:
            rtl_paths = [str(f) for f in design_files]

            # create a process to be able to timeout the PPA extraction if it takes too long
            result_queue: multiprocessing.Queue = multiprocessing.Queue()
            proc = multiprocessing.Process(
                target=_ppa_worker,
                args=(rtl_paths, self.target_delay, worker_path,
                      top_module or "top", result_queue),
                kwargs={"tb_path": tb_path, "data_files": data_files or None,
                        "technology": self.technology},
            )
            proc.start()
            proc.join(timeout=self.ppa_timeout)
            if proc.is_alive():
                proc.terminate()
                proc.join()
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"PPA extraction timed out after {self.ppa_timeout}s",
                )

            try:
                status, data = result_queue.get_nowait()
            except _queue.Empty:
                return CostResult(
                    ok=False, value=None, stats={},
                    error="PPA extraction process ended without result",
                )

            if status == "error":
                return CostResult(
                    ok=False, value=None, stats={},
                    error=f"PPA extraction failed: {data}",
                )

            ppa = data
            value = ppa.get(self._ppa_key)
            return CostResult(ok=True, value=float(value), stats=ppa)

        except Exception as e:
            return CostResult(
                ok=False, value=None, stats={},
                error=f"PPA extraction failed: {e}",
            )
        finally:
            shutil.rmtree(worker_path, ignore_errors=True)


class PPADelayCost(PPACost):
    """Cost metric: critical-path delay via Yosys + OpenROAD STA."""
    _ppa_key = "delay"
    _name = "delay"
    primary_key = "delay"
    tiebreaker_key = "area"


class PPAAreaCost(PPACost):
    """Cost metric: design area via Yosys + OpenROAD STA."""
    _ppa_key = "area"
    _name = "area"
    primary_key = "area"
    tiebreaker_key = "delay"


class PPAPowerCost(PPACost):
    """Cost metric: total power via Yosys + OpenROAD STA."""
    _ppa_key = "power"
    _name = "power"
    primary_key = "power"
    tiebreaker_key = "delay"


class PPAAreaDelayProductCost(PPACost):
    """Cost metric: area × delay product via Yosys + OpenROAD STA."""
    _ppa_key = "area"  # base class extracts area; we override to compute product
    _name = "area_delay_product"
    primary_key = "area_delay_product"
    tiebreaker_key = "delay"

    def evaluate(self, workdir: Path, top_module: Optional[str] = None,
                 design_file: Optional[Path] = None) -> CostResult:
        result = super().evaluate(workdir, top_module, design_file)
        if not result.ok:
            return result
        area = result.stats.get("area")
        delay = result.stats.get("delay")
        if area is None or delay is None:
            return CostResult(
                ok=False, value=None, stats=result.stats,
                error="PPA extraction missing area or delay for product",
            )
        adp = float(area) * float(delay)
        result.value = adp
        result.stats["area_delay_product"] = adp  # first-class stats key for primary_key lookups
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

COST_METRICS = {
    "transistors": YosysTransistorCost,
    "delay": PPADelayCost,
    "area": PPAAreaCost,
    "power": PPAPowerCost,
    "area_delay_product": PPAAreaDelayProductCost,
    "sky130_adp": Sky130ADPCost,
    "sky130_adp_v2": Sky130ADPCostV2,
    "yosys_wires": YosysWiresCost,
    "yosys_cells": YosysCellsCost,
    "yosys_transistors": YosysTransistorsCost,
    "aig_count": AigCountCost,
    "aig_depth": AigDepthCost,
    "aig_count_deepsyn": AigCountDeepsynCost,
    "aig_depth_deepsyn": AigDepthDeepsynCost,
    "aig_count_resyn2": AigCountResyn2Cost,
    "aig_depth_resyn2": AigDepthResyn2Cost,
}


def make_cost_metric(name: str, target_delay: float = 500.0,
                     technology: str = "asap7") -> CostMetric:
    """Create a CostMetric by name.

    Args:
        name: One of 'transistors', 'delay', 'area', 'power', 'area_delay_product'.
        target_delay: Target delay in {target_delay_time_unit} for PPA metrics (ignored for transistors).
        technology: Process technology for PPA metrics (ignored for transistors/sky130).
    """
    if name == "transistors":
        return YosysTransistorCost()
    if name == "sky130_adp":
        return Sky130ADPCost()
    if name == "sky130_adp_v2":
        return Sky130ADPCostV2()
    if name == "yosys_wires":
        return YosysWiresCost()
    if name == "yosys_cells":
        return YosysCellsCost()
    if name == "yosys_transistors":
        return YosysTransistorsCost()
    if name == "aig_count":
        return AigCountCost()
    if name == "aig_depth":
        return AigDepthCost()
    if name == "aig_count_deepsyn":
        return AigCountDeepsynCost()
    if name == "aig_depth_deepsyn":
        return AigDepthDeepsynCost()
    if name == "aig_count_resyn2":
        return AigCountResyn2Cost()
    if name == "aig_depth_resyn2":
        return AigDepthResyn2Cost()
    cls = COST_METRICS.get(name)
    if cls is None:
        raise ValueError(f"Unknown cost metric: {name!r}. "
                         f"Choose from: {sorted(COST_METRICS)}")
    return cls(target_delay=target_delay, technology=technology)

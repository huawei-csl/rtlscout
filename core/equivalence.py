"""Combinational equivalence checking (CEC) via Yosys + yosys-abc.

Verifies that a produced design is *logically* equivalent to a golden
reference — a stronger guarantee than testbench simulation, which only
covers the directed/random vectors in ``tb.sv``.

Flow (mirrors a standard ABC cec setup):
  1. Synthesize each design to a BLIF netlist with Yosys
     (``synth -flatten; async2sync; dffunmap`` flattens registers out so the
     comparison is combinational).
  2. Run ``yosys-abc -c "cec golden.blif design.blif"`` and parse the verdict.

Port-name constraint: ABC's ``cec`` matches primary inputs/outputs *by name*
after flattening. The golden reference must therefore expose the same top-level
port names as the design under test. This holds by construction in RTL Scout —
both implement the same benchmark I/O contract (same ``description.txt`` /
``tb.sv``) — so no port renaming is attempted here.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# Timeout (seconds) for each yosys/yosys-abc subprocess in the CEC flow.
CEC_TIMEOUT = int(os.environ.get("CEC_TIMEOUT", "120"))


@dataclass
class CECResult:
    ran: bool                     # CEC was actually attempted
    equivalent: Optional[bool]    # True/False verdict; None on tool error
    tool_ok: bool                 # synth + abc completed without process error
    error: str = ""               # human-readable failure reason ("" on success)
    log: str = ""                 # combined yosys + abc output (caller truncates)


def _synth_to_blif(src: Path, top: Optional[str], out_blif: Path,
                   cwd: Path, timeout: int) -> Tuple[bool, str]:
    """Synthesize one Verilog/SV file to a flattened BLIF netlist.

    Returns (ok, log).  ``ok`` is True only if yosys exited 0 and the BLIF
    was written.
    """
    if shutil.which("yosys") is None:
        return False, "yosys not found"
    hierarchy = f"hierarchy -top {top}" if top else "hierarchy -auto-top"
    script = "; ".join([
        f"read_verilog -sv {src}",
        hierarchy,
        "proc", "opt", "techmap", "opt",
        "synth -flatten",
        "async2sync", "dffunmap",
        "clean -purge",
        f"write_blif {out_blif}",
    ])
    try:
        proc = subprocess.run(
            ["yosys", "-q", "-p", script],
            cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"yosys synth timed out ({src.name})"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"yosys synth error ({src.name}): {e}"
    log = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0 and out_blif.exists()
    return ok, log


def run_cec(
    design_file: Path,
    reference_file: Path,
    workdir: Path,
    design_top_module: Optional[str] = None,
    reference_top_module: Optional[str] = None,
    timeout: int = CEC_TIMEOUT,
) -> CECResult:
    """Check combinational equivalence of *design_file* vs *reference_file*.

    Both are synthesized to BLIF with Yosys, then compared with
    ``yosys-abc``'s ``cec`` command.  The reference is synthesized with the
    design's top module name when no separate ``reference_top_module`` is given.
    """
    design_file = Path(design_file)
    reference_file = Path(reference_file)
    workdir = Path(workdir).resolve()

    if shutil.which("yosys") is None or shutil.which("yosys-abc") is None:
        return CECResult(ran=True, equivalent=None, tool_ok=False,
                         error="yosys/yosys-abc not found")
    if not design_file.exists():
        return CECResult(ran=True, equivalent=None, tool_ok=False,
                         error=f"design file not found: {design_file}")
    if not reference_file.exists():
        return CECResult(ran=True, equivalent=None, tool_ok=False,
                         error=f"reference file not found: {reference_file}")

    cec_dir = workdir / "_cec"
    cec_dir.mkdir(parents=True, exist_ok=True)
    design_blif = cec_dir / "design.blif"
    golden_blif = cec_dir / "golden.blif"

    ref_top = reference_top_module or design_top_module

    logs = []
    d_ok, d_log = _synth_to_blif(design_file.resolve(), design_top_module,
                                 design_blif, cec_dir, timeout)
    logs.append("=== design synth ===\n" + d_log)
    if not d_ok:
        return CECResult(ran=True, equivalent=None, tool_ok=False,
                         error="failed to synthesize design to BLIF",
                         log="\n".join(logs))
    g_ok, g_log = _synth_to_blif(reference_file.resolve(), ref_top,
                                 golden_blif, cec_dir, timeout)
    logs.append("=== golden synth ===\n" + g_log)
    if not g_ok:
        return CECResult(ran=True, equivalent=None, tool_ok=False,
                         error="failed to synthesize golden reference to BLIF",
                         log="\n".join(logs))

    abc_cmd = f"cec {golden_blif} {design_blif}; print_stats -S;"
    try:
        proc = subprocess.run(
            ["yosys-abc", "-c", abc_cmd],
            cwd=str(cec_dir), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logs.append("=== abc cec ===\n(timed out)")
        return CECResult(ran=True, equivalent=None, tool_ok=False,
                         error="yosys-abc cec timed out", log="\n".join(logs))
    abc_out = (proc.stdout or "") + (proc.stderr or "")
    logs.append("=== abc cec ===\n" + abc_out)
    full_log = "\n".join(logs)

    # Parse verdict. Check NOT-equivalent first so "Networks are NOT
    # EQUIVALENT" is never misread as the equivalent case.
    upper = abc_out.upper()
    if "NOT EQUIVALENT" in upper:
        return CECResult(ran=True, equivalent=False, tool_ok=True, log=full_log)
    if "ARE EQUIVALENT" in upper:
        return CECResult(ran=True, equivalent=True, tool_ok=True, log=full_log)
    return CECResult(ran=True, equivalent=None, tool_ok=False,
                     error="could not parse cec verdict from yosys-abc output",
                     log=full_log)


def resolve_golden_reference(benchmark, dest_dir: Path) -> Optional[Path]:
    """Resolve ``benchmark.golden_reference`` into an absolute Verilog path.

    - None / missing            -> None (CEC disabled for this benchmark).
    - ``.v`` / ``.sv``          -> returned directly (used in place).
    - ``.py``                   -> copied into *dest_dir*, compiled to a golden
                                   ``.v`` via the SpireHDL/Amaranth compiler
                                   selected by ``golden_reference_language``,
                                   and returned as ``dest_dir/golden.v``.

    Compiling a ``.py`` reference happens once (call this at run setup, not per
    evaluation).  A compile failure raises so the run surfaces a clear error
    rather than silently skipping the equivalence gate.
    """
    gr = getattr(benchmark, "golden_reference", None)
    if gr is None:
        return None
    gr = Path(gr)
    if not gr.is_absolute():
        gr = (benchmark.root / gr).resolve()

    suffix = gr.suffix.lower()
    if suffix in (".v", ".sv"):
        return gr
    if suffix != ".py":
        raise ValueError(f"Unsupported golden_reference type: {gr}")

    # .py generator -> compile to Verilog.
    from core.evaluation import (
        SPIREHDL_VERILOG_OUTPUT, _compile_amaranth, _compile_spirehdl,
    )

    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_py = dest_dir / gr.name
    if gr.resolve() != local_py:
        shutil.copy2(gr, local_py)

    language = getattr(benchmark, "golden_reference_language", "spirehdl")
    if language == "amaranth":
        err, _ = _compile_amaranth(dest_dir, local_py.name)
    else:
        err, _ = _compile_spirehdl(dest_dir, local_py.name)
    if err:
        raise RuntimeError(f"Golden reference compile failed ({gr.name}): {err}")

    produced = dest_dir / SPIREHDL_VERILOG_OUTPUT
    golden_v = dest_dir / "golden.v"
    if produced.exists():
        produced.replace(golden_v)
    if not golden_v.exists():
        raise RuntimeError(
            f"Golden reference compile produced no Verilog ({gr.name})")
    return golden_v

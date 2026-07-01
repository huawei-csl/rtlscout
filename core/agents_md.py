"""Render AGENTS.md for OpenCode runs — one lean renderer for every HDL.

The OpenCode agent has a real shell + read access, so these prompts are deliberately lean:
task/objective → workflow (the shared execution section) → concise HDL essentials → pointers
to reference material to read on demand → optimization guidance → seed. It drops the react
loop's mechanics (the in-house ``create_file``/``run_evaluation``/``done`` tool list, the
"always call a tool" rule, the step budget) that don't apply when the agent has a shell — so
the "ignore those tool notes" override the react prompts needed is unnecessary here.

Per-language differences are captured in ``_CFG``:
  - SpireHDL: inline the curated hints (``deps/spire-hdl/docs/hints.md``) + point at the
    spire-hdl READMEs; supports the optimization-decorator flags.
  - Amaranth: a short inline note (its API isn't universally known and has no readable
    in-repo docs) + point at the reference designs.
  - Verilog: a one-line note + point at the reference designs.

Reuses the reference registries + ``_build_optimization_guidance`` from ``core/prompts.py``.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from core.prompts import (AMARANTH_REFERENCES, SPIREHDL_REFERENCES, VERILOG_REFERENCES, _SPIRE,
                          _build_optimization_guidance)

if TYPE_CHECKING:
    from core.agent_backend import BackendRequest

# spire-hdl ships topic READMEs next to its main one — pointed at (not inlined) so a
# shell-capable agent reads what it needs on demand.
_SPIRE_DOC_READMES = [
    ("README.md", "main SpireHDL overview — start here"),
    ("README_arithmetic_generator.md", "configurable multiplier/adder generators"),
    ("README_arithmetic_optimization.md", "arithmetic architecture optimization"),
    ("README_optimization_decorators.md", "@abc_optimized / @flowy_optimized / etc."),
    ("README_fsm_optimization.md", "FSM / state-encoding optimization"),
    ("README_state_machines.md", "state machines"),
    ("README_aggregate_types.md", "structs / arrays / aggregate types"),
    ("README_memories.md", "memories"),
    ("README_custom_verilog.md", "embedding custom Verilog"),
]

_VERILOG_ESSENTIALS = (
    "## Verilog notes\n\n"
    "Write synthesizable Verilog/SystemVerilog directly in `design.sv` (split helpers across "
    "files if useful). The module name and ports must match the specification exactly. Your "
    "design is checked for correctness (Verilator simulation against the testbench) and cost "
    "(Yosys synthesis)."
)

_AMARANTH_ESSENTIALS = (
    "## Amaranth notes\n\n"
    "Amaranth HDL is a Python library that generates synthesizable Verilog via Yosys. Define "
    "your design as an `Elaboratable`, then convert it to Verilog and write `design.v`:\n\n"
    "```python\n"
    "from amaranth import *\n"
    "from amaranth.back.verilog import convert\n\n"
    "class MyDesign(Elaboratable):\n"
    "    def __init__(self):\n"
    "        self.a = Signal(8); self.b = Signal(8); self.y = Signal(8)\n"
    "    def elaborate(self, platform):\n"
    "        m = Module()\n"
    "        m.d.comb += self.y.eq(self.a + self.b)\n"
    "        return m\n\n"
    "top = MyDesign()\n"
    "with open('design.v', 'w') as f:\n"
    "    f.write(convert(top, ports=[top.a, top.b, top.y], name='<module_name>'))\n"
    "```\n\n"
    "The emitted module name and ports must match the specification exactly. Your working "
    "directory is on the Python path, so `from helper import ...` works."
)

# lang -> (hdl label, reference registry, doc-readme list, inline essentials, supports opt-flags)
_CFG = {
    "verilog":  dict(hdl="Verilog / SystemVerilog", refs=VERILOG_REFERENCES, doc_readmes=[],
                     essentials=_VERILOG_ESSENTIALS, opt_flags=False),
    "amaranth": dict(hdl="Amaranth HDL (Python → Verilog)", refs=AMARANTH_REFERENCES,
                     doc_readmes=[], essentials=_AMARANTH_ESSENTIALS, opt_flags=False),
    "spirehdl": dict(hdl="SpireHDL (Python EDSL → Verilog)", refs=SPIREHDL_REFERENCES,
                     doc_readmes=_SPIRE_DOC_READMES, essentials=None, opt_flags=True),
}

_HINTS_PATH = _SPIRE / "docs" / "hints.md"


def _demote_headings(md: str) -> str:
    """Add one '#' to each markdown heading so an external doc nests under this AGENTS.md.
    Fence-aware: never touches '#' comments inside ``` code blocks."""
    out, in_fence = [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("#"):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def _objective(req: "BackendRequest", metric_name: str, cfg: dict) -> str:
    note = getattr(req.cost_metric, "metric_note", "") if req.cost_metric else ""
    note_line = f"\n\n**Cost metric `{metric_name}`:** {note}" if note else ""
    return (
        f"# Task — optimize a {cfg['hdl']} design\n\n"
        f"## Specification\n{req.benchmark.description}\n\n"
        f"## Objective\n"
        f"Write a **functionally correct** design (module name + ports must match the spec "
        f"exactly), then minimize **{metric_name}** without breaking correctness. Correctness "
        f"first, then cost.{note_line}"
    )


def _essentials(cfg: dict) -> str:
    """Concise HDL essentials. SpireHDL inlines the curated hints file (headings demoted);
    verilog/amaranth use a short inline note."""
    if cfg["essentials"] is not None:
        return cfg["essentials"]
    if _HINTS_PATH.exists():
        return _demote_headings(_HINTS_PATH.read_text().strip())
    return (f"## SpireHDL essentials\n\nRead `{_HINTS_PATH}` for the key API + common mistakes, "
            f"then the READMEs below.")


def _references(cfg: dict) -> str:
    lines = [
        "## Reference docs & examples",
        "",
        "You have a shell and read access — **read these files yourself with `cat` instead of "
        "guessing.** They are not inlined here, to keep this prompt small.",
    ]
    if cfg["doc_readmes"]:
        lines += ["", "**Docs (start with the main README):**"]
        lines += [f"- `{_SPIRE / fname}` — {desc}" for fname, desc in cfg["doc_readmes"]]
    if cfg["refs"]:
        lines += ["", "**Reference implementations / examples (read the ones you need):**"]
        lines += [f"- `{ref['path']}` — {ref['description']}" for ref in cfg["refs"]]
    return "\n".join(lines)


def _optimization_guidance(req: "BackendRequest", cfg: dict) -> str:
    if not cfg["opt_flags"]:
        return ""
    return _build_optimization_guidance(req.abc_optimize, req.flowy_optimize,
                                        req.arith_autoconfig, req.dont_touch_main_arith,
                                        req.fsm_optimize).strip()


def _seed(seed_text: str) -> str:
    return ("## Seed design & lessons from previous agents\n\n" + seed_text.strip()
            if seed_text and seed_text.strip() else "")


def render_opencode_agents_md(req: "BackendRequest", *, execution_section: str,
                              metric_name: str, seed_text: str = "") -> str:
    """Assemble the complete AGENTS.md for an OpenCode run in any supported HDL.

    ``execution_section`` is the shared OpenCode workflow block (shell, ./evaluate_design,
    ./remaining_time, time budget, finishing-up) built by the backend — passed in so there is
    one copy across languages.
    """
    cfg = _CFG.get(req.language, _CFG["verilog"])
    sections = [
        _objective(req, metric_name, cfg),
        execution_section,
        _essentials(cfg),
        _references(cfg),
        _optimization_guidance(req, cfg),
        _seed(seed_text),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"

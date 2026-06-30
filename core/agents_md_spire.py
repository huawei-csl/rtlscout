"""Render AGENTS.md for the OpenCode + SpireHDL case — and only that case.

Kept separate from ``core/prompts.py`` (which serves the in-process react loop) so this
stays small and readable. The OpenCode agent has a shell + read access, so this prompt is
deliberately lean: it states the task, hands over the workflow (the shared execution
section), inlines the distilled SpireHDL **hints** (``deps/spire-hdl/docs/hints.md``), and
**points** at the spire-hdl READMEs + reference files for depth rather than inlining ~100 KB
of source. The verbose "SpireHDL Overview" prose from the react prompt is intentionally
dropped — it duplicates the READMEs.

Reuses a few building blocks from ``core/prompts.py`` (reference pointers, optimization
guidance) so there is one source of truth for those.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.prompts import (SPIREHDL_REFERENCES, _SPIRE, _build_optimization_guidance,
                          _build_reference_pointers_block)

if TYPE_CHECKING:
    from core.agent_backend import BackendRequest

_HINTS_PATH = _SPIRE / "docs" / "hints.md"


def _objective(req: "BackendRequest", metric_name: str) -> str:
    note = getattr(req.cost_metric, "metric_note", "") if req.cost_metric else ""
    note_line = f"\n\n**Cost metric `{metric_name}`:** {note}" if note else ""
    return (
        f"# Task — optimize a SpireHDL design\n\n"
        f"## Specification\n{req.benchmark.description}\n\n"
        f"## Objective\n"
        f"Write a **functionally correct** SpireHDL design (module name + ports must match the "
        f"spec exactly), then minimize **{metric_name}** without breaking correctness. "
        f"Correctness first, then cost.{note_line}"
    )


def _demote_headings(md: str) -> str:
    """Add one '#' to each markdown heading so an external doc (its own H1/H2) nests cleanly
    under this AGENTS.md. Fence-aware: never touches '#' comments inside ``` code blocks."""
    out, in_fence = [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("#"):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def _spirehdl_essentials() -> str:
    """Inline the curated hints (key API + common mistakes), headings demoted so they nest
    under this doc. Sourced from deps/spire-hdl/docs/hints.md so it stays maintainable; falls
    back to a pointer if the file isn't present yet."""
    if _HINTS_PATH.exists():
        return _demote_headings(_HINTS_PATH.read_text().strip())
    return ("## SpireHDL essentials\n\n"
            f"Read `{_HINTS_PATH}` for the key API + common mistakes, then the READMEs below.")


def _references() -> str:
    return ("## SpireHDL reference docs & examples\n\n"
            + _build_reference_pointers_block(SPIREHDL_REFERENCES))


def _optimization_guidance(req: "BackendRequest") -> str:
    return _build_optimization_guidance(req.abc_optimize, req.flowy_optimize,
                                        req.arith_autoconfig, req.dont_touch_main_arith,
                                        req.fsm_optimize).strip()


def _seed(seed_text: str) -> str:
    return ("## Seed design & lessons from previous agents\n\n" + seed_text.strip()
            if seed_text and seed_text.strip() else "")


def render_spire_agents_md(req: "BackendRequest", *, execution_section: str,
                           metric_name: str, seed_text: str = "") -> str:
    """Assemble the complete AGENTS.md for an OpenCode + SpireHDL run.

    ``execution_section`` is the shared OpenCode workflow block (shell, ./evaluate_design,
    ./remaining_time, time budget, required final steps) built by the backend — passed in so
    there is one copy across languages.
    """
    sections = [
        _objective(req, metric_name),
        execution_section,
        _spirehdl_essentials(),
        _references(),
        _optimization_guidance(req),
        _seed(seed_text),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"

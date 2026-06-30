"""Authoritative, clean-room re-evaluation of a finished run (handover doc §4.4, §5.3).

THE integrity rule: the recorded score is **never** the number the agent's container
produced. After the agent finishes, ``reeval_run`` re-scores every ``eval_{i}/`` it
stored — each in a fresh workspace built from the **benchmark's own inputs**
(``provision_workspace``), with only the agent's **design source** overlaid (its
``tb.sv``/``*.dat`` are discarded; the benchmark's win). The same ``evaluate()`` runs;
only the inputs' provenance differs. Authoritative numbers then overwrite
``result.json`` and pick ``best_design/`` — so the pool and Pareto get trustworthy
numbers. An agreement gate flags runs where the agent's claim diverges from the
authoritative score (cheating or nondeterminism).

Each candidate's re-eval runs via the ``judge_sandbox``: ``LocalSandbox`` in
single-container mode (lower assurance — §3.1), a fresh ``--rm`` container per
candidate in orchestrated mode. Either way ``evaluate()`` executes the agent's ``.py``,
so even the local path uses a fresh workdir with the benchmark's own inputs + extracted
design only.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.eval_store import read_evals, select_best_eval, snapshot_best

# Agent-workspace entries that are NEVER taken as design source: the benchmark owns the
# testbench + data (integrity), and these are housekeeping / caches / generated outputs.
_NEVER_FROM_AGENT = {
    "tb.sv", "obj_dir", "_cec", "_golden", "_best_meta.json",
    "result.json", "summary.txt", "evals.jsonl", ".spirehdl_cache",
}

# Heuristic tamper signatures to scan session logs for (advisory; the cost/PASS
# divergence below is the authoritative signal).
_TAMPER_PATTERNS = [
    re.compile(r"\btb\.sv\b"),
    re.compile(r"\brun_eval\.py\b"),
    re.compile(r"\bevals\.jsonl\b"),
    re.compile(r"(?:^|\s)(?:export\s+)?PATH="),
    re.compile(r"\bcore/(?:evaluation|equivalence|cost|reeval|eval_store)\.py\b"),
]


def _overlay_design_source(agent_workspace: Path, fresh_workspace: Path,
                           benchmark) -> None:
    """Overlay the agent's design source onto a freshly-provisioned workspace.

    The benchmark's ``tb.sv`` + ``*.dat`` (already laid down by ``provision_workspace``)
    always win — they are never taken from the agent. Everything else the agent
    authored (``design.*``, helper modules, etc.) is copied in, overwriting the
    provisioned starting versions, because that is precisely what we are scoring.
    """
    dat_names = {p.name for p in benchmark.root.glob("*.dat")}
    for item in Path(agent_workspace).iterdir():
        name = item.name
        if name in _NEVER_FROM_AGENT or name in dat_names or name.endswith(".dat"):
            continue
        dest = fresh_workspace / name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def _reeval_one(eval_dir: Path, benchmark, judge_sandbox, cost_metric, language: str,
                run_cec: bool, parent_tmp: Path) -> Dict[str, Any]:
    """Authoritatively re-score a single ``eval_{i}/``. Returns the new eval dict
    (also written over ``eval_dir/result.json``)."""
    from core.evaluation import evaluate
    from core.runner import provision_workspace
    from core.sandbox import SandboxSpec

    advisory = {}
    adv_path = eval_dir / "result.json"
    if adv_path.exists():
        try:
            advisory = json.loads(adv_path.read_text())
        except json.JSONDecodeError:
            advisory = {}

    eval_index = advisory.get("eval_index")
    if eval_index is None:
        m = re.search(r"eval_(\d+)$", eval_dir.name)
        eval_index = int(m.group(1)) if m else 0
    design_file = advisory.get("design_file")
    target_delay = advisory.get("target_delay")

    # Fresh judge workdir built from the benchmark's OWN inputs, with the agent's
    # design source overlaid. The agent's tb.sv/*.dat never participate.
    judge_workdir = Path(tempfile.mkdtemp(prefix=f"reeval_{eval_index}_", dir=parent_tmp))
    try:
        fresh_ws, cec_reference = provision_workspace(
            benchmark, judge_workdir, language=language, run_cec=run_cec)
        agent_ws = eval_dir / "workspace"
        if agent_ws.is_dir():
            _overlay_design_source(agent_ws, fresh_ws, benchmark)

        if hasattr(cost_metric, "target_delay") and target_delay is not None:
            cost_metric.target_delay = target_delay

        spec = SandboxSpec(workdir=judge_workdir, network="none")

        def _do_eval():
            return evaluate(fresh_ws, benchmark.module_name, cost_metric=cost_metric,
                            language=language, design_file=design_file or None,
                            run_cec=run_cec, cec_reference=cec_reference)

        try:
            result = judge_sandbox.run_callable(_do_eval, spec)
            eval_dict = result.to_dict()
        except Exception as e:  # adversarial .py may crash the evaluator
            eval_dict = {
                "passed": False, "cost_value": None,
                "cost": {"ok": False, "value": None, "error": f"reeval error: {e}"},
                "metrics": {}, "error": f"reeval error: {e}",
            }

        eval_dict["eval_index"] = eval_index
        eval_dict["design_file"] = design_file
        eval_dict["target_delay"] = target_delay
        if "context_window_tokens" in advisory:
            eval_dict["context_window_tokens"] = advisory["context_window_tokens"]
        eval_dict["authoritative"] = True
        eval_dict["advisory_cost_value"] = advisory.get("cost_value")
        eval_dict["advisory_passed"] = advisory.get("passed")

        adv_path.write_text(json.dumps(eval_dict, indent=2))
        return eval_dict
    finally:
        shutil.rmtree(judge_workdir, ignore_errors=True)


def _scan_session_logs(session_logs: Optional[List[Path]]) -> List[str]:
    hits: List[str] = []
    for log in session_logs or []:
        log = Path(log)
        if not log.exists():
            continue
        try:
            text = log.read_text(errors="ignore")
        except OSError:
            continue
        for pat in _TAMPER_PATTERNS:
            if pat.search(text):
                hits.append(f"{log.name}: matched {pat.pattern!r}")
    return hits


def reeval_run(run_dir: Path, benchmark, judge_sandbox, *, cost_metric, language: str,
               run_cec: bool = True, rel_tol: float = 1e-3,
               session_logs: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Re-evaluate every ``eval_{i}/`` in ``run_dir`` authoritatively, rewrite
    ``result.json`` + ``best_design/`` from the authoritative numbers, and return an
    agreement report. ``run_dir`` is the agent's workdir (containing ``eval_{i}/``,
    ``best_design/``, ``result.json``)."""
    run_dir = Path(run_dir)

    # Capture the agent's advisory claim BEFORE we overwrite anything.
    run_result_path = run_dir / "result.json"
    advisory_run = {}
    if run_result_path.exists():
        try:
            advisory_run = json.loads(run_result_path.read_text())
        except json.JSONDecodeError:
            advisory_run = {}
    advisory_best_cost = advisory_run.get("best_cost")
    advisory_passed = advisory_run.get("passed")

    eval_dirs = sorted(
        [d for d in run_dir.glob("eval_*") if d.is_dir() and re.match(r"eval_\d+$", d.name)],
        key=lambda d: int(d.name.split("_")[1]),
    )

    report: Dict[str, Any] = {
        "n_evals": len(eval_dirs),
        "advisory_best_cost": advisory_best_cost,
        "advisory_passed": advisory_passed,
        "authoritative_best_cost": None,
        "authoritative_passed": False,
        "best_eval_index": None,
        "diverged": False,
        "flags": [],
        "tamper_signatures": _scan_session_logs(session_logs),
    }

    if not eval_dirs:
        report["flags"].append("no eval_*/ to re-score")
        return report

    parent_tmp = run_dir / "_reeval"
    parent_tmp.mkdir(exist_ok=True)
    try:
        authoritative: List[Dict[str, Any]] = []
        for eval_dir in eval_dirs:
            authoritative.append(
                _reeval_one(eval_dir, benchmark, judge_sandbox, cost_metric,
                            language, run_cec, parent_tmp))
    finally:
        shutil.rmtree(parent_tmp, ignore_errors=True)

    tiebreaker_key = getattr(type(cost_metric), "tiebreaker_key", None)
    best = select_best_eval(authoritative, tiebreaker_key)

    report["authoritative_passed"] = best is not None
    report["authoritative_best_cost"] = best.get("cost_value") if best else None
    report["best_eval_index"] = best.get("eval_index") if best else None

    # Rebuild best_design/ from the authoritative-best eval's agent design source.
    if best is not None:
        best_ws = run_dir / f"eval_{best.get('eval_index')}" / "workspace"
        if best_ws.is_dir():
            snapshot_best(run_dir, best_ws, best.get("eval_index"), best.get("cost_value"),
                          cost_metric.metric_name, best.get("design_file"))

    # Rewrite the run-level result.json with authoritative numbers (preserve the rest).
    updated = dict(advisory_run)
    updated["passed"] = best is not None
    updated["best_cost"] = best.get("cost_value") if best else None
    updated["best_metrics"] = best.get("metrics") if best else None
    updated["best_eval"] = best
    updated["all_evals"] = authoritative
    updated["cost_metric"] = cost_metric.metric_name
    updated["reeval"] = {
        "applied": True,
        "advisory_best_cost": advisory_best_cost,
        "authoritative_best_cost": report["authoritative_best_cost"],
    }
    run_result_path.write_text(json.dumps(updated, indent=2))

    # Agreement gate: did the agent's claim match the authoritative score?
    auth_cost = report["authoritative_best_cost"]
    if bool(advisory_passed) != bool(report["authoritative_passed"]):
        report["diverged"] = True
        report["flags"].append(
            f"pass/fail mismatch: advisory passed={advisory_passed!r}, "
            f"authoritative passed={report['authoritative_passed']!r}")
    elif advisory_best_cost is not None and auth_cost is not None:
        denom = abs(advisory_best_cost) or 1.0
        if abs(auth_cost - advisory_best_cost) / denom > rel_tol:
            report["diverged"] = True
            report["flags"].append(
                f"best-cost divergence: advisory={advisory_best_cost}, authoritative={auth_cost}")
    elif (advisory_best_cost is None) != (auth_cost is None):
        report["diverged"] = True
        report["flags"].append(
            f"best-cost presence mismatch: advisory={advisory_best_cost}, authoritative={auth_cost}")

    if report["tamper_signatures"]:
        report["flags"].append(
            f"{len(report['tamper_signatures'])} tamper-signature hit(s) in session log")

    return report

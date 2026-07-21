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
import shlex
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.eval_store import read_evals, select_best_eval, snapshot_best

# Agent-workspace entries that are NEVER taken as design source: the benchmark owns the
# testbench + data (integrity), and these are housekeeping / caches / generated outputs.
_NEVER_FROM_AGENT = {
    "tb.sv", "obj_dir", "_cec", "_golden", "_best_meta.json",
    "result.json", "summary.txt", "agent_evals.jsonl", ".spire_cache",
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

    authoritative: List[Dict[str, Any]] = []
    if getattr(judge_sandbox, "runs_in_process", True):
        # Local judge: re-eval each candidate in-process (single-container mode).
        parent_tmp = run_dir / "_reeval"
        parent_tmp.mkdir(exist_ok=True)
        try:
            for eval_dir in eval_dirs:
                authoritative.append(
                    _reeval_one(eval_dir, benchmark, judge_sandbox, cost_metric,
                                language, run_cec, parent_tmp))
        finally:
            shutil.rmtree(parent_tmp, ignore_errors=True)
    else:
        # Container judge (orchestrated): a fresh --rm judge container per candidate runs
        # `python -m core.reeval` against the benchmark's own inputs and writes the
        # authoritative result.json into the (bind-mounted) eval_dir.
        from core.sandbox import SandboxSpec
        for eval_dir in eval_dirs:
            argv = _container_judge_argv(eval_dir, benchmark, cost_metric, language, run_cec)
            res = judge_sandbox.run_command(argv, SandboxSpec(workdir=run_dir, network="none"))
            rj = eval_dir / "result.json"
            if rj.exists():
                try:
                    authoritative.append(json.loads(rj.read_text()))
                    continue
                except json.JSONDecodeError:
                    pass
            authoritative.append({
                "passed": False, "cost_value": None, "metrics": {},
                "cost": {"ok": False, "value": None, "error": "judge produced no result"},
                "eval_index": int(eval_dir.name.split("_")[1]),
                "error": f"container judge failed: {(res.stderr or '')[-200:]}",
            })

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


# result.json keys the authoritative re-score rewrites — pool/Pareto selection then reads
# these, never the agent-container numbers.
_AUTHORITATIVE_KEYS = ("passed", "best_cost", "best_metrics", "best_eval", "all_evals", "cost_metric")


def adopt_authoritative_result(result_dict: Dict[str, Any], benchmark, judge_sandbox, *,
                               cost_metric, language: str, run_cec: bool = True,
                               run_label: str = "") -> None:
    """Re-score a finished run and adopt the authoritative numbers into *result_dict* in place.

    Handover §4.4/§5.3: recorded numbers come from the judge re-scoring the candidate set
    against the benchmark's own inputs, never the agent's container. Runs ``reeval_run`` on
    ``result_dict["workdir"]``, overwrites the authoritative keys, attaches the report as
    ``reeval_report``, and prints a line when the agreement gate flags divergence. Never
    raises: a failed re-eval is recorded as ``reeval_error`` (the advisory numbers stand).
    """
    try:
        workdir = Path(result_dict["workdir"])
        # opencode_session.json is the complete record; opencode_session.log is the fallback
        # (only present if the export failed). The scan reads whichever exist.
        session_logs = [workdir / "opencode_session.json", workdir / "opencode_session.log",
                        workdir / "chat_log.txt"]
        report = reeval_run(workdir, benchmark, judge_sandbox, cost_metric=cost_metric,
                            language=language, run_cec=run_cec, session_logs=session_logs)
        auth = json.loads((workdir / "result.json").read_text())
        for k in _AUTHORITATIVE_KEYS:
            if k in auth:
                result_dict[k] = auth[k]
        result_dict["reeval_report"] = report
        if report.get("diverged"):
            print(f"[REEVAL] {run_label or workdir.name}: DIVERGENCE flagged: "
                  f"{report.get('flags')}", flush=True)
    except Exception as e:
        traceback.print_exc()
        result_dict["reeval_error"] = str(e)


def _container_judge_argv(eval_dir: Path, benchmark, cost_metric, language: str,
                          run_cec: bool) -> List[str]:
    """Build the `bash -c` argv that re-evals ONE eval_dir inside a judge container.
    Uses identity-mounted paths (host == container), the image's venv python, and
    cd's into the repo so `core` is importable."""
    repo = Path(__file__).resolve().parent.parent
    py = "/home/vscode/pyenv_eda/bin/python"
    parts = [py, "-m", "core.reeval",
             "--eval-dir", str(eval_dir),
             "--benchmark-root", str(benchmark.root),
             "--cost-metric", cost_metric.metric_name,
             "--language", language,
             "--technology", str(getattr(cost_metric, "technology", "asap7")),
             "--energy-exp", str(getattr(cost_metric, "energy_exp", 1.0))]
    if run_cec:
        parts.append("--run-cec")
    inner = f"cd {shlex.quote(str(repo))} && exec " + " ".join(shlex.quote(p) for p in parts)
    return ["bash", "-c", inner]


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: re-evaluate a SINGLE eval_{i}/ authoritatively and write its result.json.
    Invoked inside a judge container by `reeval_run` (orchestrated mode), but also usable
    standalone. Runs the same in-process re-eval (`_reeval_one`) the local judge uses."""
    import argparse
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric
    from core.sandbox import LocalSandbox

    p = argparse.ArgumentParser(description="Authoritative re-eval of one eval_{i}/ directory.")
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--benchmark-root", required=True)
    p.add_argument("--cost-metric", default="transistors")
    p.add_argument("--language", default="verilog")
    p.add_argument("--technology", default="asap7")
    p.add_argument("--energy-exp", type=float, default=1.0)
    p.add_argument("--run-cec", action="store_true")
    args = p.parse_args(argv)

    benchmark = load_benchmark(Path(args.benchmark_root))
    cost_metric = make_cost_metric(args.cost_metric, technology=args.technology,
                                   energy_exp=args.energy_exp)
    parent_tmp = Path(tempfile.mkdtemp(prefix="reeval_cli_"))
    try:
        _reeval_one(Path(args.eval_dir), benchmark, LocalSandbox(), cost_metric,
                    args.language, args.run_cec, parent_tmp)
    finally:
        shutil.rmtree(parent_tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

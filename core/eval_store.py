"""Advisory eval + snapshot shim (handover doc §5.2) and the shared snapshot helpers.

``run_eval_and_store`` is the **agent-side advisory** eval command: it runs the same
``core.evaluation.evaluate`` the react loop uses, then emits the *exact* on-disk tree
the loop produces today (``evals.jsonl``, ``eval_{i}/``, ``best_design/`` +
``_best_meta.json``) so every downstream consumer (multirun pool/seeding, Pareto) is
untouched. It is **advisory**: scored against the agent's own (writable) copy of the
inputs. The authoritative score is re-derived later by ``core.reeval.reeval_run``
against the benchmark's own inputs.

The OpenCode backend (Phase 2) wires this in as the agent's ``eval_cmd`` (run as
``python -m core.eval_store``). The snapshot helpers here are also reused by
``core.reeval`` so advisory and authoritative passes write identical trees.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

# Names that are never the agent's *design source* — the benchmark owns these, and the
# authoritative re-eval lays down its own copies. Used by core.reeval when extracting
# design source from a stored eval workspace.
SNAPSHOT_SKIP = {"obj_dir", "_cec"}


def snapshot_best(workdir: Path, workspace: Path, eval_index, best_cost,
                  cost_metric_name: str, design_file: Optional[str] = None) -> Path:
    """Copy the design files of ``workspace`` into ``workdir/best_design`` and write
    ``_best_meta.json``. Mirrors ``RTLAgent._snapshot_best`` (skips ``obj_dir``)."""
    best_dir = Path(workdir) / "best_design"
    if best_dir.exists():
        shutil.rmtree(best_dir)
    best_dir.mkdir(parents=True)
    for item in Path(workspace).iterdir():
        if item.name == "obj_dir":
            continue
        dest = best_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    meta = {
        "eval_index": eval_index,
        "best_cost": best_cost,
        "cost_metric": cost_metric_name,
        "design_file": design_file,
    }
    (best_dir / "_best_meta.json").write_text(json.dumps(meta, indent=2))
    return best_dir


def snapshot_eval(workdir: Path, workspace: Path, eval_index,
                  eval_dict: Dict[str, Any], summary_text: str) -> Path:
    """Snapshot ``workspace`` + result + summary into ``workdir/eval_{i}/``.
    Mirrors ``RTLAgent._snapshot_eval`` (ignores ``obj_dir``/``_cec``)."""
    eval_dir = Path(workdir) / f"eval_{eval_index}"
    if eval_dir.exists():
        shutil.rmtree(eval_dir)
    eval_dir.mkdir(parents=True)
    shutil.copytree(
        workspace, eval_dir / "workspace",
        ignore=shutil.ignore_patterns("obj_dir", "_cec"),
    )
    (eval_dir / "result.json").write_text(json.dumps(eval_dict, indent=2))
    (eval_dir / "summary.txt").write_text(summary_text)
    return eval_dir


def select_best_eval(eval_dicts: List[Dict[str, Any]],
                     tiebreaker_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Pick the best eval dict: lowest ``cost_value`` among 100%-correct designs,
    ties broken by ``tiebreaker_key`` (lower wins). Mirrors the agent's best-tracking
    (``RTLAgent._run_evaluation``). Returns ``None`` if no eval passed."""
    best = None
    best_cost = None
    best_metrics: Dict[str, Any] = {}
    for ed in eval_dicts:
        if not ed.get("passed"):
            continue
        cost = ed.get("cost") or {}
        if not cost.get("ok"):
            continue
        cv = ed.get("cost_value")
        if cv is None:
            continue
        metrics = ed.get("metrics") or {}
        better = False
        if best_cost is None or cv < best_cost:
            better = True
        elif cv == best_cost and tiebreaker_key:
            new_sec = metrics.get(tiebreaker_key)
            old_sec = best_metrics.get(tiebreaker_key)
            if new_sec is not None and (old_sec is None or new_sec < old_sec):
                better = True
        if better:
            best, best_cost, best_metrics = ed, cv, metrics
    return best


def read_evals(evals_path: Path) -> List[Dict[str, Any]]:
    """Read ``evals.jsonl`` (one eval dict per line). Returns [] if absent."""
    evals_path = Path(evals_path)
    if not evals_path.exists():
        return []
    out = []
    for line in evals_path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def run_eval_and_store(
    workspace: Path,
    *,
    design_top_module: Optional[str],
    cost_metric,
    language: str = "verilog",
    run_root: Optional[Path] = None,
    design_file: Optional[str] = None,
    run_cec: bool = True,
    cec_reference: Optional[Path] = None,
    target_delay: Optional[float] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Run one advisory evaluation and emit the standard on-disk tree.

    Stateless across calls: the eval index and running best are derived from the
    files in ``run_root`` (``evals.jsonl`` + ``eval_{i}/``), so the OpenCode agent
    can invoke this as a fresh subprocess each time. Returns the eval dict.
    """
    from core.evaluation import evaluate

    workspace = Path(workspace)
    run_root = Path(run_root) if run_root is not None else workspace.parent
    run_root.mkdir(parents=True, exist_ok=True)
    evals_path = run_root / "evals.jsonl"

    existing = read_evals(evals_path)
    eval_index = len(existing) + 1

    # Apply per-eval target delay if the metric supports it (mirrors the react loop).
    if hasattr(cost_metric, "target_delay"):
        default_td = getattr(cost_metric, "target_delay", None)
        cost_metric.target_delay = target_delay if target_delay is not None else default_td

    obj_dir = workspace / "obj_dir"
    if obj_dir.exists():
        shutil.rmtree(obj_dir)

    result = evaluate(workspace, design_top_module, cost_metric=cost_metric, language=language,
                      design_file=design_file or None, run_cec=run_cec, cec_reference=cec_reference)

    eval_dict = result.to_dict()
    eval_dict["eval_index"] = eval_index
    eval_dict["design_file"] = design_file or None
    eval_dict["target_delay"] = target_delay

    with open(evals_path, "a") as f:
        f.write(json.dumps(eval_dict) + "\n")

    metric_name = cost_metric.metric_name
    tiebreaker_key = getattr(type(cost_metric), "tiebreaker_key", None)
    best = select_best_eval(existing + [eval_dict], tiebreaker_key)

    summary = result.summary_str()
    if best is not None:
        summary += (f"\n\nBest so far: {best.get('cost_value')} {metric_name} "
                    f"(eval {best.get('eval_index', '?')})")

    eval_dir = snapshot_eval(run_root, workspace, eval_index, eval_dict, summary)

    # Refresh best_design/ from the current overall-best eval's stored workspace.
    if best is not None:
        best_ws = run_root / f"eval_{best.get('eval_index')}" / "workspace"
        if best_ws.is_dir():
            snapshot_best(run_root, best_ws, best.get("eval_index"), best.get("cost_value"),
                          metric_name, best.get("design_file"))

    if not quiet:
        print(f"[Eval saved to {eval_dir.name}/]")
        print(summary, flush=True)

    return eval_dict


# --------------------------------------------------------------------------------------
# CLI: the OpenCode agent runs this as `python -m core.eval_store [design_file]`.
# Run config (top module, cost metric, language, golden ref, budget) is read from
# `<run_root>/_eval_config.json`, written once by the OpenCode backend at provision time.
# --------------------------------------------------------------------------------------

def load_eval_config(run_root: Path) -> Dict[str, Any]:
    cfg_path = Path(run_root) / "_eval_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"No _eval_config.json in {run_root}. The agent backend must write the eval config "
            f"before the agent runs the eval command.")
    return json.loads(cfg_path.read_text())


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    from core.cost import make_cost_metric

    parser = argparse.ArgumentParser(description="Advisory eval + snapshot shim (OpenCode eval_cmd).")
    parser.add_argument("design_file", nargs="?", default=None,
                        help="Main design file to evaluate (e.g. design.sv / design.py). "
                             "Omit to auto-detect.")
    parser.add_argument("--workspace", default=".", help="Workspace to evaluate (default: cwd).")
    parser.add_argument("--run-root", default=None,
                        help="Where eval_{i}/ + best_design/ + evals.jsonl live (default: workspace parent).")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    run_root = Path(args.run_root).resolve() if args.run_root else workspace.parent
    cfg = load_eval_config(run_root)

    cost_metric = make_cost_metric(
        cfg.get("cost_metric", "transistors"),
        target_delay=cfg.get("target_delay", 500.0),
        technology=cfg.get("technology", "asap7"),
        energy_exp=cfg.get("energy_exp", 1.0),
    )
    cec_reference = cfg.get("cec_reference")
    run_eval_and_store(
        workspace,
        design_top_module=cfg.get("design_top_module"),
        cost_metric=cost_metric,
        language=cfg.get("language", "verilog"),
        run_root=run_root,
        design_file=args.design_file,
        run_cec=cfg.get("run_cec", True),
        cec_reference=Path(cec_reference) if cec_reference else None,
        target_delay=cfg.get("target_delay"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

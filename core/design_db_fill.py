"""Fill the Spire design DB with RTLScout — the non-agentic campaign filler + PPA scorer (R1).

``fill_slot`` turns a DB slot into an **ephemeral RTLScout benchmark** (auto description/metadata;
the slot's golden as the CEC reference; an advisory data-driven ``tb.sv`` — the slot's frozen sim tb
when present, else golden-simulated random/corner vectors), runs a normal campaign
(``run_multirun(reeval=True)``), and pushes **every verification-passing candidate through Spire's
insert gate** — the gate re-verifies each design against the slot's frozen verification, so the
campaign's own numbers never decide admission. The slot's own golden is **seeded first**
(``seed_original``) as the selection floor / report baseline.

``rtlscout_fill`` / ``make_rtlscout_fill`` adapt this as the decorator's ``fill=`` hook.
``score_designs`` ("db score") enriches stored designs with per-technology PPA metrics
(area/delay/... via the existing cost metrics), unlocking ``metric="asap7"`` selection.

Direction note: RTLScout imports Spire (this module imports ``spire.design_db``); Spire never
imports RTLScout back.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from spire.design_db import DesignDB, DesignDBError, insert_design, seed_original
from spire.design_db.verify import VerificationError
# Reuse the S3 harness internals for the advisory tb (same-family repos, deliberate reuse).
from spire.design_db.verify_sim import (_ports_split, _run_verilator, _tb_text, _top_module_name,
                                        generate_auto_stimulus)

#: objective (selection vocabulary) -> RTLScout cost metric driving the campaign. PPA metrics need
#: the tech_eval/OpenROAD stack per eval — 'transistors' is the fast, always-available default.
OBJECTIVE_TO_COST = {"area": "transistors", "delay": "delay", "adp": "area_delay_product"}

FILL_MODEL_ENV = "RTLSCOUT_FILL_MODEL"


@dataclass
class FillReport:
    spec_key: str
    seeded: Optional[str] = None
    attempted: int = 0
    admitted: List[str] = field(default_factory=list)
    deduped: int = 0
    rejected: int = 0
    errors: List[str] = field(default_factory=list)
    runs_root: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _load_slot(db: Optional[Any], spec_key: str):
    d = DesignDB.open(db)
    slot = d.slot_dir(spec_key)
    spec = d.read_json(slot / "spec.json", None)
    if spec is None:
        raise DesignDBError(f"unknown slot {spec_key[:12]}… — register it first")
    return d, slot, spec


def _sanitize(name: str) -> str:
    out = re.sub(r"\W+", "_", name).strip("_") or "design"
    return out if out[0].isalpha() else "m_" + out


def _describe(spec: Dict[str, Any], module_name: str) -> str:
    lines = [f"Optimize this combinational/sequential block. Write a Verilog module named "
             f"`{module_name}` with exactly these ports:", ""]
    for p in spec["ports"]:
        lines.append(f"  - {p['dir']:6s} {p['name']}  ({p['width']} bit"
                     f"{'s' if p['width'] != 1 else ''}{', signed' if p['signed'] else ''})")
    lines += ["", "The module must be functionally equivalent to the reference behavior checked by "
              "the testbench; it is additionally verified against a golden reference. Minimize the "
              "cost metric."]
    return "\n".join(lines) + "\n"


def _materialize_benchmark(slot: Path, spec: Dict[str, Any], verification: Dict[str, Any],
                           bench_dir: Path, module_name: str, n_advisory_vectors: int,
                           sim_budget_s: float) -> None:
    """Write an ephemeral RTLScout benchmark dir for one slot."""
    bench_dir.mkdir(parents=True)
    golden_text = (slot / "golden.v").read_text()
    golden_top = _top_module_name(golden_text)
    if golden_top != module_name:      # rtlscout synthesizes the reference with the design's top name
        golden_text = re.sub(rf"\bmodule\s+{re.escape(golden_top)}\b",
                             f"module {module_name}", golden_text, count=1)
    (bench_dir / "golden.v").write_text(golden_text)
    (bench_dir / "description.txt").write_text(_describe(spec, module_name))
    (bench_dir / "metadata.json").write_text(json.dumps({
        "name": bench_dir.name, "module_name": module_name,
        "golden_reference": "golden.v", "golden_reference_language": "verilog",
        "generator": {"tool": "design_db_fill", "spec_key": slot.name,
                      "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
    }, indent=2) + "\n")

    if (slot / "tb.sv").exists() and (slot / "vectors.dat").exists():
        # A frozen sim verification exists — its tb doubles as the benchmark tb (contract-compatible).
        tb_text = (slot / "tb.sv").read_text().replace("`DUT", module_name)
        (bench_dir / "tb.sv").write_text(tb_text)
        shutil.copyfile(slot / "vectors.dat", bench_dir / "vectors.dat")
        return

    # Tier-0 slot: build an advisory golden-simulated vector tb (CEC stays the authority).
    ins, outs, clk, rst = _ports_split(spec)
    vectors = generate_auto_stimulus(ins, n_advisory_vectors, seed=0, sequential=clk is not None)
    with tempfile.TemporaryDirectory(prefix="fill_advtb_") as td:
        w = Path(td)
        (w / "golden.v").write_text(golden_text)
        (w / "inputs.dat").write_text(
            "\n".join(" ".join(str(v[p["name"]]) for p in ins) for v in vectors) + "\n")
        (w / "tb_gen.sv").write_text(_tb_text("gen", ins, outs, clk, rst))
        _run_verilator([w / "tb_gen.sv", w / "golden.v"], w, module_name, sim_budget_s)
        shutil.copyfile(w / "vectors.dat", bench_dir / "vectors.dat")
    (bench_dir / "tb.sv").write_text(
        _tb_text("check", ins, outs, clk, rst).replace("`DUT", module_name))


def _harvest_candidates(runs_root: Path) -> List[Path]:
    """All verification-passing candidate design files across a campaign's eval snapshots."""
    files: List[Path] = []
    for top in sorted(runs_root.glob("run_*/**/result.json")):
        if "/eval_" in str(top):
            continue
        workdir = top.parent
        for eval_dir in sorted(workdir.glob("eval_*"),
                               key=lambda p: int(p.name.split("_")[1])):
            rj = eval_dir / "result.json"
            try:
                res = json.loads(rj.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not res.get("passed"):
                continue
            ws = eval_dir / "workspace"
            named = res.get("design_file")
            cands = ([ws / named] if named else []) + [ws / "design.v", ws / "design.sv"]
            for c in cands:
                if c.exists():
                    files.append(c)
                    break
    return files


def fill_slot(spec_key: str, *, model: str, db: Optional[Any] = None,
              objective: str = "area", cost_metric: Optional[str] = None,
              module_name: Optional[str] = None, total_runs: int = 1, max_steps: int = 12,
              max_concurrent: int = 1, language: str = "verilog",
              n_advisory_vectors: int = 64, sim_budget_s: float = 300.0,
              keep_runs: bool = False, seed_baseline: bool = True) -> FillReport:
    """Run an RTLScout campaign against one slot and admit every passing candidate.

    Raises ``DesignDBError`` for unusable slots (unknown / unverified — freeze a verification
    first: ``spire db set-verification --slot <key> …``).
    """
    d, slot, spec = _load_slot(db, spec_key)
    verification = d.read_json(slot / "verification.json", None)
    if verification is None:
        raise DesignDBError(
            "slot has no frozen verification — freeze one first: "
            "spire db set-verification --slot <key> [--cec | --auto | --stimulus <file>]")

    report = FillReport(spec_key=spec_key)
    if seed_baseline:
        report.seeded = seed_original(spec_key, db=db).design_id

    module = module_name or _sanitize(spec.get("name", "design"))
    from core.cost import COST_METRICS  # rtlscout-side import, deliberately local
    cost = cost_metric or OBJECTIVE_TO_COST.get(str(objective), "transistors")
    if cost not in COST_METRICS:
        cost = "transistors"

    tmp_ctx = None
    if keep_runs:
        root = Path(tempfile.mkdtemp(prefix="rtlscout_fill_"))
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="rtlscout_fill_")
        root = Path(tmp_ctx.name)
    try:
        bench_root = root / "benchmarks"
        _materialize_benchmark(slot, spec, verification, bench_root / module, module,
                               n_advisory_vectors, sim_budget_s)
        from core.multirun import run_multirun
        run_multirun(
            benchmark_name=module, model=model, total_runs=total_runs,
            max_concurrent=max_concurrent, max_steps=max_steps, cost_metric=cost,
            language=language, benchmarks_root=bench_root, runs_root=root / "runs",
            run_cec=(verification.get("method") == "cec"), agent_backend="react", reeval=True)

        for cand in _harvest_candidates(root / "runs"):
            report.attempted += 1
            source = f"rtlscout:{model.split(':', 1)[-1]}:{cand.parent.parent.name}"
            try:
                res = insert_design(spec_key, cand, source=source, db=db)
            except VerificationError as exc:
                report.rejected += 1
                report.errors.append(f"{cand.parent.parent.name}: {type(exc).__name__}: "
                                     f"{str(exc).splitlines()[0][:160]}")
                continue
            if res.deduped:
                report.deduped += 1
            else:
                report.admitted.append(res.design_id)
        if keep_runs:
            report.runs_root = str(root)
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    return report


def make_rtlscout_fill(**cfg):
    """A configured ``fill=`` hook for ``@from_design_db`` — e.g.
    ``fill=make_rtlscout_fill(model="openrouter:z-ai/glm-5.2", total_runs=2)``."""
    def _fill(spec_key: str, db_root: Optional[Any] = None, objective: str = "area",
              metric: Optional[str] = None, **_ignored) -> None:
        fill_slot(spec_key, db=db_root, objective=objective, **cfg)
    return _fill


def rtlscout_fill(spec_key: str, db_root: Optional[Any] = None, objective: str = "area",
                  metric: Optional[str] = None, **overrides) -> None:
    """The default ``fill=`` hook. The model comes from ``$RTLSCOUT_FILL_MODEL`` (no silent
    default — generation spends budget, so the choice must be explicit)."""
    model = overrides.pop("model", None) or os.environ.get(FILL_MODEL_ENV)
    if not model:
        raise DesignDBError(f"rtlscout_fill needs a model: set ${FILL_MODEL_ENV} or use "
                            f"make_rtlscout_fill(model=...)")
    fill_slot(spec_key, db=db_root, objective=objective, model=model, **overrides)


# --- db score: per-technology PPA enrichment ---------------------------------------------------


def score_designs(spec_keys: Optional[Sequence[str]] = None, *, db: Optional[Any] = None,
                  technology: str = "asap7", target_delay: float = 500.0,
                  run_netlist_sim: bool = False, force: bool = False,
                  max_designs: Optional[int] = None,
                  designs: Optional[Sequence[str]] = None,
                  dry_run: bool = False) -> Dict[str, Any]:
    """Measure per-technology PPA on stored designs and (unless ``dry_run``) annotate the DB.

    Adds ``metrics[<technology>] = {area, delay, ...}`` to each design's ``metrics.json`` and the
    slot ``index.json`` — after this, ``select_design(..., metric=technology)`` works.
    ``designs`` limits scoring to the named design_ids (or unique prefixes) within the selected
    slots. ``dry_run`` runs the same cost flow but **writes nothing** — the measured values are
    only returned (report ``measured``), for looking at numbers without committing them.
    """
    from core.cost import make_cost_metric
    metric = make_cost_metric("area", target_delay=target_delay, technology=technology,
                              run_netlist_sim=run_netlist_sim)
    from spire.design_db import annotate
    d = DesignDB.open(db)
    keys = list(spec_keys) if spec_keys else \
        sorted(p.name for p in d.v1.iterdir() if p.is_dir()) if d.v1.is_dir() else []
    scored, skipped, failed = 0, 0, []
    measured: Dict[str, Dict[str, Any]] = {}
    for key in keys:
        slot = d.slot_dir(key)
        index = d.read_json(slot / "index.json", {})
        wanted = None
        if designs is not None:                 # exact ids or unique prefixes, within this slot
            wanted = set()
            for ref in designs:
                hits = [did for did in index if did == ref or did.startswith(ref)]
                if len(hits) == 1:
                    wanted.add(hits[0])
                elif len(hits) > 1:
                    raise DesignDBError(f"ambiguous design ref {ref!r} in slot {key[:12]}…: "
                                        f"{len(hits)} matches")
        for design_id in sorted(index):
            if wanted is not None and design_id not in wanted:
                continue
            if max_designs is not None and scored >= max_designs:
                break
            if not dry_run and not force and technology in (index[design_id].get("metrics") or {}):
                skipped += 1
                continue
            design_v = slot / "designs" / design_id / "design.v"
            if not design_v.exists():
                failed.append(f"{design_id}: design.v missing")
                continue
            with tempfile.TemporaryDirectory(prefix="db_score_") as td:
                w = Path(td)
                shutil.copyfile(design_v, w / "design.v")
                top = _top_module_name(design_v.read_text())
                cost = metric.evaluate(w, top_module=top, design_file=w / "design.v")
            if not cost.ok:
                failed.append(f"{design_id}: {getattr(cost, 'error', 'cost evaluation failed')}")
                continue
            stats = dict(cost.stats or {})
            values = {"area": stats.get("area"),
                      "delay": stats.get("delay", stats.get("runtime")),
                      "adp": stats.get("adp", stats.get("area_delay_product")),
                      "edap": stats.get("edap")}
            if values["adp"] is None and values["area"] is not None and values["delay"] is not None:
                values["adp"] = values["area"] * values["delay"]
            values = {k: v for k, v in values.items() if v is not None}
            measured[design_id] = values
            if not dry_run:
                # spire owns the write (metrics.json + index mirror, schema, reserved-name guard)
                annotate(key, design_id, tech=technology, values=values, raw=stats, force=True,
                         db=db)
            scored += 1
    return {"technology": technology, "scored": scored, "skipped": skipped, "failed": failed,
            "dry_run": dry_run, "measured": measured}

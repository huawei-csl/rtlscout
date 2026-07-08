#!/usr/bin/env python3
"""Measure the full-circuit composition space of a design-DB skills run.

For every combination of per-slot Pareto-front designs (plus the seeded-original baseline
combo), the run's decorated ``design.py`` is recompiled with the selection FORCED to that
combination (``select_design`` is patched to a ``pin=`` chooser inside the compile subprocess),
and the composed Verilog is measured: transistors (rtlscout metric — the same system as the
run's eval numbers) and AIG depth (from the gate's own AAG conversion). The starting point
(``eval_1``'s workspace snapshot) is measured the same way when present.

Writes ``composition_space.json`` into the run dir; ``visualize_db_run.py`` picks it up as the
full-circuit composition-space panel.

Usage: python measure_db_compositions.py <run_dir>
"""
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


def pareto(points):
    """Non-dominated set for (area, depth), both minimized; sorted by area."""
    pts = sorted(points, key=lambda p: (p["area"], p["depth"]))
    front, best_d = [], float("inf")
    for p in pts:
        if p["depth"] < best_d:
            front.append(p)
            best_d = p["depth"]
    return front


def aag_depth(aag_lines):
    """Longest AND-gate path from an ASCII AAG (structural delay, same units as slot aig_depth)."""
    head = aag_lines[0].split()
    n_in, n_latch, n_out, n_and = (int(x) for x in head[2:6])
    depth = {}
    start = 1 + n_in + n_latch + n_out
    for line in aag_lines[start:start + n_and]:
        lhs, a, b = (int(x) for x in line.split()[:3])
        depth[lhs // 2] = 1 + max(depth.get(a // 2, 0), depth.get(b // 2, 0))
    return max(depth.values(), default=0)


#: compile bootstrap: force the decorator's selection to the given {spec_key: design_id} map by
#: patching select_design to a pin= chooser — INSIDE the compile subprocess, where the
#: decorators actually fire. An empty map leaves selection untouched (used for eval snapshots).
_BOOT = """\
import json, runpy, sys
force = json.loads(sys.argv[1])
if force:
    import spire.design_db.decorator as dec
    from spire.design_db.select import select_design as _real
    def chooser(spec_key, objective="area", metric=None, pin=None, db=None, record=False):
        return _real(spec_key, pin=force[spec_key], db=db, record=False)
    dec.select_design = chooser
runpy.run_path("design.py", run_name="__main__")
"""


def measure_design(design_py: Path, workdir: Path, force, env):
    """Compile ``design_py`` (selections forced to ``force``) and measure the emitted design.v.

    Returns ``(transistors, aig_depth)``.
    """
    from core.cost import make_cost_metric
    from spire.design_db._yosys import run_yosys
    if Path(design_py).resolve() != (workdir / "design.py").resolve():
        shutil.copyfile(design_py, workdir / "design.py")
    proc = subprocess.run([sys.executable, "-c", _BOOT, json.dumps(force)], cwd=str(workdir),
                          capture_output=True, text=True, timeout=300, env=env)
    design_v = workdir / "design.v"
    if proc.returncode != 0 or not design_v.exists():
        raise RuntimeError(f"compile failed:\n{proc.stdout[-400:]}\n{proc.stderr[-400:]}")
    cost = make_cost_metric("transistors").evaluate(workdir, design_file=design_v)
    if not cost.ok:
        raise RuntimeError(f"cost evaluation failed: {cost.error}")
    aag = workdir / "full.aag"
    r = run_yosys([f"read_verilog -sv {design_v}", "hierarchy -auto-top", "proc",
                   "synth -flatten", "async2sync", "dffunmap", "clean", "aigmap",
                   f"write_aiger -ascii -symbols -no-startoffset {aag}"], workdir, 300)
    if r.returncode != 0 or not aag.exists():
        raise RuntimeError(f"AAG conversion failed:\n{(r.stdout + r.stderr)[-400:]}")
    return int(cost.value), aag_depth(aag.read_text().splitlines())


def _slot_designs(d, spec_key):
    out = []
    for dd in (d.slot_dir(spec_key) / "designs").iterdir():
        m = json.loads((dd / "metrics.json").read_text())
        out.append({"id": dd.name,
                    "area": m["transistors"]["metrics"]["transistors_heavy"],
                    "depth": m["aig"]["metrics"]["aig_depth"]})
    return out


def _measure_snapshot(ws_dir: Path, base_env):
    """Measure one eval_N workspace snapshot, compiled against the snapshot's own design_db
    (the DB state the agent saw) when it carries one."""
    from spire.design_db.store import DB_ENV
    with tempfile.TemporaryDirectory(prefix="comp_ev_") as td:
        w = Path(td)
        for f in ws_dir.iterdir():
            if f.name == "obj_dir":
                continue
            (shutil.copytree if f.is_dir() else shutil.copyfile)(f, w / f.name)
        env = dict(base_env)
        if (w / "design_db").exists():
            env[DB_ENV] = str(w / "design_db")
        else:
            env.pop(DB_ENV, None)
        return measure_design(w / "design.py", w, {}, env)


def measure_run(run_dir: Path, all_designs: bool = False) -> Path:
    from spire.design_db import DesignDB
    from spire.design_db.store import DB_ENV
    db_root = run_dir / "workspace" / "design_db"
    env = {**os.environ, DB_ENV: str(db_root)}
    d = DesignDB.open(db_root)
    man = d.read_json(d.manifest_path, {})
    slots = {n: e["spec_key"] for n, e in man.get("slots", {}).items()}
    if not slots:
        raise SystemExit(f"no slots in {db_root} — nothing to compose")
    selected = {n: e.get("selected_id") for n, e in man["slots"].items()}

    fronts, originals = {}, {}
    for name, key in slots.items():
        ds = _slot_designs(d, key)
        originals[name] = next((x for x in ds if x["id"].startswith("original:")), None)
        fronts[name] = sorted(ds, key=lambda x: (x["area"], x["depth"])) if all_designs else pareto(ds)
        print(f"{name}: {'all' if all_designs else 'front'} "
              f"{[(x['id'][:28], x['area'], x['depth']) for x in fronts[name]]}")

    names = sorted(slots)
    combos = [dict(zip(names, pick)) for pick in itertools.product(*(fronts[n] for n in names))]
    if all(originals[n] for n in names):
        combos.append({n: originals[n] for n in names})          # the seeded-original baseline

    design_py = run_dir / "workspace" / "design.py"
    results, seen = [], set()
    for i, combo in enumerate(combos):
        picks = {n: combo[n]["id"] for n in names}
        pick_key = tuple(sorted(picks.items()))
        if pick_key in seen:                                     # baseline may already be a combo
            continue
        seen.add(pick_key)
        force = {slots[n]: picks[n] for n in names}
        with tempfile.TemporaryDirectory(prefix="comp_") as td:
            area, depth = measure_design(design_py, Path(td), force, env)
        results.append({"picks": picks, "area": area, "depth": depth,
                        "baseline": all(v.startswith("original:") for v in picks.values()),
                        "selected": all(picks[n] == selected[n] for n in names)})
        print(f"[{i + 1}/{len(combos)}] area={area} depth={depth} {picks}")

    out = {"slots": names, "results": results}

    # The designs the main agent ACTUALLY evaluated: recompile each eval_N workspace snapshot —
    # against the snapshot's own design_db when present, i.e. the exact DB state the agent saw
    # at eval time — and measure area + depth (the recorded eval carries only the cost metric).
    evals_meta = []
    ev_file = run_dir / "agent_evals.jsonl"
    if ev_file.exists():
        evals_meta = [json.loads(l) for l in ev_file.read_text().splitlines()]
    evaluations, n = [], 1
    while (run_dir / f"eval_{n}" / "workspace" / "design.py").exists():
        area, depth = _measure_snapshot(run_dir / f"eval_{n}" / "workspace", env)
        rec = evals_meta[n - 1] if n <= len(evals_meta) else {}
        evaluations.append({"eval_index": n, "area": area, "depth": depth,
                            "recorded_cost": rec.get("cost_value"), "passed": rec.get("passed")})
        print(f"eval_{n}: area={area} depth={depth} (recorded {rec.get('cost_value')})")
        n += 1
    if evaluations:
        out["evaluations"] = evaluations
        out["starting_point"] = {"area": evaluations[0]["area"], "depth": evaluations[0]["depth"]}

    out_path = run_dir / "composition_space.json"
    out_path.write_text(json.dumps(out, indent=1))
    print("wrote", out_path)
    return out_path


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", help="a skills-run directory (holds workspace/design_db)")
    ap.add_argument("--all-designs", action="store_true",
                    help="compose over ALL admitted designs per slot instead of only the "
                         "per-slot Pareto fronts (combination count grows multiplicatively)")
    args = ap.parse_args(argv)
    measure_run(Path(args.run_dir).resolve(), all_designs=args.all_designs)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Batch ABC `&deepsyn` runner: N parallel optimizations starting from one design.

Mirrors the role of `batch_flowy_multirun.py` but for ABC's `&deepsyn` instead
of mockturtle/Flowy. ABC's `&deepsyn -S <seed>` accepts only seeds 0..100, so we
combine it with a small set of deterministic pre-scramble scripts to get a wider
range of unique trajectories.

Layout (default --full, 650 configs):
    variant 0: ""                                                 × seeds 0..100  (101 cfgs)
    variant 1: "b; rw; rf; b; rw; rwz; b; rfz; rwz; b"           × seeds 0..100  (101 cfgs)  [resyn2]
    variant 2: "b -l; rw -l; rf -l; b -l; rw -l; rwz -l; ..."    × seeds 0..100  (101 cfgs)  [compress2]
    variant 3: "&dc2"                                             × seeds 0..100  (101 cfgs)
    variant 4: "balance; rewrite -z; balance"                     × seeds 0..100  (101 cfgs)
    variant 5: "&syn3"                                            × seeds 0..100  (101 cfgs)
    variant 6: "&fraig"                                           × seeds 0..43   ( 44 cfgs)
    -----------------------------------------------------------------------------
    total                                                                          650 cfgs

Each worker invocation:
    yosys-abc -c "read_aiger <initial.aig>; <preamble>; strash; &get -n;
                  &deepsyn -T <budget> -S <seed>; &put; write_aiger <out>"

Then the output AIG is wrapped to named ports using helpers from eval_aig.py and
written as design_NNN/design.v so that `batch_eval.py` can evaluate it.

Usage:
    # Smoke (≈2 min)
    python batch_deepsyn.py --benchmark benchmarks/fpmul_f16 --top fp_mul_e5f10 \
        --initial-design benchmarks/fpmul_f16/context/design.v \
        --smoke -o pareto_fronts/fpmul_initial_deepsyn_smoke

    # Full equal-compute run (≈3 h wall clock on 80 cores)
    python batch_deepsyn.py --benchmark benchmarks/fpmul_f16 --top fp_mul_e5f10 \
        --initial-design benchmarks/fpmul_f16/context/design.v \
        --time-budget 1200 --workers 80 \
        -o pareto_fronts/fpmul_initial_deepsyn

    # Then evaluate:
    python batch_eval.py pareto_fronts/fpmul_initial_deepsyn \
        --benchmark benchmarks/fpmul_f16 --target-delay 800 1800 --workers 80 \
        -o pareto_fronts/fpmul_initial_deepsyn/eval_results.json
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from eval_aig import (
    emit_wrapper_from_map,
    BENCHMARK_PORTS,
    aig_to_flat_verilog,
    emit_wrapper,
    parse_port_spec,
    flat_clock_port,
    pin_pad,
    rename_flat_module,
)


# ABC alias expansions taken from /app/abc/abc.rc — yosys-abc doesn't load
# abc.rc by default, AND it doesn't recognize the short aliases `b`, `rw`, `rf`,
# `rwz`, `rfz`. So we expand to canonical command names too.
#   b   -> balance
#   rw  -> rewrite
#   rwz -> rewrite -z
#   rf  -> refactor
#   rfz -> refactor -z
RESYN2 = ("balance; rewrite; refactor; balance; rewrite; rewrite -z; "
          "balance; refactor -z; rewrite -z; balance")
COMPRESS2 = ("balance -l; rewrite -l; refactor -l; balance -l; rewrite -l; "
             "rewrite -z -l; balance -l; refactor -z -l; rewrite -z -l; balance -l")

# Variant table: (label, space, preamble_script, num_seeds_to_use)
# `space` selects where the preamble runs:
#   "aig" — between read_aiger and `&get -n` (operates on regular AIG manager).
#           Use for `balance`, `rewrite`, `refactor`, `resyn*`, `compress*`.
#   "gia" — between `&get -n` and `&deepsyn` (operates on the GIA).
#           Use for ABC9 commands prefixed with `&` such as `&dc2`, `&syn3`, `&fraig`.
VARIANTS_FULL = [
    ("plain",     "aig", "",                                 101),
    ("resyn2",    "aig", RESYN2,                             101),
    ("compress2", "aig", COMPRESS2,                          101),
    ("dc2",       "gia", "&dc2",                             101),
    ("balance",   "aig", "balance; rewrite -z; balance",     101),
    ("syn3",      "gia", "&syn3",                            101),
    ("fraig",     "gia", "&fraig",                            44),
]  # total = 650

VARIANTS_SMOKE = [
    ("plain",   "aig", "",                            2),
    ("resyn2",  "aig", RESYN2,                        1),
    ("dc2",     "gia", "&dc2",                        1),
]  # total = 4


def enumerate_configs(variants):
    """Flatten variants into a list of (idx, vid, label, space, preamble, seed)."""
    configs = []
    idx = 0
    for vid, (label, space, preamble, n_seeds) in enumerate(variants):
        for s in range(n_seeds):
            configs.append((idx, vid, label, space, preamble, s))
            idx += 1
    return configs


def prepare_initial_aig(design_v: Path, out_aig: Path, top_hint: str | None = None) -> Path:
    """Run Yosys once on design.v to produce a clean initial AIG.

    Recipe matches the head of spire-hdl's abc_optimize (deps/spire-hdl/.../optimize.py:879-892)
    minus the user-supplied `abc -script <deepsyn>` step, so the AIG we hand to
    deepsyn here is the same one a non-decorated SpireHDL design would produce.
    """
    top_clause = f"hierarchy -check -top {top_hint}" if top_hint else "hierarchy -check -auto-top"
    yosys_script = (
        f"read_verilog -sv {design_v}; "
        f"{top_clause}; "
        f"proc; opt; flatten; fsm; memory; opt; "
        f"techmap; opt; abc -fast; opt; "
        # Sequential designs: aigmap rejects anything but plain posedge DFFs, so
        # legalize first. Both passes are no-ops on combinational designs.
        f"async2sync; dfflegalize -cell $_DFF_P_ 01; "
        f"aigmap; "
        f"write_aiger -map {out_aig}.map {out_aig}"
    )
    proc = subprocess.run(
        ["yosys", "-q", "-p", yosys_script],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out_aig.exists():
        raise RuntimeError(
            f"Initial AIG prep failed (rc={proc.returncode}):\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return out_aig


def _run_one(args_tuple) -> dict:
    """Worker: run one deepsyn invocation + wrap to Verilog."""
    (idx, variant_id, variant_label, space, preamble, seed, initial_aig, out_root,
     top, inputs, outputs, msb_first, time_budget, benchmark_dir) = args_tuple

    design_dir = out_root / f"design_{idx:03d}"
    design_dir.mkdir(parents=True, exist_ok=True)
    run_aig = design_dir / "run.aig"
    design_v = design_dir / "design.v"
    meta_path = design_dir / "meta.json"

    # Resume support: if design.v + run.aig + meta.json exist, skip.
    if design_v.exists() and run_aig.exists() and meta_path.exists():
        return {
            "idx": idx, "variant_id": variant_id, "variant": variant_label,
            "seed": seed, "ok": True, "skipped": True,
        }

    # Build the ABC script. AIG-space preambles run on the regular AIG manager
    # (before `&get -n`); GIA-space preambles (`&dc2` etc.) run after `&get -n`.
    parts = [f"read_aiger {initial_aig}"]
    if preamble and space == "aig":
        parts.append(preamble)
    parts.append("strash")
    parts.append("&get -n")
    if preamble and space == "gia":
        parts.append(preamble)
    parts.append(f"&deepsyn -T {time_budget} -S {seed}")
    parts.append("&put")
    parts.append(f"write_aiger {run_aig}")
    script = "; ".join(parts)

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["yosys-abc", "-c", script],
            capture_output=True, text=True,
            # &deepsyn honours -T to within a few seconds, but large sequential
            # AIGs add ~100 s of I/O on top, so a flat +300 left only 15%
            # headroom over the 1300 s nominal at -T 1200 and any machine
            # slowdown truncated the run (200/250 lost that way).
            timeout=max(time_budget * 2, time_budget + 300),
        )
    except subprocess.TimeoutExpired:
        meta_path.write_text(json.dumps({
            "variant_id": variant_id, "variant": variant_label, "preamble": preamble,
            "seed": seed, "elapsed_s": time.monotonic() - t0,
            "error": "yosys-abc timed out",
        }, indent=2))
        return {"idx": idx, "variant_id": variant_id, "variant": variant_label,
                "seed": seed, "ok": False, "error": "timeout"}

    elapsed = time.monotonic() - t0

    if proc.returncode != 0 or not run_aig.exists():
        meta_path.write_text(json.dumps({
            "variant_id": variant_id, "variant": variant_label, "preamble": preamble,
            "seed": seed, "elapsed_s": elapsed, "abc_returncode": proc.returncode,
            "error": "deepsyn failed",
            "stderr_tail": proc.stderr[-1000:],
        }, indent=2))
        return {"idx": idx, "variant_id": variant_id, "variant": variant_label,
                "seed": seed, "ok": False, "error": "deepsyn_failed"}

    # Wrap the output AIG into named-port Verilog so batch_eval.py can pick it up.
    try:
        flat_v = design_dir / "_flat.v"
        aig_to_flat_verilog(run_aig, flat_v)
        flat_module = rename_flat_module(flat_v, top)
        map_file = Path(str(initial_aig) + ".map")
        flat_text = flat_v.read_text()
        pi_pad, po_pad = pin_pad(flat_text)
        clock_port = flat_clock_port(flat_text)
        if map_file.exists():
            wrapper_text = emit_wrapper_from_map(
                flat_module, top, map_file.read_text(), inputs, outputs,
                pi_pad, po_pad, clock_port)
        elif clock_port:
            raise RuntimeError("sequential AIG needs the write_aiger -map file "
                               "to identify the clock PI")
        else:
            wrapper_text = emit_wrapper(flat_module, top, inputs, outputs,
                                        msb_first, pi_pad, po_pad)
        design_v.write_text(wrapper_text + "\n" + flat_v.read_text())
        flat_v.unlink(missing_ok=True)
    except Exception as e:
        meta_path.write_text(json.dumps({
            "variant_id": variant_id, "variant": variant_label, "preamble": preamble,
            "seed": seed, "elapsed_s": elapsed, "abc_returncode": proc.returncode,
            "error": f"wrap failed: {e}",
        }, indent=2))
        return {"idx": idx, "variant_id": variant_id, "variant": variant_label,
                "seed": seed, "ok": False, "error": f"wrap_failed: {e}"}

    # Copy testbench/vectors so batch_eval.py finds them in-place.
    for name in ("tb.sv", "vectors.dat"):
        src = benchmark_dir / name
        if src.exists():
            dst = design_dir / name
            if not dst.exists():
                shutil.copy2(src, dst)

    meta_path.write_text(json.dumps({
        "variant_id": variant_id, "variant": variant_label, "preamble": preamble,
        "seed": seed, "elapsed_s": elapsed, "abc_returncode": proc.returncode,
    }, indent=2))

    return {
        "idx": idx, "variant_id": variant_id, "variant": variant_label,
        "seed": seed, "ok": True, "skipped": False, "elapsed_s": elapsed,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--initial-design", type=Path,
                   default=Path("benchmarks/fpmul_f16/context/design.v"),
                   help="Initial Verilog (default: benchmarks/fpmul_f16/context/design.v)")
    p.add_argument("--benchmark", type=Path, required=True,
                   help="Benchmark directory (for tb.sv, vectors.dat)")
    p.add_argument("--top", default=None,
                   help="Top module name. If --benchmark name is in BENCHMARK_PORTS, "
                        "derived automatically.")
    p.add_argument("--inputs", default=None,
                   help="Input port spec like 'a:16,b:16' (overrides "
                        "BENCHMARK_PORTS). ORDER MUST MATCH yosys "
                        "used only for widths; PI order comes from write_aiger -map "
                        "(observed; wrapper maps spec-order to pi indexes).")
    p.add_argument("--outputs", default=None,
                   help="Output port spec like 'y:16' (overrides BENCHMARK_PORTS)")
    p.add_argument("--msb-first", action="store_true",
                   help="MSB-first bit ordering inside buses (default: LSB-first)")
    p.add_argument("--time-budget", type=int, default=1200,
                   help="`&deepsyn -T <budget>` in seconds (default: 1200 = 20 min)")
    p.add_argument("--workers", type=int, default=80,
                   help="Parallel workers (default: 80)")
    p.add_argument("--smoke", action="store_true",
                   help="Smoke test: 4 configs, -T=30s, --workers=4")
    p.add_argument("--config-offset", type=int, default=0,
                   help="Skip the first N configs before taking --num-runs. Lets "
                        "several invocations cover DISJOINT slices of the config "
                        "space (e.g. per-seed refinement arms that together span "
                        "the same configs a single from-scratch arm would use).")
    p.add_argument("--num-runs", type=int, default=None,
                   help="Use only the first N of the enumerated configs "
                        "(e.g. 50 for the paper's per-design refinement budget); "
                        "default: all 650")
    p.add_argument("-o", "--output", type=Path, required=True,
                   help="Output dir for design_NNN/ subdirs")
    args = p.parse_args()

    # Resolve top + ports
    bench_name = args.benchmark.name
    if bench_name in BENCHMARK_PORTS:
        cfg = BENCHMARK_PORTS[bench_name]
        top = args.top or cfg["top"]
        inputs = parse_port_spec(args.inputs) if args.inputs else cfg["inputs"]
        outputs = parse_port_spec(args.outputs) if args.outputs else cfg["outputs"]
    else:
        if not (args.top and args.inputs and args.outputs):
            sys.exit(f"Benchmark '{bench_name}' not in BENCHMARK_PORTS; "
                     f"pass --top/--inputs/--outputs explicitly.")
        top = args.top
        inputs = parse_port_spec(args.inputs)
        outputs = parse_port_spec(args.outputs)

    if args.smoke:
        variants = VARIANTS_SMOKE
        time_budget = 30
        workers = min(args.workers, 4)
    else:
        variants = VARIANTS_FULL
        time_budget = args.time_budget
        workers = args.workers

    configs = enumerate_configs(variants)
    if args.num_runs is not None:
        if args.num_runs + args.config_offset > len(configs) and variants is VARIANTS_FULL:
            # The 650 total comes from truncating the fraig variant at 44
            # seeds; un-truncate it (0..100) before giving up -> max 707.
            extended = VARIANTS_FULL[:-1] + [("fraig", "gia", "&fraig", 101)]
            # Still short for large fronts (observed 2026-07-31: a 16-design
            # front -> 800 matched equal-compute runs): append further
            # standard preamble variants, +101 configs each -> max 909.
            # Appended at the END so the config ordering consumed by earlier
            # runs stays a stable prefix.
            # Full command names, NOT abc.rc aliases (b/rw/rwz) — the
            # standalone abc subprocess loads no abc.rc, so aliases fail
            # with "unknown command" (bit the glm52 run: 93 dead configs).
            extended += [("resyn", "aig",
                          "balance; rewrite; rewrite -z; balance; rewrite -z; balance", 101),
                         ("syn2", "gia", "&syn2", 101)]
            configs = enumerate_configs(extended)
        if args.num_runs + args.config_offset > len(configs):
            sys.exit(f"--num-runs {args.num_runs} (+offset {args.config_offset}) "
                     f"exceeds the {len(configs)} "
                     f"distinct deepsyn configs (&deepsyn seeds are limited "
                     f"to 0..100 per variant); add preamble variants to go "
                     f"higher.")
        off = args.config_offset
        if off:
            if off + args.num_runs > len(configs):
                sys.exit(f"--config-offset {off} + --num-runs {args.num_runs} "
                         f"exceeds the {len(configs)} available configs")
            configs = configs[off:off + args.num_runs]
        else:
            configs = configs[:args.num_runs]
    initial_design = args.initial_design.resolve()
    benchmark_dir = args.benchmark.resolve()
    out_root = args.output.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if not initial_design.exists():
        sys.exit(f"Initial design not found: {initial_design}")

    print(f"batch_deepsyn: {len(configs)} configs, -T={time_budget}s, workers={workers}")
    print(f"  Initial design: {initial_design}")
    print(f"  Top:            {top}")
    print(f"  Inputs:         {inputs}")
    print(f"  Outputs:        {outputs}")
    print(f"  Output dir:     {out_root}")
    print()

    # Step 1: produce initial AIG once.
    initial_aig = out_root / "initial.aig"
    if initial_aig.exists():
        print(f"[1/2] Re-using existing {initial_aig}")
    else:
        print(f"[1/2] Preparing initial AIG via Yosys -> {initial_aig}")
        prepare_initial_aig(initial_design, initial_aig, top_hint=top)
    print(f"      initial.aig: {initial_aig.stat().st_size} bytes\n")

    # Step 2: parallel deepsyn jobs.
    print(f"[2/2] Running {len(configs)} deepsyn jobs ({workers} parallel workers)")
    print(f"      Variants: " + ", ".join(
        f"{lbl}×{n}" for (lbl, _sp, _pre, n) in variants))
    print()

    job_args = [
        (idx, vid, label, space, preamble, seed,
         initial_aig, out_root,
         top, inputs, outputs, args.msb_first, time_budget, benchmark_dir)
        for (idx, vid, label, space, preamble, seed) in configs
    ]

    t_start = time.monotonic()
    completed = 0
    failed = 0
    skipped = 0
    results = []

    if workers <= 1:
        for ja in job_args:
            r = _run_one(ja)
            results.append(r)
            completed += 1
            if not r.get("ok"):
                failed += 1
            elif r.get("skipped"):
                skipped += 1
            print(f"  [{completed}/{len(job_args)}] design_{r['idx']:03d} "
                  f"({r['variant']} S={r['seed']}): "
                  f"{'OK' if r.get('ok') else 'FAIL'}"
                  + (f" ({r.get('elapsed_s', 0):.0f}s)" if r.get('elapsed_s') else ""))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_one, ja): ja for ja in job_args}
            for fut in as_completed(futures):
                r = fut.result()
                results.append(r)
                completed += 1
                if not r.get("ok"):
                    failed += 1
                elif r.get("skipped"):
                    skipped += 1
                if completed % 10 == 0 or completed == len(job_args) or not r.get("ok"):
                    elapsed = time.monotonic() - t_start
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (len(job_args) - completed) / rate if rate > 0 else float("inf")
                    print(f"  [{completed}/{len(job_args)}] "
                          f"design_{r['idx']:03d} ({r['variant']} S={r['seed']}): "
                          f"{'OK' if r.get('ok') else 'FAIL'} "
                          f"| failed={failed} skipped={skipped} "
                          f"| eta={eta/60:.1f}min")

    elapsed = time.monotonic() - t_start
    print(f"\nDone in {elapsed/60:.1f} min. "
          f"OK={completed-failed} FAIL={failed} SKIPPED={skipped}")

    # Build a manifest that batch_eval.py understands. Each entry has
    # "design" name so batch_eval.py's manifest lookup matches.
    manifest = []
    for r in sorted(results, key=lambda x: x["idx"]):
        manifest.append({
            "design": f"design_{r['idx']:03d}",
            "variant_id": r.get("variant_id"),
            "variant": r.get("variant"),
            "seed": r.get("seed"),
            "ok": r.get("ok"),
            "elapsed_s": r.get("elapsed_s"),
        })
    (out_root / "multirun_results.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote manifest: {out_root / 'multirun_results.json'}")
    print(f"\nNext: python batch_eval.py {out_root} "
          f"--benchmark {benchmark_dir} --target-delay 800 1800 --workers {workers}")


if __name__ == "__main__":
    main()

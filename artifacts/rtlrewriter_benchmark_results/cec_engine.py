#!/usr/bin/env python3
"""Formally equivalence-check (CEC) the best RTLRewriter designs vs. the benchmark.

For every ``(case, language)`` in a ``rtl_rewriter_multirun`` ``summary.json`` this
picks the design that achieved the table's reported best (= min) value for the
chosen metric — i.e. the exact number printed in ``table_rtl_rewriter.tex`` /
``table_rtl_rewriter_transistors_v2.tex`` — and checks it against that language's
benchmark *reference* design with Yosys.

Reference (gold):
  verilog   -> ``<benchmark_path>/context/starting_point.v``
  spirehdl  -> ``<benchmark_path>/context/design.v``      (SpireHDL-compiled baseline)

Best design (gate):
  base phase    -> identical to the reference (the shipped baseline)  => IDENTITY
  agent verilog -> ``<workdir>/best_design/<design_file>``            (.sv RTL)
  agent spirehdl-> ``<workdir>/best_design/design.v``                 (compiled .v)

Method:
  * ``equiv_make`` + ``equiv_simple`` + ``equiv_induct`` + ``equiv_status`` — handles
    combinational *and* sequential (temporal-induction) designs. ``case1`` (a
    re-pipelined parity), ``case9``/``case10`` (re-encoded FSMs) are sequential
    (``tb_mode=seq``); the rest are combinational.
  * For combinational designs that don't come back fully proven, a definitive
    ``miter -equiv`` + ``sat -prove-asserts`` fallback decides EQUIVALENT vs.
    NOT_EQUIVALENT (with a counterexample). Sequential designs left unproven by
    induction are reported INCONCLUSIVE (they still passed vector simulation in
    the run, recorded in the summary).

Outcomes per design: EQUIVALENT / NOT_EQUIVALENT / INCONCLUSIVE / IDENTITY / ERROR.
"""

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

METRIC_BASELINE = {
    "cells": "baseline_cells",
    "wires": "baseline_wires",
    "transistors": "baseline_transistors",
}


def _primary_metric(summary: Dict[str, Any]) -> str:
    cm = summary.get("cost_metric", "yosys_cells")
    if cm == "yosys_wires":
        return "wires"
    if cm in ("yosys_transistors", "transistors"):
        return "transistors"
    return "cells"


def _case_sort_key(case_id: str) -> int:
    return int(case_id.replace("case", ""))


def _phase_min(rec: Dict[str, Any], phase: str, metric: str) -> Optional[float]:
    """Table's reported best for a phase = min of ``best_<metric>`` over its runs."""
    return (rec.get(phase) or {}).get("stats", {}).get(metric, {}).get("min")


def _phase_design(rec: Dict[str, Any], phase: str) -> Tuple[Optional[str], Optional[str]]:
    """(global_best_workdir, design_file) for a phase, or (None, None)."""
    p = rec.get(phase) or {}
    wd = p.get("global_best_workdir")
    runs = p.get("runs") or [{}]
    design_file = (runs[0].get("best_eval") or {}).get("design_file")
    return wd, design_file


def _benchmark_meta(benchmark_path: str) -> Dict[str, Any]:
    meta = REPO_ROOT / benchmark_path / "metadata.json"
    try:
        return json.loads(meta.read_text())
    except Exception:
        return {}


def _reference_file(language: str, benchmark_path: str) -> Path:
    base = REPO_ROOT / benchmark_path / "context"
    return base / ("starting_point.v" if language == "verilog" else "design.v")


def _canonical_module(case_id: str, fallback: Optional[str]) -> str:
    """The paper's per-case Module label — same for both languages.

    Mirrors ``table_rtl_rewriter_multirun._case_label``: the RTLRewriter
    ``source.upstream_name`` (e.g. ``multi_constant_multiplication``). The verilog
    metadata always carries it; the spire metadata is missing it for most cases,
    so resolving per-language would show the bland top module (`example`) on the
    spire side. Prefer verilog, fall back to spire, then the top module name.
    """
    for root in ("rtl_rewriter", "rtl_rewriter_spirehdl"):
        up = (_benchmark_meta(f"benchmarks/{root}/{case_id}").get("source") or {}).get("upstream_name")
        if up:
            return up
    return fallback or case_id


def _resolve_gate(language: str, workdir: Optional[str], design_file: Optional[str]) -> Optional[Path]:
    """File holding the actual best design (verilog: the .sv; spirehdl: compiled .v)."""
    if not workdir:
        return None
    wd = Path(workdir)
    if language == "verilog":
        names = [design_file] if design_file else []
        # A `seed_<name>` pointer (phase2 tied phase1) doesn't exist on disk;
        # the underlying design is stored under its un-prefixed name.
        if design_file and design_file.startswith("seed_"):
            names.append(design_file[len("seed_"):])
        for name in names:
            for cand in (wd / "best_design" / name, wd / "workspace" / name):
                if cand.exists():
                    return cand
        return None
    # spirehdl: the SpireHDL source is a .py; the compiled verilog is design.v,
    # snapshotted into best_design/ alongside the winning design_v*.py.
    for cand in (wd / "best_design" / "design.v", wd / "workspace" / "design.v"):
        if cand.exists():
            return cand
    return None


def pick_best(rec: Dict[str, Any], metric: str) -> Dict[str, Any]:
    """Choose the phase achieving the language's min for ``metric``.

    Ties: prefer phase1 > phase2 > base. When phase2 only *ties* phase1 (no
    improvement) the summary points phase2's ``global_best_workdir`` back at the
    phase1 run and rewrites the design name with a ``seed_`` prefix that doesn't
    exist on disk — so phase1 is the reliable holder of a tied best. ``base``
    means the shipped baseline already won (the design *is* the reference =>
    IDENTITY).
    """
    base_val = rec.get(METRIC_BASELINE[metric])
    cands: List[Tuple[str, Optional[float], Optional[str], Optional[str]]] = []
    if base_val is not None:
        cands.append(("base", float(base_val), None, None))
    for phase in ("phase1", "phase2"):
        v = _phase_min(rec, phase, metric)
        if v is not None:
            wd, df = _phase_design(rec, phase)
            cands.append((phase, float(v), wd, df))
    if not cands:
        return {"phase": None, "value": None}
    best_val = min(c[1] for c in cands)
    order = {"phase1": 3, "phase2": 2, "base": 1}
    winners = sorted((c for c in cands if c[1] == best_val),
                     key=lambda c: order[c[0]], reverse=True)
    phase, value, wd, df = winners[0]
    return {"phase": phase, "value": value, "workdir": wd, "design_file": df}


# ---------------------------------------------------------------------------
# Yosys
# ---------------------------------------------------------------------------
def _run_yosys(yosys: str, script: str) -> Tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".ys", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        # No -q: we parse the equiv_status / sat log lines from stdout.
        p = subprocess.run([yosys, path], capture_output=True, text=True, timeout=600)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"
    finally:
        Path(path).unlink(missing_ok=True)


# `flatten` inlines submodules so each design becomes one self-contained module
# (the agent's designs often instantiate helpers like `times9`) — required before
# `design -copy-from`, which copies only the named top. `async2sync` rewrites async
# set/reset FFs (the FSM cases use `posedge reset`) to synchronous form so the SAT
# engine can reason about them; both are no-ops when not needed.
_PREP = "proc\nflatten\nmemory\nasync2sync\nopt -full"

# Reset-port patterns, longest/active-low first so `reset_n` wins over `reset`.
_RESET_PATTERNS = [
    (re.compile(r"\b(reset_n|rst_n|resetn|rstn|n_reset|nreset)\b", re.I), 0),
    (re.compile(r"\b(reset|rst|areset|arst|sync_reset)\b", re.I), 1),
]


def _reset_port(reference: Path) -> Tuple[Optional[str], int]:
    """(reset-port name, active level) parsed from the reference's module header.

    These benchmarks use an active-high ``reset``; the active-low patterns are a
    guard for completeness. Returns (None, 1) when the design has no reset.
    """
    try:
        text = reference.read_text()
    except Exception:
        return None, 1
    head = text.split("endmodule", 1)[0]
    for pat, active in _RESET_PATTERNS:
        m = pat.search(head)
        if m:
            return m.group(1), active
    return None, 1


def _common_prologue(gold: Path, gate: Path, top: str) -> str:
    return f"""
read_verilog -sv {gold}
hierarchy -top {top}
{_PREP}
rename {top} gold
design -stash gold_s

read_verilog -sv {gate}
hierarchy -top {top}
{_PREP}
rename {top} gate
design -stash gate_s

design -copy-from gold_s -as gold gold
design -copy-from gate_s -as gate gate
"""


def _equiv_script(gold: Path, gate: Path, top: str) -> str:
    # Structure-aware flow: equiv_make matches internal points, so equiv_simple /
    # equiv_induct stay tractable even on the big arithmetic networks (case2/12,
    # ~14k cells) where a monolithic miter+SAT would choke.
    return _common_prologue(gold, gate, top) + """
equiv_make gold gate equiv
hierarchy -top equiv
clean -purge
equiv_simple
equiv_induct
equiv_status
"""


def _miter_script(gold: Path, gate: Path, top: str, sat_cmd: str) -> str:
    # `-ignore_gold_x`: don't flag frames where the *reference* output is x
    # (its FFs are undef until reset loads them).
    return _common_prologue(gold, gate, top) + f"""
miter -equiv -flatten -make_assert -ignore_gold_x gold gate miter
hierarchy -top miter
opt -full
{sat_cmd}
"""


# Combinational: a single-frame miter SAT is definitive; `-set-def-inputs`
# forbids x on inputs (real input bits are 2-valued) so x-propagation
# differences between a `case` and boolean logic aren't reported as mismatches.
_SAT_COMB = "sat -prove-asserts -set-def-inputs miter"


def _sat_seq(reset_port: Optional[str], reset_active: int, *, bmc: int = 0) -> str:
    rst = f" -set-at 0 in_{reset_port} {reset_active}" if reset_port else ""
    if bmc:
        # Bounded fallback: reset at frame 0, skip the undef-load transient.
        return (f"sat -seq {bmc} -prove-asserts -prove-skip 1 "
                f"-set-init-undef -set-def-inputs{rst} miter")
    # Temporal (k-)induction = unbounded proof; reset-anchored so base cases and
    # the induction frame start from the reachable reset state.
    return (f"sat -tempinduct -prove-asserts -seq 1 -maxsteps 40 "
            f"-set-init-undef -set-def-inputs{rst} miter")


_PROVEN_RE = re.compile(r"(\d+)\s+are proven and\s+(\d+)\s+are unproven")


def cec_one(yosys: str, gold: Path, gate: Path, top: str, seq: bool,
            reset_port: Optional[str], reset_active: int) -> Dict[str, Any]:
    # Stage 1: structure-aware equiv flow (fast, scales to the big arithmetic).
    rc, out = _run_yosys(yosys, _equiv_script(gold, gate, top))
    if "TIMEOUT" in out:
        return {"status": "ERROR", "detail": "equiv flow timed out (600s)"}
    if rc != 0 and "Equivalence successfully proven" not in out and _PROVEN_RE.search(out) is None:
        return {"status": "ERROR", "detail": _last_error(out), "log": out[-1500:]}

    m = _PROVEN_RE.search(out)
    proven, unproven = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    if "Equivalence successfully proven!" in out or (unproven == 0 and m):
        return {"status": "EQUIVALENT", "method": "equiv_induct",
                "detail": f"equiv flow: all {proven} $equiv cells proven", "proven": proven}

    # Stage 2: definitive fallback on the points equiv couldn't close.
    if not seq:
        rc2, out2 = _run_yosys(yosys, _miter_script(gold, gate, top, _SAT_COMB))
        if "no model found" in out2:
            return {"status": "EQUIVALENT", "method": "miter+SAT",
                    "detail": "miter+SAT UNSAT — no input distinguishes the designs"}
        if "model found" in out2:
            return {"status": "NOT_EQUIVALENT", "method": "miter+SAT",
                    "detail": "miter+SAT found a distinguishing input", "log": out2[-2000:]}
        return {"status": "ERROR", "detail": "miter+SAT gave no verdict", "log": out2[-1500:]}

    # Sequential: reset-anchored temporal induction (complete proof) ...
    sat_ti = _sat_seq(reset_port, reset_active)
    rc3, out3 = _run_yosys(yosys, _miter_script(gold, gate, top, sat_ti))
    if "Induction step proven: SUCCESS!" in out3:
        return {"status": "EQUIVALENT", "method": "tempinduct",
                "detail": "reset-anchored temporal induction — complete proof"}
    if "model found for base case" in out3:
        return {"status": "NOT_EQUIVALENT", "method": "tempinduct",
                "detail": "temporal-induction base case found a reachable mismatch",
                "log": out3[-2000:]}
    # ... induction didn't converge: fall back to a deep bounded check from reset.
    sat_bmc = _sat_seq(reset_port, reset_active, bmc=64)
    rc4, out4 = _run_yosys(yosys, _miter_script(gold, gate, top, sat_bmc))
    if "no model found" in out4:
        return {"status": "EQUIVALENT", "method": "BMC-64",
                "detail": "bounded SEC clean to 64 cycles from reset (induction "
                          "did not converge); also vector-verified in the run"}
    if "model found" in out4:
        return {"status": "NOT_EQUIVALENT", "method": "BMC-64",
                "detail": "bounded SEC found a reachable mismatch", "log": out4[-2000:]}
    return {"status": "INCONCLUSIVE",
            "detail": "sequential induction did not converge and BMC gave no verdict"}


def _last_error(out: str) -> str:
    errs = [ln for ln in out.splitlines() if "ERROR" in ln or "Error" in ln]
    return errs[-1].strip() if errs else (out.strip().splitlines() or ["unknown error"])[-1]


# ---------------------------------------------------------------------------
# Simulation-based equivalence (for designs whose formal CEC is intractable —
# e.g. the case2 / case12 networks with 32-bit multipliers, where a SAT miter
# blows up). Both designs are driven with the SAME random vectors and their
# outputs compared cycle-by-cycle. Not a proof, but N=200k random vectors over
# combinational arithmetic is strong evidence, on top of the run's own TB.
# ---------------------------------------------------------------------------
def _emit_renamed(yosys: str, src: Path, top: str, new_name: str,
                  out_v: Path, ports_json: Optional[Path]) -> Tuple[bool, str]:
    cmds = [f"read_verilog -sv {src}", f"hierarchy -top {top}", "proc", "flatten",
            "opt -full", f"rename {top} {new_name}", f"write_verilog {out_v}"]
    if ports_json:
        cmds.append(f"write_json {ports_json}")
    rc, out = _run_yosys(yosys, "\n".join(cmds) + "\n")
    return rc == 0, out


def _gen_tb(ports: List[Tuple[str, int, str]]) -> str:
    """SystemVerilog TB: drive both designs with identical random vectors, compare."""
    ins = [(n, w) for n, w, d in ports if d == "input"]
    outs = [(n, w) for n, w, d in ports if d == "output"]

    def rnd(w: int) -> str:
        n = (w + 31) // 32
        return "{" + ",".join(["$random"] * n) + "}" if n > 1 else "$random"

    L = ["module tb;", "  integer i, errors;"]
    L += [f"  reg [{w-1}:0] {n};" for n, w in ins]
    L += [f"  wire [{w-1}:0] {n}_g, {n}_k;" for n, w in outs]
    gconn = ", ".join([f".{n}({n})" for n, _ in ins] + [f".{n}({n}_g)" for n, _ in outs])
    kconn = ", ".join([f".{n}({n})" for n, _ in ins] + [f".{n}({n}_k)" for n, _ in outs])
    L += [f"  gold g({gconn});", f"  gate k({kconn});",
          "  initial begin", "    errors = 0;",
          "    for (i = 0; i < `NVEC; i = i + 1) begin"]
    L += [f"      {n} = {rnd(w)};" for n, w in ins]
    cmp = " || ".join([f"({n}_g !== {n}_k)" for n, _ in outs]) or "1'b0"
    L += ["      #1;",
          f"      if ({cmp}) begin errors = errors + 1; "
          f"if (errors <= 5) $display(\"MISMATCH i=%0d\", i); end",
          "    end",
          "    $display(\"SIM_EQUIV vectors=%0d errors=%0d\", `NVEC, errors);",
          "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def _sim_label(n: int) -> str:
    if n >= 1_000_000 and n % 1_000_000 == 0:
        return f"sim-{n // 1_000_000}M"
    if n % 1000 == 0:
        return f"sim-{n // 1000}k"
    return f"sim-{n}"


def sim_equiv(yosys: str, verilator: str, gold: Path, gate: Path, top: str,
              n_vectors: int) -> Dict[str, Any]:
    import shutil
    lbl = _sim_label(n_vectors)
    workdir = Path(tempfile.mkdtemp(prefix="cecsim_"))
    try:
        gold_v, gate_v = workdir / "gold_r.v", workdir / "gate_r.v"
        ports_json = workdir / "ports.json"
        ok1, o1 = _emit_renamed(yosys, gold, top, "gold", gold_v, ports_json)
        ok2, o2 = _emit_renamed(yosys, gate, top, "gate", gate_v, None)
        if not (ok1 and ok2 and ports_json.exists()):
            return {"status": "ERROR", "method": lbl,
                    "detail": "yosys netlist emit failed for sim",
                    "log": (o1 + o2)[-1200:]}
        mod = json.loads(ports_json.read_text())["modules"]["gold"]
        ports = [(n, len(p["bits"]), p["direction"]) for n, p in mod["ports"].items()]
        (workdir / "tb.sv").write_text(_gen_tb(ports))
        build = subprocess.run(
            [verilator, "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTH",
             "-Wno-UNOPTFLAT", "-Wno-CASEINCOMPLETE", "-Wno-MULTIDRIVEN",
             "-Wno-SELRANGE", f"-DNVEC={n_vectors}", "--top-module", "tb",
             "gold_r.v", "gate_r.v", "tb.sv", "-o", "simbin"],
            cwd=workdir, capture_output=True, text=True, timeout=600)
        if build.returncode != 0:
            return {"status": "ERROR", "method": lbl,
                    "detail": "verilator build failed",
                    "log": (build.stdout + build.stderr)[-1500:]}
        run = subprocess.run([str(workdir / "obj_dir" / "simbin")],
                             cwd=workdir, capture_output=True, text=True, timeout=600)
        m = re.search(r"SIM_EQUIV vectors=(\d+) errors=(\d+)", run.stdout)
        if not m:
            return {"status": "ERROR", "method": lbl,
                    "detail": "sim produced no verdict", "log": run.stdout[-1200:]}
        vecs, errs = int(m.group(1)), int(m.group(2))
        if errs == 0:
            return {"status": "EQUIVALENT", "method": lbl,
                    "detail": f"{vecs:,} random vectors, 0 mismatches (simulation; "
                              f"formal CEC intractable — 32-bit multipliers)"}
        return {"status": "NOT_EQUIVALENT", "method": lbl,
                "detail": f"{errs} mismatches in {vecs:,} random vectors",
                "log": run.stdout[-1200:]}
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "method": "sim", "detail": "sim timed out (600s)"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _row_sort_key(r: Dict[str, Any]) -> Tuple[int, int]:
    return (_case_sort_key(r["case"]), 0 if r.get("language") == "verilog" else 1)


def _prepare_row(case_id: str, language: str, rec: Dict[str, Any],
                 metric: str, sim_cases: set) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Build the row; resolve the design pair. Returns (row, runnable) where
    ``runnable`` is a dict of CEC/sim arguments, or None when the row is already
    decided (IDENTITY / ERROR) and needs no run."""
    bpath = rec.get("benchmark_path")
    meta = _benchmark_meta(bpath)
    top = meta.get("module_name") or rec.get("module_name")
    seq = meta.get("tb_mode") == "seq"
    upstream = _canonical_module(case_id, top)  # paper label, same for both langs
    best = pick_best(rec, metric)
    row: Dict[str, Any] = {
        "case": case_id, "language": language, "module": upstream,
        "top": top, "seq": seq, "metric": metric,
        "value": best.get("value"), "phase": best.get("phase"),
    }
    gold = _reference_file(language, bpath)
    if not gold.exists():
        row.update(status="ERROR", detail=f"reference missing: {gold}")
        return row, None
    if best.get("phase") == "base":
        # The winning design is the shipped baseline == the reference itself.
        row.update(status="IDENTITY",
                   detail="best = shipped baseline (identical to the reference)",
                   gate=str(gold))
        return row, None
    gate = _resolve_gate(language, best.get("workdir"), best.get("design_file"))
    if not gate or not gate.exists():
        row.update(status="ERROR",
                   detail=f"best design file not found (phase={best.get('phase')}, "
                          f"file={best.get('design_file')})")
        return row, None
    row["gate"] = str(gate)
    reset_port, reset_active = _reset_port(gold) if seq else (None, 1)
    return row, {"gold": gold, "gate": gate, "top": top, "seq": seq,
                 "reset_port": reset_port, "reset_active": reset_active,
                 "sim": _case_sort_key(case_id) in sim_cases}


def run_table(summary: Dict[str, Any], metric: str, yosys: str,
              only_cases: Optional[List[int]], workers: int,
              out_path: Optional[Path], json_path: Optional[Path],
              label: str, sim_cases: Optional[set] = None,
              sim_vectors: int = 200000, verilator: str = "verilator"
              ) -> List[Dict[str, Any]]:
    """Run all (case, language) CECs concurrently, re-writing the report after
    every completion so the partial table is readable at any time."""
    sim_cases = sim_cases or set()
    results = summary.get("results", {})
    rows: List[Dict[str, Any]] = []
    pending: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for case_id in sorted(results, key=_case_sort_key):
        if only_cases and _case_sort_key(case_id) not in only_cases:
            continue
        for language in ("verilog", "spirehdl"):
            rec = results[case_id].get(language, {})
            if not rec:
                continue
            row, runnable = _prepare_row(case_id, language, rec, metric, sim_cases)
            if runnable is None:
                rows.append(row); _log_row(row)
            else:
                row["status"] = "RUNNING"
                rows.append(row)
                pending.append((row, runnable))

    total = len(rows)
    lock = threading.Lock()
    _emit(rows, out_path, json_path, metric, label, total)

    def work(item: Tuple[Dict[str, Any], Dict[str, Any]]) -> Dict[str, Any]:
        row, a = item
        if a["sim"]:
            res = sim_equiv(yosys, verilator, a["gold"], a["gate"], a["top"], sim_vectors)
        else:
            res = cec_one(yosys, a["gold"], a["gate"], a["top"], a["seq"],
                          a["reset_port"], a["reset_active"])
        row.update(res)
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(work, it) for it in pending]
        for fut in concurrent.futures.as_completed(futs):
            row = fut.result()
            with lock:
                _log_row(row)
                _emit(rows, out_path, json_path, metric, label, total)
    return rows


_STATUS_MARK = {
    "EQUIVALENT": "✅", "IDENTITY": "✅", "NOT_EQUIVALENT": "❌",
    "INCONCLUSIVE": "⚠️", "ERROR": "🛑",
}


def _log_row(row: Dict[str, Any]) -> None:
    mark = _STATUS_MARK.get(row.get("status", ""), "?")
    print(f"  {mark} {row['case']:7s} {row['language']:8s} {row['module']:28s} "
          f"{row['metric']}={row.get('value')!s:>7} phase={row.get('phase')!s:6s} "
          f"-> {row.get('status')}: {row.get('detail','')}", file=sys.stderr)


_STATUS_MARK_RUN = dict(_STATUS_MARK, RUNNING="⏳")


def render_markdown(rows: List[Dict[str, Any]], metric: str, label: str,
                    total: Optional[int] = None) -> str:
    from collections import Counter
    rows = sorted(rows, key=_row_sort_key)
    done = sum(1 for r in rows if r.get("status") not in (None, "RUNNING"))
    total = total or len(rows)
    head = f"## CEC results — {label} (metric: {metric})"
    if done < total:
        head += f"  *(in progress: {done}/{total} done)*"
    out = [head, "",
           "| Case | Module | Lang | Best phase | "
           f"{metric} | Type | CEC result | Method · detail |",
           "|:---|:---|:---|:---|---:|:---:|:---|:---|"]
    for r in rows:
        mark = _STATUS_MARK_RUN.get(r.get("status", ""), "")
        val = r.get("value")
        val_s = "—" if val is None else (str(int(val)) if float(val).is_integer() else str(val))
        meth = r.get("method")
        detail = (f"`{meth}` · " if meth else "") + str(r.get("detail", ""))
        out.append(f"| {r['case']} | `{r['module']}` | {r['language']} | "
                   f"{r.get('phase')} | {val_s} | {'seq' if r.get('seq') else 'comb'} | "
                   f"{mark} {r.get('status')} | {detail} |")
    tally = Counter(r.get("status") for r in rows)
    out += ["", "**Summary:** " + ", ".join(f"{k}: {v}" for k, v in sorted(tally.items())) +
            f"  (total {len(rows)})", ""]
    return "\n".join(out)


def _emit(rows: List[Dict[str, Any]], out_path: Optional[Path],
          json_path: Optional[Path], metric: str, label: str, total: int) -> None:
    """Atomically rewrite the JSON + markdown so the partial table is always readable."""
    ordered = sorted(rows, key=_row_sort_key)
    if json_path:
        tmp = json_path.with_suffix(json_path.suffix + ".tmp")
        tmp.write_text(json.dumps(ordered, indent=2))
        tmp.replace(json_path)
    if out_path:
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(render_markdown(ordered, metric, label, total) + "\n")
        tmp.replace(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("summary_json", type=Path)
    ap.add_argument("--metric", choices=["cells", "wires", "transistors"], default=None,
                    help="default: the summary's primary cost metric")
    ap.add_argument("--label", default=None, help="human label for the report section")
    ap.add_argument("--cases", type=int, nargs="*", default=None,
                    help="restrict to these case numbers")
    ap.add_argument("--yosys", default="yosys")
    ap.add_argument("--verilator", default="verilator")
    ap.add_argument("--workers", type=int, default=16,
                    help="number of (case,language) CECs to run concurrently")
    ap.add_argument("--sim-cases", type=int, nargs="*", default=[],
                    help="run these cases via random-vector simulation instead of "
                         "formal CEC (for designs whose miter is SAT-intractable, "
                         "e.g. 32-bit multipliers in case2/case12)")
    ap.add_argument("--sim-vectors", type=int, default=1000000,
                    help="number of random vectors for --sim-cases")
    ap.add_argument("--out", type=Path, default=None,
                    help="markdown report (rewritten after every completion)")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="raw results JSON (rewritten after every completion)")
    args = ap.parse_args()

    summary = json.loads(args.summary_json.read_text())
    metric = args.metric or _primary_metric(summary)
    label = args.label or args.summary_json.parent.name
    print(f"[cec] {label}: metric={metric} workers={args.workers} "
          f"sim_cases={args.sim_cases}", file=sys.stderr)
    rows = run_table(summary, metric, args.yosys, args.cases,
                     args.workers, args.out, args.json_out, label,
                     sim_cases=set(args.sim_cases), sim_vectors=args.sim_vectors,
                     verilator=args.verilator)

    if not args.out:
        print(render_markdown(rows, metric, label))
    else:
        print(f"[cec] wrote {args.out}", file=sys.stderr)
    if args.json_out:
        print(f"[cec] wrote {args.json_out}", file=sys.stderr)

    return 1 if any(r.get("status") == "NOT_EQUIVALENT" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

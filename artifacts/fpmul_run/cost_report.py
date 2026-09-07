"""Per-phase cost breakdown: LLM/API cost and compute cost (core-hours).

Standalone by design — it only READS existing pipeline artifacts (run
result.json files, deepsyn meta.json files, command logs) and writes:
  state/<tag>/cost_breakdown.json
  figures/<tag>/table_cost_breakdown_v{1,2,3}.tex   (LaTeX variants)
report.py renders the JSON as a section in REPORT_<tag>.md.

Methodology (noted per row in the output):
- LLM tokens/cost: summed from each agent run's result.json token_usage;
  priced via MODEL_PRICING (USD per 1M tokens, incl. cache write/read).
- Agent compute: sum of per-eval measured wall clock x 1 core (sims and
  synthesis are single-threaded; short Verilator build bursts use up to
  8-16 cores and are not counted -> slight underestimate).
- Deepsyn compute: sum of per-job measured elapsed_s x 1 core (yosys-abc is
  single-threaded) — fully measured.
- Sweep / batch-eval / verification: wall clock from the command log
  (last "===== [ts]" header to file mtime) x the configured concurrency,
  capped by job count -> estimate (upper bound).
"""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "stages"))
import rerun_config as cfg

# USD per 1M tokens — official price list (user-confirmed 2026-07-28).
# cache_write is the 5-minute tier ($6.25; 1h would be $10): the runner's
# cache_control blocks are {"type": "ephemeral"} with no ttl -> 5m default.
MODEL_PRICING = {
    "claude-opus-5": {"input": 5.0, "output": 25.0,
                      "cache_write": 6.25, "cache_read": 0.50},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0,
                        "cache_write": 6.25, "cache_read": 0.50},
    # OpenRouter listing (fetched 2026-07-29); our OpenRouter client does no
    # prompt caching, so cache terms are 0 in usage anyway (cache_write is
    # not billed separately by these providers).
    "moonshotai/kimi-k3": {"input": 3.0, "output": 15.0,
                           "cache_write": 0.0, "cache_read": 0.30},
    "z-ai/glm-5.2": {"input": 0.6916, "output": 2.1736,
                     "cache_write": 0.0, "cache_read": 0.12844},
}

# Monetize compute for a single-unit total: USD per CPU-core-hour, using a
# public-cloud on-demand vCPU-hour equivalent (AWS c7a-class ~$0.04-0.05).
COMPUTE_USD_PER_CORE_H = 0.04

_TS_RE = re.compile(r"^===== \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", re.M)


def _price(usage: dict, model: str) -> float:
    p = MODEL_PRICING[model.split(":")[-1]]
    return (usage.get("input_tokens", 0) * p["input"]
            + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1e6


def _log_wall_s(log_name: str) -> float:
    """Wall seconds of the LAST invocation recorded in logs/<name>.log."""
    log = cfg.LOGS / f"{log_name}.log"
    if not log.exists():
        return 0.0
    stamps = _TS_RE.findall(log.read_text(errors="replace"))
    if not stamps:
        return 0.0
    t0 = datetime.datetime.strptime(stamps[-1], "%Y-%m-%d %H:%M:%S").timestamp()
    return max(0.0, log.stat().st_mtime - t0)


def _agent_phase(campaigns) -> dict:
    tok = {"input_tokens": 0, "output_tokens": 0,
           "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    usd = runs = steps = 0
    run_wall_s = eval_wall_s = 0.0
    evals = 0
    for _name, root, *_ in campaigns:
        for rj in Path(root).glob("run_*/*/*/*/result.json"):
            r = json.loads(rj.read_text())
            u = r.get("token_usage") or {}
            for k in tok:
                tok[k] += u.get(k, 0)
            usd += _price(u, cfg.MODEL)
            runs += 1
            steps += r.get("num_steps", 0)
            run_wall_s += r.get("duration_s", 0.0)
        for ej in Path(root).glob("run_*/*/*/*/eval_*/result.json"):
            e = json.loads(ej.read_text())
            eval_wall_s += e.get("duration_s", 0.0)
            evals += 1
    return {"tok": tok, "usd": usd, "runs": runs, "steps": steps, "evals": evals,
            "run_wall_s": run_wall_s, "eval_wall_s": eval_wall_s}


def _deepsyn_core_s(front: Path) -> float:
    return sum(json.loads(m.read_text()).get("elapsed_s", 0.0)
               for m in front.glob("**/meta.json"))


def _verify_wall_s() -> float:
    total = 0.0
    for front in (cfg.FRONT_ABC, cfg.FRONT_NO_ABC, cfg.FRONT_SWEEP_DEDUP,
                  cfg.FRONT_DEEPSYN_REFINE / "reported_front",
                  cfg.FRONT_INITIAL_DEEPSYN / "reported_front",
                  cfg.FRONT_INITIAL_DEEPSYN_2X / "reported_front"):
        vr = front / "verification_results.json"
        if vr.exists():
            total += json.loads(vr.read_text()).get("duration_s", 0.0)
    return total


def collect_costs() -> dict:
    rows = []

    for label, campaigns in (("Phase 1 (agent)", cfg.CAMPAIGNS_P1),
                             ("Phase 2 (agent+synth)", cfg.CAMPAIGNS_P2)):
        a = _agent_phase(campaigns)
        if a["runs"] == 0:
            continue
        rows.append({
            "phase": label, "llm_runs": a["runs"], "llm_steps": a["steps"],
            "tok_in_M": (a["tok"]["input_tokens"]
                         + a["tok"]["cache_creation_input_tokens"]
                         + a["tok"]["cache_read_input_tokens"]) / 1e6,
            "tok_out_M": a["tok"]["output_tokens"] / 1e6,
            "llm_usd": a["usd"],
            "wall_h": a["run_wall_s"] / 3600,
            "core_h": a["eval_wall_s"] / 3600,   # evals, 1 core each
            "note": f"{a['evals']} evals; compute = measured eval wall x 1 core",
        })

    sweep_wall = _log_wall_s("stage3_sweep")
    if sweep_wall:
        jobs = 2 if cfg.SWEEP_SINGLE_POINT else 183
        conc = min(80, jobs)
        rows.append({
            "phase": "Phase 3 (arch sweep)", "llm_runs": 0, "llm_steps": 0,
            "tok_in_M": 0.0, "tok_out_M": 0.0, "llm_usd": 0.0,
            "wall_h": sweep_wall / 3600, "core_h": sweep_wall / 3600 * conc,
            "note": f"est: wall x min(80, {jobs} jobs/case)",
        })

    # Method cost: the REFINE arm only. The equal-compute from-scratch arm
    # is a comparison baseline, not part of the RTLScout method (user
    # decision 2026-08-04) — reported separately and excluded from Total.
    ev_conc = min(cfg.EVAL_WORKERS, 8)
    ds_refine = _deepsyn_core_s(cfg.FRONT_DEEPSYN_REFINE)
    if ds_refine:
        ev_wall = sum(_log_wall_s(f"stage4_eval_{d.name}") for d in
                      cfg.FRONT_DEEPSYN_REFINE.glob("design_*") if d.is_dir())
        rows.append({
            "phase": "Phase 4 (Deepsyn refine)", "llm_runs": 0, "llm_steps": 0,
            "tok_in_M": 0.0, "tok_out_M": 0.0, "llm_usd": 0.0,
            "wall_h": (ds_refine / cfg.DEEPSYN_WORKERS + ev_wall) / 3600,
            "core_h": (ds_refine + ev_wall * ev_conc) / 3600,
            "note": "refine arm only; deepsyn measured per-job x 1 core; "
                    f"evals est wall x min(workers, {ev_conc})",
        })
    ds_base = _deepsyn_core_s(cfg.FRONT_INITIAL_DEEPSYN)
    if ds_base:
        ev_wall_b = _log_wall_s("stage4_eval_equal_compute")
        rows.append({
            "phase": "Baseline: Deepsyn only", "llm_runs": 0,
            "llm_steps": 0, "tok_in_M": 0.0, "tok_out_M": 0.0, "llm_usd": 0.0,
            "wall_h": (ds_base / cfg.DEEPSYN_WORKERS + ev_wall_b) / 3600,
            "core_h": (ds_base + ev_wall_b * ev_conc) / 3600,
            "baseline": True,
            "note": "equal-compute COMPARISON arm — not part of the RTLScout "
                    "method; excluded from Total",
        })
    ds_base2 = (_deepsyn_core_s(cfg.FRONT_INITIAL_DEEPSYN_2X)
                if cfg.FRONT_INITIAL_DEEPSYN_2X.exists() else 0.0)
    if ds_base2:
        ev_wall_b2 = _log_wall_s("stage4_eval_equal_compute_2x")
        rows.append({
            "phase": "Baseline: from scratch 2x effort", "llm_runs": 0,
            "llm_steps": 0, "tok_in_M": 0.0, "tok_out_M": 0.0, "llm_usd": 0.0,
            "wall_h": (ds_base2 / cfg.DEEPSYN_WORKERS + ev_wall_b2) / 3600,
            "core_h": (ds_base2 + ev_wall_b2 * ev_conc) / 3600,
            "baseline": True,
            "note": "double-effort comparison arm; excluded from Total",
        })

    v_wall = _verify_wall_s()
    if v_wall:
        rows.append({
            "phase": "Verification", "llm_runs": 0, "llm_steps": 0,
            "tok_in_M": 0.0, "tok_out_M": 0.0, "llm_usd": 0.0,
            "wall_h": v_wall / 3600, "core_h": v_wall / 3600 * 16,
            "note": "est: wall x 16 (build 8-way; 2^32 sim bursts 110-way, short)",
        })

    method = [r for r in rows if not r.get("baseline")]
    total = {"phase": "Total (method)",
             "llm_runs": sum(r["llm_runs"] for r in method),
             "llm_steps": sum(r["llm_steps"] for r in method),
             "tok_in_M": sum(r["tok_in_M"] for r in method),
             "tok_out_M": sum(r["tok_out_M"] for r in method),
             "llm_usd": sum(r["llm_usd"] for r in method),
             "wall_h": sum(r["wall_h"] for r in method),
             "core_h": sum(r["core_h"] for r in method), "note": ""}
    for r in rows + [total]:
        r["compute_usd"] = r["core_h"] * COMPUTE_USD_PER_CORE_H
        r["total_usd"] = r["llm_usd"] + r["compute_usd"]
    return {"rows": rows, "total": total, "model": cfg.MODEL,
            "compute_usd_per_core_h": COMPUTE_USD_PER_CORE_H,
            "pricing_usd_per_M": MODEL_PRICING[cfg.MODEL.split(":")[-1]],
            "profile": cfg.PROFILE,
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------- rendering
def markdown_table(c: dict) -> list:
    lines = ["| phase | LLM runs | tokens in (M) | tokens out (M) | LLM ($) "
             "| wall (h) | compute (core-h) | compute ($) | total ($) |",
             "|---|---|---|---|---|---|---|---|---|"]
    _method = [r for r in c["rows"] if not r.get("baseline")]
    _base = [r for r in c["rows"] if r.get("baseline")]
    for r in _method + [c["total"]] + _base:
        lines.append(f"| {r['phase']} | {r['llm_runs'] or '—'} "
                     f"| {r['tok_in_M']:.1f} | {r['tok_out_M']:.2f} "
                     f"| {r['llm_usd']:.2f} | {r['wall_h']:.2f} | {r['core_h']:.1f} "
                     f"| {r['compute_usd']:.2f} | {r['total_usd']:.2f} |")
    lines.append("")
    lines.append(f"Pricing ({c['model']}, USD/M tok): {c['pricing_usd_per_M']} "
                 "(official list, 5m-cache-write tier); compute at "
                 f"${c['compute_usd_per_core_h']}/core-h (cloud on-demand "
                 "vCPU-hour equivalent). Notes: "
                 + " · ".join(f"{r['phase']}: {r['note']}" for r in c["rows"]))
    return lines


def _tex_row(r, cols):
    fmt = {"phase": lambda v: v, "llm_runs": lambda v: str(v) if v else "--",
           "tok_in_M": lambda v: f"{v:.1f}", "tok_out_M": lambda v: f"{v:.2f}",
           "llm_usd": lambda v: f"{v:.2f}", "wall_h": lambda v: f"{v:.1f}",
           "core_h": lambda v: f"{v:.1f}", "compute_usd": lambda v: f"{v:.2f}",
           "total_usd": lambda v: f"{v:.2f}"}
    return " & ".join(fmt[c](r[c]) for c in cols) + r" \\"


def latex_tables(c: dict) -> dict:
    rows, total = c["rows"], c["total"]
    method_rows = [r for r in rows if not r.get("baseline")]
    base_rows = [r for r in rows if r.get("baseline")]
    v = {}
    # v1 — detailed: one row per phase, all resource columns.
    cols = ["phase", "llm_runs", "tok_in_M", "tok_out_M", "llm_usd", "wall_h",
            "core_h", "compute_usd", "total_usd"]
    v["v1"] = "\n".join(
        [r"\begin{tabular}{@{}lrrrrrrrr@{}}", r"\toprule",
         r"Phase & Runs & \multicolumn{2}{c}{Tokens (M)} & API & Wall "
         r"& \multicolumn{2}{c}{Compute} & Total \\",
         r" & & in & out & (\$) & (h) & (core-h) & (\$) & (\$) \\", r"\midrule"]
        + [_tex_row(r, cols) for r in method_rows]
        + [r"\midrule", _tex_row(total, cols)]
        + ([r"\midrule"] + [_tex_row(r, cols) for r in base_rows]
           if base_rows else [])
        + [r"\bottomrule", r"\end{tabular}"])
    # v2 — compact: dollars-first view.
    cols2 = ["phase", "llm_usd", "core_h", "compute_usd", "total_usd"]
    v["v2"] = "\n".join(
        [r"\begin{tabular}{@{}lrrrr@{}}", r"\toprule",
         r"Phase & API (\$) & Compute (core-h) & Compute (\$) & Total (\$) \\",
         r"\midrule"]
        + [_tex_row(r, cols2) for r in method_rows]
        + [r"\midrule", _tex_row(total, cols2)]
        + ([r"\midrule"] + [_tex_row(r, cols2) for r in base_rows]
           if base_rows else [])
        + [r"\bottomrule", r"\end{tabular}"])
    # v3 — resource-grouped with multicolumn headers.
    cols3 = ["phase", "tok_in_M", "tok_out_M", "llm_usd", "wall_h", "core_h",
             "compute_usd", "total_usd"]
    v["v3"] = "\n".join(
        [r"\begin{tabular}{@{}lrrrrrrr@{}}", r"\toprule",
         r" & \multicolumn{3}{c}{LLM / API} & \multicolumn{3}{c}{Compute} & \\",
         r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
         r"Phase & tok in (M) & tok out (M) & \$ & wall (h) & core-h & \$ "
         r"& Total (\$) \\",
         r"\midrule"]
        + [_tex_row(r, cols3) for r in method_rows]
        + [r"\midrule", _tex_row(total, cols3)]
        + ([r"\midrule"] + [_tex_row(r, cols3) for r in base_rows]
           if base_rows else [])
        + [r"\bottomrule", r"\end{tabular}"])
    return v


def write_all() -> dict:
    c = collect_costs()
    cfg.STATE.mkdir(parents=True, exist_ok=True)
    (cfg.STATE / "cost_breakdown.json").write_text(json.dumps(c, indent=2))
    cfg.FIGURES.mkdir(parents=True, exist_ok=True)
    for name, tex in latex_tables(c).items():
        (cfg.FIGURES / f"table_cost_breakdown_{name}.tex").write_text(tex + "\n")
    return c


if __name__ == "__main__":
    c = write_all()
    print("\n".join(markdown_table(c)))
    print(f"\nwrote {cfg.STATE / 'cost_breakdown.json'} + "
          f"{cfg.FIGURES}/table_cost_breakdown_v{{1,2,3}}.tex")

#!/usr/bin/env python3
"""Visualize a design-DB skills run (`--agent-backend opencode --design-db-skills`).

Reads only on-disk run artifacts — design_db provenance/metrics/manifest, agent_evals.jsonl,
eval_N snapshot times, _deadline_epoch — and emits one self-contained HTML report (inline SVG,
native tooltips, zero dependencies): per-slot Pareto fronts (area x AIG depth) colored by
source tag, the main agent's selections, admission timelines with running best, agent activity
lanes, and (if measure_db_compositions.py ran on the run first) the measured full-circuit
composition space.

Usage: python visualize_db_run.py <run_dir> [-o out.html]
"""
import datetime as dt
import json
import sys
from pathlib import Path

UTC = dt.timezone.utc

# source tag -> (color, label)
PALETTE = ["#2563eb", "#ea580c", "#9333ea", "#0d9488", "#ca8a04"]
ORIG_COLOR = "#111111"
SEL_COLOR = "#dc2626"
BEST_COLOR = "#10b981"


def load_run(run_dir: Path):
    db = run_dir / "workspace" / "design_db" / "v1"
    man = json.loads((db / "manifest.json").read_text())
    slots = {}
    for name, entry in man["slots"].items():
        sdir = db / entry["spec_key"]
        designs = []
        for d in (sdir / "designs").iterdir():
            p = json.loads((d / "provenance.json").read_text())
            m = json.loads((d / "metrics.json").read_text())
            t = dt.datetime.fromisoformat(p["created"]).replace(tzinfo=UTC).timestamp()
            designs.append({
                "id": d.name, "source": p["source"], "t": t,
                "area": m["transistors"]["metrics"]["transistors_heavy"],
                "depth": m["aig"]["metrics"]["aig_depth"],
                "nodes": m["aig"]["metrics"]["aig_nodes"],
            })
        designs.sort(key=lambda x: x["t"])
        slots[name] = {"designs": designs, "selected": entry.get("selected_id"),
                       "objective": entry.get("objective"), "metric": entry.get("metric")}
    evals = [json.loads(l) for l in (run_dir / "agent_evals.jsonl").read_text().splitlines()]
    eval_times = []
    for i in range(1, len(evals) + 1):
        p = run_dir / f"eval_{i}"
        eval_times.append(p.stat().st_mtime if p.exists() else None)
    deadline = None
    dl = run_dir / "_deadline_epoch"
    if dl.exists():
        deadline = float(dl.read_text().strip())
    result = json.loads((run_dir / "result.json").read_text()) if (run_dir / "result.json").exists() else {}
    return slots, evals, eval_times, deadline, result


def pareto(points):
    """Non-dominated set for (area, depth), both minimized; returned sorted by area."""
    pts = sorted(points, key=lambda p: (p["area"], p["depth"]))
    front, best_d = [], float("inf")
    for p in pts:
        if p["depth"] < best_d:
            front.append(p)
            best_d = p["depth"]
    return front


def lin(lo, hi, a, b):
    span = (hi - lo) or 1.0
    return lambda v: a + (v - lo) / span * (b - a)


def ticks(lo, hi, n=5):
    import math
    span = (hi - lo) or 1.0
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    t0 = math.ceil(lo / step) * step
    out = []
    while t0 <= hi + 1e-9:
        out.append(round(t0, 6))
        t0 += step
    return out


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_axes(x0, y0, x1, y1, xt, yt, sx, sy, xlabel, ylabel, xfmt=str):
    s = [f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" class="ax"/>',
         f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" class="ax"/>']
    for v in xt:
        px = sx(v)
        s.append(f'<line x1="{px:.1f}" y1="{y1}" x2="{px:.1f}" y2="{y1 + 4}" class="ax"/>'
                 f'<text x="{px:.1f}" y="{y1 + 16}" class="tick" text-anchor="middle">{xfmt(v)}</text>')
    for v in yt:
        py = sy(v)
        s.append(f'<line x1="{x0 - 4}" y1="{py:.1f}" x2="{x0}" y2="{py:.1f}" class="ax"/>'
                 f'<text x="{x0 - 7}" y="{py + 3.5:.1f}" class="tick" text-anchor="end">{xfmt(v)}</text>'
                 f'<line x1="{x0}" y1="{py:.1f}" x2="{x1}" y2="{py:.1f}" class="grid"/>')
    s.append(f'<text x="{(x0 + x1) / 2}" y="{y1 + 32}" class="lab" text-anchor="middle">{xlabel}</text>')
    s.append(f'<text x="{x0 - 44}" y="{(y0 + y1) / 2}" class="lab" text-anchor="middle" '
             f'transform="rotate(-90 {x0 - 44} {(y0 + y1) / 2})">{ylabel}</text>')
    return "".join(s)


def load_session_spans(run_dir: Path):
    """Exact session spans from the recovered `opencode export` files (parent +
    opencode_child_*.json): {path-stem: (t0, t1, n_msgs, raw_text)}. Empty if no exports."""
    out = {}
    for f in sorted(run_dir.glob("opencode_child_*.json")) + [run_dir / "opencode_session.json"]:
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        times = [m["info"]["time"]["created"] for m in d.get("messages", [])
                 if m.get("info", {}).get("time", {}).get("created")]
        if times:
            out[f.name] = (min(times) / 1000, max(times) / 1000, len(d.get("messages", [])),
                           f.read_text())
    return out


def color_map(slots):
    tags = []
    for s in slots.values():
        for d in s["designs"]:
            if d["source"] != "original" and d["source"] not in tags:
                tags.append(d["source"])
    return {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(tags)}


def pareto_panel(name, slot, colors, W=470, H=340):
    ds = slot["designs"]
    x0, y0, x1, y1 = 62, 16, W - 14, H - 46
    ax = [d["area"] for d in ds]
    dx = [d["depth"] for d in ds]
    padx = (max(ax) - min(ax)) * 0.08 or 5
    pady = (max(dx) - min(dx)) * 0.10 or 1
    sx = lin(min(ax) - padx, max(ax) + padx, x0, x1)
    sy = lin(min(dx) - pady, max(dx) + pady, y1, y0)   # smaller depth = lower = better -> down
    out = [svg_axes(x0, y0, x1, y1, ticks(min(ax), max(ax)), ticks(min(dx), max(dx)),
                    sx, sy, "area (transistors, heavy est.)", "delay (AIG depth)")]
    front = pareto(ds)
    pl = " ".join(f"{sx(p['area']):.1f},{sy(p['depth']):.1f}" for p in front)
    out.append(f'<polyline points="{pl}" fill="none" stroke="{BEST_COLOR}" stroke-width="1.6" '
               f'stroke-dasharray="5 3" opacity="0.9"/>')
    sel = slot["selected"]
    for d in ds:
        px, py = sx(d["area"]), sy(d["depth"])
        tip = (f"{d['id']}\nsource: {d['source']}\narea {d['area']}  depth {d['depth']}  "
               f"nodes {d['nodes']}\n{dt.datetime.fromtimestamp(d['t'], UTC).strftime('%H:%M:%S')} UTC")
        title = f"<title>{esc(tip)}</title>"
        if d["source"] == "original":
            out.append(f'<path d="M {px} {py - 6} L {px + 6} {py} L {px} {py + 6} L {px - 6} {py} Z" '
                       f'fill="{ORIG_COLOR}" opacity="0.9">{title}</path>')
        else:
            c = colors[d["source"]]
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{c}" fill-opacity="0.75" '
                       f'stroke="white" stroke-width="0.8">{title}</circle>')
        if d["id"] == sel:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9.5" fill="none" '
                       f'stroke="{SEL_COLOR}" stroke-width="2.2">{title}</circle>'
                       f'<text x="{px + 12:.1f}" y="{py - 9:.1f}" class="selab">selected</text>')
    orig = next(d for d in ds if d["source"] == "original")
    best = min(ds, key=lambda d: d["area"])
    sub = (f"{len(ds)} designs · original {orig['area']} → best {best['area']} "
           f"({(best['area'] / orig['area'] - 1) * 100:+.1f}%)")
    head = (f'<div class="ptitle">slot <code>{esc(name)}</code>'
            f'<span class="psub">{esc(sub)}</span></div>')
    return (f'<div class="panel">{head}<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg></div>')


def evolution_panel(name, slot, colors, t0, t_end, evals_at, W=960, H=230):
    ds = slot["designs"]
    x0, y0, x1, y1 = 62, 14, W - 14, H - 44
    a = [d["area"] for d in ds]
    pad = (max(a) - min(a)) * 0.12 or 5
    sx = lin(0, (t_end - t0) / 60, x0, x1)
    sy = lin(min(a) - pad, max(a) + pad, y1, y0)
    out = [svg_axes(x0, y0, x1, y1, ticks(0, (t_end - t0) / 60), ticks(min(a), max(a), 4),
                    sx, sy, "minutes since run start", "area (transistors)")]
    orig = next(d for d in ds if d["source"] == "original")
    out.append(f'<line x1="{x0}" y1="{sy(orig["area"]):.1f}" x2="{x1}" y2="{sy(orig["area"]):.1f}" '
               f'stroke="{ORIG_COLOR}" stroke-dasharray="2 4" opacity="0.55"/>'
               f'<text x="{x1 - 4}" y="{sy(orig["area"]) - 4:.1f}" class="tick" text-anchor="end">'
               f'seeded original {orig["area"]}</text>')
    # running best step line
    best, px_prev, py_prev = None, None, None
    step = []
    for d in ds:
        tmin = (d["t"] - t0) / 60
        if best is None or d["area"] < best:
            if best is not None:
                step.append(f"{sx(tmin):.1f},{py_prev:.1f}")
            best = d["area"]
            step.append(f"{sx(tmin):.1f},{sy(best):.1f}")
            py_prev = sy(best)
    step.append(f"{sx((t_end - t0) / 60):.1f},{py_prev:.1f}")
    out.append(f'<polyline points="{" ".join(step)}" fill="none" stroke="{BEST_COLOR}" '
               f'stroke-width="1.8" opacity="0.9"/>')
    for d in ds:
        px, py = sx((d["t"] - t0) / 60), sy(d["area"])
        tip = f"{d['id']}\nsource: {d['source']}\narea {d['area']}  depth {d['depth']}"
        c = ORIG_COLOR if d["source"] == "original" else colors[d["source"]]
        out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{c}" fill-opacity="0.8" '
                   f'stroke="white" stroke-width="0.8"><title>{esc(tip)}</title></circle>')
        if d["id"] == slot["selected"]:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="8.5" fill="none" '
                       f'stroke="{SEL_COLOR}" stroke-width="2"/>')
    for te, cost in evals_at:
        px = sx((te - t0) / 60)
        out.append(f'<line x1="{px:.1f}" y1="{y0}" x2="{px:.1f}" y2="{y1}" stroke="#64748b" '
                   f'stroke-dasharray="3 3"><title>full-design eval: {cost} transistors</title></line>')
    px = sx((t_end - t0) / 60)
    out.append(f'<line x1="{px:.1f}" y1="{y0}" x2="{px:.1f}" y2="{y1}" stroke="{SEL_COLOR}" '
               f'stroke-width="1.6"><title>wall-clock kill</title></line>')
    head = f'<div class="ptitle">admissions over time — <code>{esc(name)}</code></div>'
    return (f'<div class="panel wide">{head}<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg></div>')


def composition_panel(comp, W=620, H=380):
    res = comp["results"]
    sp = comp.get("starting_point")
    evs = comp.get("evaluations") or []
    pts = ([{"area": r["area"], "depth": r["depth"]} for r in res]
           + ([sp] if sp and not evs else [])
           + [{"area": e["area"], "depth": e["depth"]} for e in evs])
    x0, y0, x1, y1 = 62, 16, W - 14, H - 46
    ax = [q["area"] for q in pts]; dx = [q["depth"] for q in pts]
    padx = (max(ax) - min(ax)) * 0.08 or 5
    pady = (max(dx) - min(dx)) * 0.14 or 1
    sx = lin(min(ax) - padx, max(ax) + padx, x0, x1)
    sy = lin(min(dx) - pady, max(dx) + pady, y1, y0)
    out = [svg_axes(x0, y0, x1, y1, ticks(min(ax), max(ax)), ticks(min(dx), max(dx), 4),
                    sx, sy, "full-circuit area (transistors)", "full-circuit delay (AIG depth)")]
    front = pareto(pts)
    pl = " ".join(f"{sx(q['area']):.1f},{sy(q['depth']):.1f}" for q in front)
    out.append(f'<polyline points="{pl}" fill="none" stroke="{BEST_COLOR}" stroke-width="1.6" '
               f'stroke-dasharray="5 3" opacity="0.9"/>')
    for r in res:
        px, py = sx(r["area"]), sy(r["depth"])
        picks = "\n".join(f"{k}: {v}" for k, v in r["picks"].items())
        tip = f"area {r['area']}  depth {r['depth']}\n{picks}"
        if r.get("baseline"):
            out.append(f'<path d="M {px} {py - 6} L {px + 6} {py} L {px} {py + 6} L {px - 6} {py} Z" '
                       f'fill="none" stroke="{ORIG_COLOR}" stroke-width="2"><title>seeded originals\n'
                       f'{esc(tip)}</title></path>'
                       f'<text x="{px + 9:.1f}" y="{py + 4:.1f}" class="tick">originals {r["area"]}</text>')
        else:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.5" fill="#94a3b8" fill-opacity="0.7" '
                       f'stroke="white" stroke-width="0.8"><title>{esc(tip)}</title></circle>')
        if r.get("selected"):
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="10" fill="none" stroke="{SEL_COLOR}" '
                       f'stroke-width="2.2"/><text x="{px + 12:.1f}" y="{py - 8:.1f}" class="selab">'
                       f'agent selection {r["area"]}/{r["depth"]}</text>')
    if evs:
        labeled = set()
        for e in evs:
            px, py = sx(e["area"]), sy(e["depth"])
            rec = f"\nrecorded cost {e['recorded_cost']}" if e.get("recorded_cost") is not None else ""
            out.append(f'<rect x="{px - 5:.1f}" y="{py - 5:.1f}" width="10" height="10" '
                       f'fill="#334155" fill-opacity="0.9" stroke="white" stroke-width="0.8">'
                       f'<title>main-agent eval {e["eval_index"]}\narea {e["area"]}  '
                       f'depth {e["depth"]}{rec}</title></rect>')
            if (e["area"], e["depth"]) not in labeled:
                labeled.add((e["area"], e["depth"]))
                ids = ",".join(str(x["eval_index"]) for x in evs
                               if (x["area"], x["depth"]) == (e["area"], e["depth"]))
                out.append(f'<text x="{px + 9:.1f}" y="{py + 4:.1f}" class="tick">eval {ids} '
                           f'({e["area"]})</text>')
    elif sp:
        px, py = sx(sp["area"]), sy(sp["depth"])
        out.append(f'<path d="M {px} {py - 7} L {px + 7} {py} L {px} {py + 7} L {px - 7} {py} Z" '
                   f'fill="{ORIG_COLOR}"><title>starting point (in-run evals)\narea {sp["area"]}  '
                   f'depth {sp["depth"]}</title></path>'
                   f'<text x="{px + 10:.1f}" y="{py + 4:.1f}" class="tick">starting point {sp["area"]}</text>')
    head = ('<div class="ptitle">full-circuit composition space'
            f'<span class="psub">{len(res)} measured splice combinations of the per-slot fronts '
            '(offline recompiles, forced via pin); squares = the main agent\'s actual evals</span></div>')
    return (f'<div class="panel">{head}<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg></div>')


def evals_over_time_panel(evals, eval_times, comp, t0, t_end, W=960, H=230):
    """The main agent's ./evaluate_design calls: recorded cost over time, with the measured
    offline composition references when available."""
    pts = []
    measured = {e["eval_index"]: e for e in (comp.get("evaluations") or [])} if comp else {}
    for i, (e, t) in enumerate(zip(evals, eval_times), start=1):
        if t is None:
            continue
        m = measured.get(i)
        area = (m or {}).get("area", e.get("cost_value"))
        if area is None:
            continue
        pts.append({"i": i, "t": t, "area": area, "rec": e.get("cost_value"),
                    "depth": (m or {}).get("depth"), "passed": e.get("passed")})
    refs = []
    if comp:
        seld = next((r for r in comp["results"] if r.get("selected")), None)
        if seld:
            refs.append((seld["area"], f"selected composition (measured offline) {seld['area']}"))
    ys = [q["area"] for q in pts] + [r[0] for r in refs]
    if not ys:
        return ""
    x0, y0, x1, y1 = 62, 14, W - 14, H - 44
    pad = (max(ys) - min(ys)) * 0.15 or 10
    sx = lin(0, (t_end - t0) / 60, x0, x1)
    sy = lin(min(ys) - pad, max(ys) + pad, y1, y0)
    out = [svg_axes(x0, y0, x1, y1, ticks(0, (t_end - t0) / 60), ticks(min(ys), max(ys), 4),
                    sx, sy, "minutes since run start", "area (transistors)")]
    for area, label in refs:
        out.append(f'<line x1="{x0}" y1="{sy(area):.1f}" x2="{x1}" y2="{sy(area):.1f}" '
                   f'stroke="{BEST_COLOR}" stroke-dasharray="5 3" opacity="0.9"/>'
                   f'<text x="{x1 - 4}" y="{sy(area) - 5:.1f}" class="tick" text-anchor="end">'
                   f'{esc(label)}</text>')
    for q in pts:
        px, py = sx((q["t"] - t0) / 60), sy(q["area"])
        extra = f"  depth {q['depth']}" if q.get("depth") is not None else ""
        tip = f"eval {q['i']}\narea {q['area']}{extra}\npassed: {q.get('passed')}"
        out.append(f'<rect x="{px - 5:.1f}" y="{py - 5:.1f}" width="10" height="10" '
                   f'fill="#334155" fill-opacity="0.9" stroke="white" stroke-width="0.8">'
                   f'<title>{esc(tip)}</title></rect>'
                   f'<text x="{px + 8:.1f}" y="{py - 8:.1f}" class="tick">eval {q["i"]}</text>')
    px = sx((t_end - t0) / 60)
    out.append(f'<line x1="{px:.1f}" y1="{y0}" x2="{px:.1f}" y2="{y1}" stroke="{SEL_COLOR}" '
               f'stroke-width="1.6"><title>wall-clock kill</title></line>')
    head = ('<div class="ptitle">full-circuit evals over time'
            '<span class="psub">the main agent\'s ./evaluate_design calls'
            + (' · squares use the measured snapshot recompiles' if measured else '')
            + '</span></div>')
    return (f'<div class="panel wide">{head}<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg></div>')


def lanes_panel(slots, colors, t0, t_end, evals_at, W=960, sessions=None):
    sessions = sessions or {}
    clip = lambda t: max(0.0, min(t, (t_end - t0) / 60))
    parent = sessions.get("opencode_session.json")
    parent_span = (clip((parent[0] - t0) / 60), clip((parent[1] - t0) / 60)) if parent \
        else (0, (t_end - t0) / 60)
    exact = bool(sessions)
    rows = [("main agent (parent session)", ORIG_COLOR, [parent_span],
             [((te - t0) / 60, f"full-design eval {c}") for te, c in evals_at])]
    child_spans = {n: v for n, v in sessions.items() if n.startswith("opencode_child_")}
    for name, slot in slots.items():
        for tag in {d["source"] for d in slot["designs"]} - {"original"}:
            ts = [(d["t"] - t0) / 60 for d in slot["designs"] if d["source"] == tag]
            span = (min(ts), max(ts))
            match = next((v for v in child_spans.values() if tag in v[3]), None)
            if match:                       # exact session window from the recovered export
                span = (clip((match[0] - t0) / 60), clip((match[1] - t0) / 60))
            rows.append((f"{tag}  →  {name}", colors[tag], [span],
                         [(t, "gated admission") for t in ts]))
    lane_h, top, left = 34, 12, 250
    H = top + lane_h * len(rows) + 40
    x0, x1 = left, W - 14
    sx = lin(0, (t_end - t0) / 60, x0, x1)
    out = []
    for v in ticks(0, (t_end - t0) / 60):
        px = sx(v)
        out.append(f'<line x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{H - 34}" class="grid"/>'
                   f'<text x="{px:.1f}" y="{H - 20}" class="tick" text-anchor="middle">{v:g}</text>')
    for i, (label, color, spans, marks) in enumerate(rows):
        cy = top + lane_h * i + lane_h / 2
        out.append(f'<text x="{left - 10}" y="{cy + 4:.1f}" class="lanelab" text-anchor="end">{esc(label)}</text>')
        for lo, hi in spans:
            out.append(f'<rect x="{sx(lo):.1f}" y="{cy - 7:.1f}" width="{max(sx(hi) - sx(lo), 2):.1f}" '
                       f'height="14" rx="7" fill="{color}" opacity="0.18"/>')
        for t, tip in marks:
            out.append(f'<line x1="{sx(t):.1f}" y1="{cy - 7:.1f}" x2="{sx(t):.1f}" y2="{cy + 7:.1f}" '
                       f'stroke="{color}" stroke-width="2"><title>{esc(tip)} @ {t:.1f} min</title></line>')
    px = sx((t_end - t0) / 60)
    out.append(f'<line x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{H - 34}" stroke="{SEL_COLOR}" '
               f'stroke-width="1.6"/><text x="{px - 4:.1f}" y="{top + 10}" class="tick" '
               f'text-anchor="end" fill="{SEL_COLOR}">wall-clock kill</text>')
    out.append(f'<text x="{(x0 + x1) / 2}" y="{H - 6}" class="lab" text-anchor="middle">minutes since run start</text>')
    sub = ("child spans = exact session windows (recovered exports)" if exact
           else "child spans = first→last gated admission")
    head = f'<div class="ptitle">who worked when <span class="psub">({sub})</span></div>'
    return (f'<div class="panel wide">{head}<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg></div>')


def build_story(slots, colors, comp):
    tags = list(colors)
    n_adm = sum(1 for s in slots.values() for d in s["designs"] if d["source"] != "original")
    story = (f"The main agent seeded {len(slots)} slot(s) and delegated to {len(tags)} subagent "
             f"worker(s) ({', '.join(f'<code>{esc(t)}</code>' for t in tags)}), which pushed "
             f"{n_adm} designs through spire's verification gate. Red rings mark the main "
             f"agent's recorded selections.")
    if comp:
        sp = comp.get("starting_point")
        seld = next((r for r in comp["results"] if r.get("selected")), None)
        base = next((r for r in comp["results"] if r.get("baseline")), None)
        if sp and seld:
            story += (f" The composed selection measures <b>{seld['area']} transistors / "
                      f"depth {seld['depth']}</b> vs the starting point's "
                      f"{sp['area']}/{sp['depth']} ({(seld['area'] / sp['area'] - 1) * 100:+.1f}% area)."
                      + (f" Splicing just the seeded originals measures {base['area']}/{base['depth']}"
                         f" — the decomposition itself contributes." if base else ""))
    else:
        story += (" Run <code>measure_db_compositions.py &lt;run_dir&gt;</code> first to add the "
                  "full-circuit composition-space panel (measured splice combinations).")
    return story


def generate(run_dir: Path, out_path: Path) -> Path:
    slots, evals, eval_times, deadline, result = load_run(run_dir)
    colors = color_map(slots)
    all_t = [d["t"] for s in slots.values() for d in s["designs"]]
    all_t += [t for t in eval_times if t]
    t0 = min(all_t)
    t_end = deadline or max(all_t)
    evals_at = [(t, e.get("cost_value")) for t, e in zip(eval_times, evals) if t]
    comp = None
    cs = run_dir / "composition_space.json"
    if cs.exists():
        comp = json.loads(cs.read_text())

    legend = "".join(
        f'<span class="chip"><span class="dot" style="background:{c}"></span>{esc(t)}</span>'
        for t, c in colors.items())
    legend = (f'<span class="chip"><span class="dot" style="background:{ORIG_COLOR}"></span>original (seed)</span>'
              + legend +
              f'<span class="chip"><span class="dot" style="background:{BEST_COLOR}"></span>Pareto front / running best</span>'
              f'<span class="chip"><span class="dot" style="border:2px solid {SEL_COLOR};background:none"></span>selected by main agent</span>')

    rows = []
    for name, s in slots.items():
        orig = next(d for d in s["designs"] if d["source"] == "original")
        seld = next((d for d in s["designs"] if d["id"] == s["selected"]), None)
        sel_txt = f"{seld['area']} / {seld['depth']}" if seld else "—"
        delta = f"{(seld['area'] / orig['area'] - 1) * 100:+.1f}%" if seld else "—"
        rows.append(f"<tr><td><code>{esc(name)}</code></td><td>{len(s['designs'])}</td>"
                    f"<td>{esc(s['objective'])} / {esc(s['metric'])}</td>"
                    f"<td>{orig['area']} / {orig['depth']}</td><td>{sel_txt}</td><td>{delta}</td>"
                    f"<td><code>{esc(s['selected'] or '—')}</code></td></tr>")

    bench = run_dir.parent.parent.name
    model = run_dir.parent.name
    n_adm = sum(1 for s in slots.values() for d in s["designs"] if d["source"] != "original")
    meta = (f"model {model} · wall clock ≈ {(t_end - t0) / 60:.0f} min · {len(slots)} slots · "
            f"{n_adm} gated admissions · {len(evals)} in-run full-design evals")
    story = build_story(slots, colors, comp)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Skills run — {esc(bench)}</title><style>
body {{ font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; color: #1e293b; margin: 24px auto; max-width: 1020px; padding: 0 16px; }}
h1 {{ font-size: 21px; margin: 0 0 2px; }} .meta {{ color: #64748b; margin-bottom: 14px; }}
.story {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 16px; margin: 14px 0; }}
.panels {{ display: flex; gap: 16px; flex-wrap: wrap; }}
.panel {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px 4px; margin: 8px 0; }}
.panel.wide {{ width: 100%; box-sizing: border-box; overflow-x: auto; }}
.ptitle {{ font-weight: 600; margin-bottom: 4px; }} .psub {{ color: #64748b; font-weight: 400; margin-left: 10px; font-size: 12.5px; }}
.ax {{ stroke: #94a3b8; stroke-width: 1; }} .grid {{ stroke: #f1f5f9; stroke-width: 1; }}
.tick {{ font-size: 10.5px; fill: #64748b; }} .lab {{ font-size: 12px; fill: #475569; }}
.lanelab {{ font-size: 12px; fill: #334155; }} .selab {{ font-size: 11px; fill: {SEL_COLOR}; font-weight: 600; }}
.chip {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid #e2e8f0; border-radius: 999px; padding: 2px 10px; margin: 2px 6px 2px 0; font-size: 12.5px; }}
.dot {{ width: 10px; height: 10px; border-radius: 999px; display: inline-block; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }} td, th {{ border-bottom: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }}
code {{ background: #f1f5f9; border-radius: 4px; padding: 1px 5px; font-size: 12px; }}
.foot {{ color: #94a3b8; font-size: 12px; margin-top: 16px; }}
</style></head><body>
<h1>Design-DB skills run — {esc(bench)}</h1>
<div class="meta">{esc(meta)}</div>
<div class="story"><b>The story.</b> {story}</div>
<div>{legend}</div>
<div class="panels">{"".join(pareto_panel(n, s, colors) for n, s in slots.items())}</div>
{"".join(evolution_panel(n, s, colors, t0, t_end, evals_at) for n, s in slots.items())}
{composition_panel(comp) if comp else ""}
{evals_over_time_panel(evals, eval_times, comp, t0, t_end)}
{lanes_panel(slots, colors, t0, t_end, evals_at, sessions=load_session_spans(run_dir))}
<div class="panel wide"><div class="ptitle">selections</div>
<table><tr><th>slot</th><th>designs</th><th>objective/metric</th><th>original a/d</th>
<th>selected a/d</th><th>Δ area</th><th>selected id</th></tr>{"".join(rows)}</table></div>
<div class="foot">source: {esc(str(run_dir))} — design_db provenance + metrics, agent_evals.jsonl,
eval_N snapshot times, _deadline_epoch. Hover any point for id/source/metrics.</div>
</body></html>"""
    out_path.write_text(html)
    return out_path


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", help="a run directory (the one holding agent_evals.jsonl)")
    ap.add_argument("-o", "--out", default=None, help="output HTML (default: <run_dir>/visualization.html)")
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    out = Path(args.out) if args.out else run_dir / "visualization.html"
    print(generate(run_dir, out))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Combine per-benchmark table.json files into ONE generalization table.

Each run_all.py run writes table.json as {language: {phase: {area, delay, adp,
n}}}. This merges several of those side by side -- one column group per
benchmark, rows shared -- and emits Markdown and LaTeX.

    make_generalization_table.py                      # the defaults below
    make_generalization_table.py -o /tmp/gen \\
        --source "PDPU-16 comb=artifacts/pdpu_run/data/<run>/table.json" \\
        --source "PDPU-16 pipe=.../table_dummy.json"

A source whose file is missing is dropped with a warning, so a partially
finished suite still produces a table.
"""
import argparse
import json
from pathlib import Path

REPO = Path("/workspaces/rtl_scout")

# label -> table.json. Order here is the column order in the output.
# fpadd-16 is deliberately excluded (its run data remains under data/fpadd-glm_*).
DEFAULT_SOURCES = [
    ("fpadd-32",
     REPO / "artifacts/pdpu_run/data/fpadd32-glm_20260812_143328/table.json"),
    ("PDPU-16 (comb.)",
     REPO / "artifacts/pdpu_run/data/pdpu16-glm_20260807_074125/table.json"),
    ("PDPU-16 (pipelined)",
     REPO / "artifacts/pdpu_run/data/pdpu16p-glm_20260808_181936/table.json"),
]

# Row order. Rows absent from every source are dropped.
ROWS = [
    "Starting design",
    "Phase 1 (agent)",
    "Phase 2 (+decorators)",
    "Phase 4 (deepsyn refine)",
    "From scratch, equal compute",
    "From scratch, 2x effort",
]
# run_all writes the 2x row with a unicode multiplication sign in some runs
ROW_ALIASES = {"From scratch, 2x effort": ["From scratch, 2× effort"]}

# Display names (the keys above must stay as run_all writes them in table.json).
ROW_LABELS = {"Phase 4 (deepsyn refine)": "RTLScout: Phase 4 (deepsyn refine)"}
# A rule is drawn immediately BELOW this row, splitting the pipeline's own
# results from the from-scratch baselines it is compared against.
RULE_AFTER = "Phase 4 (deepsyn refine)"

METRICS = [("area", "Area", 1, 1.0),        # key, header, decimals, scale
           ("delay", "Delay", 0, 1.0),
           ("adp", "ADP", 1, 1e-3)]

LANG = "spirehdl"


def load(sources):
    """[(label, {phase: metrics})] for every source whose file exists."""
    out = []
    for label, path in sources:
        p = Path(path)
        if not p.exists():
            print(f"  WARNING: {label}: {p} missing — column dropped")
            continue
        data = json.loads(p.read_text())
        # table.json is {lang: {phase: {...}}}; fall back to a flat {phase: ...}
        phases = data.get(LANG, data)
        out.append((label, phases))
    return out


def _get(phases, row):
    if row in phases:
        return phases[row]
    for alt in ROW_ALIASES.get(row, []):
        if alt in phases:
            return phases[alt]
    return None


def active_rows(cols):
    return [r for r in ROWS if any(_get(ph, r) for _, ph in cols)]


def cells(cols):
    """(rows, text[r][c], bold[r][c]) — bold marks the best value per column.

    Every metric here is lower-is-better. Ties are decided on the RENDERED
    string, so two cells that print the same minimum are both bold rather than
    one winning on invisible digits.
    """
    rows = active_rows(cols)
    raw, txt = [], []
    for r in rows:
        rv, rt = [], []
        for _, ph in cols:
            m = _get(ph, r)
            for k, _h, dec, scale in METRICS:
                v = None if not m or m.get(k) is None else m[k] * scale
                rv.append(v)
                rt.append("--" if v is None else f"{v:.{dec}f}")
        raw.append(rv)
        txt.append(rt)
    bold = [[False] * len(raw[0]) for _ in rows] if rows else []
    for c in range(len(cols) * len(METRICS)):
        present = [i for i in range(len(rows)) if raw[i][c] is not None]
        if not present:
            continue
        best_i = min(present, key=lambda i: raw[i][c])
        for i in present:
            if txt[i][c] == txt[best_i][c]:
                bold[i][c] = True
    return rows, txt, bold


def to_markdown(cols):
    rows, txt, bold = cells(cols)
    head = "| phase |" + "".join(
        f" {lbl} {h} |" for lbl, _ in cols for _, h, _, _ in METRICS)
    sep = "|---|" + "---|" * (len(cols) * len(METRICS))
    lines = [head, sep]
    for i, r in enumerate(rows):
        row = "".join(f" {'**' + t + '**' if b else t} |"
                      for t, b in zip(txt[i], bold[i]))
        lines.append(f"| {ROW_LABELS.get(r, r)} |{row}")
        if r == RULE_AFTER and i < len(rows) - 1:
            lines.append("|---|" + "---|" * (len(cols) * len(METRICS)))
    lines.append("")
    lines.append("Area in um^2, delay in ps, ADP in 10^3 um^2*ps. Each cell is an "
                 "independent best over that phase's evaluated designs; **bold** "
                 "is the best value in that column.")
    return "\n".join(lines) + "\n"


def to_latex(cols):
    rows, txt, bold = cells(cols)
    ncol = len(METRICS)
    spec = "@{}l" + "".join(["c" * ncol] * len(cols)) + "@{}"
    out = [r"\begin{tabular}{" + spec + "}", r"\toprule"]
    # benchmark group header
    grp = "Phase" + "".join(
        f" & \\multicolumn{{{ncol}}}{{c}}{{{lbl}}}" for lbl, _ in cols)
    out.append(grp + r" \\")
    starts = [2 + i * ncol for i in range(len(cols))]
    out.append("".join(f"\\cmidrule(lr){{{s}-{s + ncol - 1}}}" for s in starts))
    sub = "" + "".join(f" & {h}" for _ in cols for _, h, _, _ in METRICS)
    out.append(sub + r" \\")
    out.append(r"\midrule")
    for i, r in enumerate(rows):
        label = ROW_LABELS.get(r, r).replace("2x effort", r"2$\times$ effort")
        row = "".join(" & " + (f"\\textbf{{{t}}}" if b else t)
                      for t, b in zip(txt[i], bold[i]))
        out.append(f"{label}{row} \\\\")
        if r == RULE_AFTER and i < len(rows) - 1:
            out.append(r"\midrule")
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", type=Path,
                    default=REPO / "artifacts/pdpu_run/data/generalization_table",
                    help="output stem; writes <stem>.md and <stem>.tex")
    ap.add_argument("--source", action="append", default=None,
                    metavar="LABEL=PATH", help="repeatable; overrides the defaults")
    ap.add_argument("--paper-out", type=Path, default=None,
                    help="also write a complete \\begin{table} with caption/label "
                         "here, for \\input{} into the paper")
    ap.add_argument("--caption", default=None, help="caption for --paper-out")
    ap.add_argument("--label", default="tab:generalization-circuits")
    args = ap.parse_args()

    if args.source:
        sources = []
        for s in args.source:
            label, _, path = s.partition("=")
            sources.append((label, Path(path)))
    else:
        sources = DEFAULT_SOURCES

    cols = load(sources)
    if not cols:
        raise SystemExit("no readable sources — nothing to write")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    md, tex = args.output.with_suffix(".md"), args.output.with_suffix(".tex")
    md.write_text(to_markdown(cols))
    tex.write_text(to_latex(cols))
    print(f"columns: {', '.join(l for l, _ in cols)}")
    print(f"wrote {md}\nwrote {tex}")

    if args.paper_out:
        cap = args.caption or (
            "Generalization to other circuits: best per-phase area "
            "(\\textmu m$^2$), delay (ps) and area-delay product "
            "($10^3$\\,\\textmu m$^2\\cdot$ps) for each benchmark, all Spire, "
            "evaluated at a common set of target delays. Each cell is an "
            "independent best over that phase's evaluated designs; "
            "\\textbf{bold} marks the best value per column.")
        body = [
            "% Generated by artifacts/pdpu_run/make_generalization_table.py "
            "-- do not edit by hand.",
            "% Host preamble needs: \\usepackage{booktabs}",
            "\\begin{table}[t]", "\\centering", f"\\caption{{{cap}}}",
            f"\\label{{{args.label}}}", "\\resizebox{\\columnwidth}{!}{%",
            to_latex(cols).rstrip(), "}", "\\end{table}", ""]
        args.paper_out.write_text("\n".join(body))
        print(f"wrote {args.paper_out}")


if __name__ == "__main__":
    main()

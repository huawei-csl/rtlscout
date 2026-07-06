#!/usr/bin/env python3
"""Generate all prompt previews for review, for each HDL:

  - the OpenCode AGENTS.md  (core.opencode_backend.render_agents_md)  -> _AGENTS_preview_<lang>.md
  - the react-loop system prompt (core.prompts.build_*_system_prompt)  -> _react_prompt_<lang>.txt

6 files total (3 HDLs x 2 backends), written next to this script (metadocuments/). These are
review-only scratch artifacts (git-ignored). Run from anywhere:

    python metadocuments/gen_prompt_previews.py

Must run in an environment with the toolchain deps importable (the rtlscout container), since
core.prompts imports tech_eval/spirehdl.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

# One representative benchmark per HDL (+ a cost metric that exercises the prompt).
CASES = [
    ("spirehdl", "benchmarks/fpmul_f16", "area"),
    ("verilog",  "benchmarks/dr_rtl/fifo", "yosys_cells"),
    ("amaranth", "benchmarks/simple_adder", "transistors"),
]

# A short sample seed so the previews also show the seed/lessons section.
SAMPLE_SEED = ("(sample) Previous best: 12345 area. A prior agent used a carry-save adder tree; "
               "the final CPA dominated area — try a prefix adder there next.")


def _react_prompt(language, description, metric_name, cost_metric):
    """Render the react-loop system prompt for one HDL (mirrors what RTLAgent.run builds)."""
    from core.prompts import (build_amaranth_system_prompt, build_spirehdl_system_prompt,
                              build_system_prompt)
    td_settable = hasattr(cost_metric, "target_delay")
    note = getattr(cost_metric, "metric_note", "") or ""
    if language == "spirehdl":
        return build_spirehdl_system_prompt(description, metric_name, extra=SAMPLE_SEED,
                                            target_delay_is_settable=td_settable, max_steps=20,
                                            cost_metric_note=note)
    if language == "amaranth":
        return build_amaranth_system_prompt(description, metric_name, extra=SAMPLE_SEED,
                                            max_steps=20, cost_metric_note=note)
    return build_system_prompt(description, metric_name, extra=SAMPLE_SEED,
                               target_delay_is_settable=td_settable, max_steps=20,
                               cost_metric_note=note)


def _agents_md(language, benchmark, cost_metric):
    """Render the OpenCode AGENTS.md for one HDL."""
    import shutil
    from core.agent_backend import BackendRequest, RunLimits
    from core.opencode_backend import render_agents_md
    from core.runner import provision_workspace
    wd = Path("/tmp") / f"_preview_{language}"
    shutil.rmtree(wd, ignore_errors=True)
    ws, _ = provision_workspace(benchmark, wd, language=language, run_cec=False)
    req = BackendRequest(
        benchmark=benchmark, workdir=wd, workspace=ws, model="z-ai/glm-5.2",
        provider="openrouter", cost_metric=cost_metric, language=language,
        limits=RunLimits(max_steps=20, wall_clock_s=600),
        system_prompt_extra=SAMPLE_SEED,
    )
    return render_agents_md(req)


def main():
    from core.benchmarks import load_benchmark
    from core.cost import make_cost_metric

    for language, bench_path, metric in CASES:
        bench = load_benchmark(REPO / bench_path)
        cost_metric = make_cost_metric(metric)

        agents = _agents_md(language, bench, cost_metric)
        agents_path = OUT / f"_AGENTS_preview_{language}.md"
        agents_path.write_text(agents)

        react = _react_prompt(language, bench.description, metric, cost_metric)
        react_path = OUT / f"_react_prompt_{language}.txt"
        react_path.write_text(react)

        print(f"{language:9s}  AGENTS.md {len(agents):>6d}B -> {agents_path.name}   "
              f"react {len(react):>7d}B -> {react_path.name}")


if __name__ == "__main__":
    main()

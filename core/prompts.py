"""System prompt builders for the RTL agent."""

import re
from pathlib import Path
from typing import List

from tech_eval.ppa_extract.core.template import target_delay_time_unit
from core.evaluation import SPIREHDL_VERILOG_OUTPUT, AMARANTH_VERILOG_OUTPUT

# ---------------------------------------------------------------------------
# Optimization decorators README (read once at import time from spire-hdl)
# ---------------------------------------------------------------------------

_opt_dec_path = Path(__file__).parent.parent / "deps" / "spire-hdl" / "README_optimization_decorators.md"
_OPTIMIZATION_DECORATORS_MD = _opt_dec_path.read_text()

_arith_opt_path = Path(__file__).parent.parent / "deps" / "spire-hdl" / "README_arithmetic_optimization.md"
_ARITHMETIC_OPTIMIZATION_MD = _arith_opt_path.read_text()

_fsm_opt_path = Path(__file__).parent.parent / "deps" / "spire-hdl" / "README_fsm_optimization.md"
_FSM_OPTIMIZATION_MD = _fsm_opt_path.read_text()

_state_machines_path = Path(__file__).parent.parent / "deps" / "spire-hdl" / "README_state_machines.md"
_STATE_MACHINES_MD = _state_machines_path.read_text()


def _extract_md_section(md: str, heading: str) -> str:
    """Extract a section from markdown by its ## heading."""
    lines = md.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## ") and heading in line:
            start = i
        elif start is not None and line.strip().startswith("## "):
            return "".join(lines[start:i])
    if start is not None:
        return "".join(lines[start:])
    return ""


# ---------------------------------------------------------------------------
# Reference file registries
# ---------------------------------------------------------------------------

VERILOG_REFERENCES = [
    {
        "name": "Add.sv",
        "path": "/app/ELAU/src/Add.sv",
        "description": "Parallel-prefix adder (ripple-carry / carry-lookahead)",
        "lang": "systemverilog",
    },
    {
        "name": "PrefixAndOr.sv",
        "path": "/app/ELAU/src/PrefixAndOr.sv",
        "description": "Prefix AND-OR structures (Sklansky, Brent-Kung, serial)",
        "lang": "systemverilog",
    },
]

SPIREHDL_REFERENCES = [
    {
        "name": "README.md",
        "path": str(Path(__file__).parent / "spirehdl_readme.md"),
        "description": "SpireHDL project README",
        "lang": "markdown",
    },
    {
        "name": "spirehdl.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/src/spirehdl/spirehdl.py",
        "description": "Core SpireHDL DSL source (signals, types, operators)",
        "lang": "python",
    },
    {
        "name": "spirehdl_module.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/src/spirehdl/spirehdl_module.py",
        "description": "SpireHDL Module class (ports, wires, Verilog emission)",
        "lang": "python",
    },
    {
        "name": "prefix_adder_clean.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/src/spirehdl/arithmetic/prefix_adders/prefix_adder_clean.py",
        "description": "Prefix adder builder and classic topologies (Kogge-Stone, Slansky, etc.)",
        "lang": "python",
    },
    {
        "name": "sign_magnitude.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/src/spirehdl/arithmetic/encoding/sign_magnitude.py",
        "description": "Two's complement / sign-magnitude encoder and decoder components",
        "lang": "python",
    },
    {
        "name": "direct_expression_basics.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/testing/examples/direct_expression_basics.py",
        "description": "Example: direct arithmetic expressions, constants, mux usage",
        "lang": "python",
    },
    # {
    #     "name": "rv32i.py",
    #     "path": "/workspaces/rtlagent/deps/spire-hdl/testing/riscv/rv32i.py",
    #     "description": "Example: minimal RISC-V RV32I",
    #     "lang": "python",
    # },
    {
        "name": "sprout_sequential_mac.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/testing/basic_examples/sprout_sequential_mac.py",
        "description": "Example: sequential multiply-accumulate (MAC) with clock and reset",
        "lang": "python",
    },
    # Optional matmul-accumulate core examples (included only when files exist)
    {
        "name": "matmul_accumulate_core.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/src/spirehdl/cores/matmul_accumulate/matmul_accumulate_core.py",
        "description": "Core: matrix multiply-accumulate implementation",
        "lang": "python"
    },
    {
        "name": "matmul_accumulate_core_fused.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/src/spirehdl/cores/matmul_accumulate/matmul_accumulate_core_fused.py",
        "description": "Core: fused matrix multiply-accumulate implementation",
        "lang": "python"
    },
    {
        "name": "test_matmul_accumulate_core_fused.py",
        "path": "/workspaces/rtlagent/deps/spire-hdl/testing/matmul_accumulate_core/test_matmul_accumulate_core_fused.py",
        "description": "Example: test/usage of the fused matmul-accumulate core",
        "lang": "python"
    },
]


# ---------------------------------------------------------------------------
# Reference loading helpers
# ---------------------------------------------------------------------------

def _load_references(registry: List[dict]) -> List[dict]:
    """Load reference files from a registry list.

    Returns a list of dicts with keys: name, description, lang, content.
    Optional entries (optional=True) are silently skipped when the file does not exist.
    """
    loaded = []
    for ref in registry:
        p = Path(ref["path"])
        content = p.read_text() if p.exists() else f"({ref['name']} not found)"
        loaded.append({
            "name": ref["name"],
            "description": ref["description"],
            "lang": ref["lang"],
            "content": content,
        })
    return loaded


def _build_references_block(registry: List[dict]) -> str:
    """Load references and format them as markdown sections."""
    refs = _load_references(registry)
    sections = []
    for ref in refs:
        sections.append(
            f"### {ref['description']} ({ref['name']})\n"
            f"```{ref['lang']}\n{ref['content']}\n```"
        )
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Shared prompt fragments
# ---------------------------------------------------------------------------

# File-operation tool lines shared by both prompts.
_TOOLS_FILE_OPS = (
    "- create_file: Create a new file in your working directory\n"
    "- replace_file: Replace the entire contents of an existing file\n"
    "- apply_diff: Apply a unified diff to modify a file\n"
    "- edit_file: Edit a file by replacing an exact string match with new content. "
    "Provide old_string (must match exactly once) and new_string.\n"
    "- ls: List files in your working directory\n"
    "- read_file: Read the contents of a file"
)

# Strategy steps 2-6 are identical in both prompts.
# Use str.format(cost_metric_name=...) when embedding.
_STRATEGY_STEPS_3_TO_7 = (
    "3. Run evaluation to confirm correctness and get the initial cost ({cost_metric_name}).\n"
    "4. ONLY after achieving 100% correctness, try to optimize the design to reduce the {cost_metric_name}.\n"
    "5. After each optimization, run evaluation to verify correctness is maintained and check the new cost.\n"
    "6. If an optimization breaks correctness, revert and try a different approach.\n"
    "7. Keep iterating until you run out of steps — use every step to try improvements. Only call done if you are truly stuck with no more ideas."
)

# Creativity, evaluation reminder, and thinking note shared by both prompts.
# Use str.format(cost_metric_name=...) when embedding.
_CREATIVITY_AND_EVAL_BLOCK = (
    "In general, be creative and take risk. At least after you have a correct design, try bold optimizations to reduce {cost_metric_name}, even if they might break correctness. You can always revert if it doesn't work.\n"
    "The best results you obtain which is 100% correctness counts.\n"
    "Try to beat at least the straightforward implementation.\n"
    "\n"
    "Running evaluation is crucial after every change to ensure correctness and track cost. Do not skip evaluations.\n"
    "\n"
    "You may do some 'thinking' alongside with your tool calling responses to explain your reasoning, but always remember to call a tool in every response."
)

# Important bullets shared by both prompts.
# Use str.format(max_steps=...) when embedding.
_IMPORTANT_COMMON = (
    "- Always call a tool in every response.\n"
    "- You have a maximum of **{max_steps} steps** (tool calls / LLM turns). Budget them wisely: get a correct design first, then optimise.\n"
    "- The best result is the one with lowest cost among designs that pass 100% of testbench checks.\n"
    "- Use different filenames for different design variants so you can retrieve them later.\n"
    "- If context files (e.g. component source files) are in your workspace, you can modify them directly "
    "using edit_file or replace_file to optimize the design. Make targeted, incremental changes rather than "
    "rewriting files from scratch — small edits are less likely to introduce bugs."
)

# target_delay note shared by both prompts (used when target_delay_is_settable=True).
_TARGET_DELAY_NOTE = (
    f"- You can pass `target_delay` ({target_delay_time_unit}) to `run_evaluation` to try different synthesis "
    "timing constraints; experimenting with this may improve PPA results "
    "(lower target delay may reduce delay, higher target delay may reduce area/transistor count). "
    "target_delay must be > 0.\n"
    "- Do not spend too many steps sweeping `target_delay` — basically if you want to minimize delay choose a low value,"
    "if you want to minimize area/transistor count choose a high value. That's it."
    "A few targeted experiments are more productive than an exhaustive sweep.\n"
)

# Delay optimization tips shared by both prompts.
_DELAY_OPTIMIZATION_TIPS = (
    "## Delay Optimization Tips\n"
    "- Varying `target_delay` during synthesis can help Yosys explore different trade-offs. Try aggressive values (e.g., 200–500 ps) to pressure the synthesizer toward faster logic, and also try higher values (1000–1500 ps) which may allow Yosys to re-map to smaller/faster cells differently.\n"
    "- After getting a correct design, try different accumulation orderings (sequential vs. tree) and compare results — Yosys synthesis can produce noticeably different delays (~10 ps) from structurally similar descriptions.\n"
    "- For designs dominated by a multiply-accumulate chain, the critical path is the multiplier followed by the adder tree. Reducing the adder depth or splitting into parallel partial sums can help."
)

# Agent-specific strategy tips for @flowy_optimized (appended after the README section).
# The arithmetic restriction ("What NOT to optimize") is included only when
# arith_autoconfig is NOT enabled — when it is, those ops are fair game.
_FLOWY_OPTIMIZE_AGENT_TIPS_BASE = (
    "### Agent Strategy for @flowy_optimized\n"
    "- **Chunk size matters**: The optimizer works best on reasonably sized chunks of logic. "
    "If a function is too large, the optimization will time out and fail. "
    "Break large functions into smaller pieces and decorate each piece separately.\n"
    "- **Runtime scales with search budget**: compute time is roughly proportional to "
    "`iterations × mockturtle_chains × mockturtle_chain_len`. A single call with "
    "`iterations=2, mockturtle_chains=2, mockturtle_chain_len=5` on a 32-bit multiplier could already trip the timeout. "
    "**Start small** (`iterations=1, mockturtle_chains=1, mockturtle_chain_len=2, mockturtle_chain_workers=1`) "
    "to confirm the wrapping compiles and improves cost, then scale up only if the improvement is meaningful "
    "and you have step budget to spare.\n"
    "- **On timeout, choose one**: (a) reduce search budget parameters "
    "(`iterations`, `mockturtle_chains`, `mockturtle_chain_len`) before retrying, OR "
    "(b) split the decorated function into smaller sub-functions and decorate each one.\n"
    "- **Non-deterministic**: The optimizer uses randomized search internally, so results may vary "
    "slightly between runs.\n"
    "- **selection_metric**: Controls what the optimizer targets. Pass as a decorator argument:\n"
    "  - For **area** optimization: `selection_metric='aig_count'` (default) or `selection_metric='nb_transistors'`\n"
    "  - For **delay** optimization: `selection_metric='mockturtle_depth'` or `selection_metric='max_depth'`\n"
    "  Example: `@flowy_optimized(selection_metric='mockturtle_depth')`\n\n"
)

_FLOWY_OPTIMIZE_STRATEGY = (
    "### Strategy\n"
    "1. Identify the computationally intensive functions in your design (mux trees, normalization, rounding, etc.)\n"
    "2. Wrap them with `@flowy_optimized` using **small parameters first** "
    "(`iterations=1, mockturtle_chains=1, mockturtle_chain_len=2`) to confirm the flow runs and helps.\n"
    "3. If optimization times out: **either** reduce the search budget (see tips above) **or** "
    "split the function into smaller sub-functions and decorate each one.\n"
    "4. Evaluate after each change to verify correctness and measure cost improvement.\n"
)

_CORE_ARITH_RESTRICTION = (
    "## Core Arithmetic Restriction\n\n"
    "IMPORTANT: Do NOT change the internal multiplier or adder configurations "
    "(MultiplierConfig, AdderConfig). Do NOT put the mantissa multiplier (`*`) or "
    "exponent adder (`+`) inside optimization decorator blocks. "
    "These core arithmetic operations will be optimized at a later stage using "
    "automated architecture sweeps. Focus your optimization on the surrounding "
    "floating-point logic only (mux trees, normalization, rounding, etc.).\n"
)


def _flowy_agent_tips() -> str:
    """Build flowy agent tips."""
    return _FLOWY_OPTIMIZE_AGENT_TIPS_BASE + _FLOWY_OPTIMIZE_STRATEGY


def _build_optimization_guidance(abc_optimize: bool, flowy_optimize: bool,
                                 arith_autoconfig: bool,
                                 dont_touch_main_arith: bool = False,
                                 fsm_optimize: bool = False) -> str:
    """Build the optimization guidance section for the system prompt."""
    if (not abc_optimize and not flowy_optimize and not arith_autoconfig
            and not dont_touch_main_arith and not fsm_optimize):
        return ""

    parts = []

    # --- Decorator-based optimizations (abc / flowy) ---
    if abc_optimize or flowy_optimize:
        parts.append("## Synthesis Optimization Decorators\n")

        if abc_optimize and flowy_optimize:
            parts.append(
                "You have two optimization decorators available. Both optimize combinational "
                "logic at the AIG level — choose based on circuit characteristics.\n\n"
            )

        if abc_optimize:
            parts.append(_extract_md_section(_OPTIMIZATION_DECORATORS_MD, "@abc_optimized"))

        if flowy_optimize:
            parts.append(_extract_md_section(_OPTIMIZATION_DECORATORS_MD, "@flowy_optimized"))
            parts.append("\n" + _flowy_agent_tips())

        caching = _extract_md_section(_OPTIMIZATION_DECORATORS_MD, "Caching")
        if caching:
            parts.append(caching)

    # --- Arithmetic auto-config ---
    if arith_autoconfig:
        parts.append(_ARITHMETIC_OPTIMIZATION_MD)
        # Newer sibling decorator to replace_arithmetic_ops — same idea but
        # scoped per-function and content-cached. Keep it alongside the
        # whole-component pass so the agent knows both exist.
        arith_dec = _extract_md_section(_OPTIMIZATION_DECORATORS_MD, "@arithmetic_optimized")
        if arith_dec:
            parts.append(arith_dec)

    # --- Stacking decorators ---
    # Only relevant when the agent has a *partner* decorator to stack with —
    # i.e. `--abc-optimize` or `--flowy-optimize`. With just `--arith-autoconfig`,
    # `@arithmetic_optimized` stands alone (no outer decorator to wrap it with),
    # so the stacking section would be noise.
    if abc_optimize or flowy_optimize:
        stacking = _extract_md_section(_OPTIMIZATION_DECORATORS_MD, "Stacking decorators")
        if stacking:
            # The README's stacking example uses @abc_optimized as the outer
            # decorator. When only --flowy-optimize is on, the agent doesn't
            # have @abc_optimized available, so swap the example over to
            # @flowy_optimized (and drop the abc_script kwarg that has no
            # meaning for flowy) to avoid pointing the agent at an unavailable
            # decorator. If --abc-optimize is on, the example is kept as-is.
            if flowy_optimize and not abc_optimize:
                stacking = re.sub(
                    r"@abc_optimized\([^)]*\)",
                    "@flowy_optimized",
                    stacking,
                )
                stacking = stacking.replace("@abc_optimized", "@flowy_optimized")
            parts.append(stacking)

    # --- FSM / state-encoding optimization ---
    # When the design has (or could have) a state machine, surface the basic
    # `State` API and the `optimized_fsm` / `optimized_encoding` wrappers. Both
    # files together since the optimizer wrappers reference the State API.
    if fsm_optimize:
        parts.append(_STATE_MACHINES_MD)
        parts.append(_FSM_OPTIMIZATION_MD)

    # --- Core arithmetic restriction ---
    if dont_touch_main_arith:
        parts.append(_CORE_ARITH_RESTRICTION)

    return "\n".join(parts)

# Reference implementations section header shared by both prompts.
_REFERENCES_HEADER = (
    "## Reference Implementations\n"
    "The following are reference implementations for inspiration. Study them for patterns and techniques, but do not copy them directly — adapt ideas to your specific design."
)


# ---------------------------------------------------------------------------
# System prompt builders
# ---------------------------------------------------------------------------

def build_system_prompt(description: str, cost_metric_name: str, extra: str = "",
                        target_delay_is_settable: bool = False,
                        max_steps: int = 20) -> str:
    references_block = _build_references_block(VERILOG_REFERENCES)

    run_eval_line = (
        f"- run_evaluation(filename[, target_delay]): Run evaluation on the given design file. "
        f"Returns correctness (Verilator simulation) + cost (Yosys {cost_metric_name}). "
        f"The filename must be your main design file (e.g. 'design.sv'). "
        f"Optionally pass target_delay ({target_delay_time_unit}) to override the synthesis timing constraint."
        if target_delay_is_settable else
        f"- run_evaluation(filename): Run evaluation on the given design file. "
        f"Returns correctness (Verilator simulation) + cost (Yosys {cost_metric_name}). "
        f"The filename must be your main design file (e.g. 'design.sv')."
    )

    target_delay_note = _TARGET_DELAY_NOTE if target_delay_is_settable else ""
    strategy_steps = _STRATEGY_STEPS_3_TO_7.format(cost_metric_name=cost_metric_name)
    creativity_block = _CREATIVITY_AND_EVAL_BLOCK.format(cost_metric_name=cost_metric_name)
    important_common = _IMPORTANT_COMMON.format(max_steps=max_steps)

    return f"""You are an RTL (Register Transfer Level) design agent. Your task is to create a Verilog/SystemVerilog design that satisfies the given specification, is functionally correct, and has minimal cost ({cost_metric_name}).

## Specification
{description}

## Tools
{_TOOLS_FILE_OPS}
{run_eval_line}
- done: Signal completion (only use when truly stuck with no more ideas)

## Strategy
1. Lay out an action plan. Try to cover a diverse set of approaches in your plan to increase the chances of finding a good solution within the step limit. Also once you find a new best solution, explore close solutions. Trade off exploration with exploitation.
2. First, create a simple, straightforward design that is functionally correct. Focus on getting 100% correctness first.
{strategy_steps}

{creativity_block}

## Important
{important_common}
- Write clean, synthesizable RTL code.
{target_delay_note}
{_DELAY_OPTIMIZATION_TIPS}

{_REFERENCES_HEADER}

{references_block}
""" + (f"\n## Additional guidance\n{extra}\n" if extra else "")


def build_spirehdl_system_prompt(description: str, cost_metric_name: str, extra: str = "",
                                  target_delay_is_settable: bool = False,
                                  max_steps: int = 20,
                                  flowy_optimize: bool = False,
                                  abc_optimize: bool = False,
                                  arith_autoconfig: bool = False,
                                  dont_touch_main_arith: bool = False,
                                  fsm_optimize: bool = False) -> str:
    references_block = _build_references_block(SPIREHDL_REFERENCES)

    run_eval_line = (
        f"- run_evaluation(filename[, target_delay]): Run the given SpireHDL .py file "
        f"(which writes Verilog via m.to_verilog_file), "
        f"then run evaluation (correctness via Verilator + cost via Yosys {cost_metric_name}). "
        f"The filename must be your main design file (e.g. 'design.py'). "
        f"Optionally pass target_delay ({target_delay_time_unit}) to override the synthesis timing constraint."
        if target_delay_is_settable else
        f"- run_evaluation(filename): Run the given SpireHDL .py file "
        f"(which writes Verilog via m.to_verilog_file), "
        f"then run evaluation (correctness via Verilator + cost via Yosys {cost_metric_name}). "
        f"The filename must be your main design file (e.g. 'design.py')."
    )

    target_delay_note = _TARGET_DELAY_NOTE if target_delay_is_settable else ""
    strategy_steps = _STRATEGY_STEPS_3_TO_7.format(cost_metric_name=cost_metric_name)
    creativity_block = _CREATIVITY_AND_EVAL_BLOCK.format(cost_metric_name=cost_metric_name)
    important_common = _IMPORTANT_COMMON.format(max_steps=max_steps)

    return f"""You are an RTL design agent using SpireHDL, a Python EDSL for hardware description. Your task is to create a design that satisfies the given specification, is functionally correct, and has minimal cost ({cost_metric_name}).

## Specification
{description}

## SpireHDL Overview
SpireHDL is a Python embedded DSL that generates synthesizable Verilog. You write a Python script that constructs a hardware Module using the SpireHDL API, then writes Verilog to a file via `m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}")`.

### Canonical Pattern
```python
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt, Bool, SInt, Const, mux, cat

m = Module("mult8", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
p = m.output(UInt(16), "p")

p <<= a * b

m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}")
```

### Key API
- `Module(name, with_clock=False, with_reset=False)` — Create a module
- `m.input(UInt(N), "name")` — Declare input port
- `m.output(UInt(N), "name")` — Declare output port
- `m.wire(UInt(N), "name")` — Declare internal wire
- `signal <<= expr` — Drive a signal (combinational assignment)
- Types: `UInt(N)`, `SInt(N)`, `Bool()`
- `Const(value, type)` — Constant literal, e.g. `Const(0, UInt(1))`, `Const(3, SInt(8))`
- Operators: `+`, `-`, `*`, `&`, `|`, `^`, `~`, `<<`, `>>`, `==`, `!=`, `<`, `<=`, `>`, `>=`
- `mux(sel, a, b)` — Ternary: sel ? a : b
- `cat(a, b, ...)` — Concatenation (LSB first, i.e. `cat(a, b)` places `a` in lower bits and `b` in higher bits)
- `signal[i]` — Bit select; `signal[lo:hi]` — Bit slice (Python-style, exclusive upper bound). **Do NOT use Verilog's `+:` part-select syntax** — write `signal[lo : lo+N]`, not `signal[lo +: N]`.
- `m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}")` — Write Verilog directly to a file. Pass `simplify=True` (e.g. `m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}", simplify=True)`) to run a peephole simplification pass before emission (constant folding, boolean identities, trivial-mux collapse, mux-tree guard substitution). It often shrinks the output and can improve synthesis quality, but it adds significant compile time and may time out on larger or more complex circuits. Default is off.
- mostly no need to declare wires for intermediate expressions; just create them inline: a = b + c, vs a = m.wire(UInt(8), "a"); a <<= b + c.

### Common Mistakes — Avoid These
- **WRONG slicing syntax**: Do NOT use Verilog's `+:` part-select. Write `signal[lo : lo+N]`, not `signal[lo +: N]`.
- **Width packing bug**: See "Signal Width Inference" below.

### Signal Width Inference — CRITICAL for correct output packing
SpireHDL automatically infers signal widths from arithmetic expressions. The result of an addition or multiplication may be **wider than you expect** (e.g., summing four 8-bit products gives a 10-bit value, then adding a 10-bit operand gives 11 or 12 bits). When you pass signals to `cat()`, the concatenation uses each signal's **inferred width**, not the output port's target width.

**Common pitfall (bug)**: If you compute `y[i][j] = sum_of_products + c[i][j]` and the inferred width is 12 bits, then `cat(*results)` packs elements at 12-bit strides. But if the specification requires 11-bit element strides in the output bus, the packed output will be wrong — every element will be at the wrong bit offset.

**Fix**: Before packing with `cat()`, explicitly truncate each element to the required bit width using slicing:
```python
# Correct: truncate each result to exactly 11 bits
y <<= cat(*[result[0:11] for result in results])
```
Tip: If necessary, check the generated Verilog wire widths to verify element sizes match the specification.

### SpireHDL API Notes
- `UInt(N)` takes **exactly one argument** (the bit-width N). Use `Const(value, UInt(N))` to create a constant signal.
- When accumulating signals in a loop, prefer starting from the first signal element rather than from a zero constant, to avoid an unnecessary adder level:
  ```python
  # Preferred: start from first product (no +0 overhead)
  sum_val = a_elem[i][0] * b_elem[0][j]
  for k in range(1, 4):
      sum_val = sum_val + a_elem[i][k] * b_elem[k][j]
  result = sum_val + c_elem[i][j]
  ```
- To force an intermediate result to a specific bit width, assign it to a named wire: `w = m.wire(UInt(N), "name"); w <<= expr` — this tells SpireHDL (and Yosys) the exact width, which can affect synthesis quality. Named wires create explicit cut-points in the circuit, helping Yosys optimise each stage independently. For a 4-input multiply-accumulate this looks like:
  ```python
  # Pre-declare all products as explicit 8-bit wires, then build the adder tree:
  prod = [[[m.wire(UInt(8), f"p_{{i}}_{{k}}_{{j}}") for j in range(4)] for k in range(4)] for i in range(4)]
  for i in range(4):
      for k in range(4):
          for j in range(4):
              prod[i][k][j] <<= a_elem[i][k] * b_elem[k][j]
  # Then for each output element (i,j), build the adder tree:
  s01 = m.wire(UInt(9),  f"s{{i}}{{j}}_01"); s01 <<= prod[i][0][j] + prod[i][1][j]
  s23 = m.wire(UInt(9),  f"s{{i}}{{j}}_23"); s23 <<= prod[i][2][j] + prod[i][3][j]
  sp  = m.wire(UInt(10), f"sp{{i}}{{j}}");   sp  <<= s01 + s23
  result = sp + c_elem   # 11-bit final (truncate before cat)
  ```
  Precomputing all products as explicit 8-bit wires before the adder tree has been observed to give better delay than computing products inline. Note that the exact ordering and naming of wire declarations can also slightly affect synthesis timing, so it is worth trying variations.

### How It Works
1. You create a `.py` file (e.g. `design.py`) using the SpireHDL API
2. Your script writes Verilog directly via `m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}")`
3. The framework runs your script; the generated Verilog file is evaluated for correctness and cost
4. You can split helpers across multiple `.py` files — your working directory is on the Python path, so plain imports work: from helper import build_adder

## Tools
{_TOOLS_FILE_OPS}
{run_eval_line}
- done: Signal completion (only use when truly stuck with no more ideas, but better have the 'I can do it attitude' and keep on trying)

## Strategy
1. Lay out an action plan. Try to cover a diverse set of approaches in your plan to increase the chances of finding a good solution within the step limit. Also once you find a new best solution, explore close solution. Trade off exploration with exploitation.
2. First, create a simple, straightforward design (e.g. `design.py`) that is functionally correct. Use the canonical pattern above. Focus on getting 100% correctness first.
{strategy_steps}

{creativity_block}

## Important
{important_common}
- Your Python file MUST write Verilog using `m.to_verilog_file("{SPIREHDL_VERILOG_OUTPUT}")`.
- You MUST use the SpireHDL API to describe your design. Do NOT bypass SpireHDL by writing Verilog directly from Python (e.g. via `open(...).write(...)` or string templates). The entire design must be expressed through SpireHDL constructs.
- The generated Verilog module name and ports must match the specification exactly.
- You may split logic across multiple `.py` files — your working directory is on the Python path, so plain imports work: `from helper import build_adder`.
- IMPORTANT: Use Python features creatively — recursion, loops, helper functions, classes, optimization routines, debug prints, in-code analysis to pick the best variant, etc. are all fair game when constructing the hardware logic.
{target_delay_note}
{_DELAY_OPTIMIZATION_TIPS}

{_build_optimization_guidance(abc_optimize, flowy_optimize, arith_autoconfig, dont_touch_main_arith, fsm_optimize)}

{_REFERENCES_HEADER}

{references_block}
""" + (f"\n## Additional guidance\n{extra}\n" if extra else "")


# ---------------------------------------------------------------------------
# Amaranth HDL references
# ---------------------------------------------------------------------------

AMARANTH_REFERENCES = [
    {
        "name": "Add.sv",
        "path": "/app/ELAU/src/Add.sv",
        "description": "Parallel-prefix adder (ripple-carry / carry-lookahead) — reference Verilog",
        "lang": "systemverilog",
    },
    {
        "name": "PrefixAndOr.sv",
        "path": "/app/ELAU/src/PrefixAndOr.sv",
        "description": "Prefix AND-OR structures — reference Verilog",
        "lang": "systemverilog",
    },
]


def build_amaranth_system_prompt(description: str, cost_metric_name: str, extra: str = "",
                                  target_delay_is_settable: bool = False,
                                  max_steps: int = 20) -> str:
    references_block = _build_references_block(AMARANTH_REFERENCES)

    run_eval_line = (
        f"- run_evaluation(filename[, target_delay]): Run the given Amaranth .py file "
        f"(which writes Verilog via amaranth.back.verilog.convert), "
        f"then run evaluation (correctness via Verilator + cost via Yosys {cost_metric_name}). "
        f"The filename must be your main design file (e.g. 'design.py'). "
        f"Optionally pass target_delay ({target_delay_time_unit}) to override the synthesis timing constraint."
        if target_delay_is_settable else
        f"- run_evaluation(filename): Run the given Amaranth .py file "
        f"(which writes Verilog via amaranth.back.verilog.convert), "
        f"then run evaluation (correctness via Verilator + cost via Yosys {cost_metric_name}). "
        f"The filename must be your main design file (e.g. 'design.py')."
    )

    target_delay_note = _TARGET_DELAY_NOTE if target_delay_is_settable else ""
    strategy_steps = _STRATEGY_STEPS_3_TO_7.format(cost_metric_name=cost_metric_name)
    creativity_block = _CREATIVITY_AND_EVAL_BLOCK.format(cost_metric_name=cost_metric_name)
    important_common = _IMPORTANT_COMMON.format(max_steps=max_steps)

    return f"""You are an RTL design agent using Amaranth HDL, a Python library for hardware description. Your task is to create a design that satisfies the given specification, is functionally correct, and has minimal cost ({cost_metric_name}).

## Specification
{description}

## Amaranth HDL Overview
Amaranth HDL is a Python library that generates synthesizable Verilog via Yosys. You write a Python script that defines a hardware design as an `Elaboratable` class, then converts it to Verilog using `amaranth.back.verilog.convert()` and writes it to `"{AMARANTH_VERILOG_OUTPUT}"`.

### Canonical Pattern
```python
from amaranth import *
from amaranth.back.verilog import convert

class MyDesign(Elaboratable):
    def __init__(self):
        # Declare all signals as instance attributes
        self.a   = Signal(8)   # 8-bit input
        self.b   = Signal(8)   # 8-bit input
        self.out = Signal(8)   # 8-bit output

    def elaborate(self, platform):
        m = Module()
        # Combinational logic
        m.d.comb += self.out.eq(self.a + self.b)
        return m

dut = MyDesign()
verilog_text = convert(dut, ports=[dut.a, dut.b, dut.out], name="my_design", strip_internal_attrs=True)
with open("{AMARANTH_VERILOG_OUTPUT}", "w") as f:
    f.write(verilog_text)
```

### Key API

#### Signals
- `Signal(N)` — unsigned N-bit signal (default reset=0)
- `Signal(N, reset=V)` — N-bit signal with reset value V
- `Signal(name="foo")` — 1-bit signal with explicit name (for debugging)
- `Const(value, N)` — N-bit constant literal

#### Combinational Logic
```python
m.d.comb += sig.eq(expr)          # single assignment
m.d.comb += [                     # list of assignments
    sig1.eq(expr1),
    sig2.eq(expr2),
]
```

#### Sequential (Clocked) Logic
```python
m.d.sync += sig.eq(expr)          # clocked on posedge clk, sync reset
```
The `convert()` call automatically adds `clk` and `rst` ports when `m.d.sync` is used.

#### Operators
- Arithmetic: `a + b`, `a - b`, `a * b`
- Bitwise: `a & b`, `a | b`, `a ^ b`, `~a`
- Shift: `a << n`, `a >> n`
- Comparison: `a == b`, `a != b`, `a < b`, `a <= b`, `a > b`, `a >= b`
- Reduction: `a.any()`, `a.all()`, `a.xor()`

#### Concatenation and Slicing
- `Cat(a, b, ...)` — concatenation: `a` placed in **lower** bits, `b` in **higher** bits (LSB-first)
  - e.g. `Cat(low8, high8)` produces a 16-bit value with low8 in bits [7:0]
- `sig[i]` — bit select (0-indexed from LSB)
- `sig[i:j]` — slice bits i to j-1 (Python-style, exclusive upper bound)

#### Mux
- `Mux(sel, val_if_1, val_if_0)` — ternary: when sel=1 return val_if_1, else val_if_0

#### Submodules
```python
sub = SubModule()
m.submodules.sub = sub
m.d.comb += sub.input.eq(self.a)
```

#### If/Elif/Else (within elaborate)
```python
with m.If(condition):
    m.d.comb += sig.eq(val1)
with m.Elif(other_cond):
    m.d.comb += sig.eq(val2)
with m.Else():
    m.d.comb += sig.eq(val3)
```

#### Switch/Case
```python
with m.Switch(self.sel):
    with m.Case(0b00):
        m.d.comb += self.out.eq(self.a)
    with m.Case(0b01):
        m.d.comb += self.out.eq(self.b)
    with m.Default():
        m.d.comb += self.out.eq(0)
```

#### Intermediate Signals (Wires)
Declare intermediate signals as local variables inside `elaborate`:
```python
def elaborate(self, platform):
    m = Module()
    partial = Signal(9)
    m.d.comb += [
        partial.eq(self.a + self.b),
        self.out.eq(partial[:8]),
    ]
    return m
```

#### Verilog Generation
```python
verilog_text = convert(
    dut,
    ports=[dut.a, dut.b, dut.out],   # list of top-level ports
    name="module_name",               # Verilog module name (must match spec)
    strip_internal_attrs=True,        # cleaner output (recommended)
)
with open("{AMARANTH_VERILOG_OUTPUT}", "w") as f:
    f.write(verilog_text)
```
- **`ports`**: must include ALL inputs and outputs. Signals not listed are internal only.
- **`name`**: sets the Verilog `module` name — must exactly match the specification.
- The `convert()` call runs Yosys internally and produces synthesizable Verilog.

### Common Pitfalls — Avoid These
- **Width truncation**: Amaranth arithmetic widens results (e.g., 8-bit + 8-bit → 9-bit). If your output is 8 bits, truncate: `self.out.eq((self.a + self.b)[:8])`.
- **Cat direction**: `Cat(low, high)` — `low` goes in the **lower** bits. Opposite of Verilog `{{high, low}}`.
- **Signal name conflicts**: in loops use `Signal(N, name=f"sig_{{i}}")` to give unique names.
- **Missing ports**: any signal not in the `ports=[...]` list will not appear as a port.
- **No unsigned/signed import needed** for basic use; for signed signals use `Signal(shape=signed(N))` with `from amaranth.hdl import signed`.

### How It Works
1. You create a `.py` file (e.g. `design.py`) using Amaranth
2. Your script writes Verilog to `"{AMARANTH_VERILOG_OUTPUT}"` via `convert()`
3. The framework runs your script; the generated Verilog is evaluated for correctness and cost
4. You can split helpers across multiple `.py` files — your working directory is on the Python path

## Tools
{_TOOLS_FILE_OPS}
{run_eval_line}
- done: Signal completion (only use when truly stuck with no more ideas)

## Strategy
1. Lay out an action plan covering diverse approaches.
2. First, create a simple, straightforward design (e.g. `design.py`) that is functionally correct. Use the canonical pattern above. Focus on getting 100% correctness first.
{strategy_steps}

{creativity_block}

## Important
{important_common}
- Your Python file MUST write Verilog to `"{AMARANTH_VERILOG_OUTPUT}"` using `amaranth.back.verilog.convert()`.
- Do NOT write Verilog directly (no string templates, no `open(...).write(...)`). Use Amaranth constructs.
- The generated Verilog module name and ports must match the specification exactly.
- You may split logic across multiple `.py` files — your working directory is on the Python path.
- IMPORTANT: Use Python features creatively — loops, recursion, helper functions, in-code analysis, etc. are all valid.
- Available imports: `from amaranth import *`, `from amaranth.back.verilog import convert`.
{target_delay_note}
{_DELAY_OPTIMIZATION_TIPS}

{_REFERENCES_HEADER}

{references_block}
""" + (f"\n## Additional guidance\n{extra}\n" if extra else "")

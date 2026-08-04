"""The generated functional cell models must match the liberty functions.

Pure-python check (no simulator): for every combinational module in
asap7_functional_cells.v, evaluate its assign expression against the
liberty `function` of the same cell for all input combinations.
"""
import gzip
import itertools
import re
from pathlib import Path

import pytest

from tech_eval.ppa_extract.core import template


def _read_lib(path):
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt").read()
    return p.read_text()


def _liberty_functions():
    """{cell: (inputs, {out: liberty_expr})} for all cells in the asap7 libs."""
    cfg = template.get_tech_config("asap7")
    cells = {}
    for libpath in cfg.lib_paths:
        text = _read_lib(libpath)
        for m in re.finditer(r"^\s*cell \((\S+)\) \{", text, re.M):
            depth, i = 0, m.end() - 1
            while text[i] != "}" or depth != 1:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            body = text[m.start():i]
            inputs, funcs = [], {}
            for pm in re.finditer(r"(?<![a-z_])pin \((\S+)\) \{", body):
                pbody = body[pm.end():pm.end() + 2000]
                d = re.search(r"direction\s*:\s*(\w+)", pbody)
                if not d:
                    continue
                if d.group(1) == "input":
                    inputs.append(pm.group(1))
                elif d.group(1) == "output":
                    fn = re.search(r'function\s*:\s*"([^"]+)"', pbody)
                    if fn:
                        funcs[pm.group(1)] = fn.group(1)
            cells[m.group(1)] = (inputs, funcs)
    return cells


def _verilog_modules():
    """{cell: (ports, {out: verilog_expr})} from the generated file."""
    cfg = template.get_tech_config("asap7")
    text = Path(cfg.functional_models).read_text()
    mods = {}
    for m in re.finditer(r"module (\S+) \((.*?)\);(.*?)endmodule", text, re.S):
        name, ports, body = m.group(1), m.group(2), m.group(3)
        assigns = dict(re.findall(r"assign (\w+) = (.*?);", body))
        mods[name] = (ports, assigns)
    return mods


def _eval_expr(expr, assign, ops):
    e = expr
    for a, b in ops:
        e = e.replace(a, b)
    return bool(eval(e, {"__builtins__": {}}, {k: bool(v) for k, v in assign.items()}))


def test_functional_models_match_liberty():
    lib = _liberty_functions()
    mods = _verilog_modules()
    assert len(mods) >= 170, f"suspiciously few modules: {len(mods)}"
    checked = 0
    for cell, (ports, assigns) in mods.items():
        if not assigns:  # behavioral flop modules have no assigns
            assert cell.startswith("DFFHQN"), cell
            continue
        inputs, funcs = lib[cell]
        for out, vexpr in assigns.items():
            lexpr = funcs[out]
            for bits in itertools.product([0, 1], repeat=len(inputs)):
                a = dict(zip(inputs, bits))
                v = _eval_expr(vexpr, a, [("&", " and "), ("|", " or "), ("~", " not "), ("^", " != ")])
                l = _eval_expr(lexpr, a, [("*", " and "), ("+", " or "), ("!", " not "), ("^", " != ")])
                assert v == l, f"{cell}.{out} mismatch at {a}"
            checked += 1
    assert checked >= 170


def test_functional_models_file_configured():
    cfg = template.get_tech_config("asap7")
    assert cfg.functional_models and Path(cfg.functional_models).exists()
    assert isinstance(template.NETLIST_FUNCTIONAL_SIM_CELL_MODELS, bool)
    # flop model present for the only SEQ cell abc maps to
    assert "module DFFHQNx1_ASAP7_75t_R" in Path(cfg.functional_models).read_text()

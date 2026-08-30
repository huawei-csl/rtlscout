#!/usr/bin/env python3
"""Generate functional Verilog cell models from the ASAP7 liberty files.

One module per cell, derived from the liberty `function` attribute:
combinational cells as a single assign (liberty '*'/'+'/'!' mapped to
'&'/'|'/'~'), DFFHQN* flops as a behavioral non-blocking always block.
Cells whose liberty functions reference internal nodes (latches, ICGs,
scan/other flop families) are skipped -- the abc-mapped netlists never
use them; extend here if that changes.

These models replace the vendor UDP simulation models for gate-level
netlist sims (selected via NETLIST_FUNCTIONAL_SIM_CELL_MODELS in core/template.py):
verified power-equivalent, ~5x faster to build, ~25x faster to simulate,
and immune to the Verilator sequential-UDP mis-lowering.

Run: python gen_asap7_functional_cells.py   (writes asap7_functional_cells.v)
"""
import gzip
import re
from pathlib import Path

from tech_eval.ppa_extract.core.template import get_tech_config

HERE = Path(__file__).resolve().parent


def read_lib(path):
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt").read()
    return p.read_text()


def split_cells(text):
    """{cellname: body} via brace counting from each 'cell (NAME) {'."""
    out = {}
    for m in re.finditer(r"^\s*cell \((\S+)\) \{", text, re.M):
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[m.group(1)] = text[m.start():i]
    return out


def parse_pins(body):
    inputs, outputs, funcs = [], [], {}
    for pm in re.finditer(r"(?<![a-z_])pin \((\S+)\) \{", body):
        pname = pm.group(1)
        pbody = body[pm.end():pm.end() + 2000]
        d = re.search(r"direction\s*:\s*(\w+)", pbody)
        if not d:
            continue
        if d.group(1) == "output":
            outputs.append(pname)
            fn = re.search(r'function\s*:\s*"([^"]+)"', pbody)
            if fn:
                funcs[pname] = fn.group(1)
        elif d.group(1) == "input":
            inputs.append(pname)
    return inputs, outputs, funcs


def main():
    cfg = get_tech_config("asap7")
    out = ["// functional ASAP7 models generated from liberty functions",
           "// (gen_asap7_functional_cells.py -- do not edit by hand)"]
    emitted, dropped = 0, []
    for libpath in cfg.lib_paths:
        for cell, body in split_cells(read_lib(libpath)).items():
            inputs, outputs, funcs = parse_pins(body)
            if cell.startswith("DFFHQN"):
                out.append(f"module {cell} (output reg QN, input D, input CLK);")
                out.append("  always @(posedge CLK) QN <= ~D;")
                out.append("endmodule")
                emitted += 1
                continue
            if not outputs or not funcs:
                dropped.append(cell)
                continue
            pins = set(inputs) | set(outputs)
            assigns, ok = [], True
            for o in outputs:
                if o not in funcs:
                    ok = False
                    break
                expr = funcs[o].replace("*", "&").replace("+", "|").replace("!", "~")
                if set(re.findall(r"[A-Za-z_]\w*", expr)) - pins:
                    ok = False  # references an internal node (latch/ICG etc.)
                    break
                assigns.append(f"  assign {o} = {expr};")
            if not ok:
                dropped.append(cell)
                continue
            ports = ", ".join([f"output {o}" for o in outputs]
                              + [f"input {p}" for p in inputs])
            out.append(f"module {cell} ({ports});")
            out += assigns
            out.append("endmodule")
            emitted += 1
    (HERE / "asap7_functional_cells.v").write_text("\n".join(out) + "\n")
    print(f"asap7_functional_cells.v: {emitted} cells, {len(dropped)} skipped "
          f"(no simple function)")


if __name__ == "__main__":
    main()

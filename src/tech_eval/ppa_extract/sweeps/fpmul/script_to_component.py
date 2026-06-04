"""Convert reference design scripts to Component source files.

Reads a reference design script (e.g. ``seed_seed_design_v5.py``), applies AST
transformations to make the multiplier and adder configurable, and writes a
proper :class:`Component` class file next to the original.

The generated file lives alongside ``.spirehdl_cache`` so that
``flowy_optimized`` can find cached optimisation results via
``inspect.getfile()``.

Usage::

    python -m tech_eval.ppa_extract.sweeps.fpmul.script_to_component \\
        references/pareto_front/design_000/seed_seed_design_v5.py
"""

import ast
import importlib.util
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

# Top-level constants derived from EW / FW — these become computed attributes
# in the Component __init__ and are removed from the script body.
_PARAM_CONSTANTS = {"EW", "FW", "W", "BIAS", "MAX_E", "PROD_W"}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

class _PatchMultAdd(ast.NodeTransformer):
    """Replace ``prod = mA_eff * mB_eff`` and ``exp_sum = eA_eff + eB_eff``
    with configurable calls to ``build_multiplier`` / ``build_adder``."""

    def __init__(self):
        super().__init__()
        self.mult_count = 0
        self.add_count = 0

    @staticmethod
    def _cond_call(func_name, cfg_name, left_id, right_id, original):
        """``func(l, r, cfg) if cfg is not None else original``"""
        return ast.IfExp(
            test=ast.Compare(
                left=ast.Name(id=cfg_name, ctx=ast.Load()),
                ops=[ast.IsNot()],
                comparators=[ast.Constant(value=None)],
            ),
            body=ast.Call(
                func=ast.Name(id=func_name, ctx=ast.Load()),
                args=[
                    ast.Name(id=left_id, ctx=ast.Load()),
                    ast.Name(id=right_id, ctx=ast.Load()),
                    ast.Name(id=cfg_name, ctx=ast.Load()),
                ],
                keywords=[],
            ),
            orelse=original,
        )

    def visit_Assign(self, node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return self.generic_visit(node)
        name = node.targets[0].id
        val = node.value

        # prod = mA_eff * mB_eff
        if (name == "prod"
                and isinstance(val, ast.BinOp) and isinstance(val.op, ast.Mult)
                and isinstance(val.left, ast.Name) and val.left.id == "mA_eff"
                and isinstance(val.right, ast.Name) and val.right.id == "mB_eff"):
            node.value = self._cond_call(
                "build_multiplier", "mult_cfg", "mA_eff", "mB_eff", val)
            self.mult_count += 1
            return node

        # exp_sum = eA_eff + eB_eff
        if (name == "exp_sum"
                and isinstance(val, ast.BinOp) and isinstance(val.op, ast.Add)
                and isinstance(val.left, ast.Name) and val.left.id == "eA_eff"
                and isinstance(val.right, ast.Name) and val.right.id == "eB_eff"):
            node.value = self._cond_call(
                "build_adder", "adder_cfg", "eA_eff", "eB_eff", val)
            self.add_count += 1
            return node

        return self.generic_visit(node)


def _is_module_creation(node) -> Tuple[bool, Optional[str]]:
    """Return ``(True, var_name)`` if *node* is ``var = Module(...)``."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)):
        return False, None
    func = node.value.func
    if (isinstance(func, ast.Name) and func.id == "Module") or \
       (isinstance(func, ast.Attribute) and func.attr == "Module"):
        return True, node.targets[0].id
    return False, None


def _is_io_setup(node, mod_var: str) -> bool:
    """True for ``x = mod_var.input(...)`` or ``x = mod_var.output(...)``."""
    return (isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == mod_var
            and node.value.func.attr in ("input", "output"))


def _is_to_verilog(node) -> bool:
    return (isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "to_verilog_file")


def _is_param_constant(node) -> bool:
    return (isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in _PARAM_CONSTANTS)


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

_HEADER = '''\
"""Auto-generated Component wrapper for {source_name}.

Generated by script_to_component.py from:
  {source_name}

Do not edit manually -- re-run the converter if the source script changes.
"""
from dataclasses import dataclass
from typing import Optional

from spirehdl.spirehdl_module import Component
from spirehdl.spirehdl import *
from spirehdl.optimize import flowy_optimized
from spirehdl.arithmetic.int_arithmetic_config import (
    AdderConfig,
    MultiplierConfig,
    build_adder,
    build_multiplier,
)


class FpMulComponent(Component):
    """FP multiplier component generated from {source_name}."""

    @dataclass
    class IO:
        a: Signal
        b: Signal
        y: Signal

    def __init__(
        self,
        EW: int,
        FW: int,
        *,
        subnormals: bool = True,
        always_subnormal_rounding: bool = False,
        mult_cfg: Optional[MultiplierConfig] = None,
        adder_cfg: Optional[AdderConfig] = None,
    ) -> None:
        self.EW = EW
        self.FW = FW
        self.W = 1 + EW + FW
        self.BIAS = (1 << (EW - 1)) - 1
        self.MAX_E = (1 << EW) - 1
        self.PROD_W = 2 * (FW + 1)
        self.subnormals = subnormals
        self.always_subnormal_rounding = always_subnormal_rounding
        self.mult_cfg = mult_cfg
        self.adder_cfg = adder_cfg

        self.io = self.IO(
            a=Signal(name="a", typ=UInt(self.W), kind="input"),
            b=Signal(name="b", typ=UInt(self.W), kind="input"),
            y=Signal(name="y", typ=UInt(self.W), kind="output"),
        )
        self.elaborate()

    def elaborate(self) -> None:
        EW = self.EW
        FW = self.FW
        W = self.W
        BIAS = self.BIAS
        MAX_E = self.MAX_E
        PROD_W = self.PROD_W
        mult_cfg = self.mult_cfg
        adder_cfg = self.adder_cfg
        a, b, y = self.io.a, self.io.b, self.io.y

'''


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

def convert_script_to_component(
    script_path: str,
    output_path: Optional[str] = None,
) -> str:
    """Read *script_path*, apply transforms, write a Component source file.

    Returns the path to the generated file.
    """
    src = Path(script_path).resolve()
    if output_path is None:
        dst = src.with_name(src.stem + "_component.py")
    else:
        dst = Path(output_path).resolve()

    source = src.read_text()
    tree = ast.parse(source, filename=str(src))

    # -- Classify top-level statements ---------------------------------------
    mod_var: Optional[str] = None
    logic: List[ast.stmt] = []

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if _is_param_constant(node):
            continue
        is_mod, name = _is_module_creation(node)
        if is_mod:
            mod_var = name
            continue
        if mod_var and _is_io_setup(node, mod_var):
            continue
        if _is_to_verilog(node):
            continue
        logic.append(node)

    if mod_var is None:
        raise RuntimeError(f"No Module(...) creation found in {src}")

    # -- Patch mult / add ----------------------------------------------------
    patcher = _PatchMultAdd()
    patched: List[ast.stmt] = []
    for stmt in logic:
        stmt = patcher.visit(stmt)
        ast.fix_missing_locations(stmt)
        patched.append(stmt)

    if patcher.mult_count != 1:
        raise RuntimeError(
            f"Expected exactly 1 'prod = mA_eff * mB_eff' in {src.name}, "
            f"found {patcher.mult_count}")
    if patcher.add_count != 1:
        raise RuntimeError(
            f"Expected exactly 1 'exp_sum = eA_eff + eB_eff' in {src.name}, "
            f"found {patcher.add_count}")

    # -- Generate source text ------------------------------------------------
    body_parts: List[str] = []
    for stmt in patched:
        # Add a blank line before function definitions for readability
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and body_parts:
            body_parts.append("")
        body_parts.append(ast.unparse(stmt))

    elaborate_body = "\n".join(body_parts)
    elaborate_body = textwrap.indent(elaborate_body, "        ")

    out = _HEADER.format(source_name=src.name) + elaborate_body + "\n"

    dst.write_text(out)
    print(f"Generated component: {dst}")
    return str(dst)


# ---------------------------------------------------------------------------
# Loader (for use in sweep scripts)
# ---------------------------------------------------------------------------

def _has_component_class(source: str) -> bool:
    """Return True if *source* defines a class that inherits from Component."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = None
                if isinstance(base, ast.Name):
                    name = base.id
                elif isinstance(base, ast.Attribute):
                    name = base.attr
                if name == "Component":
                    return True
    return False


def _import_module(file_path: Path, module_name: str):
    """Import *file_path* as *module_name*, registering in ``sys.modules``.

    The registration is required so the class is picklable by
    :func:`multiprocessing.Pool.map`.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _find_component_class(mod) -> type:
    """Return the first Component subclass defined in *mod*."""
    from spirehdl.spirehdl_module import Component
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if (isinstance(obj, type)
                and issubclass(obj, Component)
                and obj is not Component):
            return obj
    raise RuntimeError(f"No Component subclass found in {mod}")


def load_component_cls(script_path: str):
    """Load a Component class from *script_path*.

    Auto-detects whether the file already defines a Component subclass
    (import directly) or is a flat script that needs conversion to a
    Component via AST transformation.
    """
    src = Path(script_path).resolve()
    source = src.read_text()

    if _has_component_class(source):
        # Already a Component — import directly.
        module_name = f"_gen_{src.parent.name}_{src.stem}"
        mod = _import_module(src, module_name)
        cls = _find_component_class(mod)
        cls.__name__ = f"{cls.__name__}_{src.parent.name}"
        return cls

    # Flat script — generate a _component.py wrapper and import that.
    dst = src.with_name(src.stem + "_component.py")
    if not dst.exists():
        print(f"Component file not found, generating: {dst}")
        convert_script_to_component(str(src), str(dst))

    module_name = f"_gen_{src.stem}_component"
    mod = _import_module(dst, module_name)
    cls = mod.FpMulComponent
    cls.__name__ = f"FpMulComponent_{src.stem}"
    return cls


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <script_path> [output_path]")
        sys.exit(1)
    convert_script_to_component(
        sys.argv[1],
        sys.argv[2] if len(sys.argv) > 2 else None,
    )

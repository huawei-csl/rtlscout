"""Convert reference design scripts to Component source files.

Reads a reference design script (e.g. ``seed_seed_design_v5.py``), applies AST
transformations to make the multiplier and adder configurable, and writes a
:class:`Component` class file (auto-generated ones go to a content-keyed temp
cache; optimization decorators then use the global ``.spire_cache``).

Usage::

    python -m tech_eval.ppa_extract.sweeps.fpmul.script_to_component \\
        references/pareto_front/design_000/seed_seed_design_v5.py
"""

import ast
import hashlib
import importlib.util
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

# Top-level constants derived from EW / FW — these become computed attributes
# in the Component __init__ and are removed from the script body.
_PARAM_CONSTANTS = {"EW", "FW", "W", "BIAS", "MAX_E", "PROD_W"}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _comment_anchor_lines(source: str) -> Tuple[set, set]:
    """1-based line numbers carrying the arithmetic anchor comments.

    The benchmark library marks the two sweep targets with ``# mantissa
    multiplier`` / ``# exponent adder`` comments, and agent-written designs
    demonstrably propagate them even when they rename every operand — so the
    comments are a far more robust anchor than variable names.
    """
    mult, add = set(), set()
    for i, line in enumerate(source.splitlines(), start=1):
        if "# mantissa multiplier" in line:
            mult.add(i)
        if "# exponent adder" in line:
            add.add(i)
    return mult, add


def _self_cfg(attr: str) -> ast.expr:
    """``getattr(self, "<attr>", None)`` — cfg reference for class methods."""
    return ast.Call(
        func=ast.Name(id="getattr", ctx=ast.Load()),
        args=[ast.Name(id="self", ctx=ast.Load()),
              ast.Constant(value=attr), ast.Constant(value=None)],
        keywords=[])


class _PatchMultAdd(ast.NodeTransformer):
    """Replace the main mantissa multiply / exponent add with configurable
    ``build_multiplier`` / ``build_adder`` calls.

    Loosened matcher (2026-07-28, fpadd-style per the rerun handover): an
    assignment is patched when its value is a plain BinOp (``*`` / ``+``) and
    it either sits on a comment-anchored line (see _comment_anchor_lines) or
    assigns to a conventional target name (``prod`` / ``exp_sum`` / ``esum``).
    Operand expressions are arbitrary. The exponent-adder patch is OPTIONAL —
    some agent designs fuse the exponent add away entirely.
    """

    def __init__(self, mult_lines=frozenset(), adder_lines=frozenset(),
                 mult_cfg_expr=None, adder_cfg_expr=None):
        super().__init__()
        self.mult_lines = mult_lines
        self.adder_lines = adder_lines
        self.mult_cfg_expr = mult_cfg_expr or ast.Name(id="mult_cfg", ctx=ast.Load())
        self.adder_cfg_expr = adder_cfg_expr or ast.Name(id="adder_cfg", ctx=ast.Load())
        self.mult_count = 0
        self.add_count = 0

    @staticmethod
    def _cond_call(func_name, cfg_expr, original):
        """``func(left, right, cfg) if cfg is not None else original``"""
        import copy
        return ast.IfExp(
            test=ast.Compare(
                left=copy.deepcopy(cfg_expr),
                ops=[ast.IsNot()],
                comparators=[ast.Constant(value=None)],
            ),
            body=ast.Call(
                func=ast.Name(id=func_name, ctx=ast.Load()),
                args=[copy.deepcopy(original.left),
                      copy.deepcopy(original.right),
                      copy.deepcopy(cfg_expr)],
                keywords=[],
            ),
            orelse=original,
        )

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            return self.generic_visit(node)
        tgt = node.targets[0]
        tname = tgt.id if isinstance(tgt, ast.Name) else None
        val = node.value
        if not isinstance(val, ast.BinOp):
            return self.generic_visit(node)

        if isinstance(val.op, ast.Mult) and (
                node.lineno in self.mult_lines or tname == "prod"):
            node.value = self._cond_call("build_multiplier", self.mult_cfg_expr, val)
            self.mult_count += 1
            return node

        if isinstance(val.op, ast.Add) and (
                node.lineno in self.adder_lines or tname in ("exp_sum", "esum")):
            node.value = self._cond_call("build_adder", self.adder_cfg_expr, val)
            self.add_count += 1
            return node

        return self.generic_visit(node)

    def visit_AugAssign(self, node):
        # Wire-drive form (2026-07-30): agents following the explicit-Wire
        # cut-point hint write the anchored multiply/add as
        # ``prod_w <<= a * b  # mantissa multiplier`` — an AugAssign with
        # LShift. Patch its RHS exactly like the plain-assignment form.
        if not isinstance(node.op, ast.LShift) or not isinstance(node.value, ast.BinOp):
            return self.generic_visit(node)
        val = node.value
        tname = node.target.id if isinstance(node.target, ast.Name) else None

        if isinstance(val.op, ast.Mult) and (
                node.lineno in self.mult_lines or tname == "prod"):
            node.value = self._cond_call("build_multiplier", self.mult_cfg_expr, val)
            self.mult_count += 1
            return node

        if isinstance(val.op, ast.Add) and (
                node.lineno in self.adder_lines or tname in ("exp_sum", "esum")):
            node.value = self._cond_call("build_adder", self.adder_cfg_expr, val)
            self.add_count += 1
            return node

        return self.generic_visit(node)


def _check_patch_counts(patcher: "_PatchMultAdd", name: str) -> None:
    """Exactly one multiplier patch is required; the adder patch is optional
    (0 is a warning — some designs fuse the exponent add), >1 is ambiguous."""
    if patcher.mult_count != 1:
        raise RuntimeError(
            f"Expected exactly 1 main mantissa multiply in {name}, "
            f"found {patcher.mult_count} (anchor: '# mantissa multiplier' "
            f"comment or 'prod = <a> * <b>')")
    if patcher.add_count > 1:
        raise RuntimeError(
            f"Ambiguous exponent adder in {name}: {patcher.add_count} matches")
    if patcher.add_count == 0:
        print(f"WARNING: no exponent-adder statement found in {name} — "
              f"adder_cfg will be inert for this design (fused exponent path)")


_CLASS_WRAPPER = '''

# ---- auto-generated sweep wrapper (canonical config signature) ----
from spire.arithmetic.int_arithmetic_config import (
    AdderConfig, MultiplierConfig, build_adder, build_multiplier)
import inspect as _inspect


class FpMulSwept({orig_cls}):
    """{orig_cls} with the sweep's canonical constructor. mult_cfg/adder_cfg
    reach the patched arithmetic via self.sweep_mult_cfg/self.sweep_adder_cfg;
    remaining kwargs are forwarded only if {orig_cls}.__init__ accepts them."""

    def __init__(self, EW=5, FW=10, subnormals=True,
                 always_subnormal_rounding=False, mult_cfg=None, adder_cfg=None):
        self.sweep_mult_cfg = mult_cfg
        self.sweep_adder_cfg = adder_cfg
        _params = _inspect.signature({orig_cls}.__init__).parameters
        _kw = {{k: v for k, v in dict(
            EW=EW, FW=FW, subnormals=subnormals,
            always_subnormal_rounding=always_subnormal_rounding,
            mult_cfg=mult_cfg, adder_cfg=adder_cfg).items() if k in _params}}
        super().__init__(**_kw)
'''


def _find_class_def(tree: ast.Module) -> Tuple[Optional[str], bool]:
    """(class name, delegates) for the first Component subclass. ``delegates``
    is True when the class has bases besides Component (e.g.
    ``class FpMulInit(FpMulSN, Component)``) — such classes inherit a natively
    configurable __init__ and must be imported directly, not converted."""
    # Top-level classes only: a class nested inside a function cannot be
    # subclassed or imported at module scope (agent scripts sometimes define
    # the component inside a build() factory).
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            names = [b.id if isinstance(b, ast.Name) else
                     (b.attr if isinstance(b, ast.Attribute) else None)
                     for b in node.bases]
            if "Component" in names:
                return node.name, any(n != "Component" for n in names)
    return None, False


def _stmt_elaborates(node: ast.stmt, cls_name: str) -> bool:
    """True for top-level statements that would elaborate or write files on
    import (``m = Cls(...).to_module(...)``, ``m.to_verilog_file(...)``)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Name) and f.id == cls_name:
                return True
            if isinstance(f, ast.Attribute) and f.attr in (
                    "to_module", "to_netlist", "to_verilog", "to_verilog_file"):
                return True
    return False


def convert_class_script_to_component(src_path: str, dst_path: str) -> str:
    """Convert a Component-class design script into a sweepable module:
    patch the main arithmetic (self.sweep_*_cfg-guarded build_* calls), strip
    module-level elaboration, and append an FpMulSwept wrapper class with the
    sweep's canonical constructor."""
    src, dst = Path(src_path), Path(dst_path)
    source = src.read_text()
    tree = ast.parse(source, filename=str(src))
    cls_name, _ = _find_class_def(tree)
    if cls_name is None:
        raise RuntimeError(f"No Component subclass found in {src}")

    patcher = _PatchMultAdd(*_comment_anchor_lines(source),
                            mult_cfg_expr=_self_cfg("sweep_mult_cfg"),
                            adder_cfg_expr=_self_cfg("sweep_adder_cfg"))
    tree = patcher.visit(tree)
    ast.fix_missing_locations(tree)
    _check_patch_counts(patcher, src.name)

    tree.body = [n for n in tree.body if not _stmt_elaborates(n, cls_name)]
    out = (f'"""Auto-generated sweepable module from {src.name} — do not edit."""\n'
           + ast.unparse(tree) + "\n"
           + _CLASS_WRAPPER.format(orig_cls=cls_name))
    dst.write_text(out)
    print(f"Generated component (class path): {dst}")
    return str(dst)


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

from spire import Component
from spire.expr import *
from spire.optimize import flowy_optimized
from spire.arithmetic.int_arithmetic_config import (
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
    patcher = _PatchMultAdd(*_comment_anchor_lines(source))
    patched: List[ast.stmt] = []
    for stmt in logic:
        stmt = patcher.visit(stmt)
        ast.fix_missing_locations(stmt)
        patched.append(stmt)

    _check_patch_counts(patcher, src.name)

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
    for node in tree.body:          # top-level only (see _find_class_def)
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
    from spire import Component
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if (isinstance(obj, type)
                and issubclass(obj, Component)
                and obj is not Component):
            return obj
    raise RuntimeError(f"No Component subclass found in {mod}")


def _component_cache_path(src: Path, source: str) -> Path:
    """Content-keyed temp cache path for a generated *_component.py."""
    key = hashlib.sha256(source.encode()).hexdigest()[:16]
    d = Path(tempfile.gettempdir()) / "tech_eval_components"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{src.stem}_{key}_component.py"


def load_component_cls(script_path: str):
    """Load a Component class from *script_path*.

    Auto-detects whether the file already defines a Component subclass
    (import directly) or is a flat script that needs conversion to a
    Component via AST transformation.
    """
    src = Path(script_path).resolve()
    source = src.read_text()

    if _has_component_class(source):
        _, delegates = _find_class_def(ast.parse(source))
        if delegates:
            # Inherits a configurable library class (e.g. FpMulSN) — the
            # canonical constructor comes for free; import directly.
            module_name = f"_gen_{src.parent.name}_{src.stem}"
            mod = _import_module(src, module_name)
            cls = _find_component_class(mod)
            cls.__name__ = f"{cls.__name__}_{src.parent.name}"
            return cls
        # Bare Component subclass (spire-era agent designs). Direct import is
        # NOT sweepable — the agent's own __init__ knows nothing of
        # mult_cfg/adder_cfg — so convert: patch arithmetic + append the
        # FpMulSwept wrapper (2026-07-28; previously imported unpatched).
        dst = _component_cache_path(src, source)
        if not dst.exists():
            convert_class_script_to_component(str(src), str(dst))
        module_name = f"_gen_{src.parent.name}_{src.stem}_component"
        mod = _import_module(dst, module_name)
        cls = mod.FpMulSwept
        cls.__name__ = f"FpMulSwept_{src.parent.name}"
        return cls

    # Flat script — generate a _component.py wrapper and import that.
    dst = _component_cache_path(src, source)
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

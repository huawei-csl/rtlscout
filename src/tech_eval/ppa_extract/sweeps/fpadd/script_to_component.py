"""Load and patch FP adder designs for architecture sweep.

All fpadd Pareto designs are Component subclasses with the pattern:
    mant_add = m_big_ext + m_small_shift

This module patches that single addition to use build_adder when an
adder_cfg is provided, and loads the resulting class for sweep configs.
"""

import ast
import importlib.util
import sys
import textwrap
from pathlib import Path
from typing import Optional


class _PatchMantAdd(ast.NodeTransformer):
    """Replace ``mant_add = m_big_ext + m_small_shift``
    with ``build_adder(m_big_ext, m_small_shift, self.adder_cfg) if self.adder_cfg ...``."""

    def __init__(self):
        super().__init__()
        self.patch_count = 0

    def visit_Assign(self, node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return self.generic_visit(node)
        name = node.targets[0].id
        val = node.value

        # mant_add = m_big_ext + m_small_shift
        if (name == "mant_add"
                and isinstance(val, ast.BinOp) and isinstance(val.op, ast.Add)):
            # Replace with: build_adder(...) if self.adder_cfg is not None else original
            node.value = ast.IfExp(
                test=ast.Compare(
                    left=ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr="adder_cfg",
                        ctx=ast.Load(),
                    ),
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=None)],
                ),
                body=ast.Call(
                    func=ast.Name(id="build_adder", ctx=ast.Load()),
                    args=[val.left, val.right,
                          ast.Attribute(
                              value=ast.Name(id="self", ctx=ast.Load()),
                              attr="adder_cfg",
                              ctx=ast.Load(),
                          )],
                    keywords=[],
                ),
                orelse=val,
            )
            ast.fix_missing_locations(node)
            self.patch_count += 1
            return node

        return self.generic_visit(node)


class _AddAdderCfgParam(ast.NodeTransformer):
    """Add ``adder_cfg=None`` parameter to Component __init__ and store as self.adder_cfg."""

    def __init__(self):
        super().__init__()
        self.patched_init = False

    def visit_FunctionDef(self, node):
        if node.name != "__init__":
            return self.generic_visit(node)

        # Check if adder_cfg param already exists
        existing_args = {arg.arg for arg in node.args.args}
        if "adder_cfg" not in existing_args:
            # Add adder_cfg=None parameter
            node.args.args.append(ast.arg(arg="adder_cfg", annotation=None))
            node.args.defaults.append(ast.Constant(value=None))

        # Add self.adder_cfg = adder_cfg before self.elaborate()
        store_stmt = ast.parse("self.adder_cfg = adder_cfg").body[0]
        # Insert before the last statement (which is typically self.elaborate())
        insert_pos = len(node.body) - 1
        for i, stmt in enumerate(node.body):
            if (isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Attribute)
                    and stmt.value.func.attr == "elaborate"):
                insert_pos = i
                break
        node.body.insert(insert_pos, store_stmt)
        ast.fix_missing_locations(node)
        self.patched_init = True
        return node


def patch_fpadd_source(source: str, filename: str = "<fpadd>") -> str:
    """Patch an FpAdd Component source to accept adder_cfg and use build_adder.

    Returns the modified source text.
    """
    tree = ast.parse(source, filename=filename)

    # Add import for build_adder at the top
    import_node = ast.parse(
        "from spirehdl.arithmetic.int_arithmetic_config import AdderConfig, build_adder"
    ).body[0]
    # Insert after existing imports
    insert_idx = 0
    for i, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_idx = i + 1
    tree.body.insert(insert_idx, import_node)

    # Patch __init__ to accept adder_cfg
    init_patcher = _AddAdderCfgParam()
    tree = init_patcher.visit(tree)
    if not init_patcher.patched_init:
        raise RuntimeError(f"No __init__ found to patch in {filename}")

    # Patch mant_add = m_big_ext + m_small_shift
    mant_patcher = _PatchMantAdd()
    tree = mant_patcher.visit(tree)
    if mant_patcher.patch_count == 0:
        raise RuntimeError(
            f"No 'mant_add = m_big_ext + m_small_shift' found in {filename}")

    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _import_from_source(source_text: str, file_path: Path, module_name: str):
    """Import a module from source text, writing to a temp file next to the original."""
    dst = file_path.with_name(file_path.stem + "_adder_sweep.py")
    dst.write_text(source_text)

    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(dst))
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


def load_fpadd_component_cls(script_path: str):
    """Load an FpAdd Component class from *script_path*, patched with adder_cfg support.

    The returned class accepts ``adder_cfg`` as a keyword argument in __init__.
    """
    src = Path(script_path).resolve()
    source = src.read_text()

    patched_source = patch_fpadd_source(source, filename=str(src))

    module_name = f"_gen_fpadd_{src.parent.name}_{src.stem}"
    mod = _import_from_source(patched_source, src, module_name)
    cls = _find_component_class(mod)
    cls.__name__ = f"{cls.__name__}_{src.parent.name}"
    return cls

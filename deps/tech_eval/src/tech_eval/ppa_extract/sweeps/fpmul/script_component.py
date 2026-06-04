"""Auto-wrap reference design scripts as Components via AST patching.

Reads a reference ``references/design_vXX.py`` script, patches the mantissa
multiplier and exponent adder lines to use configurable implementations, then
executes the script to obtain a Module which is converted to a Component.
"""

import ast
from pathlib import Path

from spirehdl.arithmetic.int_arithmetic_config import (
    build_adder,
    build_multiplier,
)


# ---------------------------------------------------------------------------
# AST transformer
# ---------------------------------------------------------------------------

class FpMulPatcher(ast.NodeTransformer):
    """Patch ``prod = mA_eff * mB_eff`` and ``exp_sum = eA_eff + eB_eff``
    in a reference design script, and strip ``to_verilog_file`` calls."""

    def __init__(self):
        super().__init__()
        self.mult_count = 0
        self.add_count = 0

    # -- helpers to build AST nodes ------------------------------------------

    @staticmethod
    def _name(id: str) -> ast.Name:
        return ast.Name(id=id, ctx=ast.Load())

    @staticmethod
    def _is_binop(node, left_id: str, op_type, right_id: str) -> bool:
        return (
            isinstance(node, ast.BinOp)
            and isinstance(node.left, ast.Name) and node.left.id == left_id
            and isinstance(node.op, op_type)
            and isinstance(node.right, ast.Name) and node.right.id == right_id
        )

    def _make_conditional_call(
        self, func_name: str, cfg_name: str, left_id: str, right_id: str, original: ast.BinOp,
    ) -> ast.IfExp:
        """Build: ``func(left, right, cfg) if cfg is not None else left <op> right``"""
        return ast.IfExp(
            test=ast.Compare(
                left=self._name(cfg_name),
                ops=[ast.IsNot()],
                comparators=[ast.Constant(value=None)],
            ),
            body=ast.Call(
                func=self._name(func_name),
                args=[self._name(left_id), self._name(right_id), self._name(cfg_name)],
                keywords=[],
            ),
            orelse=original,
        )

    # -- visitors ------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target = node.targets[0].id

            # T1: prod = mA_eff * mB_eff
            if target == "prod" and self._is_binop(node.value, "mA_eff", ast.Mult, "mB_eff"):
                node.value = self._make_conditional_call(
                    "build_multiplier", "mult_cfg", "mA_eff", "mB_eff", node.value,
                )
                self.mult_count += 1
                return node

            # T2: exp_sum = eA_eff + eB_eff
            if target == "exp_sum" and self._is_binop(node.value, "eA_eff", ast.Add, "eB_eff"):
                node.value = self._make_conditional_call(
                    "build_adder", "adder_cfg", "eA_eff", "eB_eff", node.value,
                )
                self.add_count += 1
                return node

        return self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
        # T3: remove *.to_verilog_file(...) calls
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "to_verilog_file"
        ):
            return None  # remove node
        return self.generic_visit(node)


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

def _run_patched_script(script_path: str, mult_cfg, adder_cfg):
    """Read, AST-patch, and execute a reference design script.

    Returns the Module ``m`` produced by the script.
    """
    source = Path(script_path).read_text()
    tree = ast.parse(source, filename=script_path)

    patcher = FpMulPatcher()
    tree = patcher.visit(tree)
    ast.fix_missing_locations(tree)

    if patcher.mult_count != 1:
        raise RuntimeError(
            f"Expected exactly 1 'prod = mA_eff * mB_eff' in {script_path}, "
            f"found {patcher.mult_count}"
        )
    if patcher.add_count != 1:
        raise RuntimeError(
            f"Expected exactly 1 'exp_sum = eA_eff + eB_eff' in {script_path}, "
            f"found {patcher.add_count}"
        )

    code = compile(tree, script_path, "exec")

    ns = {
        "__builtins__": __builtins__,
        "mult_cfg": mult_cfg,
        "adder_cfg": adder_cfg,
        "build_multiplier": build_multiplier,
        "build_adder": build_adder,
    }
    exec(code, ns)

    if "m" not in ns:
        raise RuntimeError(f"Script {script_path} did not produce a module 'm'")
    return ns["m"]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_script_component_cls(script_path: str):
    """Return a callable compatible with ``InstanceConfig(impl_cls=...)``.

    The returned factory, when called with ``FpMulCfg`` fields, executes the
    reference script with AST-patched mult/add lines and returns a Component.
    """
    resolved = str(Path(script_path).resolve())

    def factory(
        EW,
        FW,
        *,
        subnormals=True,
        always_subnormal_rounding=False,
        mult_cfg=None,
        adder_cfg=None,
    ):
        m = _run_patched_script(resolved, mult_cfg, adder_cfg)
        return m.to_component()

    factory.__name__ = f"ScriptComponent_{Path(script_path).stem}"
    return factory

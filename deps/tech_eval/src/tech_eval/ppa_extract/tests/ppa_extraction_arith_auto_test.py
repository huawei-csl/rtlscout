"""PPA extraction for a multiplier using spirehdl's
``ArithmeticAutoConfig`` optimiser.

The component below declares ``y = a * b`` as a plain ``Op2<*>`` node.
``replace_arithmetic_ops`` then rewrites the multiply into a StageBased
multiplier whose PPG/PPA/FSA choices come from the evaluation database
for the requested objective (``area`` / ``delay`` / ``adp``). Each
objective is then run through ``get_ppa`` at several target delays, and
the resulting (delay, area) points are plotted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from spirehdl.aggregate.aggregate_record import AggregateRecord
from spirehdl.arithmetic.int_arithmetic_config import (
    ArithmeticAutoConfig,
    replace_arithmetic_ops,
)
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    TwoInputAritEncodings,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import (
    Encoding,
    MultiplierTestVectors,
)
from spirehdl.arithmetic.int_multipliers.multipliers.multiplier_stage_core import (
    StageBasedMultiplierIO,
)
from spirehdl.spirehdl import Signal, UInt, reset_shared_cache
from spirehdl.spirehdl_module import Component

from tech_eval.int_tb_sim import TwInputArit, generate_vectors, run_component_with_vectors
from tech_eval.ppa_extract.core.ppa_extraction import get_ppa


A_W = 5
B_W = A_W
Y_W = A_W + B_W  # 16-bit product


class Mul(Component):
    """Plain ``y = a * b`` component with ``A_W``-bit × ``B_W``-bit inputs.

    The multiply is left as an ``Op2<*>`` node so that
    ``replace_arithmetic_ops`` can substitute it with a StageBased
    multiplier picked by the evaluation database.
    """

    def __init__(self) -> None:
        self.io = StageBasedMultiplierIO(
            a=Signal(name="a", typ=UInt(A_W), kind="input"),
            b=Signal(name="b", typ=UInt(B_W), kind="input"),
            y=Signal(name="y", typ=UInt(Y_W), kind="output"),
        )
        self.elaborate()

    def elaborate(self) -> None:
        self.io.y <<= self.io.a * self.io.b


@dataclass
class SquarerIO(AggregateRecord):
    a: Signal
    y: Signal


class Squarer(Component):
    """``y = a * a`` — shares both multiplier operands so synthesis can
    exploit the partial-product symmetry (``a[i]*a[j] == a[j]*a[i]``).

    The test checks whether the optimiser + downstream synthesis actually
    collapse the duplicate partial products and end up smaller than a
    plain multiplier of the same width.
    """

    def __init__(self) -> None:
        self.io = SquarerIO(
            a=Signal(name="a", typ=UInt(A_W), kind="input"),
            y=Signal(name="y", typ=UInt(Y_W), kind="output"),
        )
        self.elaborate()

    def elaborate(self) -> None:
        self.io.y <<= self.io.a * self.io.a


def _generate_squarer_vectors(num_vectors: int, a_w: int):
    """Plain ``(a, a*a)`` vectors for the single-input squarer."""
    rng = np.random.default_rng(0xC0FFEE)
    vecs = []
    for i in range(num_vectors):
        a = int(rng.integers(0, 1 << a_w))
        vecs.append((f"sq_{i}", {"a": a}, {"y": a * a}))
    return vecs


def _build_optimised_module(factory: Callable[[], Component], objective: str, module_name: str):
    """Construct a fresh component, optionally apply the auto-optimiser.

    ``objective == "none"`` skips ``replace_arithmetic_ops`` entirely so the
    emitted Verilog keeps the raw ``*`` operator and the downstream
    synthesiser decides the implementation on its own.
    """
    reset_shared_cache()
    comp = factory()
    if objective != "none":
        replace_arithmetic_ops(comp, ArithmeticAutoConfig(objective=objective))
    return comp, comp.to_module(module_name, with_clock=True)


def _prepare_design(
    design_label: str,
    factory: Callable[[], Component],
    vectors,
    objective: str,
    out_root: str,
) -> dict:
    """Phase 1 (sequential): build component, simulate, return paths."""
    module_name = f"{design_label}_{objective}"
    worker_path = os.path.join(out_root, f"worker_{design_label}_{objective}")
    os.makedirs(worker_path, exist_ok=True)

    comp, _module = _build_optimised_module(factory, objective, module_name)

    sim_result = run_component_with_vectors(
        comp,
        vectors,
        module_name=module_name,
        tb_from_data=True,
        save_vcd=False,
        worker_path=worker_path,
    )

    return {
        "design_label": design_label,
        "objective": objective,
        "rtl_path": sim_result["verilog_filename"],
        "top_module_name": sim_result["module_name"],
        "tb_filename": sim_result["tb_filename"],
        "tb_name": sim_result["tb_name"],
        "worker_path": worker_path,
    }


def _run_single_ppa(args: tuple) -> dict:
    """Phase 2 worker: single ``get_ppa`` call."""
    info, target_delay = args
    worker_path = os.path.join(info["worker_path"], f"td_{target_delay}")
    os.makedirs(worker_path, exist_ok=True)
    ppa = get_ppa(
        rtl_path=info["rtl_path"],
        target_delay=target_delay,
        worker_path=worker_path,
        top_module_name=info["top_module_name"],
        run_verilator=True,
        tb_filename=info["tb_filename"],
        tb_name=info["tb_name"],
        save_vcd=False,
        use_vcd_for_power=False,
    )
    ppa["objective"] = info["objective"]
    ppa["design"] = info["design_label"]
    print(
        f"[{info['design_label']}/{info['objective']}] target={target_delay}ps  "
        f"delay={ppa['delay']:.1f}ps  area={ppa['area']:.1f}  "
        f"slack={ppa['worst_slack']:.1f}ps"
    )
    return ppa


def _plot_area_vs_delay(
    all_results: Dict[Tuple[str, str], List[dict]], out_path: str
) -> None:
    """Plot area vs delay. Optimised objectives (area/delay/adp) are merged
    into a single 'optimized' series per design; 'none' becomes 'raw *'."""
    fig, ax = plt.subplots(figsize=(7, 5))
    linestyles = {"mul": "-", "squarer": "--"}
    markers = {"mul": "o", "squarer": "s"}
    class_colors = {"raw *": "tab:gray", "optimized": "tab:blue"}

    # Merge objective results per (design, class)
    merged: Dict[Tuple[str, str], List[dict]] = {}
    for (design_label, objective), results in all_results.items():
        cls = "raw *" if objective == "none" else "optimized"
        key = (design_label, cls)
        merged.setdefault(key, []).extend(results)

    # Deduplicate identical (delay, area) points within each series
    for key, results in merged.items():
        seen = set()
        deduped = []
        for r in results:
            pt = (r["delay"], r["area"])
            if pt not in seen:
                seen.add(pt)
                deduped.append(r)
        deduped.sort(key=lambda r: r["delay"])
        merged[key] = deduped

    for (design_label, cls), results in merged.items():
        xs = [r["delay"] for r in results]
        ys = [r["area"] for r in results]
        ax.plot(
            xs, ys,
            marker=markers.get(design_label, "o"),
            color=class_colors.get(cls, "black"),
            linestyle=linestyles.get(design_label, "-"),
            label=f"{design_label} / {cls}",
        )

    ax.set_xlabel("Delay (ps)")
    ax.set_ylabel("Area")
    ax.set_title(
        f"Mul {A_W}x{B_W} vs Squarer {A_W}\u00b2 \u2014 raw * vs spirehdl-optimized"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved plot to {out_path}")


def test_arith_auto_config_ppa_sweep() -> None:
    from multiprocessing import Pool

    objectives = ["none", "area", "delay", "adp"]
    target_delays = [80, 200, 300, 400]
    n_processes = 16

    out_root = os.path.join("results", "ppa_arith_auto")
    os.makedirs(out_root, exist_ok=True)

    mul_vectors = generate_vectors(
        vec_cls=MultiplierTestVectors,
        encodings=TwoInputAritEncodings.with_enc(Encoding.unsigned),
        sigma=None,
        widths=TwInputArit(a_w=A_W, b_w=B_W),
        num_vectors=256,
        y_w=Y_W,
    )
    squarer_vectors = _generate_squarer_vectors(num_vectors=256, a_w=A_W)

    designs: List[Tuple[str, Callable[[], Component], list]] = [
        ("mul", Mul, mul_vectors),
        ("squarer", Squarer, squarer_vectors),
    ]

    # Phase 1 (sequential): build + simulate each (design, objective)
    prepared: List[dict] = []
    for design_label, factory, vectors in designs:
        for objective in objectives:
            info = _prepare_design(design_label, factory, vectors, objective, out_root)
            prepared.append(info)

    # Phase 2 (parallel): run get_ppa for every (design, objective, target_delay)
    pool_args = [
        (info, td)
        for info in prepared
        for td in target_delays
    ]
    with Pool(processes=n_processes) as pool:
        ppa_results = pool.map(_run_single_ppa, pool_args)

    # Organise results back into {(design, objective): [ppa_per_delay]}
    all_results: Dict[Tuple[str, str], List[dict]] = {}
    for ppa in ppa_results:
        key = (ppa["design"], ppa["objective"])
        all_results.setdefault(key, []).append(ppa)
    for v in all_results.values():
        v.sort(key=lambda r: r["target_delay"])

    _plot_area_vs_delay(all_results, os.path.join(out_root, "area_vs_delay.png"))

    print()
    print(f"=== Squarer vs Mul at target_delay={target_delays[-1]}ps ===")
    for cls_label, obj_list in [("raw *", ["none"]), ("optimized", ["area", "delay", "adp"])]:
        mul_areas = [all_results[("mul", o)][-1]["area"] for o in obj_list]
        sq_areas = [all_results[("squarer", o)][-1]["area"] for o in obj_list]
        mul_a = min(mul_areas)
        sq_a = min(sq_areas)
        pct = 100.0 * (sq_a - mul_a) / mul_a
        print(
            f"  {cls_label:<12s}  "
            f"mul_area={mul_a:.1f}  "
            f"sq_area={sq_a:.1f}  "
            f"diff={pct:+.1f}%"
        )


if __name__ == "__main__":
    test_arith_auto_config_ppa_sweep()

import os

import matplotlib.pyplot as plt
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    PPAOption,
    PPGOption,
    MultiplierOption
)
from spirehdl.arithmetic.int_multipliers.multipliers.multiplier_stage_core import (
    StageBasedMultiplierBasic,
)

from tech_eval.ppa_extract.core.ppa_extraction import get_ppa_multiprocess, get_target_delay


def run_ppa_mp():
    n_bits = 16
    signed = False

    mult_cls = MultiplierOption.STAGE_BASED_MULTIPLIER.value
    mult = mult_cls(
        a_w=n_bits,
        b_w=n_bits,
        optim_type="area",
        ppg_cls=PPGOption.AND.value,
        ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
        fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
    )

    module = mult.to_module(f"Mul{n_bits}", with_clock=True)

    rtl_path = "int_multiplier.v"
    module.to_verilog_file(rtl_path)
    top_module_name = module.name

    target_delays = get_target_delay(n_bits)

    results = get_ppa_multiprocess(
        rtl_path=rtl_path,
        target_delays=target_delays,
        worker_base_path="worker_ppa_mp",
        keep_files=False,
        top_module_name=top_module_name,
    )

    if not results:
        print("No results generated.")
        return

    areas = [r["area"] for r in results]
    delays = [r["delay"] for r in results]

    os.makedirs("results/ppa", exist_ok=True)
    out_path = os.path.join("results", "ppa", f"{top_module_name}_area_vs_delay.png")

    plt.figure(figsize=(5, 4))
    plt.scatter(areas, delays, color="tab:blue")
    for a, d, t in zip(areas, delays, target_delays):
        plt.annotate(f"t={t}", (a, d), textcoords="offset points", xytext=(5, 5), fontsize=8)
    plt.title(f"{n_bits}b Mult - Delay vs Area")
    plt.xlabel("Area (um^2)")
    plt.ylabel("Delay (ns)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

    print(f"Saved plot to {out_path}")
    for res in results:
        print(res)


if __name__ == "__main__":
    run_ppa_mp()

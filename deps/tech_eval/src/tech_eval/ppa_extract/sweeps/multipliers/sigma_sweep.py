import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tech_eval.int_tb_sim import TwInputArit, generate_vectors, run_component_with_vectors
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    Encoding,
    FSAOption,
    PPAOption,
    PPGOption,
    MultiplierOption,
    TwoInputAritEncodings,
    MultiplierTestVectors,
)
from spirehdl.arithmetic.int_multipliers.multipliers.multiplier_stage_core import (
    StageBasedMultiplierBasic,
)

from tech_eval.ppa_extract.core.ppa_extraction import get_ppa, remove_worker_path


def _sigma_values(start: float = 0.0, stop: float = 8.0, step: float = 0.5):
    return [round(start + i * step, 2) for i in range(int((stop - start) / step) + 1)]


def run_sigma_sweep_and_plot():
    n_bits = 4
    #encoding = Encoding.twos_complement # choose between Encoding.unsigned, Encoding.twos_complement, Encoding.sign_magnitude
    #encoding_output = encoding
    encoding = Encoding.sign_magnitude_ext
    encoding_output =  Encoding.twos_complement
    tb_from_data = True
    target_delay = 1200  # ps
    worker_base = "worker_sigma"
    keep_files = False
    
    num_vectors = 1000
    step = 2.0

    os.makedirs(worker_base, exist_ok=True)

    input_widths = TwInputArit(a_w=n_bits, b_w=n_bits)
    encodings = TwoInputAritEncodings.with_enc(encoding).set_output(encoding_output)
    # might want to use functionfrom sporuthdl library: 
    #   def encoding_for_multiplier(multiplier_cls: type[StageBasedMultiplierBase]) -> List[TwoInputAritEncodings]:

    if encoding in (Encoding.twos_complement, Encoding.unsigned) and encoding_output == encoding:
        signed = True if encoding == Encoding.twos_complement else False

        mult = StageBasedMultiplierBasic(
            a_w=n_bits,
            b_w=n_bits,
            signed_a=signed,
            signed_b=signed,
            optim_type="speed",
            ppg_cls=PPGOption.BAUGH_WOOLEY.value,
            ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
            fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
        )
    elif encoding == Encoding.sign_magnitude and encoding_output == encoding:  
        mult = MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_MULTIPLIER.value(
            a_w=n_bits,
            b_w=n_bits,
            a_encoding = encodings.a,
            b_encoding = encodings.b,
            optim_type="speed",
            ppg_cls=PPGOption.AND.value,
            ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
            fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
        )
    elif encoding == Encoding.sign_magnitude_ext and encoding_output == encoding:  
        mult = MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_MULTIPLIER.value(
            a_w=n_bits,
            b_w=n_bits,
            a_encoding = encodings.a,
            b_encoding = encodings.b,
            optim_type="speed",
            ppg_cls=PPGOption.AND.value,
            ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
            fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
        )
    elif encoding == Encoding.sign_magnitude and encoding_output == Encoding.twos_complement:  
        mult = MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_TO_TWOS_COMPLEMENT_MULTIPLIER.value(
            a_w=n_bits,
            b_w=n_bits,
            a_encoding = encodings.a,
            b_encoding = encodings.b,
            optim_type="speed",
            ppg_cls=PPGOption.AND.value,
            ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
            fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
        )
    elif encoding == Encoding.sign_magnitude_ext and encoding_output == Encoding.twos_complement: 
        mult = MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_TO_TWOS_COMPLEMENT_MULTIPLIER.value(
            a_w=n_bits,
            b_w=n_bits,
            a_encoding = encodings.a,
            b_encoding = encodings.b,
            optim_type="speed",
            ppg_cls=PPGOption.AND.value,
            ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
            fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
        )
    else:
        raise ValueError(f"Unsupported encoding: {encoding}")

    sigma_vals = _sigma_values(step=step)
    ppa_results = []
    powers = []

    for sigma in sigma_vals:
        print(f"Running sigma={sigma:.2f}...")
        worker_path = os.path.join(worker_base, f"sigma_{sigma:.1f}".replace(".", "_"))
        os.makedirs(worker_path, exist_ok=True)

        vectors = generate_vectors(
            vec_cls=MultiplierTestVectors,
            encodings=encodings,
            sigma=sigma,
            widths=input_widths,
            num_vectors=num_vectors,
            y_w=mult.io.y.typ.width,
        )

        module_name = f"Mul{n_bits}"
        sim_result = run_component_with_vectors(
            mult,
            vectors,
            module_name=module_name,
            decoder=None,
            tb_from_data=tb_from_data,
            worker_path=worker_path,
        )


        use_vcd_for_power = True

        ppa = get_ppa(
            rtl_path=sim_result["verilog_filename"],
            target_delay=target_delay,
            worker_path=worker_path,
            top_module_name=sim_result["module_name"],
            run_verilator=True,
            tb_filename=sim_result["tb_filename"],
            tb_name=sim_result["tb_name"],
            use_vcd_for_power=use_vcd_for_power,
            save_vcd=use_vcd_for_power,
        )
        remove_worker_path(worker_path)
        ppa["sigma"] = sigma
        ppa_results.append(ppa)
        powers.append(ppa["power"])

    plot_path = os.path.join(worker_base, "power_vs_sigma.png")
    plt.figure(figsize=(6, 4))
    plt.plot(sigma_vals, [p*1000 for p in powers], marker="o")
    plt.xlabel("Sigma [LSB]")
    plt.ylabel("Power [mW]")
    # newline in title for better fit
    #plt.title(f"Power vs sigma: {module_name} with multipler {type(mult).__name__} and {encoding.name} encoding ", fontsize=8)
    plt.title(f"Power vs sigma:\n{module_name} with {type(mult).__name__}, {encoding.name}", fontsize=8)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(plot_path)

    return {
        "ppa_results": ppa_results,
        "plot_path": plot_path,
    }


if __name__ == "__main__":
    result = run_sigma_sweep_and_plot()
    print(f"Saved power vs sigma plot to {result['plot_path']}")
    for entry in result["ppa_results"]:
        print(f"sigma={entry['sigma']:.2f}, power={entry['power']}")

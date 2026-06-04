import os
from dataclasses import dataclass
from multiprocessing import Pool
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tech_eval.int_tb_sim import TwInputArit, run_component_with_vectors

from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    PPAOption,
    PPGOption,
    MultiplierOption,
    TwoInputAritEncodings,
    MultiplierTestVectors,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import (
    Encoding as VecEncoding,
    EncoderDecoderTestVectors,
)

from spirehdl.arithmetic.encoding.sign_magnitude import TwosComplementToSignMagnitudeEncoder
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    encoding_for_multiplier,
)

from tech_eval.ppa_extract.core.ppa_extraction import get_ppa, remove_worker_path
from spirehdl.spirehdl import reset_shared_cache
from spirehdl.helpers import  refactor_module_to_aig

CASE_MULTIPLIER = "multiplier"
CASE_ENCODER = "encoder"


def _sigma_values(start: float = 0.0, stop: float = 8.0, step: float = 0.5):
    return [round(start + i * step, 2) for i in range(int((stop - start) / step) + 1)]


def _get_ppa(
    comp,
    vectors,
    *,
    module_name: str,
    tb_from_data: bool,
    target_delay: int,
    worker_path: str,
):
    sim_result = run_component_with_vectors(
        comp,
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
    return ppa


@dataclass(frozen=True)
class CaseSpec:
    name: str
    case_type: str
    multiplier_option: Optional[MultiplierOption] = None
    encoder_input_encoding: Optional[VecEncoding] = None
    encoder_output_encoding: Optional[VecEncoding] = None
    encoder_clip_most_negative: Optional[bool] = None


def make_multiplier_case(opt: MultiplierOption) -> CaseSpec:
    return CaseSpec(name=opt.name, case_type=CASE_MULTIPLIER, multiplier_option=opt)


def make_encoder_case(
    *,
    name: str,
    input_encoding: VecEncoding,
    output_encoding: VecEncoding,
    clip_most_negative: bool,
) -> CaseSpec:
    return CaseSpec(
        name=name,
        case_type=CASE_ENCODER,
        encoder_input_encoding=input_encoding,
        encoder_output_encoding=output_encoding,
        encoder_clip_most_negative=clip_most_negative,
    )


# def _case_label(case_name: str, encoding_names: Tuple[str, str, str]) -> str:
#     a_name, b_name, y_name = encoding_names
#     return f"{case_name} (a={a_name}, b={b_name}, y={y_name})"

# alternative _case_label implementation, e.g. ENC SM->TC, or MUL TC->TC
def _case_label(case_name: str, encoding_names: Tuple[str, str, str]) -> str:
    a_name, b_name, y_name = encoding_names
    def abbreviate(name: str) -> str:
        if name == "twos_complement":
            return "TC"
        elif name == "twos_complement_symmetric":
            return "TCS"
        elif name == "sign_magnitude":
            return "SM"
        elif name == "sign_magnitude_ext":
            return "SME"
        else:
            return name
    if case_name.startswith("ENC"):
        return f"ENC {abbreviate(a_name)}$\\rightarrow${abbreviate(y_name)}"
    else:
        return f"MUL {abbreviate(a_name)}$\\rightarrow${abbreviate(y_name)}"


def _run_case(
    args: Tuple[CaseSpec, int, List[float], bool, int, str, int]
) -> Dict[str, Any]:
    case, n_bits, sigma_vals, tb_from_data, target_delay, worker_base, num_vectors = args

    reset_shared_cache()

    input_widths = TwInputArit(a_w=n_bits, b_w=n_bits)

    if case.case_type == CASE_MULTIPLIER:
        if case.multiplier_option is None:
            raise ValueError(f"Missing multiplier_option for case {case.name}")

        opt = case.multiplier_option
        encodings_options = encoding_for_multiplier(opt.value)
        encodings = encodings_options[-1]  # pick default

        comp = opt.value(
            a_w=input_widths.a_w,
            b_w=input_widths.b_w,
            a_encoding=encodings.a,
            b_encoding=encodings.b,
            optim_type="speed",
            ppg_cls=PPGOption.BAUGH_WOOLEY.value
            if opt == MultiplierOption.STAGE_BASED_MULTIPLIER
            else PPGOption.AND.value,
            ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
            fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
        )

        def make_vectors(sigma: float):
            return MultiplierTestVectors(
                a_w=input_widths.a_w,
                b_w=input_widths.b_w,
                y_w=comp.io.y.typ.width,
                num_vectors=num_vectors,
                tb_sigma=sigma,
                a_encoding=encodings.a,
                b_encoding=encodings.b,
                y_encoding=encodings.y,
            ).generate()

    elif case.case_type == CASE_ENCODER:
        if case.encoder_input_encoding is None or case.encoder_output_encoding is None:
            raise ValueError(f"Missing encoder encodings for case {case.name}")

        encodings = (
            TwoInputAritEncodings.with_enc(case.encoder_input_encoding)
            .set_output(case.encoder_output_encoding)
        )
        comp = TwosComplementToSignMagnitudeEncoder(
            width=input_widths.a_w,
            clip_most_negative=bool(case.encoder_clip_most_negative),
        )

        def make_vectors(sigma: float):
            return EncoderDecoderTestVectors(
                width=input_widths.a_w,
                num_vectors=num_vectors,
                tb_sigma=sigma,
                input_encoding=encodings.a,
                output_encoding=encodings.y,
            ).generate()

    else:
        raise ValueError(f"Unknown case type: {case.case_type}")
    
    # optional    
    #comp = refactor_module_to_aig(comp.to_module(), optimize=True).to_component()

    ppa_results = []
    powers = []

    for sigma in sigma_vals:
        worker_path = os.path.join(
            worker_base,
            case.name,
            f"sigma_{sigma:.1f}".replace(".", "_"),
        )
        os.makedirs(worker_path, exist_ok=True)

        vectors = make_vectors(sigma)

        ppa = _get_ppa(
            comp,
            vectors,
            module_name=f"DUT_{case.name}_{n_bits}",
            tb_from_data=tb_from_data,
            target_delay=target_delay,
            worker_path=worker_path,
        )

        remove_worker_path(worker_path)
        ppa["sigma"] = sigma
        ppa_results.append(ppa)
        powers.append(ppa["power"])

    encoding_names = (encodings.a.name, encodings.b.name, encodings.y.name)
    return {
        "case_name": case.name,
        "encoding_names": encoding_names,
        "ppa_results": ppa_results,
        "powers": powers,
    }


def run_sigma_sweep_and_plot(processes: Optional[int] = None):
    n_bits = 4
    tb_from_data = True
    target_delay = 1200 #450  # in ps,  depending on target the power changes significantly
    worker_base = "worker_sigma"
    step = 1.0

    num_vectors = 10000

    sigma_vals = _sigma_values(step=step)

    cases = [
        make_multiplier_case(MultiplierOption.STAGE_BASED_MULTIPLIER),
        make_multiplier_case(MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_MULTIPLIER),
        make_multiplier_case(MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_MULTIPLIER),
        make_multiplier_case(MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_TO_TWOS_COMPLEMENT_MULTIPLIER),
        make_multiplier_case(MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_TO_TWOS_COMPLEMENT_MULTIPLIER),
        make_encoder_case(
            name="ENC_TC_to_SM_clipTrue",
            input_encoding=VecEncoding.twos_complement,
            output_encoding=VecEncoding.sign_magnitude,
            clip_most_negative=True,
        ),
        make_encoder_case(
            name="ENC_TC_to_SMEXT_clipFalse",
            input_encoding=VecEncoding.twos_complement,
            output_encoding=VecEncoding.sign_magnitude_ext,
            clip_most_negative=False,
        ),
        make_encoder_case(
            name="ENC_TCSYM_to_SM_clipFalse",
            input_encoding=VecEncoding.twos_complement_symmetric,
            output_encoding=VecEncoding.sign_magnitude,
            clip_most_negative=False,
        ),
    ]

    os.makedirs(worker_base, exist_ok=True)

    args = [
        (case, n_bits, sigma_vals, tb_from_data, target_delay, worker_base, num_vectors)
        for case in cases
    ]

    with Pool(processes=processes) as pool:
        all_results = pool.map(_run_case, args)

    plot_path = os.path.join(worker_base, "power_vs_sigma.png")
    plt.figure(figsize=(8, 6))

    for result in all_results:
        label = _case_label(result["case_name"], result["encoding_names"])
        plt.plot(
            sigma_vals,
            [p * 1000 for p in result["powers"]],
            marker="o",
            label=label,
        )

    plt.xlabel("Sigma [LSB]")
    plt.ylabel("Power [mW]")
    plt.title(f"Power vs sigma, {n_bits}-bit sweep", fontsize=10)
    plt.legend(fontsize=8, loc="upper left", framealpha=0.5)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(plot_path)
    
    # barplot of area at target delay
    plt.figure(figsize=(8, 6))
    for result in all_results:
        area = result["ppa_results"][0]['area']
        label = _case_label(result["case_name"], result["encoding_names"])
        plt.bar(label, area)
    plt.xlabel("Case")
    plt.ylabel("Area [um^2]")
    plt.title(f"Area, {n_bits}-bit sweep", fontsize=10)
    plt.xticks(rotation=45, ha='right', fontsize=8)
    plt.tight_layout()
    area_plot_path = os.path.join(worker_base, "area_at_target_delay.png")
    plt.savefig(area_plot_path)

    plt.figure(figsize=(8, 6))
    for result in all_results:
        delay = result["ppa_results"][0]['delay']
        label = _case_label(result["case_name"], result["encoding_names"])
        plt.bar(label, delay)
    plt.xlabel("Case")
    plt.ylabel("Delay [ps]")
    plt.title(f"Delay, {n_bits}-bit sweep", fontsize=10)
    plt.xticks(rotation=45, ha='right', fontsize=8)
    plt.tight_layout()
    delay_plot_path = os.path.join(worker_base, "delay_at_target_delay.png")
    plt.savefig(delay_plot_path)
    
    return {"all_results": all_results, "sigma_vals": sigma_vals, "plot_path": plot_path}


if __name__ == "__main__":
    result = run_sigma_sweep_and_plot()
    print(f"Saved power vs sigma plot to {result['plot_path']}")
    for entry in result["all_results"]:
        a_name, b_name, y_name = entry["encoding_names"]
        print("Case:", entry["case_name"], f"(a={a_name}, b={b_name}, y={y_name})")
        for ppa in entry["ppa_results"]:
            print(f"  sigma={ppa['sigma']:.2f}, power={ppa['power']}")

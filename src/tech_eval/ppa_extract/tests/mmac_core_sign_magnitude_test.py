from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from tech_eval.int_tb_sim import run_component_with_vectors
from tech_eval.ppa_extract.core.ppa_extraction import get_ppa, remove_worker_path
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    MultiplierOption,
    PPAOption,
    PPGOption,
    TwoInputAritEncodings,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding, EncodingModel
from spirehdl.cores.matmul_accumulate.matmul_accumulate_core import (
    AdderConfig,
    MMAcDims,
    MMAcWidths,
    max_y_width_unsigned,
    MatmulAccumulateCore,
)
from spirehdl.cores.matmul_accumulate.matmul_accumulate_core_sign_magnitude import (
    MMAcEncodedCfg,
    MultiplierConfig,
    SignMagnitudeEncoderConfig,
    MatmulAccumulateComponent,
)

from tech_eval.ppa_extract.tests.mmac_core_test import _build_vectors_encoding


def _shape2d(arr) -> tuple[int, int]:
    return len(arr), len(arr[0])


def _rand_mat(rng: np.random.Generator, arr, width: int) -> np.ndarray:
    rows, cols = _shape2d(arr)
    return rng.integers(0, 2**width, size=(rows, cols), dtype=int)


def _build_vectors(core, num_vectors: int) -> List[Tuple[str, Dict[str, int], Dict[str, int]]]:
    a_width = core.A[0, 0].typ.width
    b_width = core.B[0, 0].typ.width
    c_width = core.C[0, 0].typ.width

    a_rows, a_cols = _shape2d(core.A)  # A: (m, k)
    b_rows, b_cols = _shape2d(core.B)  # B: (k, n)
    c_rows, c_cols = _shape2d(core.C)  # C/Y: (m, n)

    rng = np.random.default_rng(seed=42)
    vectors: List[Tuple[str, Dict[str, int], Dict[str, int]]] = []

    for idx in range(num_vectors):
        a_vals = _rand_mat(rng, core.A, a_width)
        b_vals = _rand_mat(rng, core.B, b_width)
        c_vals = _rand_mat(rng, core.C, c_width)
        y_vals = a_vals @ b_vals + c_vals

        ins: Dict[str, int] = {}
        outs: Dict[str, int] = {}

        # A: (m, k)
        for i in range(a_rows):
            for k in range(a_cols):
                ins[core.A[i, k].name] = int(a_vals[i, k])

        # B: (k, n)
        for k in range(b_rows):
            for j in range(b_cols):
                ins[core.B[k, j].name] = int(b_vals[k, j])

        # C/Y: (m, n)
        for i in range(c_rows):
            for j in range(c_cols):
                ins[core.C[i, j].name] = int(c_vals[i, j])
                outs[core.Y[i, j].name] = int(y_vals[i, j])

        vectors.append((f"vec_{idx}", ins, outs))

    return vectors



def _write_vector_data_file(
    input_names: List[str],
    output_names: List[str],
    vectors: List[Tuple[str, Dict[str, int], Dict[str, int]]],
    filepath: Path,
) -> None:
    with open(filepath, "w") as f:
        for _, ins, outs in vectors:
            values = [ins[name] for name in input_names] + [outs[name] for name in output_names]
            f.write(" ".join(str(val) for val in values) + "\n")


def test_mmac_core_sign_magnitude_vector_simulation() -> None:
    dim_m = 4
    dim_n = 4
    dim_k = 4
    a_width = 4
    b_width = 4
    c_width = max_y_width_unsigned(a_width, b_width, dim_k, include_carry_from_add=False)
    sigma: Optional[float] = 3.0  # e.g., 1.0 for normal distribution, None for uniform

    encoding = Encoding.twos_complement_symmetric

    mult_enc = (
        Encoding.sign_magnitude
        if encoding == Encoding.twos_complement_symmetric
        else Encoding.sign_magnitude_ext
    )

    mult_cfg = MultiplierConfig(
        use_operator=False,
        multiplier_opt=(
            MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_MULTIPLIER
            if encoding == Encoding.twos_complement_symmetric
            else MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_EXT_MULTIPLIER
        ),
        encodings=TwoInputAritEncodings.with_enc(mult_enc),
        ppg_opt=PPGOption.AND,
        ppa_opt=PPAOption.WALLACE_TREE,
        fsa_opt=FSAOption.RIPPLE_CARRY,
    )
    add_cfg = AdderConfig(
        use_operator=False,
        fsa_opt=FSAOption.RIPPLE_CARRY,
        full_output_bit=True,
        encoding=encoding,
    )
    encoding_cfg = SignMagnitudeEncoderConfig(
        encoder_clip_most_negative=False,
        decoder_clip_most_negative=False,
    )

    core_cfg = MMAcEncodedCfg(
        dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
        widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
        mult_cfg=mult_cfg,
        add_cfg=add_cfg,
        encoding_cfg=encoding_cfg,
    )


    comp = MatmulAccumulateComponent(core_cfg, signed_io_type=False)
    module = comp.to_module()

    vectors = _build_vectors_encoding(comp, encoding=encoding, num_vectors=50, sigma=sigma)

    worker_path = Path(f"worker_mmac_core_sign_mag_{encoding.value}")
    worker_path.mkdir(parents=True, exist_ok=True)

    target_delay = 1200  # in ps

    sim_result = run_component_with_vectors(
        module.to_component(),
        vectors,
        module_name=module.name,
        decoder=None,
        tb_from_data=True,
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
    
    print(f"PPA results: {ppa}")
    
    # save ppa results to a json file    
    with open(worker_path / "ppa_results.json", "w") as f:
        json.dump(ppa, f, indent=4)
    
    remove_data = False
    if remove_data:
        remove_worker_path(worker_path)
    else:
        print(f"Worker path retained at: {worker_path}")


if __name__ == "__main__":
    test_mmac_core_sign_magnitude_vector_simulation()

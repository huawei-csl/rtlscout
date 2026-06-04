from __future__ import annotations

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
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding, EncodingModel, is_signed
from spirehdl.cores.matmul_accumulate.matmul_accumulate_core import (
    AdderConfig,
    MMAcCfg,
    MMAcDims,
    MMAcWidths,
    MultiplierConfig,
    build_matmul_accumulate,
    max_y_width_unsigned,
    MatmulAccumulateCore
)
from spirehdl.helpers import run_vectors_on_simulator
from spirehdl.spirehdl_simulator import Simulator
from spirehdl.spirehdl_verilog_testbench import TestbenchGenSimulator


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


# should be same as generate_matmul_vectors in spirehdl
def _build_vectors_encoding(
    core: MatmulAccumulateCore, encoding: Encoding, num_vectors: int, sigma: Optional[float] = None, encoding_ab_inputs: Optional[Encoding] = None,
) -> List[Tuple[str, Dict[str, int], Dict[str, int]]]:
    a_width = core.io.A[0, 0].typ.width
    b_width = core.io.B[0, 0].typ.width
    c_width = core.io.C[0, 0].typ.width

    a_rows, a_cols = _shape2d(core.io.A)  # A: (m, k)
    b_rows, b_cols = _shape2d(core.io.B)  # B: (k, n)
    c_rows, c_cols = _shape2d(core.io.C)  # C/Y: (m, n)

    enc_model = EncodingModel(encoding)
    enc_model_inputs = EncodingModel(encoding_ab_inputs) if encoding_ab_inputs else enc_model
    vectors: List[Tuple[str, Dict[str, int], Dict[str, int]]] = []

    for idx in range(num_vectors):
        
        if sigma is None:
            a_vals = enc_model_inputs.get_uniform_sample_np(a_width, size=(a_rows, a_cols))
            b_vals = enc_model_inputs.get_uniform_sample_np(b_width, size=(b_rows, b_cols))
            c_vals = enc_model.get_uniform_sample_np(c_width, size=(c_rows, c_cols))
        else:
            a_vals = enc_model_inputs.get_normal_sample_np(a_width, sigma, size=(a_rows, a_cols))
            b_vals = enc_model_inputs.get_normal_sample_np(b_width, sigma, size=(b_rows, b_cols))
            c_vals = enc_model.get_normal_sample_np(c_width, sigma, size=(c_rows, c_cols))
        
        y_vals = a_vals @ b_vals + c_vals
        
        # encode the values according to the encoding
        a_vals = np.vectorize(lambda x: enc_model_inputs.encode_value(int(x), a_width))(a_vals)
        b_vals = np.vectorize(lambda x: enc_model_inputs.encode_value(int(x), b_width))(b_vals)
        c_vals = np.vectorize(lambda x: enc_model.encode_value(int(x), c_width))(c_vals)
        y_vals = np.vectorize(lambda x: enc_model.encode_value(int(x), core.Y[0, 0].typ.width))(y_vals)

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


def test_mmac_core_vector_simulation() -> None:
    dim_m = 4
    dim_n = 4
    dim_k = 4
    a_width = 4
    b_width = 4
    c_width = max_y_width_unsigned(a_width, b_width, dim_k, include_carry_from_add=False)
    sigma: Optional[float] = 3.0  # e.g., 1.0 for normal distribution, None for uniform

    encoding = Encoding.unsigned

    mult_cfg = MultiplierConfig(
        use_operator=False,
        multiplier_opt=MultiplierOption.STAR_MULTIPLIER,
        encodings=TwoInputAritEncodings.with_enc(encoding),
        ppg_opt=PPGOption.BAUGH_WOOLEY if is_signed(encoding) else PPGOption.AND,
        ppa_opt=PPAOption.WALLACE_TREE,
        fsa_opt=FSAOption.RIPPLE_CARRY,
    )
    add_cfg = AdderConfig(use_operator=False, fsa_opt=FSAOption.RIPPLE_CARRY, full_output_bit=True, encoding=encoding)

    core_cfg = MMAcCfg(
        dims=MMAcDims(dim_m=dim_m, dim_n=dim_n, dim_k=dim_k),
        widths=MMAcWidths(a_width=a_width, b_width=b_width, c_width=c_width),
        mult_cfg=mult_cfg,
        add_cfg=add_cfg,
    )

    core = build_matmul_accumulate(cfg=core_cfg, signed_io_type=False)
    module = core.module
    
    
    # just for testing
    sim = Simulator(core.module)
    a_vals = EncodingModel(encoding).get_uniform_sample_np(a_width, size=(dim_m, dim_k))
    b_vals = EncodingModel(encoding).get_uniform_sample_np(b_width, size=(dim_k, dim_n))
    c_vals = EncodingModel(encoding).get_uniform_sample_np(c_width, size=(dim_m, dim_n))
    
    for i in range(dim_m):
        for j in range(dim_n):
            sim.set(core.A[i, j], int(a_vals[i, j]))
            sim.set(core.B[i, j], int(b_vals[i, j]))
            sim.set(core.C[i, j], int(c_vals[i, j]))
    
    sim.eval()
    
    y_hw = np.zeros((dim_m, dim_n), dtype=int)
    for i in range(dim_m):
        for j in range(dim_n):
            y_hw[i, j] = sim.get(core.Y[i, j])
    
    y_np = a_vals @ b_vals + c_vals
    signed_io_type = False
    if signed_io_type:
        assert np.array_equal(y_hw, y_np), "Simulation mismatch for matmul accumulate core"
    else:
        # encode each element according to the encoding
        y_np_encoded = np.vectorize(
            lambda x: EncodingModel(encoding).encode_value(int(x), core.Y[0, 0].typ.width)
        )(y_np)
        assert np.array_equal(y_hw, y_np_encoded), "Simulation mismatch for matmul accumulate core"
    
    # just for testing end

    vectors = _build_vectors_encoding(core.component, encoding=encoding, num_vectors=50, sigma=sigma)

    worker_path = Path("worker_mmac_core")
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
    
    remove_data = False
    if remove_data:
        remove_worker_path(worker_path)
    else:
        print(f"Worker path retained at: {worker_path}")


if __name__ == "__main__":
    test_mmac_core_vector_simulation()

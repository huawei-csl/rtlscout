import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Type

from tech_eval.ppa_extract.core.ppa_extraction import _run_verilator_generic
from tech_eval.ppa_extract.core.template import (
    make_vcd_flags,
    verilator_common_flags,
    verilator_directive_flags,
)
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    TwoInputAritEncodings,
    PPAOption,
    PPGOption,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import (
    AdderTestVectors,
    Encoding,
    MultiplierTestVectors,
    TwoInputArithmeticTestVectorsBase,
    TestVectors
)
from spirehdl.arithmetic.int_multipliers.multipliers.multiplier_stage_core import (
    StageBasedMultiplierBasic,
)
from spirehdl.arithmetic.int_multipliers.multipliers.multipliers_ext_optimized import (
    OptimizedMultiplierFrom4BitBlocks,
    OptimizedMultiplierFrom4BitBlocksStrong,
    OptimizedSignMagnitudeMultiplier,
)
from spirehdl.arithmetic.prefix_adders.adders import StageBasedPrefixAdder
from spirehdl.helpers import run_vectors_on_simulator
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl_simulator import Simulator
from spirehdl.spirehdl_verilog_testbench import TestbenchGenSimulator, write_vector_data_file
from spirehdl.various.vcd_writer import write_vcd
from spirehdl.spirehdl_module import Component

@dataclass(frozen=True)
class TwInputArit:
    a_w: int
    b_w: int


def _envflag(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() not in {"0", "false", "no", "off"}



def _run_verilator(
    verilog_file: str,
    tb_file: str,
    top_module_tb: str,
    log_path: Optional[str] = None,
    test_name: Optional[str] = None,
    vcd_file_path: Optional[str] = None,
    obj_dir: Optional[str] = None,
    extra_flags: Optional[List[str]] = None,
) -> None:
    build_dir = obj_dir or "./obj_dir"
    log_file = log_path or os.path.join(build_dir, f"{top_module_tb}_verilator.log")

    flags = list(verilator_directive_flags) + list(verilator_common_flags)
    if vcd_file_path:
        flags += make_vcd_flags(vcd_file_path)
    if extra_flags:
        flags += list(extra_flags)

    _run_verilator_generic(
        sources=[verilog_file, tb_file],
        tb_top_module=top_module_tb,
        build_dir=build_dir,
        log_path=log_file,
        flags=flags,
        test_name=test_name,
    )


def generate_vectors(
    vec_cls: Type[TwoInputArithmeticTestVectorsBase],
    encodings: TwoInputAritEncodings,
    sigma: Optional[float],
    widths: TwInputArit,
    num_vectors: int,
    y_w: int,
) -> TestVectors:
    vec_kwargs = {
        "a_w": widths.a_w,
        "b_w": widths.b_w,
        "y_w": y_w,
        "num_vectors": num_vectors,
        "tb_sigma": sigma,
        "a_encoding": encodings.a,
        "b_encoding": encodings.b,
        "y_encoding": encodings.y,
    }
    return list(vec_cls(**vec_kwargs).generate())


def run_component_with_vectors(
    component: Component,
    vectors: TestVectors,
    module_name: Optional[str]=None,
    decoder=None,
    tb_from_data: bool = True,
    run_verilator: bool = True,
    save_vcd: bool = True,
    worker_path: Optional[str] = None,
    with_clock: bool = True,
) -> Dict[str, object]:
    
    if module_name is None:
        module_name = component.__class__.__name__
        
    """Run Python sim, emit Verilog/testbench/data, and execute Verilator."""
    if worker_path:
        os.makedirs(worker_path, exist_ok=True)
    base_dir = worker_path or "."
    def _join(name: str) -> str:
        return os.path.join(base_dir, name)

    module: Module = component.to_module(module_name, with_clock=with_clock)
    if not vectors:
        raise ValueError("No vectors generated for the current configuration.")

    sim = Simulator(module)
    sim.trace_enabled = True
    run_vectors_on_simulator(
        sim, vectors, decoder=decoder, print_on_pass=False, test_name="Sprout Simulation"
    )

    basename = module.name.lower()
    tb_name_lower = f"{basename}_tb"
    if save_vcd:
        sim_vcd_filename = _join(f"{tb_name_lower}_sim_sprout.vcd")
        write_vcd(
            trace_by_names=sim.get_trace_by_names(),
            filename=sim_vcd_filename,
            top_module=module.name,
            timescale="1ns",
        )
    else:
        sim_vcd_filename = None

    sim_tb = TestbenchGenSimulator(module)
    run_vectors_on_simulator(
        sim_tb, vectors, decoder=decoder, print_on_pass=False, test_name="TbGen Simulation"
    )

    tb_filename = _join(f"{tb_name_lower}_sim.v")
    verilog_filename = _join(f"{basename}.v")
    data_filename = _join(f"{basename}_vectors.dat") if tb_from_data else None

    # create module and testbench verilog files
    if tb_from_data:
        write_vector_data_file(vectors, data_filename)
        sim_tb.to_data_driver_testbench_file(
            tb_filename,
            data_file=data_filename
        )
    else:
        sim_tb.to_testbench_file(tb_filename)
        
    module.to_verilog_file(verilog_filename)
    
    tb_vcd_filename = _join(f"{tb_name_lower}_sim_verilator.vcd") if save_vcd else None
    obj_dir = _join("out_tb")
    if run_verilator:
        verilator_log_path = _join(f"{tb_name_lower}_verilator.log")
        _run_verilator(verilog_filename, tb_filename, f"{module.name}_tb", log_path=verilator_log_path, test_name="Verilator Simulation", vcd_file_path=tb_vcd_filename, obj_dir=obj_dir)
    else:
        verilator_log_path = None


    return {
        "module": module,
        "module_name": module.name,
        "vectors": vectors,
        "tb_filename": tb_filename,
        "tb_name": module.name + "_tb",
        "verilog_filename": verilog_filename,
        "data_filename": data_filename,
        "sim_vcd_filename": sim_vcd_filename,
        "tb_vcd_filename": tb_vcd_filename,
        "verilator_log_path": verilator_log_path,
    }


def int_tb_sim():
    n_bits = int(os.environ.get("N_BITS", 32))
    signed = False
    design_type = os.environ.get("DESIGN_TYPE", "adder")  # "adder" or "multiplier"
    multiplier_kind = os.environ.get(
        "MULTIPLIER_KIND", "optimized_strong"
    )  # stage_basic | optimized | optimized_strong | optimized_sign_mag
    optim_type = os.environ.get("OPTIM_TYPE", "area")
    fsa_cls = FSAOption.RIPPLE_CARRY.value
    tb_from_data = _envflag("TB_FROM_DATA", True)
    input_widths = TwInputArit(a_w=n_bits, b_w=n_bits)

    encodings = TwoInputAritEncodings.with_enc(
        Encoding.unsigned if not signed else Encoding.twos_complement,
    )

    if design_type == "adder":
        comp = StageBasedPrefixAdder(
            a_w=input_widths.a_w,
            b_w=input_widths.b_w,
            optim_type=optim_type,
            fsa_cls=fsa_cls,
            signed_a=signed,
            signed_b=signed,
        )
        vec_cls = AdderTestVectors
        num_vectors = 1600
        sigma = None
        module_name = f"Add{n_bits}"
        decoder = None
    else:
        if multiplier_kind == "stage_basic":
            comp = StageBasedMultiplierBasic(
                a_w=input_widths.a_w,
                b_w=input_widths.b_w,
                signed_a=signed,
                signed_b=signed,
                optim_type=optim_type,
                ppg_cls=PPGOption.AND.value,
                ppa_cls=PPAOption.WALLACE_TREE.value,
                fsa_cls=fsa_cls,
            )
        elif multiplier_kind == "optimized":
            comp = OptimizedMultiplierFrom4BitBlocks(
                a_w=input_widths.a_w,
                b_w=input_widths.b_w,
                optim_type=optim_type,
                ppg_cls=PPGOption.NONE.value,
            )
        elif multiplier_kind == "optimized_sign_mag":
            comp = OptimizedSignMagnitudeMultiplier(
                a_w=input_widths.a_w,
                b_w=input_widths.b_w,
                optim_type=optim_type,
                ppg_cls=PPGOption.NONE.value,
            )
        else:
            comp = OptimizedMultiplierFrom4BitBlocksStrong(
                a_w=input_widths.a_w,
                b_w=input_widths.b_w,
                optim_type=optim_type,
                ppg_cls=PPGOption.NONE.value,
            )

        vec_cls = MultiplierTestVectors
        num_vectors = 10000
        sigma = None
        module_name = f"Mul{n_bits}"
        decoder = None

    vectors = generate_vectors(
        vec_cls=vec_cls,
        encodings=encodings,
        sigma=sigma,
        widths=input_widths,
        num_vectors=num_vectors,
        y_w=comp.io.y.typ.width,
    )

    result = run_component_with_vectors(
        comp,
        vectors,
        module_name=module_name,
        decoder=decoder,
        tb_from_data=tb_from_data,
    )

    # make_clean_cmd = "make clean"
    # os.system(make_clean_cmd)

    # make_cmd = (
    #     f"make TOP_MODULE={result['module'].name} TOP_MODULE_TB={result['module'].name}_tb "
    #     f"SOURCE_FILES={result['verilog_filename']} TESTBENCH_FILE={result['tb_filename']}"
    # )
    # os.system(make_cmd)
    # df = pd.read_parquet("result/post_synth_power.parquet")
    # print(df)

    return result

if __name__ == "__main__":
    int_tb_sim()

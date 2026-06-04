from typing import Type
from tech_eval.int_tb_sim import TwInputArit, generate_vectors, run_component_with_vectors
from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import Encoding, FSAOption, PPAOption, PPGOption, TwoInputAritEncodings, MultiplierTestVectors, MultiplierOption
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import TwoInputArithmeticTestVectorsBase
from spirehdl.arithmetic.int_multipliers.multipliers.multiplier_stage_core import StageBasedMultiplierBasic
from spirehdl.arithmetic.int_multipliers.multipliers.multipliers_ext_karatsuba import KaratsubaMultiplier
from spirehdl.arithmetic.int_multipliers.multipliers.multipliers_ext_optimized import OptimizedMultiplierFrom4BitBlocks, OptimizedMultiplierFrom4BitBlocksStrong, OptimizedMultiplier, OptimizedSignMagnitudeMultiplier

from tech_eval.ppa_extract.core.ppa_extraction import get_ppa, remove_worker_path

# def get_full_target_delay(bit_width):
#     if bit_width == 8:
#         return list(range(50, 1000, 10))
#     elif bit_width == 16:
#         return list(range(50, 2000, 20))
#     elif bit_width == 32:
#         return list(range(50, 3000, 20))
#     else:
#         return list(range(50, 4000, 20))

def test1():
    
    n_bits = 16
    signed = False  
    tb_from_data = True
    input_widths = TwInputArit(a_w=n_bits, b_w=n_bits)
    encodings = TwoInputAritEncodings.with_enc(
        Encoding.sign_magnitude if signed else Encoding.unsigned
    )
    
    # 16 biy
    mult = StageBasedMultiplierBasic(
        a_w=n_bits,
        b_w=n_bits,
        signed_a=signed,
        signed_b=signed,
        optim_type="area",
        ppg_cls=PPGOption.AND.value,
        #ppa_cls=PPAOption.CARRY_SAVE_TREE.value, #PPAOption.CARRY_SAVE_TREE.value,
        #fsa_cls=FSAOption.PREFIX_KOGGE_STONE.value, #FSAOption.PREFIX_KOGGE_STONE.value,
        ppa_cls=PPAOption.CARRY_SAVE_TREE.value, #PPAOption.CARRY_SAVE_TREE.value,
        fsa_cls=FSAOption.PREFIX_HAN_CARLSON.value, #FSAOption.PREFIX_KOGGE_STONE.value,
    )
    
    # mult = MultiplierOption.STAGE_BASED_SIGN_MAGNITUDE_MULTIPLIER.value(
    #     a_w=n_bits,
    #     b_w=n_bits,
    #     a_encoding = encodings.a,
    #     b_encoding = encodings.b,
    #     optim_type="speed",
    #     ppg_cls=PPGOption.BOOTH_OPTIMISED.value,
    #     ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
    #     fsa_cls=FSAOption.PREFIX_SKLANSKY.value,
    # )
    
    # 32 bit
    # mult = KaratsubaMultiplier(
    #     a_w=n_bits,
    #     b_w=n_bits,
    #     optim_type="speed",
    #     a_encoding = encodings.a,
    #     b_encoding = encodings.b,
    #     ppg_cls=PPGOption.AND.value,
    #     ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
    #     fsa_cls=FSAOption.PREFIX_SKLANSKY.value,        
    # )
    
    # 8 bit
    # mult = OptimizedMultiplierFrom4BitBlocksStrong(
    #     a_w=n_bits,
    #     b_w=n_bits,
    #     optim_type="area",
    #     ppa_cls=PPAOption.CARRY_SAVE_TREE.value,
    #     fsa_cls=FSAOption.PREFIX_MULTI_SCAN.value,    
    # )
    
    module_name = f"Mul{n_bits}"
    decoder = None
    vec_cls : Type[TwoInputArithmeticTestVectorsBase] = MultiplierTestVectors
    num_vectors = 1000
    sigma = 3
    worker_path = "worker_11"
    
    use_simple_generation = False
    tb_filename = None
    tb_name = None
    
    use_vcd_for_power = False
    save_vcd = False
    
    with_clock = False

    if use_simple_generation:
        module = mult.to_module(module_name, with_clock=with_clock)
        rtl_path = "int_multiplier.v"
        module.to_verilog_file(rtl_path)
        top_module_name = module.name
    else:
        vectors = generate_vectors(
            vec_cls=vec_cls,
            encodings=encodings,
            sigma=sigma,
            widths=input_widths,
            num_vectors=num_vectors,
            y_w=mult.io.y.typ.width
        )

        result = run_component_with_vectors(
            mult,
            vectors,
            module_name=module_name,
            decoder=decoder,
            tb_from_data=tb_from_data,
            worker_path=worker_path,
            save_vcd=save_vcd,
            with_clock=with_clock,
        )

        rtl_path = result["verilog_filename"]
        top_module_name = result["module_name"]
        
        tb_filename = result["tb_filename"]
        tb_name = result["tb_name"]
      
   
    target_delay = 200  # in ps

    
    ppa_results = get_ppa(
        rtl_path=rtl_path,
        target_delay=target_delay,
        worker_path=worker_path,
        top_module_name=top_module_name,
        run_verilator=True,
        tb_filename=tb_filename,
        tb_name=tb_name,
        use_vcd_for_power=use_vcd_for_power,             
        save_vcd=save_vcd,
        use_fa_ha_inference=False
    )
    
    print(ppa_results)
    
    #rtl_path = "/workspaces/tech_eval/src/tech_eval/ppa_extract/tests/files/mult8.sv"
    #top_module_name = "Mul8"
    
    rtl_path = "/workspaces/tech_eval/src/tech_eval/ppa_extract/tests/files/mult16.sv"
    top_module_name = "Mul16"
    
    # rtl_path = "/workspaces/tech_eval/src/tech_eval/ppa_extract/tests/files/add16.sv"
    # top_module_name = "add16"
    
    # rtl_path = "/workspaces/tech_eval/src/tech_eval/ppa_extract/tests/files/add32.sv"
    # top_module_name = "add32"
    
    #rtl_path = "src/tech_eval/ppa_extract/tests/files/mul16_sprout.v"
    #top_module_name = "Mul16"
    
    # rtl_path = "/workspaces/tech_eval/src/tech_eval/ppa_extract/tests/files/mult32.v"
    # top_module_name = "mult32"
    
    # rtl_path = "/workspaces/tech_eval/src/tech_eval/ppa_extract/tests/files/mult32.v"
    # top_module_name = "mult32"
    # worker_path = "worker_12"
    
    # rtl_path = "src/tech_eval/ppa_extract/tests/files/matmulacc4_design_v5.v"
    # top_module_name = "matmulacc4"
    # worker_path = "worker_13"
    
    # rtl_path = "arith_das_mul_wallace.v"
    # top_module_name = "MUL"
    
    ppa_results = get_ppa(
        rtl_path=rtl_path,
        target_delay=target_delay, 
        worker_path=worker_path,
        top_module_name=top_module_name,
        run_verilator=False,
        use_fa_ha_inference=False
    )
    
    print(ppa_results)
    
    #remove_worker_path(worker_path)
    
if __name__ == "__main__":
    test1()

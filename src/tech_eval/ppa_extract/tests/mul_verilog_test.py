"""
Standalone adder and multiplier PPA sweep.

Runs a comprehensive sweep over adder and multiplier configurations,
collecting PPA (Power, Performance, Area) metrics across multiple
target delays, modelled after mmac_cores_mp.py in the restored/
directory. Results are saved to JSON and plotted using the existing
plotting2 module from the mmac sweeps.
"""
import json
import os
from dataclasses import dataclass
from itertools import product
from typing import List, Optional

from spirehdl.spirehdl import reset_shared_cache

from spirehdl.arithmetic.int_multipliers.eval.multiplier_stage_options_demo_lib import (
    FSAOption,
    PPAOption,
    PPGOption,
    MultiplierOption,
    PrefixAdderFinalStage,
    TwoInputAritEncodings,
    encoding_for_multiplier,
    get_list_from_enum,
)
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import (
    AdderTestVectors,
    Encoding,
    MultiplierTestVectors,
)
from spirehdl.arithmetic.prefix_adders.adders import StageBasedPrefixAdder

from tech_eval.ppa_extract.sweeps.plotting2 import plot_delay_vs_area, plot_power_vs_area, plot_power_vs_delay, plot_switch_count_vs_area, plot_switch_count_vs_delay, plot_transistor_count_vs_area, regroup_by_fsa, regroup_by_ppa, regroup_by_target_delay
from tech_eval.ppa_extract.core.ppa_configs import InstanceConfig
from tech_eval.ppa_extract.core.ppa_extraction_specific import run_configs
from tech_eval.ppa_extract.core.template import lib_time_unit, technology
from tech_eval.ppa_extract.sweeps.multipliers.mul_add_sweep_mp import MultiplierCfg

from spirehdl.spirehdl_module import Module, Component


n_bits = 3
ppa_opts = [PPAOption.WALLACE_TREE]
fsa_opts = [FSAOption.RIPPLE_CARRY]


optim_types = ["speed"]

encoding = Encoding.twos_complement
encodings_obj = TwoInputAritEncodings.with_enc(encoding)
ppg_opts = [PPGOption.BAUGH_WOOLEY] if encoding == Encoding.twos_complement else [PPGOption.AND]
configs = [
    InstanceConfig(
        impl_cls=MultiplierOption.STAGE_BASED_MULTIPLIER.value,
        config=MultiplierCfg(
            a_w=n_bits,
            b_w=n_bits,
            a_encoding=encodings_obj.a,
            b_encoding=encodings_obj.b,
            optim_type=optim_type,
            ppg_cls=ppg_opt.value,
            ppa_cls=ppa_opt.value,
            fsa_cls=fsa_opt.value,
        ),
    )
    for ppg_opt, ppa_opt, fsa_opt, optim_type in product(
        ppg_opts, ppa_opts, fsa_opts, optim_types
    )
]

config = configs[0]

design_prefix = "design"

# generate one instance of the design
impl : Component = config.gen_instance()
module = impl.to_module(f"{design_prefix}", with_clock=True)

# print verilog
module.to_verilog_file(f"{design_prefix}.v")
print(f"Verilog written to {design_prefix}.v")

verilog = module.to_verilog()
#print(verilog)

# print number of characters in the verilog
print(f"Verilog length: {len(verilog)} characters")
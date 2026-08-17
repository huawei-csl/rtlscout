# inspired from https://github.com/dakfjalka/Arith-DAS/blob/master/utils/template.py

import os

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class Technology(str, Enum):
    """Supported process technology libraries."""
    ASAP7 = "asap7"
    NANGATE45 = "nangate45"
    FREEPDK45 = "freepdk45"


# Cell models for gate-level netlist sims. True: use one generated Verilog
# module per cell, derived from the liberty function attributes (2-state,
# zero-delay -- same fidelity as the vendor models without SDF, ~5x faster
# builds / ~25x faster sims, immune to the Verilator sequential-UDP
# mis-lowering;
# False: use the original vendor library sim models
NETLIST_FUNCTIONAL_SIM_CELL_MODELS = True

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


@dataclass
class TechConfig:
    """All technology-dependent paths and settings."""
    lib_paths: List[str]
    lef_paths: List[str]
    lib_time_unit: str  # "ps" or "ns"
    abc_constr: str
    verilator_netlist_flags: List[str]
    adder_map_file: Optional[str] = None
    functional_models: Optional[str] = None  # generated functional cell models


_TECH_CONFIGS = {
    Technology.NANGATE45: TechConfig(
        # nangate: https://github.com/oscc-ip/nangate ( cd /app, git clone https://github.com/oscc-ip/nangate)
        lib_paths=[
            "/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib",
        ],
        lef_paths=[
            "/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef",
            "/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef",
            "/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.rect.lef",
            "/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.mod.lef",
        ],
        lib_time_unit="ns",
        abc_constr="""
    set_driving_cell BUF_X1
    set_load 10.0 [all_outputs]
    """,
        verilator_netlist_flags=["/app/nangate/sim/cells.v"],
        adder_map_file="/prog/OpenROAD-flow-scripts/flow/platforms/nangate45/cells_adders.v",
    ),
    Technology.ASAP7: TechConfig(
        # ASAP7 "most basic" (single-corner typical, RVT) library + LEF set
        lib_paths=[
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib.gz",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib.gz",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib.gz",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib.gz",  #comment out or include in the verilog files below (for separate github)
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib",
        ],
        lef_paths=[
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lef/asap7_tech_1x_201209.lef",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lef/asap7sc7p5t_28_R_1x_220121a.lef",
        ],
        lib_time_unit="ps", # zgrep -n "time_unit" /prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib.gz | head
        abc_constr="""
    set_driving_cell -lib_cell BUFx2_ASAP7_75t_R [all_inputs]
    set_load 10.0 [all_outputs]
    """,
        verilator_netlist_flags=[
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/verilog/stdcell/empty.v",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/verilog/stdcell/asap7sc7p5t_SIMPLE_RVT_TT_201020.v",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/verilog/stdcell/asap7sc7p5t_INVBUF_RVT_TT_201020.v",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/verilog/stdcell/asap7sc7p5t_AO_RVT_TT_201020.v",
            "/prog/OpenROAD-flow-scripts/flow/platforms/asap7/verilog/stdcell/asap7sc7p5t_SEQ_RVT_TT_220101.v",
            "/app/asap7sc7p5t_28/Verilog/asap7sc7p5t_OA_RVT_TT_201020.v",
        ],
        adder_map_file="/prog/OpenROAD-flow-scripts/flow/platforms/asap7/yoSys/cells_adders_R.v",
        functional_models=os.path.join(_DATA_DIR, "asap7_functional_cells.v"),
    ),
    Technology.FREEPDK45: TechConfig(
        # from https://github.com/mflowgen/mflowgen/tree/main/adks/freepdk-45nm/pkgs/base

        lib_paths=[
            "/prog/mflowgen/adks/freepdk-45nm/pkgs/base/stdcells.lib",
        ],
        lef_paths=[
            "/prog/mflowgen/adks/freepdk-45nm/pkgs/base/stdcells.lef",
        ],
        lib_time_unit="ns",
        abc_constr="""
    set_driving_cell -lib_cell BUF_X1 [all_inputs]
    set_load 10.0 [all_outputs]
    """,
        verilator_netlist_flags=[],  # not supported
        adder_map_file=None,
    ),
}


def get_tech_config(technology: str) -> TechConfig:
    """Get the technology configuration for a given technology name."""
    try:
        tech = Technology(technology)
    except ValueError:
        valid = ", ".join(t.value for t in Technology)
        raise ValueError(f"Unknown technology: {technology!r}. Choose from: {valid}")
    return _TECH_CONFIGS[tech]


# ---------------------------------------------------------------------------
# Module-level defaults (ASAP7) — backward compat for existing callers
# ---------------------------------------------------------------------------
technology = "asap7"
_default_cfg = get_tech_config(technology)
lib_paths = _default_cfg.lib_paths
lef_paths = _default_cfg.lef_paths
lib_time_unit = _default_cfg.lib_time_unit
abc_constr = _default_cfg.abc_constr
verilator_netlist_flags = _default_cfg.verilator_netlist_flags
ADDER_MAP_FILE = _default_cfg.adder_map_file

target_delay_time_unit = "ps"  # abc -D <delay> expects ps


def lib_time_to_ps(time_value: float, cfg: Optional[TechConfig] = None) -> float:
    unit = cfg.lib_time_unit if cfg else lib_time_unit
    if unit == "ns":
        return time_value * 1e3
    elif unit == "ps":
        return time_value
    else:
        raise ValueError(f"Unknown library time unit: {unit}")


def ps_to_lib_time(time_ps: float, cfg: Optional[TechConfig] = None) -> float:
    unit = cfg.lib_time_unit if cfg else lib_time_unit
    if unit == "ns":
        return time_ps / 1e3
    elif unit == "ps":
        return time_ps
    else:
        raise ValueError(f"Unknown library time unit: {unit}")


lib_paths_subst = " ".join(lib_paths)
lef_paths_subst = " ".join(lef_paths)

verilator_common_flags = [
    "-Wall",
    "-Wno-DECLFILENAME",
    "-Wno-WIDTHEXPAND",
    "-Wno-UNUSEDSIGNAL",
    "--Wno-EOFNEWLINE",
    "-Wno-BLKSEQ",
    "-Wno-fatal",
    "--timescale",
    "1ns/10ps",
]

# currently no -j flags, as evals are often parallized by the caller
verilator_directive_flags = ["--build", "--binary"]

verilator_vcd_flag = ["--trace-vcd", "--trace-underscore", "--no-trace-top"]

verilator_vcd_define = "VCD_FILE_PATH"



def make_vcd_flags(vcd_path: str):
    if not vcd_path:
        return []
    return list(verilator_vcd_flag) + [f"-D{verilator_vcd_define}={vcd_path}"]

def get_fa_ha_inference_cmds(use_fa_ha_inference: bool, cfg: Optional[TechConfig] = None) -> str:
    if not use_fa_ha_inference:
        return "# FA/HA inference disabled"

    adder_map = cfg.adder_map_file if cfg else ADDER_MAP_FILE
    if not adder_map:
        raise ValueError("FA/HA inference requested but ADDER_MAP_FILE is not defined for this technology")

    return "\n".join(
        [
            "# Optional HA/FA inference + mapping",
            "extract_fa",
            f"techmap -map {adder_map}",
            "techmap",
            "opt -fast -purge",
        ]
    )

sta_script_template = """

set lef_files "{lef_paths_subst}"
foreach lef $lef_files {{
    read_lef $lef
}}

set lib_files "{lib_paths_subst}"
foreach lib $lib_files {{
    read_lib $lib
}}

read_verilog {verilog_path}
link_design {top_module_name}


# Clock at the synthesis target: reported delay is the worst-path ARRIVAL
# (period-independent), but worst_slack becomes target - achieved instead of
# the meaningless 5ps reference. All paths stay in this one clock group.
set period {sta_target_delay}

set clk_port [get_ports -quiet clk]

if {{[llength $clk_port] > 0}} {{
    # Real clock on input port clk
    create_clock -period $period $clk_port
    set clk [lindex [all_clocks] 0]
    puts "INFO: Found port 'clk' -> created real clock on it."
    set clock_ports $clk_port
}} else {{
    # No clock port -> create a virtual clock
    puts "INFO: No port 'clk' found -> creating virtual clock VCLK."
    create_clock -name VCLK -period $period
    set clk VCLK
    set clock_ports $clk
}}

set all_paths [find_timing_paths]
puts "Number of paths found: [llength $all_paths]"

set clock_ports [get_ports clk]
set data_inputs [delete_from_list [all_inputs] $clock_ports]
set out_ports   [delete_from_list [all_outputs] $clock_ports]

set_output_delay 0 -clock $clk $out_ports

# Constrain the inputs with the CLOCK, not `set_max_delay -from [all_inputs]
# <target_delay>`. The old form put input->register paths in a separate path
# group judged against an agent-settable target, so whenever target_delay
# exceeded their arrival they showed positive slack and -sort_by_slack skipped
# them -- a design that moved all its logic in front of the first register
# reported the leftover register-to-register wire delay (53 ps instead of
# 3487 ps). One clock group makes worst-slack == longest path, for
# combinational (virtual clock) and sequential designs alike, and makes the
# reported delay independent of target_delay.
set_input_delay 0 -clock $clk $data_inputs
set critical_path [lindex [find_timing_paths -sort_by_slack] 0]
set path_delay [sta::format_time [[$critical_path path] arrival] 4]
puts "wns $path_delay"
report_design_area
# High-precision area (report_design_area rounds to integer um^2 via %.0f;
# rsz::design_area returns square meters as a Tcl double).
puts "design_area_precise [expr [rsz::design_area] * 1e12] um^2"

report_worst_slack

puts "REPORT_CHECKS_BEGIN"
report_checks
puts "REPORT_CHECKS_END"

{power_section}
#exit
"""

# Power section of the STA script (VCD path only; without a VCD no power is
# reported). Placed AFTER all timing reports: it redefines the clock to the
# testbench's simulated period so report_power's clock-pin activity is on the
# same time base as the VCD activities -- the 5 ps timing clock would model
# clock/register power at a fictitious 200 GHz.
power_section_template = """
if {{[llength $clk_port] > 0}} {{
    create_clock -period {vcd_clock_period} $clk_port
}}
read_vcd -scope {tb_scope_name} {{{vcd_path}}}
report_activity_annotation
report_power
"""

# Non-VCD fallback: probabilistic power at default input activity and the
# script clock. A RELATIVE-only estimate (not physical watts) -- meaningful
# mainly for comparing combinational blocks at a common clock; for sequential
# designs the clock-pin term dominates. Returned as
# `power_probabilistic_fixed_clock` (the fixed script clock, NOT fmax).
power_section_probabilistic = """
set_power_activity -input -activity 0.5
report_power
"""

yosys_script_template = """
design -reset
# Legacy single-file read command (reference):
# read -sv <rtl_path>
{read_verilog_cmds}
# -flatten: flatten EARLY (inside synth, before the generic optimization passes),
# so both yosys's structural optimization and abc's timing-driven mapping see
# whole cross-module paths. Hierarchical designs otherwise pay a large artificial
# delay penalty on cross-module register-to-register paths (observed 3.6x on a
# 6-module design; a late `flatten` after synth recovers only ~12% of it). The
# stat/CEC/AIG flows already use `synth -flatten`; this keeps the PPA flow
# consistent. Flattened cells keep hierarchical name prefixes, so the autoname'd
# worst-path report stays readable.
synth -flatten -top {top_module_name}

{fa_ha_inference_cmds}

# Convert async resets to sync + stamp FF init so the gate-level netlist
# resets correctly under the (specify-less) Verilator re-sim while the RTL
# keeps its async reset. Mirrors the AIG path's async2sync.
async2sync
dfflibmap {liberty_args}
# Give registers RTL-derived public names (from their connectivity) BEFORE abc,
# so the OpenROAD worst-path report shows e.g. `acc_..._Q_15` instead of `_1916_`.
autoname
abc -D {target_delay} -constr {constr_path} {liberty_args}
write_verilog {netlist_path}
"""

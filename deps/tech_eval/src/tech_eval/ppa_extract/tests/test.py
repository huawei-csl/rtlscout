
import os
from pathlib import Path
import pytest

from spirehdl.spirehdl import UInt
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl_verilog_testbench import VerilogTestbenchSimulator


def build_accumulator():
    m = Module("Mac32", with_clock=True, with_reset=True)
    a = m.input(UInt(8), "a")
    b = m.input(UInt(8), "b")
    acc = m.reg(UInt(8), "acc", init=0)
    out = m.output(UInt(8), "out")

    acc.next = acc + a + b
    out <<= acc
    return m, a, b, acc, out


def test_verilog_testbench_basic_sequence(tmp_path: Path):
    m, a, b, acc, _ = build_accumulator()

    tb = VerilogTestbenchSimulator(m, clock_period=10.0, eval_delay=1.0)
    tb.reset(True)
    tb.step()  # capture reset behaviour
    tb.deassert_reset()
    #tb.set(a, 1)
    tb.set()
    tb.set(b, 2)
    tb.eval()
    tb.step()
    tb.set(acc, 5)
    tb.eval()

    out_path = tmp_path / "mac_tb.v"
    tb.write_testbench(out_path)
    text = out_path.read_text()

    assert "module Mac32_tb" in text
    assert "Mac32 dut" in text
    assert "a = 8'h01" in text
    assert "b = 8'h02" in text
    assert "dut.acc = 8'h05" in text
    assert "$fatal" in text  # expectations are emitted
    assert "#5" in text  # half-period delay
    
    # module to file
    str_m = m.to_verilog()
    verilog_path = tmp_path / "mac.v"
    verilog_path.write_text(str_m)

def test_verilog_testbench_requires_events(tmp_path):
    m = Module("Comb", with_clock=False, with_reset=False)
    a = m.input(UInt(4), "a")
    y = m.output(UInt(4), "y")
    y <<= a

    tb = VerilogTestbenchSimulator(m)
    with pytest.raises(RuntimeError):
        tb.write_testbench(tmp_path / "comb_tb.v")

    with pytest.raises(RuntimeError):
        tb.step()
        
        
if __name__ == "__main__":
    
    # make local tempdir for testing with os tempdir
    tmpdir = os.path.join(os.getcwd(), "temp_test/")
    os.makedirs(tmpdir, exist_ok=True)
    
    #pytest.main([__file__])
    test_verilog_testbench_basic_sequence(Path(tmpdir))
    test_verilog_testbench_requires_events(Path(tmpdir))
    
    
# sources: https://github.com/antmicro/verilog-power-analysis-workflows
# https://github.com/huawei-csl/GENIAL/blob/main/src/genial/templates_and_launch_scripts/0_defaults/power_extraction_v0/launch_script_power_extraction.sh


#verilator -Wall --binary mac_tb.v mac.v --top-module Mac32_tb   -Wno-DECLFILENAME -Wno-WIDTHEXPAND -Wno-UNUSEDSIGNAL
#make: Entering directory '/workspaces/tech_eval/temp_test/obj_dir'

#./run_verilator.sh  temp_test/mac.v  temp_test/mac_tb.v  Mac32_tb

# Intro ######################################

# location of OpenROAD-flow-scripts: /prog/OpenROAD-flow-scripts
# basic config.mk file:
# export PLATFORM               = asap7

# export DESIGN_NICKNAME        = default_example
# export DESIGN_NAME            = mydesign_top

# export VERILOG_FILES         = $(sort $(wildcard $(DESIGN_HOME)/src/$(DESIGN_NICKNAME)/*.v))
# export SDC_FILE              = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc

# export CORE_UTILIZATION       = 40
# export CORE_ASPECT_RATIO      = 1
# export CORE_MARGIN            = 2
# export PLACE_DENSITY_LB_ADDON = 0.20

# export ENABLE_DPO = 0

# export TNS_END_PERCENT        = 100

# other files take from here:

# /OpenROAD-flow-scripts/flow/designs/asap7/uart$ ls /prog/OpenROAD-flow-scripts/flow/designs/asap7/uart
# config.mk  constraint.sdc  rules-base.json

# Procedure ###############################

# do a Makefile which does the following:
# use arguments which can be passed to make:

# make directory:  OpenROAD-flow-scripts/flow/designs/asap7/myname/
# copy, config.mk, constraint.sdc and rules-base.json there. optional metadata-base-ok.json and autotuner.json
# in config.mk, set the following variables:
#export DESIGN_NICKNAME        = default_example <- replace with myname
#export DESIGN_NAME            = mydesign_top <-replace with top module name, e.g. mytop

# make directory:  OpenROAD-flow-scripts/flow/designs/myname/
# copy source source files there. e.g. mydesign.v, use file /workspaces/tech_eval/temp_test/mac.v

#cd OpenROAD-flow-scripts
#make -C flow DESIGN_CONFIG=designs/asap7/myname/config.mk route

# output file path:
# output: OpenROAD-flow-scripts/flow/results/asap7/myname/base/1_synth.v
#
# run verilator on output file and testbench file, for tb file use /workspaces/tech_eval/temp_test/mac_tb.v, use run_verilator.sh
#
# trace2power --clk-freq 1000000 --top dut --remove-virtual-pins --output total_output  --limit-scope Mac32_tb.dut dump.vcd 
#
# export LIB_DIR=/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/
# export LEF_DIR=/prog/OpenROAD-flow-scripts/flow/platforms/asap7/lef/
#
# openroad -exit power.tcl
#
# instead of the above openroad command (source total_output + set_pin_activity_and_duty), following command in openroad could be used:
# (deprecated) read_power_activities -vcd dump.vcd -scope Mac32_tb 
# read_vcd  -scope Mac32_tb dump.vcd          


# Read technology LEF file FIRST
read_lef $::env(LEF_DIR)/asap7_tech_1x_201209.lef

# Read standard cell LEF files
read_lef $::env(LEF_DIR)/asap7sc7p5t_28_R_1x_220121a.lef

# Liberty (timing + power)
read_liberty $::env(LIB_DIR)/asap7sc7p5t_AO_RVT_FF_nldm_211120.lib.gz
read_liberty $::env(LIB_DIR)/asap7sc7p5t_INVBUF_RVT_FF_nldm_220122.lib.gz
read_liberty $::env(LIB_DIR)/asap7sc7p5t_OA_RVT_FF_nldm_211120.lib.gz
read_liberty $::env(LIB_DIR)/asap7sc7p5t_SIMPLE_RVT_FF_nldm_211120.lib.gz
read_liberty $::env(LIB_DIR)/asap7sc7p5t_SEQ_RVT_FF_nldm_220123.lib

# Netlist + constraints
read_verilog $::env(NETLIST_PATH)
link_design $::env(TOP_MODULE)
read_sdc $::env(SDC_PATH)

# ----- Apply average activities from a single file -----
# Expecting a Tcl file defined via TRACE2POWER_OUT that defines:
#   proc set_pin_activity_and_duty {} { set_power_activity ... }
set activity_file $::env(TRACE2POWER_OUT)
if {![file exists $activity_file]} {
  error "Activity file '$activity_file' not found in [pwd]"
}
file mkdir result

source $activity_file
 
if {[llength [info procs set_pin_activity_and_duty]]} {
  set_pin_activity_and_duty
} else {
  puts stderr "Warning: '$activity_file' did not define set_pin_activity_and_duty; assuming it already called set_power_activity."
}

# or
# read_vcd  -scope Mac32_tb dump.vcd   

# Power report (single global/average power)
report_power > result/power.rpt

# Optional timing check
report_checks -path_delay max -format json > result/post_synth_delay.rpt

report_design_area > result/area.rpt

puts "Applied activities from '$activity_file' and wrote power to result/total_output.rpt"

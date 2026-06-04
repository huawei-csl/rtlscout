SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
MAKEFILE_DIR := $(patsubst %/,%,$(dir $(MAKEFILE_PATH)))
REPO_ROOT := $(abspath $(MAKEFILE_DIR)/..)

# User-configurable variables (override via `make VAR=value`)
OR_ROOT ?= /prog/OpenROAD-flow-scripts
PLATFORM ?= asap7
DESIGN_NICKNAME ?= myname
TOP_MODULE ?= Mac32
TOP_MODULE_TB ?= Mac32_tb
OPENROAD_DESIGN_NAME ?= $(TOP_MODULE)
SOURCE_FILES ?= $(REPO_ROOT)/temp_test/mac.v
TESTBENCH_FILE ?= $(REPO_ROOT)/temp_test/mac_tb.v
CELL_SOURCES ?= /app/asap7sc7p5t_28/Verilog
DUMP_VCD ?= dump.vcd
TRACE2POWER ?= trace2power
TRACE2POWER_CLK_FREQ ?= 1000000
TRACE2POWER_TOP ?= dut
TRACE2POWER_OUT ?= result/power_activity
POWER_SCRIPT ?= $(MAKEFILE_DIR)/power.tcl
LIB_DIR ?= /prog/OpenROAD-flow-scripts/flow/platforms/asap7/lib/NLDM/
LEF_DIR ?= /prog/OpenROAD-flow-scripts/flow/platforms/asap7/lef/
VERILATOR_FLAGS_FILE := $(MAKEFILE_DIR)/sim.vc
VERILATOR_FLAGS_EXPANDED := $(MAKEFILE_DIR)/.sim.vc.expanded
VERILATOR_EXE := out/V$(TOP_MODULE_TB)
VERILATOR ?= verilator
VERILATOR_COMMON_FLAGS := -Wall -Wno-DECLFILENAME -Wno-WIDTHEXPAND -Wno-UNUSEDSIGNAL --Wno-EOFNEWLINE -Wno-BLKSEQ -Wno-fatal

# Derived paths
OR_FLOW_DIR := $(OR_ROOT)/flow
DESIGN_TEMPLATE_DIR := $(OR_FLOW_DIR)/designs/$(PLATFORM)/uart
DESIGN_CONFIG_DIR := $(OR_FLOW_DIR)/designs/$(PLATFORM)/$(DESIGN_NICKNAME)
DESIGN_SRC_DIR := $(OR_FLOW_DIR)/designs/src/$(DESIGN_NICKNAME)
CONFIG_PATH := $(DESIGN_CONFIG_DIR)/config.mk
OPENROAD_RESULT_DIR := $(OR_FLOW_DIR)/results/$(PLATFORM)/$(DESIGN_NICKNAME)/base
NETLIST_PATH := $(OPENROAD_RESULT_DIR)/1_synth.v
SDC_PATH := $(OPENROAD_RESULT_DIR)/1_synth.sdc
SOURCE_STAMP := $(DESIGN_SRC_DIR)/.sources.stamp
CONFIG_FILES := config.mk constraint.sdc rules-base.json metadata-base-ok.json autotuner.json
CONFIG_SCRIPT := $(REPO_ROOT)/src/tech_eval/update_config.py
TRACE2POWER_SCOPE := $(TOP_MODULE_TB).dut

.DEFAULT_GOAL := run

.PHONY: all run verilate power clean

all: run

# End-to-end target: prepare OpenROAD input, run the flow, then execute Verilator and power analysis
run: power

verilate: $(DUMP_VCD)
	@echo "Waveform generated at $(DUMP_VCD)"

$(DUMP_VCD): $(NETLIST_PATH) $(VERILATOR_FLAGS_EXPANDED)
	@echo "Running Verilator with synthesized netlist and testbench..."
	@echo "  Verilator command: $(VERILATOR) $(VERILATOR_COMMON_FLAGS) -f \"$(VERILATOR_FLAGS_EXPANDED)\" --top-module \"$(TOP_MODULE_TB)\" \"$(NETLIST_PATH)\" \"$(TESTBENCH_FILE)\""
	$(VERILATOR) $(VERILATOR_COMMON_FLAGS) \
		-f "$(VERILATOR_FLAGS_EXPANDED)" \
		--top-module "$(TOP_MODULE_TB)" \
		"$(NETLIST_PATH)" "$(TESTBENCH_FILE)"
	./$(VERILATOR_EXE)
	@test -f "$(DUMP_VCD)" || { echo "Expected VCD $(DUMP_VCD) not produced"; exit 1; }

power: $(DUMP_VCD)
	$(TRACE2POWER) --clk-freq "$(TRACE2POWER_CLK_FREQ)" --top "$(TRACE2POWER_TOP)" \
		--remove-virtual-pins --output "$(TRACE2POWER_OUT)" \
		--limit-scope "$(TRACE2POWER_SCOPE)" "$(DUMP_VCD)"
	export LIB_DIR="$(LIB_DIR)"; \
	export LEF_DIR="$(LEF_DIR)"; \
	export NETLIST_PATH="$(NETLIST_PATH)"; \
	export SDC_PATH="$(SDC_PATH)"; \
	export TOP_MODULE="$(TOP_MODULE)"; \
	export TRACE2POWER_OUT="$(TRACE2POWER_OUT)"; \
	openroad -exit "$(POWER_SCRIPT)"
	python -m tech_eval.recompose_total_power

# Run the OpenROAD flow to create the synthesized netlist (synth or route)
$(NETLIST_PATH): $(CONFIG_PATH) $(SOURCE_STAMP)
	$(MAKE) -C "$(OR_FLOW_DIR)" \
		DESIGN_CONFIG="designs/$(PLATFORM)/$(DESIGN_NICKNAME)/config.mk" \
		synth
	@test -f "$(NETLIST_PATH)"
	@test -f "$(SDC_PATH)"

# Expand sim.vc with the runtime CELL_SOURCES path
$(VERILATOR_FLAGS_EXPANDED): $(VERILATOR_FLAGS_FILE) $(MAKEFILE_PATH)
	CELL_SOURCES="$(CELL_SOURCES)" envsubst '$$CELL_SOURCES' < "$(VERILATOR_FLAGS_FILE)" > "$@"

# Prepare platform-specific config (copy template files, adjust variables)
$(CONFIG_PATH):
	mkdir -p "$(DESIGN_CONFIG_DIR)"
	for file in $(CONFIG_FILES); do \
		if [ -f "$(DESIGN_TEMPLATE_DIR)/$$file" ]; then \
			cp -f "$(DESIGN_TEMPLATE_DIR)/$$file" "$(DESIGN_CONFIG_DIR)/"; \
		fi; \
	done
	python3 "$(CONFIG_SCRIPT)" "$@" "$(DESIGN_NICKNAME)" "$(OPENROAD_DESIGN_NAME)"

# Copy user RTL sources into the OpenROAD design area
$(SOURCE_STAMP): $(SOURCE_FILES)
	mkdir -p "$(DESIGN_SRC_DIR)"
	cp -f $(SOURCE_FILES) "$(DESIGN_SRC_DIR)/"
	touch "$(SOURCE_STAMP)"

clean:
	rm -f "$(SOURCE_STAMP)"
	rm -rf "$(DESIGN_CONFIG_DIR)" "$(DESIGN_SRC_DIR)" out
	rm -f "$(VERILATOR_FLAGS_EXPANDED)"
	rm -f $(TRACE2POWER_OUT) $(DUMP_VCD)
	$(MAKE) -C "$(OR_FLOW_DIR)" \
	  	DESIGN_CONFIG="designs/$(PLATFORM)/$(DESIGN_NICKNAME)/config.mk" \
	    clean_synth

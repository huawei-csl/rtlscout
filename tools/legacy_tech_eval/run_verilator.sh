#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || $# -gt 5 ]]; then
    echo "Usage: $0 <source_file> <testbench_file> <top_module_name> [vcd_file_path] [obj_dir]" >&2
    exit 1
fi

SOURCE_FILE=$1
TESTBENCH_FILE=$2
TOP_MODULE=$3
# optional 4th arg: VCD file path
VCD_FILE_PATH=${4:-}
# optional 5th arg: object directory
OBJ_DIR=${5:-"./obj_dir"}

if [[ ! -f $SOURCE_FILE ]]; then
    echo "Source file not found: $SOURCE_FILE" >&2
    exit 1
fi

if [[ ! -f $TESTBENCH_FILE ]]; then
    echo "Testbench file not found: $TESTBENCH_FILE" >&2
    exit 1
fi

LOG_FILE=$(mktemp)
trap 'rm -f "$LOG_FILE"' EXIT

# set nproc
NPROC=4

VCD_DEFINE=()
if [[ -n $VCD_FILE_PATH ]]; then
    VCD_DEFINE=(-DVCD_FILE_PATH="$VCD_FILE_PATH")
fi

OBJ_DIR_ARG=()
if [[ -n $OBJ_DIR ]]; then
    OBJ_DIR_ARG=(--Mdir "$OBJ_DIR")
fi

verilator -Wall -j $NPROC --build --binary "$TESTBENCH_FILE" "$SOURCE_FILE" --top-module "$TOP_MODULE" "${VCD_DEFINE[@]}" "${OBJ_DIR_ARG[@]}" \
    -Wno-DECLFILENAME -Wno-WIDTHEXPAND -Wno-UNUSEDSIGNAL --Wno-EOFNEWLINE --trace --trace-underscore --no-trace-top | tee "$LOG_FILE"

if [[ -n $OBJ_DIR ]]; then
    EXECUTABLE="$OBJ_DIR/V${TOP_MODULE}"
else
    EXECUTABLE=./obj_dir/V${TOP_MODULE}
fi

if [[ ! -x $EXECUTABLE ]]; then
    echo "Expected executable not found: $EXECUTABLE" >&2
    exit 1
fi

"$EXECUTABLE" | tee -a "$LOG_FILE"

if grep -q 'Testbench completed successfully.' "$LOG_FILE"; then
    exit 0
fi

echo "'Testbench completed successfully.' not found in output." >&2
exit 2

#!/usr/bin/env bash
set -euo pipefail

yosys -V || true

source /home/vscode/pyenv_eda/bin/activate

uv pip install -e deps/spire-hdl
uv pip install -e deps/tech_eval
uv pip install -r requirements.txt

# flowy is not part of the public release. If a local deps/flowy is present (e.g. you added
# it yourself), install it; otherwise continue without it. The agent's flowy code paths stay
# dormant unless flowy is installed and --flowy-optimize is passed.
if [ -d deps/flowy ]; then
    uv pip install -e deps/flowy
else
    echo "INFO: flowy not included in this release — flowy-based optimization is unavailable."
fi

# --- Verilator sequential-UDP patch check -------------------------------------
# The base image must ship the patched Verilator (v5.040 + seq-UDP NBA fix,
# applied by deps/tech_eval/.devcontainer/Dockerfile; version string carries
# "(mod)"). Without it, gate-level sims of netlists with vendor UDP flop
# models can be SILENTLY corrupted
if verilator --version 2>/dev/null | grep -q "(mod)"; then
    echo "OK: patched Verilator detected: $(verilator --version)"
else
    echo "##############################################################" >&2
    echo "WARNING: UNPATCHED Verilator detected: $(verilator --version)" >&2
    echo "Sequential-UDP netlist sims (vendor cell models) may be" >&2
    echo "silently wrong. Rebuild the base image to pick up the patch:" >&2
    echo "  NO_CACHE=1 bash .devcontainer/build_image.sh" >&2
    echo "##############################################################" >&2
fi

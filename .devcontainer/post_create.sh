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

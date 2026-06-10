#!/usr/bin/env bash
# setup_workspace.sh — Initialize the spire-hdl submodule.
#
# Usage:
#   bash setup_workspace.sh
#
# tech_eval is vendored into the repo via `git subtree` (no submodule to init).
# flowy and mockturtle are intentionally not part of the public release.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# Only initialize on first startup. Skipping when already checked out avoids
# clobbering a development branch back to the committed commit (detached HEAD).
if git submodule status deps/spire-hdl 2>/dev/null | grep -q '^-'; then
  echo "Initializing spire-hdl submodule..."
  git submodule update --init deps/spire-hdl
else
  echo "spire-hdl submodule already initialized; leaving it as-is."
fi

echo ""
echo "Workspace ready."
echo ""
echo "Next steps:"
echo "  1. Copy and edit .env:  cp .env.template .env   # add your API keys"
echo "  2. Build the Docker image:  bash .devcontainer/build_image.sh"
echo "  3. Start the container:     bash .devcontainer/start_container.sh"

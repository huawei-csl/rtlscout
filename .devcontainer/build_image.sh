#!/usr/bin/env bash
# build_image.sh — Build the rtlscout_base and rtlscout Docker images.
#
# Usage:
#   bash build_image.sh
#
# Step 1 builds the rtlscout_base image from deps/tech_eval/.devcontainer/Dockerfile.
#   This is HEAVY (compiles OpenROAD from source) and network-dependent (~1-2h first time).
# Step 2 builds the thin rtlscout layer (ELAU only) on top.
#
# Env:
#   NO_CACHE=1   force a clean rebuild (docker build --no-cache) AND rebuild the base even if it
#                already exists — i.e. a genuine from-scratch build, re-fetching all upstream sources.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CACHE_FLAG=""
[ "${NO_CACHE:-0}" = "1" ] && CACHE_FLAG="--no-cache"

# ---- Step 1: Build base image from tech_eval (skip if already exists, unless NO_CACHE=1) ----
BASE_IMAGE="rtlscout_base:latest"
BASE_DOCKERFILE="$REPO_ROOT/deps/tech_eval/.devcontainer/Dockerfile"

if [ "${NO_CACHE:-0}" != "1" ] && docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    echo "Base image $BASE_IMAGE already exists, skipping."
else
    echo "Building base image $BASE_IMAGE (heavy: builds OpenROAD from source)..."
    docker build $CACHE_FLAG -t "$BASE_IMAGE" -f "$BASE_DOCKERFILE" "$REPO_ROOT/deps/tech_eval"
fi

# ---- Step 2: Build rtlscout layer ----
echo "Building rtlscout:latest..."
docker build $CACHE_FLAG \
    -t rtlscout:latest -f "$SCRIPT_DIR/Dockerfile" "$REPO_ROOT"

echo ""
echo "Done. Images: $BASE_IMAGE, rtlscout:latest"
echo "Next: bash $SCRIPT_DIR/start_container.sh"

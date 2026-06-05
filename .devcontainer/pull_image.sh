#!/usr/bin/env bash
# pull_image.sh — Pull the prebuilt slim EDA image from GHCR instead of building it from source.
#
# This is the default/recommended way to get the image: a ~3 GB pull vs. a ~1-2 h from-source build.
# It tags the pulled image as `rtlscout:latest` so start_container.sh and the VS Code devcontainer
# (which both expect that tag) use it. The self-build path (build_image.sh) remains fully supported.
#
# Usage:
#   bash pull_image.sh
# Env:
#   RTLSCOUT_IMAGE     remote image to pull (default: ghcr.io/huawei-csl/rtlscout:slim)
#   FORCE_PULL=1       re-pull even if rtlscout:latest already exists locally

set -euo pipefail

IMAGE="${RTLSCOUT_IMAGE:-ghcr.io/huawei-csl/rtlscout:slim}"
LOCAL_TAG="rtlscout:latest"

if [ "${FORCE_PULL:-0}" != "1" ] && docker image inspect "$LOCAL_TAG" >/dev/null 2>&1; then
    echo "$LOCAL_TAG already present locally — skipping pull (set FORCE_PULL=1 to re-pull)."
    exit 0
fi

echo "Pulling prebuilt image: $IMAGE"
echo "  (no GHCR login needed if the package is public; ~3 GB)"
docker pull "$IMAGE"
docker tag "$IMAGE" "$LOCAL_TAG"

echo ""
echo "Done. Tagged $IMAGE as $LOCAL_TAG."
echo "Next: bash $(dirname "${BASH_SOURCE[0]}")/start_container.sh"
echo "(To build from source instead: bash .devcontainer/build_image.sh  — or BUILD_SLIM=1 for the slim build.)"

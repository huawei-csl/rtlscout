#!/usr/bin/env bash
# start_container.sh — Start an interactive container with the repo mounted.
#
# Usage:
#   bash start_container.sh
#
# Run from the rtl_scout repo root, or the script auto-detects its location.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Verify deps are present (spire-hdl submodule + vendored tech_eval)
for repo in deps/spire-hdl deps/tech_eval; do
    if [[ ! -d "$REPO_DIR/$repo" ]]; then
        echo "ERROR: $repo not found."
        echo "  For deps/spire-hdl run: git submodule update --init deps/spire-hdl"
        exit 1
    fi
done

IMAGE="rtlscout:latest"
if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "ERROR: Docker image $IMAGE not found. Run build_image.sh first."
    exit 1
fi

HOST_UID=$(id -u)
HOST_GID=$(id -g)

echo "Starting container with mount:"
echo "  rtl_scout -> /workspaces/rtl_scout (includes deps/)"
echo ""

exec docker run --rm -it \
    --user root \
    -e HOST_UID="$HOST_UID" \
    -e HOST_GID="$HOST_GID" \
    -v "$REPO_DIR:/workspaces/rtl_scout" \
    -w /workspaces/rtl_scout \
    "$IMAGE" \
    bash /workspaces/rtl_scout/.devcontainer/entrypoint.sh

#!/bin/bash
# entrypoint.sh — Remap vscode UID/GID to match host user, then drop to vscode.
# Called by start_container.sh as root inside the container.
set -eu

# Remap vscode UID/GID to match host user
usermod -u "$HOST_UID" vscode 2>/dev/null
groupmod -g "$HOST_GID" vscode 2>/dev/null
chown -R "$HOST_UID":"$HOST_GID" /home/vscode 2>/dev/null || true

# Write the vscode startup commands to a temp script (runs as vscode)
cat > /tmp/start_vscode.sh <<'EOF'
#!/bin/bash
export PATH="/home/vscode/pyenv_eda/bin:/opt/tools/openroad/OpenROAD/bin:/opt/tools/opensta/app:/opt/tools/trace2power/bin:/usr/local/bin:$PATH"
cd /workspaces/rtl_scout
bash .devcontainer/post_create.sh
echo ""
echo "============================================================"
echo "  Environment ready!"
echo ""
echo "  Quick start (evaluate a design — no LLM needed):"
echo "    python run_eval.py <design.sv> --benchmark benchmarks/simple_adder \\"
echo "        --top-module adder --cost-metric transistors"
echo ""
echo "  Run the agent on a benchmark (needs API keys in .env):"
echo "    python run_benchmark.py --benchmark simple_adder \\"
echo "        --model claude:claude-haiku-4-5-20251001 --max-steps 5"
echo ""
echo "  NOTE: Set your API keys in .env first. See .env.template."
echo "============================================================"
echo ""
exec bash
EOF
chmod +x /tmp/start_vscode.sh
exec su -s /bin/bash vscode -c /tmp/start_vscode.sh

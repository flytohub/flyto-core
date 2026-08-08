#!/bin/bash
# Shared MCP entry point. Both Claude Code (.mcp.json) and Codex
# (~/.codex/config.toml) launch the server through this script so the two
# agents always run the same interpreter and the same code.
cd "$(dirname "$0")/src"
PY="$(cd .. && pwd)/.venv/bin/python"
[ -x "$PY" ] || PY=python3
exec "$PY" -m core.mcp_server 2>/tmp/flyto-core-mcp.log

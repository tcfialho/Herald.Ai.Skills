#!/usr/bin/env bash
# ask_claude.sh — thin shim; all logic lives in ask_claude.py (cross-platform).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/ask_claude.py" "$@"

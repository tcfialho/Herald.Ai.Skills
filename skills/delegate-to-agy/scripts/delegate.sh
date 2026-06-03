#!/usr/bin/env bash
# delegate.sh — thin Linux/macOS wrapper; delegates to delegate.py (cross-platform).
# Kept for backward compatibility. All logic lives in delegate.py.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/delegate.py" "$@"

#!/usr/bin/env bash
# release.sh — thin wrapper; all logic lives in scripts/build_release.py.
# Builds an installable copy of this skill in release/skill-test/ (excludes
# README.md, this skill's own dogfood tests/, and caches — see the script's
# docstring for the exact rules).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# `command -v` only checks existence, not that it actually runs — on Windows
# `python3` can resolve to the broken Microsoft Store app-execution-alias shim
# even when a real interpreter is on PATH as `python`. Probe execution instead.
PY=""
for candidate in python3 python py; do
  if "$candidate" --version >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "release.sh: no working Python interpreter found on PATH (tried python3, python, py)" >&2
  exit 1
fi
exec "$PY" "$SCRIPT_DIR/scripts/build_release.py" "$@"

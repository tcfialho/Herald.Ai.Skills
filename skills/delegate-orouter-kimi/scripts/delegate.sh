#!/usr/bin/env bash
set -euo pipefail

model="${OROUTER_KIMI_MODEL:-moonshotai/kimi-k2.6}"
orouter_bin="${OROUTER_BIN:-orouter}"
permission_mode="${OROUTER_KIMI_PERMISSION_MODE-}"
tools="${OROUTER_KIMI_TOOLS-}"
budget="${OROUTER_KIMI_MAX_BUDGET_USD-0.50}"
timeout_seconds="${OROUTER_KIMI_TIMEOUT_SECONDS:-120}"

if [[ $# -gt 0 ]]; then
  prompt="$*"
elif [[ ! -t 0 ]]; then
  prompt="$(cat)"
else
  cat >&2 <<'EOF'
usage:
  delegate.sh "prompt..."
  printf '%s\n' "prompt..." | delegate.sh

Delegates to orouter using moonshotai/kimi-k2.6 by default.
EOF
  exit 2
fi

if [[ -z "${prompt//[[:space:]]/}" ]]; then
  echo "delegate.sh: prompt is empty" >&2
  exit 2
fi

wrapped_prompt="$(cat <<EOF
You are Kimi running as an independent delegated reviewer for Codex.

Give a concrete second opinion. Prefer actionable findings, weak assumptions, missing checks, and concise reasoning. Do not claim to have inspected files unless the prompt includes their contents. Do not ask to modify files.

Delegated task:
$prompt
EOF
)"

args=(
  "$model"
  "--no-session-persistence"
  "--tools" "$tools"
)

if [[ -n "$permission_mode" ]]; then
  args+=("--permission-mode" "$permission_mode")
fi

if [[ -n "$budget" ]]; then
  args+=("--max-budget-usd" "$budget")
fi

args+=("-p" "$wrapped_prompt")

if [[ -n "$timeout_seconds" && "$timeout_seconds" != "0" ]]; then
  exec timeout "$timeout_seconds" "$orouter_bin" "${args[@]}"
fi

exec "$orouter_bin" "${args[@]}"

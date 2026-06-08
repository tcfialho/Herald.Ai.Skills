---
name: delegate-orouter-kimi
description: Delegate independent analysis to the local OpenRouter launcher `orouter` using `moonshotai/kimi-k2.6`. Use when Codex should get a second opinion or adversarial review from Kimi for code review, implementation plans, bug hypotheses, design tradeoffs, risk analysis, or critique of a proposed answer, especially as an alternative to delegating to `agy`.
---

# Delegate To Kimi

## Overview

Use Kimi as a read-only second opinion through the local `orouter` utility. Treat the result as advisory: verify claims against the codebase before applying changes or reporting conclusions.

## Workflow

1. Decide whether delegation is useful. Prefer it for ambiguous bugs, architectural tradeoffs, diff reviews, plan reviews, and cases where an independent critique may catch missed assumptions.
2. Build a self-contained prompt. Include the task, relevant snippets, diffs, logs, constraints, and the exact kind of output wanted. Redact secrets and avoid sending API keys or private credentials.
3. Run this skill's `scripts/delegate.sh` with the prompt by stdin or arguments:

```bash
printf '%s\n' "$prompt" | ~/.claude/skills/delegate-orouter-kimi/scripts/delegate.sh
```

or:

```bash
~/.claude/skills/delegate-orouter-kimi/scripts/delegate.sh "Review this plan: ..."
```

4. Compare Kimi's answer with local evidence. Use it to sharpen the final answer, but do not blindly adopt unverified claims.

## Script Behavior

- Model: `moonshotai/kimi-k2.6` by default.
- Command path: calls the local `orouter` launcher, which already handles OpenRouter auth and config isolation.
- Tools: disabled by default with `--tools ""`, so Kimi only sees the prompt you provide.
- Persistence: disabled with `--no-session-persistence`.
- Budget: capped by `OROUTER_KIMI_MAX_BUDGET_USD`, default `0.50`. Set it to an empty string to omit the cap.
- Timeout: capped by `OROUTER_KIMI_TIMEOUT_SECONDS`, default `120`. Set it to `0` to omit the timeout wrapper.

Environment overrides:

- `OROUTER_KIMI_MODEL`: use a different OpenRouter model.
- `OROUTER_BIN`: use a different launcher path.
- `OROUTER_KIMI_TOOLS`: pass a Claude Code tools value, for example `default`. Keep unset for read-only prompt-only delegation.
- `OROUTER_KIMI_PERMISSION_MODE`: pass a Claude Code permission mode only when needed. Keep unset by default.
- `OROUTER_KIMI_MAX_BUDGET_USD`: default `0.50`.
- `OROUTER_KIMI_TIMEOUT_SECONDS`: default `120`.

## Reporting Back

Summarize only the useful parts of Kimi's output. If it disagrees with local evidence, say so and explain which evidence wins. If Kimi surfaces a plausible issue, verify it locally before editing files.

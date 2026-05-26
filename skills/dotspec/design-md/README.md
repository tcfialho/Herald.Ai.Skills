# design-md - Standalone Agent Skill

Extract a Google-spec `DESIGN.md` from any public URL using static HTML/CSS analysis. The pipeline no longer calls a second LLM, requires no API key, and does not require a local `claude` binary. It prepares evidence and a prompt for the agent that invoked the skill; that same agent writes `DESIGN.md`, then the script finalizes deterministic artifacts.

## Install

```bash
cp -R design-md /path/to/your-project/.claude/skills/
cd /path/to/your-project/.claude/skills/design-md
npm install
```

Requirements:

- Node 18+
- No LLM API key
- No nested agent/CLI provider

## Workflow

From your project root:

```bash
node .claude/skills/design-md/run.cjs --url https://www.anthropic.com/
```

The first run writes:

```text
outputs/design-md/{slug}/.run-{timestamp}/inputs/prompt.txt
outputs/design-md/{slug}/.run-{timestamp}/caller-instructions.txt
```

Read `inputs/prompt.txt`, use the current calling agent to write `DESIGN.md` to the requested output path, then finalize:

```bash
node .claude/skills/design-md/run.cjs --url https://www.anthropic.com/ --out outputs/design-md/{slug}/.run-{timestamp} --finalize
```

## What It Produces

```text
outputs/design-md/{slug}/
  DESIGN.md
  tokens.json
  tokens-extended.json
  render-contract.json
  preview.html
  extraction-log.yaml
  lint-report.json
  quality-score.json
  style-fingerprint.json
  agent-prompt.txt
  telemetry.json
  caller-handoff.json
  caller-instructions.txt
  inputs/
```

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--url <url>` | required | Public http(s) URL |
| `--out <dir>` | scratch run under `outputs/design-md/{slug}/` | Output directory |
| `--prompt <file>` | `data/url-extract-prompt.txt` | Custom prompt template |
| `--compare <file>` | none | Drift-check against a local `DESIGN.md` |
| `--no-content-gate` | off | Skip thin-content validation |
| `--no-reuse` | off | Disable phase reuse |
| `--finalize` | off | Continue after the calling agent has written `DESIGN.md` |

Old provider flags are ignored with a compatibility warning: `--provider`, `--model`, `--max-tokens`, `--no-llm-retry`.

## Tests

```bash
npm test
```

## Design Constraint

The skill is intentionally split into deterministic collection/finalization plus caller-agent cognition. It must not call Anthropic, OpenRouter, or any other LLM API, and must not spawn a second agent session.

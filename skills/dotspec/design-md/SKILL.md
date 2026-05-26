---
name: design-md
description: 'Extracts Google-spec DESIGN.md from any URL via static HTML/CSS analysis. Uses the calling agent LLM for the cognitive step; no API key or nested LLM call is required.'
version: 1.1.0
---

# /design-md - URL to DESIGN.md Pipeline

Extract a Google-spec `DESIGN.md` from a public URL using static HTML/CSS analysis only. The Node pipeline fetches and analyzes source evidence, then hands the prepared prompt to the agent that invoked this skill. Do not call another LLM provider from inside the skill.

## When to invoke

- User asks to extract a design system or `DESIGN.md` from a URL.
- User wants `tokens.json`, `preview.html`, lint output, or drift detection from a live URL.
- User wants a stack/style fingerprint of an unknown site.

Skip if the user wants generated TSX/components rather than a design-system extraction.

## Requirements

- Node 18+
- `npm install` inside the skill folder
- No LLM API key
- No `claude` CLI requirement

## Agent Workflow

1. Run the collector:

```bash
node .claude/skills/design-md/run.cjs --url https://example.com/
```

2. Read the generated handoff:

```text
outputs/design-md/{slug}/.run-{timestamp}/caller-instructions.txt
outputs/design-md/{slug}/.run-{timestamp}/inputs/prompt.txt
```

3. As the calling agent, follow `inputs/prompt.txt` and write the requested `DESIGN.md` to the exact `OUTPUT_PATH` named in that prompt.

4. Finalize deterministic artifacts:

```bash
node .claude/skills/design-md/run.cjs --url https://example.com/ --out outputs/design-md/{slug}/.run-{timestamp} --finalize
```

The finalization step parses YAML frontmatter, enriches tokens, lints, scores quality, writes drift output when requested, renders `preview.html`, and promotes or archives the run.

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--url <url>` | required | Public http(s) URL |
| `--out <dir>` | scratch run under `outputs/design-md/{slug}/` | Output directory |
| `--prompt <file>` | `data/url-extract-prompt.txt` | Prompt template used for the caller handoff |
| `--compare <file>` | none | Local `DESIGN.md` to drift-check during finalize |
| `--no-content-gate` | off | Skip bot/paywall/thin-content validation |
| `--no-reuse` | off | Disable phase reuse from prior promoted extracts |
| `--finalize` | off | Continue after the calling agent has written `DESIGN.md` |

Removed compatibility flags (`--provider`, `--model`, `--max-tokens`, `--no-llm-retry`) are accepted only so old commands do not corrupt argument parsing; they are ignored with a warning.

## Output Layout

```text
{company}/
  DESIGN.md
  tokens.json
  tokens-extended.json
  render-contract.json
  extraction-log.yaml
  lint-report.json
  quality-score.json
  preview.html
  style-fingerprint.json
  agent-prompt.txt
  telemetry.json
  caller-handoff.json
  caller-instructions.txt
  inputs/
    prompt.txt
    page.html
    css-collected.css
    css-vars-detected.json
    font-faces.json
    token-usage-graph.json
    component-properties.json
    stack-summary.json
```

## Pipeline

1. Fetch HTML and response headers.
2. Collect linked CSS, inline CSS, `style=""`, favicon, and logo.
3. Detect colors, CSS vars, font faces, typography, spacing, radius, shadows, motion, breakpoints, dark mode, component properties, stack, and visual archetype.
4. Convert HTML to markdown and extract page copy specimens.
5. Write `inputs/prompt.txt` plus `caller-instructions.txt`.
6. The calling agent writes `DESIGN.md`; the script never invokes a second model.
7. Finalize: normalize, parse tokens, enrich deterministic artifacts, lint, score, drift-check, and render preview.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Collector handoff prepared, or finalized successfully |
| 1 | Usage error |
| 2 | `--finalize` was requested but `DESIGN.md` is missing |
| 4 | Content-validation gate failed |
| 5 | Caller-authored `DESIGN.md` is missing required sections |

## Tests

```bash
npm test
```

## Anti-Patterns

- Do not add Playwright, Puppeteer, Hyperbrowser, or browser automation.
- Do not call Anthropic, OpenRouter, or any other LLM API from this skill.
- Do not spawn `claude -p` or another agent. The current calling agent is the cognition layer.
- Do not bypass the content-validation gate unless the user explicitly accepts a lower-confidence extraction.

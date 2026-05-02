---
name: nexus2-spike
description: Nexus 2.0 /spike research stage. Use when the user needs technical discovery, proof-of-concept scripts, mini programs, integration experiments, or tradeoff analysis before backlog implementation. Produces or updates the Spikes section in nexus/spec.md and may prepare SP-* backlog stories for nexus/backlog/.
---

# Nexus 2.0 /spike

## Purpose

Specify and execute bounded technical discovery without pretending it is product implementation.

Use this for questions like:

- How should we orchestrate Claude CLI, Codex CLI, Gemini CLI, or other tools?
- Which integration approach is safest?
- How does a third-party SDK behave under timeout, streaming, cancellation, or auth?
- What mini program proves the risk before feature work starts?

## Phase Guard

Before working, run:

```text
nexusctl phase check spike
```

If it fails, stop and ask the user to call the missing previous skill.

## Outputs

Spike must update `nexus/spec.md` with:

```md
## Spikes

### SP-001 - Title

**Objective:** ...
**Research Question:** ...
**Allowed Experiments:** ...
**Deliverables:** ...
**Decision Options:** ...
```

When execution work is needed, create `SP-*` backlog stories:

```text
nexus/backlog/SP-001_READY_slug.md
```

Use `../shared/templates/spike_story_template.md`.

## Rules

- Spike scripts and mini programs must be isolated under `spikes/SP-XXX/`.
- Research reports must go under `docs/` (e.g. `docs/SP-001.md`). Create the folder if missing.
- Any scratch artifact that is **not** a declared deliverable (throwaway probes, raw API dumps, intermediate parsing output, debug logs, draft notes, downloaded fixtures) must live under `.temp/` and be deleted before the spike closes. Never pollute `spikes/SP-XXX/` or `docs/` with non-deliverable noise. Global temp-files rule applies.
- Spike does not implement production behavior unless explicitly converted into a feature story.
- Spike deliverables use `DEL-XXX` IDs instead of functional ACs.
- The final report must recommend one of: discard, implement, split into architecture decision, or create feature stories.

## Decision Rules

- Use `/spike` when the answer requires running an experiment, comparing tools, proving integration behavior, validating performance, testing CLI/process orchestration, or reducing a technical risk before backlog.
- Do not use `/spike` for normal product clarification; send that back to `/spec`.
- A spec-only Spike is enough when the research can be planned now but executed later by `/backlog` and `/dev`.
- Create an `SP-*` backlog story when the spike requires files, scripts, commands, reports, or executable experiments.
- Allowed experiments must name the boundaries: target tool/API, files allowed, commands allowed, data allowed, and what must not be changed.
- Deliverables must be auditable artifacts, not vague outcomes. Examples: report path, experiment script path, benchmark output, captured command log, ADR draft, or follow-up `US-*` list.
- Recommendation meanings: discard means no implementation; implement means create feature stories; create ADR means record a durable architecture decision; split into feature stories means research is complete but delivery needs multiple `US-*`.

## Proactive Spike Triggers (Mandatory)

Whoever runs `/spec`, `/arch`, `/design`, or `/backlog` (the AI itself, not the user) **must** create a Spike whenever any of these conditions hold. Do not wait for the user to ask. Do not assume training data is current.

- **Unfamiliar API / SDK / library / CLI.** Behavior, contract, error model, auth, rate limits, streaming, cancellation, pagination, retry semantics, or version-specific changes not already proven in this repo or read in this conversation.
- **Unfamiliar technology / framework / runtime / protocol.** Anything not validated against current docs during this conversation.
- **Web research required.** Any fact, version, deprecation status, pricing, quota, compatibility matrix, or vendor change that needs confirmation from the live web.
- **Hypothesis that needs proof.** Any "I think it works like X" that an executable mini program can confirm or refute (timing, concurrency, failure mode, data shape, schema drift, integration handshake).
- **Tool / approach comparison.** 2+ candidate tools, libraries, patterns, or approaches where the tradeoff is not already recorded in `architecture.md`.
- **Performance / cost claim.** Any latency, throughput, memory, or cost target not yet measured locally.
- **Unfamiliar format or domain rule.** New file format, binary protocol, schema, regulatory rule, or business invariant whose exact semantics are uncertain.
- **AI knowledge cutoff risk.** API/SDK/tool released or substantially changed after the AI's training cutoff — always spike before designing around it.

Skip a Spike only when the answer is already proven by current code in this repo, current Nexus artifacts (`spec.md`, `architecture.md`, `docs/`), or docs the AI has explicitly read during this conversation.

When uncertain whether a Spike is needed, **create it**. A 30-minute spike is cheaper than a wrong architecture decision.

If a Spike is created during `/arch`, `/design`, or `/backlog`, pause that phase, route through `/spike`, then resume — never paper over a knowledge gap with assumptions.

## Discovery Questions

Ask only if the answer changes risk, scope, experiment design, tool choice, or deliverable.

Use the Nexus question format:

```text
Q1. [question]

1. Discuss in free text [RECOMMENDED]
2. [best-fit option]
3. [option]
4. [option]
5. [option]
6. Auto-pick best-fit option and continue
0. End the conversation
```

## Completion Gate

Before finishing:

1. `nexus/spec.md` has `## Spikes` with at least one `SP-*`.
2. Every spike has objective, research question, experiments, deliverables, and decision options.
3. If execution is needed, `SP-*` backlog stories exist with `Research Question`, `Deliverables`, tasks, verify commands, and write scope.
4. Run `nexusctl phase done spike`.
5. Ask the user to call the next skill printed by `nexusctl phase done spike`.

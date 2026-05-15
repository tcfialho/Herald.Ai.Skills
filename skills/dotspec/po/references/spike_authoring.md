# Spike Authoring (PO Reference)

Authoring contract for **`SP-*` spike entries in `.spec/spec.md`**. Only `/po` writes here.

This document covers **when** to write a spike, **how** to structure it in `spec.md`, and **how** to scope it. Execution rules (artifact paths, deliverables under `.spec/spikes/SP-XXX/`, propagation back to Use Cases) live in `../../dev/references/spike_execution.md` — `/dev` reads that.

---

## When to Write a Spike

Add a spike whenever `/po` (or any agent that pauses and asks `/po` to add one) lacks confident, evidence-backed knowledge to design or implement the work. Default to creating one — do not assume training data is current or correct.

### Mandatory Spike Triggers

Write `SP-*` proactively, do **not** ask the user first, whenever any of these holds:

- **Unfamiliar API / SDK / library / CLI.** Behavior, contract, error model, auth, rate limits, streaming, cancellation, pagination, retry semantics, or version-specific changes not already proven in this repo or read in this conversation.
- **Unfamiliar technology / framework / runtime / protocol.** Anything not validated against current docs during this conversation.
- **Web research required.** Any fact, version, deprecation status, pricing, quota, compatibility matrix, or vendor change that needs confirmation from the live web.
- **Hypothesis that needs proof.** Any "I think it works like X" that an executable mini program can confirm or refute (timing, concurrency, failure mode, data shape, schema drift, integration handshake).
- **Tool / approach comparison.** 2+ candidate tools, libraries, patterns, or approaches where the tradeoff is not already recorded in `architecture.md`.
- **Performance / cost claim.** Any latency, throughput, memory, or cost target not yet measured locally.
- **Unfamiliar format or domain rule.** New file format, binary protocol, schema, regulatory rule, or business invariant whose exact semantics are uncertain.
- **AI knowledge cutoff risk.** API/SDK/tool released or substantially changed after the AI's training cutoff — always spike before designing around it.

### Skip a Spike Only When

The answer is already proven by:

- Current code in this repo, **or**
- Current DotSpec artifacts (`.spec/spec.md`, `.spec/architecture.md`, `docs/`), **or**
- Docs the AI has explicitly read during this conversation.

When uncertain whether a spike is needed, **create it**. A 30-minute spike is cheaper than a wrong architecture decision.

### Spikes Requested by Other Agents

If `/ux`, `/arch`, or `/sm` reports a technical gap during its phase, pause that phase, return to `/po`, add the matching `SP-*` here following the structure below, then let the calling phase resume.

`/ux`, `/arch`, and `/sm` never write `SP-*` themselves. Only `/po` does.

### Spike-Only Specs

If the user's intake is a pure research question with no product context, the entire `spec.md` may be spike-only: `## Spikes` is the only substantive section. No UCs, no `AC-*`. `/ux` and `/arch` are skipped; `/sm` builds the backlog directly from the spike entries.

---

## Structure of a Spike Entry in `spec.md`

`.spec/spec.md` has a top-level `## Spikes` section. Each `SP-*` follows this template:

```md
## Spikes

### SP-001 - [Short Title]

**Objective:** What the spike proves or decides, in one sentence.

**Research Question:** The single question the spike must answer. Phrased so the answer is testable, not an opinion.

**Allowed Experiments:**
- Target tool / API / library to probe
- Files allowed to read or write
- Commands allowed to run
- Data allowed to use
- What must not be changed

**Deliverables (DEL-*):**
- DEL-001: [Auditable artifact — path, script, benchmark, report, ADR draft, etc.]
- DEL-002: ...

**Decision Options:**
- Discard: no implementation; close with no further action.
- Implement: create one or more `US-*` feature stories from the result.
- Create ADR: record a durable architecture decision in `architecture.md`.
- Split into feature stories: research is complete but delivery needs multiple `US-*`.
```

### Field Rules

- **Objective** — one sentence. Avoid restating the research question.
- **Research Question** — phrased so the spike either succeeds or fails on evidence (e.g. "Does the SDK preserve order when streaming under `max_in_flight=4`?"), not as a vague exploration ("investigate streaming").
- **Allowed Experiments** — must name boundaries. Generic "explore the API" is rejected. Use bounded targets: a specific endpoint, file, command, dataset.
- **Deliverables** — every entry is an **auditable artifact**, not a vague outcome. Examples: report path, experiment script path, benchmark output, captured command log, ADR draft, follow-up `US-*` list. Vague entries like "understanding of the SDK" are rejected.
- **Decision Options** — always list all four. The spike must end by selecting one.

### `DEL-*` IDs

Spike stories use `DEL-*` IDs in place of functional `AC-*`. Each deliverable has a stable ID (`DEL-001`, `DEL-002`, ...) referenced by `/dev` during execution and by `/sm` when building the matching `SP-*` backlog story.

---

## Discovery Questions

Ask only when the answer changes risk, scope, experiment design, tool choice, or deliverable. Skip when the answer is obvious from context.

Use the DotSpec question format:

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

If a Discovery Question is auto-answered, record the assumption in `spec.md ## Assumptions`.

---

## What `/po` Does NOT Decide Here

These belong to `/dev` and `/sm`, not `/po`:

- Where spike scripts and reports live on disk (`.spec/spikes/SP-XXX/`).
- Distinguishing declared deliverables from throwaway scratch.
- How spike findings propagate back into affected Use Cases (`spec.md` UCs, `.spec/backlog/US-*.md`).
- The `SP-*` backlog-story structure (`.spec/backlog/SP-NNN_*.md`) — `/sm` generates that from this `## Spikes` entry using `../shared/templates/spike_story_template.md`.

`/po`'s only output is the `SP-*` entry inside `.spec/spec.md`. Everything downstream is governed by `/sm` (story generation, ordering) and `/dev` (execution, propagation).

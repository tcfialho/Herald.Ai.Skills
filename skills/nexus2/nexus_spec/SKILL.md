---
name: nexus2-spec
description: Nexus 2.0 /spec product-owner stage. Use when the user wants to specify a new product, feature, delta for an existing project, or research need that may become a Spike. Produces or updates nexus/spec.md with objective, scope, actors, use cases, flows, business rules, invariants, business entities, functional acceptance criteria, and spike requests. Writes no functional code.
---

# Nexus 2.0 /spec

## Purpose

Create or update `nexus/spec.md`, the persistent product specification.

This phase captures what the product must do. It does not decide implementation architecture, detailed NFR strategy, or production UI layout.

## Required Output

```text
nexus/spec.md
```

Use `../shared/templates/spec_template.md` as the base structure when creating a new spec.

## Phase Rules

- Before working, run `nexusctl phase check spec`. If `nexus/` does not exist, run `nexusctl init` first, then run the phase check.
- Write no functional code.
- If the project already exists, document the current behavior first as AS-IS, then add the requested delta.
- Preserve existing IDs and sections when updating.
- Use Markdown as the source of truth.
- Keep acceptance criteria functional. Technical gates belong in backlog stories or `architecture.md`.
- EARS is optional and must not be introduced unless the user explicitly wants it or the project is regulated/formal enough to justify it.

## Decision Rules

- AS-IS means observed current behavior and constraints from the existing project, not the desired future behavior.
- Put an acceptance criterion in `spec.md` when it describes user-visible behavior, business policy, permission, data rule, or outcome.
- Put a criterion in `architecture.md` or a backlog story when it only constrains implementation quality, files, tests, build, folders, or code style.
- Add a Spike whenever the AI lacks confident, evidence-backed knowledge to design or implement the work. Default to creating one — do not assume training data is current or correct.
- Mandatory Spike triggers (write `SP-*` proactively, do not ask the user first):
  - Third-party API, SDK, CLI, or library whose exact behavior, contract, error model, rate limits, auth flow, streaming, cancellation, pagination, or version semantics is not already proven in this repo.
  - Technology, framework, runtime, or protocol the AI has not validated against current docs in this conversation.
  - Web research needed to confirm a fact, version, deprecation, or pricing.
  - Hypothesis that needs an executable mini program to confirm (timing, concurrency, failure mode, data shape, integration point).
  - Comparison between 2+ tools/approaches where the tradeoff is not already documented in `architecture.md`.
  - Performance, throughput, latency, or cost claim that has not been measured locally.
  - Unfamiliar file format, binary protocol, schema, or domain rule.
- Skip a Spike only when the answer is already proven by current code in this repo, current Nexus artifacts, or a doc the AI has read in this conversation.
- When in doubt, write the Spike. Cheap research beats expensive rework.
- Use EARS only when the user asks for it, the domain is audit-heavy/regulated, or behavior needs precise event/condition/outcome wording. Otherwise use plain functional acceptance criteria with stable IDs.

## Discovery Questions

Ask only when the answer changes product behavior, scope, UX, architecture handoff, tests, or backlog.

Every necessary question must be multiple choice:

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

Never ask obvious questions. If the answer is inferable, assume it and record the assumption in `spec.md`.

## Required Sections

`spec.md` must include, in this order, mirroring `../shared/templates/spec_template.md`:

- Title heading + a one-line note pointing implementation/visual concerns to `architecture.md` and `design.md`.
- **Overview** — short paragraph: what the product is, business outcome, primary users, high-level boundary.
- **Scope** — `In Scope` and `Out Of Scope` bullet lists.
- **Actors** — table with columns `ID | Actor | Type (Human \| System \| External) | Responsibility`.
- **Use Cases**, with two subsections:
  - `Use Case Diagram` — Mermaid `graph LR` diagram. Actors as `((emoji + Name))` circles. Relations between UCs use `-.-o|include|` and `-.-o|extend|`.
  - `Use Case Matrix` — table with columns `ID | Name | Actor | Summary | Has UI`. `Has UI` is mandatory and accepts `yes`, `no`, or `partial`. UC IDs are stable (`UC-001`, `UC-002`, ...) and referenced by every downstream phase.
- **Use Case Details** — exactly one drill-down per UC in the matrix (1:1, no skipping). Each drill-down has Actor, Preconditions, `Main Flow (UC-XXX.FP)` numbered, `Alternative Flows (UC-XXX.FA1, FA2, ...)` numbered, Postconditions.
- **Business Rules** — `BR-XXX` items.
- **Invariants** — `INV-XXX` items. Invariants are conditions the system always respects regardless of trigger.
- **Business Entities** — table with columns `Entity | Type (Domain \| Actor \| External \| Value Object) | Definition`.
- **Functional Acceptance Criteria** — `AC-XXX` items. Anchor each AC to a UC when possible. EARS notation is optional; use only when the user explicitly wants it or the domain is regulated/audit-heavy.
- **Spikes** — only when unresolved technical discovery is requested. Each `SP-*` declares `Research Question` and `Deliverables (DEL-*)`.
- **Assumptions** — record every assumption, including auto-assumed answers from Discovery Questions.
- **Open Questions** — anything still ambiguous after discovery.

### What does NOT belong in spec.md

- Decisões do Projeto (auth, persistence, deploy, stack), backend rules, folder layout, dependency lists, naming conventions, performance/concurrency NFRs, quality gates → **`architecture.md`**.
- Color palette, typography, spacing, components, states, screens → **`design.md`** + `nexus/prototype/`.

If the user dictates a stack, performance target, or visual rule during `/spec`, record it in **Assumptions** and surface it again in `/arch` or `/design`. Do not embed it in spec.md sections.

## Completion Gate

Before finishing:

1. Confirm all requested behavior is represented by use cases or business rules.
2. Confirm every use case has a stable ID and a `Has UI` value (`yes | no | partial`).
3. Confirm there is exactly one drill-down per UC (1:1 with the matrix, no omissions).
4. Confirm the Mermaid `graph LR` diagram is present and includes every actor and UC referenced in the matrix.
5. Confirm every functional acceptance criterion has an ID and, when possible, a UC reference.
6. Confirm every Business Entity has a `Type` (`Domain | Actor | External | Value Object`) and a one-line definition.
7. Confirm no implementation-only detail (stack, NFR target, folder layout, visual decision) was placed in the spec when it belongs in `architecture.md` or `design.md`.
8. Run `nexusctl phase done spec`.
9. Ask the user to call the next skill printed by `nexusctl phase done spec`.

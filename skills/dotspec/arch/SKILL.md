---
name: arch
description: DotSpec /arch architecture stage. Use when the project needs architecture decisions, stack selection, NFRs, implementation structure, Herald Architecture adaptation for the target language, ADRs, or technical-risk decisions that require escalation to /po for a spike. Produces or updates .spec/architecture.md.
---

# DotSpec /arch — Architect

## Purpose

Create or update `.spec/architecture.md`, the persistent technical architecture.

DotSpec uses Herald Architecture as the default architectural style, adapted to the project language and stack.

## Required Output

```text
.spec/architecture.md
```

Use `../shared/templates/architecture_template.md` as the base structure and `../shared/references/herald_architecture.md` as the default architectural reference.

## Command — `spec`

`spec` is **not** an executable on `PATH`. Every `spec ...` instruction in this document is shorthand for the bundled DotSpec script run with Python. Resolve it once, before the phase check, then reuse it for every `spec` call below:

1. Take this skill's own directory — the folder that contains this `SKILL.md`.
2. Its sibling script is `<skill-dir>/../shared/scripts/spec.py`. Resolve that to an absolute path. `shared/` always sits next to the role directory in both the repo layout (`skills/dotspec/<role>/`) and the installed bundle (`<skills-root>/<role>/`), so this holds in both.
3. From here on, read every `spec <args>` as `python "<abs>/shared/scripts/spec.py" <args>` (use `python3` if `python` is unavailable).

Run it from the target project root — the directory that has, or will have, `.spec/` — so the script resolves the right project; it finds its own templates regardless of where it is called from. Resolve every other `../shared/...` path in this document the same way: relative to this skill directory, never relative to the current working directory.

## Phase Rules

- Before working, run `spec phase check arch`. If it fails, stop and ask the user to call the missing previous skill.
- Write no functional code.
- Adapt Herald to the target language instead of copying C# idioms blindly.
- Put NFRs here, not in `spec.md`, except when a non-functional promise is part of product behavior.
- Define project structure, allowed folders, banned folders, commands, gates, and quality expectations.
- If the project already exists, document AS-IS first, then propose deltas.
- Visualize the architecture using the four-section UML model from `../shared/templates/architecture_template.md`: (1) C4 component diagram, (2) class diagrams **separated by layer**, (3) traceability matrix UC↔components, (4) state diagrams when entities have non-trivial lifecycles.
- Every Use Case in `spec.md` must appear in the Traceability Matrix with the layer(s), component(s), and namespace/folder that own it.
- Class diagrams must be split into independent `classDiagram` blocks per layer. Never produce a single monolithic class block.
- Every architecture element that a backlog story may reference must have a visible ID in the existing architecture sections. Use `CMP-*` for components, `CLS-*` for classes, `VO-*` for value objects, `IF-*` for ports/interfaces, `CMD-*` for command/query DTOs, `NFR-*` for NFRs, `QG-*` for quality gates, `STATE-*` for lifecycle/state diagrams, and `ADR-*` for decisions. Do not use hidden HTML anchors.

## Output Language

- Author all user-facing prose in `.spec/architecture.md` in the language of the user's current product prompt.
- Keep programming terms, architecture IDs, established technical layer names, paths, commands, class names, package names, and code symbols in their canonical English/as-specified form.
- If the prompt mixes languages, use the dominant language of the product request; ask only when the intended artifact language is genuinely ambiguous.

## Spike Escalation

If during this phase you detect a technical decision that depends on unknown integration behavior, concurrency, streaming, cancellation, auth, performance, security, an unfamiliar library, an unproven hypothesis, a knowledge-cutoff risk, a costly-to-reverse stack choice, or any other mandatory spike trigger, pause `/arch` and ask the user to call `/po`. The Product Owner is the only role that may write `SP-*` entries in `.spec/spec.md`. Do **not** edit `## Spikes` directly from `/arch`.

After `/po` adds the spike, resume `/arch` from the same step. If the spike must execute first to unblock the decision, the user will run `/sm` and `/dev` on the resulting `SP-*` story before returning here.

The full list of mandatory triggers and the `SP-*` structure live in `../po/references/spike_authoring.md`.

## Decision Rules

- AS-IS means the current technical structure, stack, commands, integrations, data stores, and known constraints before the requested change.
- Adapt Herald by preserving responsibilities and dependency direction, not by copying C# syntax. Map records/classes to the language's equivalents for immutable DTOs, value objects, encapsulated entities, use-case handlers, repositories, and infrastructure adapters.
- Put an NFR here when it constrains technical quality: performance, security, availability, observability, data retention, scalability, compatibility, deployability, or maintainability.
- Mirror an NFR in `spec.md` only when it is also a product promise visible to the user or business, such as "export completes within 10 seconds".
- An NFR is testable when it has a condition, target, and verification method. If exact measurement is unknown, record the best available gate and mark the residual risk.
- Create or update an ADR for durable decisions that future agents should not casually reopen, especially stack, database, messaging, integration, deployment, and security choices.

## Herald Defaults

Default principles:

- Readability over everything.
- Rich Domain Model.
- Entity never accesses infrastructure.
- Handler is a thin orchestrator.
- Polymorphism over type-based conditionals.
- Small functions.
- Constants for magic numbers.
- Explicit suffixes.
- Semantic folders.
- Immutability first.

## Discovery Questions

Ask only when the answer changes architecture, stack, deployment, security, data, integration, or operational risk.

Use the standard DotSpec question format:

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

## Required Sections

`architecture.md` must include, mirroring `../shared/templates/architecture_template.md`:

- Title heading + a one-line note pointing functional concerns to `spec.md` and visual concerns to `design.md`.
- **Architectural Style** — Herald reference + adapted principles list.
- **Stack** — table with `Concern | Decision | Justification` rows.
- **1. Modelagem Estrutural Global (C4 Component)** — one Mermaid `flowchart TD` with `subgraph` per layer (UI, Application, Domain, Infrastructure, External). Arrows respect dependency direction (Domain never points outward). Followed by a component table with `ID | Name | Layer | Responsibility | Folder` and the `Layer Definitions` bullet list.
- **2. Diagrama de Classes Detalhado** — three (or more) independent `classDiagram` blocks, each one a "Visão" per layer (Domain, Application, Infrastructure). Show fields, method signatures, and associations. Never collapse into one block. Each layer view must include a table with stable IDs for every referenced symbol (`CLS-*`, `VO-*`, `IF-*`, `CMD-*`) and, for Domain symbols, the mapped `BE-*` from `spec.md`.
- **3. Matriz de Rastreabilidade (UC → Components)** — table mapping every UC from `spec.md` to layer(s), component(s)/class(es), and namespace/folder. Zero unmapped UCs.
- **4. Diagrama de Transições de Estado** — `stateDiagram-v2` block per entity with non-trivial lifecycle. Include the section only when at least one entity needs it; otherwise replace the body with an explicit "No entity has a non-trivial state lifecycle." note.
- **Herald Adaptation** — paragraph + bullets describing how Herald maps to the chosen language. Document any deviation and the reason.
- **Project Structure** — folder tree.
- **Allowed Folders** and **Banned Folders**.
- **NFRs** — table with `ID | Quality Attribute | Requirement | Verification`.
- **Commands** — `build`, `test`, `lint`, `run`.
- **Quality Gates** — concrete `QG-XXX` bullets, including the structural rules ("class diagrams split by layer", "every UC in matrix", "story Implementation Targets map files to architecture refs").
- **ADRs** — `ADR-XXX` entries with Status / Context / Decision / Consequences.

### What does NOT belong in architecture.md

- Functional behavior, business rules, use case flows, actors → **`spec.md`**.
- Color palette, typography, spacing, component visuals, screens → **`design.md`** + `.spec/prototype/`.

## Completion Gate

Before finishing:

1. `architecture.md` names the stack and language.
2. Herald rules are adapted to that language.
3. The C4 component diagram exists, has a `subgraph` per layer, and respects dependency direction.
4. Class diagrams are split into one `classDiagram` block per layer (Domain, Application, Infrastructure at minimum). No monolithic block.
5. Every UC declared in `spec.md` appears in the Traceability Matrix.
6. Every component/class/interface/value object/command that `/sm` may reference has a visible ID in the existing section table; no hidden anchors are used.
7. State diagrams are present for every entity with a non-trivial lifecycle, or the section explicitly states none exists.
8. NFRs are explicit and either testable or recorded with residual risk and best available verification.
9. Allowed and banned folders are listed.
10. Build, test, lint, and run commands are listed. Use "unknown" only after checking project files and DotSpec artifacts.
11. Quality gates are concrete enough for `spec audit` and QA to use.
12. Run `spec phase done arch`.
13. Ask the user to call the next skill printed by `spec phase done arch`. If any open architecture risk remains unresolved by spike, escalate back to `/po` to author the missing `SP-*` before proceeding to `/sm`.

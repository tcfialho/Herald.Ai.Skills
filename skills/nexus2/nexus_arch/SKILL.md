---
name: nexus2-arch
description: Nexus 2.0 /arch architecture stage. Use when the project needs architecture decisions, stack selection, NFRs, implementation structure, Herald Architecture adaptation for the target language, ADRs, or a decision about whether technical discovery should go to /spike. Produces or updates nexus/architecture.md.
---

# Nexus 2.0 /arch

## Purpose

Create or update `nexus/architecture.md`, the persistent technical architecture.

Nexus 2.0 uses Herald Architecture as the default architectural style, adapted to the project language and stack.

## Required Output

```text
nexus/architecture.md
```

Use `../shared/templates/architecture_template.md` as the base structure and `../shared/references/herald_architecture.md` as the default architectural reference.

## Phase Rules

- Before working, run `nexusctl phase check arch`. If it fails, stop and ask the user to call the missing previous skill.
- Write no functional code.
- Adapt Herald to the target language instead of copying C# idioms blindly.
- Put NFRs here, not in `spec.md`, except when a non-functional promise is part of product behavior.
- Define project structure, allowed folders, banned folders, commands, gates, and quality expectations.
- If the project already exists, document AS-IS first, then propose deltas.
- Visualize the architecture using the four-section UML model from `../shared/templates/architecture_template.md`: (1) C4 component diagram, (2) class diagrams **separated by layer**, (3) traceability matrix UC↔components, (4) state diagrams when entities have non-trivial lifecycles.
- Every Use Case in `spec.md` must appear in the Traceability Matrix with the layer(s), component(s), and namespace/folder that own it.
- Class diagrams must be split into independent `classDiagram` blocks per layer. Never produce a single monolithic class block.

## Decision Rules

- AS-IS means the current technical structure, stack, commands, integrations, data stores, and known constraints before the requested change.
- Adapt Herald by preserving responsibilities and dependency direction, not by copying C# syntax. Map records/classes to the language's equivalents for immutable DTOs, value objects, encapsulated entities, use-case handlers, repositories, and infrastructure adapters.
- Put an NFR here when it constrains technical quality: performance, security, availability, observability, data retention, scalability, compatibility, deployability, or maintainability.
- Mirror an NFR in `spec.md` only when it is also a product promise visible to the user or business, such as "export completes within 10 seconds".
- An NFR is testable when it has a condition, target, and verification method. If exact measurement is unknown, record the best available gate and mark the residual risk.
- Route to `/spike` when a decision depends on unknown integration behavior, concurrency, streaming, cancellation, auth, performance, security, or a costly-to-reverse stack choice that cannot be resolved by reading existing artifacts.
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

Use the standard Nexus question format:

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
- **1. Modelagem Estrutural Global (C4 Component)** — one Mermaid `flowchart TD` with `subgraph` per layer (UI, Application, Domain, Infrastructure, External). Arrows respect dependency direction (Domain never points outward). Followed by a `Layer Definitions` bullet list.
- **2. Diagrama de Classes Detalhado** — three (or more) independent `classDiagram` blocks, each one a "Visão" per layer (Domain, Application, Infrastructure). Show fields, method signatures, and associations. Never collapse into one block.
- **3. Matriz de Rastreabilidade (UC → Components)** — table mapping every UC from `spec.md` to layer(s), component(s)/class(es), and namespace/folder. Zero unmapped UCs.
- **4. Diagrama de Transições de Estado** — `stateDiagram-v2` block per entity with non-trivial lifecycle. Include the section only when at least one entity needs it; otherwise replace the body with an explicit "No entity has a non-trivial state lifecycle." note.
- **Herald Adaptation** — paragraph + bullets describing how Herald maps to the chosen language. Document any deviation and the reason.
- **Project Structure** — folder tree.
- **Allowed Folders** and **Banned Folders**.
- **NFRs** — table with `ID | Quality Attribute | Requirement | Verification`.
- **Commands** — `build`, `test`, `lint`, `run`.
- **Quality Gates** — concrete bullets, including the structural rules ("class diagrams split by layer", "every UC in matrix").
- **ADRs** — `ADR-XXX` entries with Status / Context / Decision / Consequences.

### What does NOT belong in architecture.md

- Functional behavior, business rules, use case flows, actors → **`spec.md`**.
- Color palette, typography, spacing, component visuals, screens → **`design.md`** + `nexus/prototype/`.

## Completion Gate

Before finishing:

1. `architecture.md` names the stack and language.
2. Herald rules are adapted to that language.
3. The C4 component diagram exists, has a `subgraph` per layer, and respects dependency direction.
4. Class diagrams are split into one `classDiagram` block per layer (Domain, Application, Infrastructure at minimum). No monolithic block.
5. Every UC declared in `spec.md` appears in the Traceability Matrix.
6. State diagrams are present for every entity with a non-trivial lifecycle, or the section explicitly states none exists.
7. NFRs are explicit and either testable or recorded with residual risk and best available verification.
8. Allowed and banned folders are listed.
9. Build, test, lint, and run commands are listed. Use "unknown" only after checking project files and Nexus artifacts.
10. Quality gates are concrete enough for `nexusctl audit` and QA to use.
11. Run `nexusctl phase done arch`.
12. Ask the user to call the next skill printed by `nexusctl phase done arch`. If the Decision Rules route any open architecture risk to research, direct the user to `Nexus 2.0 /spike`; otherwise direct them to `Nexus 2.0 /backlog`.

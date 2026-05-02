---
name: nexus2-backlog
description: Nexus 2.0 /backlog scrum-master stage. Use when Nexus product, design, architecture, or spike artifacts must be converted into ordered, self-contained Markdown stories under nexus/backlog/. Produces US-* feature stories and SP-* spike stories with copied context, AC/DEL coverage, tasks, verify commands, expected artifacts, architecture gates, and Definition of Done.
---

# Nexus 2.0 /backlog

## Purpose

Generate ordered, self-contained stories in `nexus/backlog/`.

The story is the operational package for DEV and QA. It intentionally duplicates selected content from `spec.md`, `design.md`, and `architecture.md` so downstream agents do not need to cross-read documents.

## Required Inputs

Before working, run `nexusctl phase check backlog`. If it fails, stop and ask the user to call the missing previous skill.

```text
nexus/spec.md
nexus/design.md       # required unless design.md explicitly says No UI
nexus/architecture.md
nexus/spec.md Spikes  # use only when spec.md contains SP-* research needs
```

## Required Output

```text
nexus/backlog/US-001_READY_slug.md
```

Use `../shared/templates/story_template.md` as the base.

## Decision Rules

- Create `US-*` for product behavior that DEV can implement and QA can validate against acceptance criteria.
- Create `SP-*` for bounded research that must produce deliverables, experiment files, or a recommendation before implementation.
- Do not turn a vague feature into a Spike only because details are missing. Ask the PO/spec skill to clarify business behavior first.
- Copy design context only when the story touches UI as defined by `design.md`. For no-UI stories, write "No UI impact" in the story.
- Complexity uses a small Fibonacci scale: 1 trivial, 2 small, 3 moderate, 5 complex, 8 ceiling. Anything above 8 triggers the **Story Split Decision (Objective)** tree below — do not eyeball, run the tree.
- Expected artifacts must be concrete paths that QA can check. Prefer specific files; use directories only when the directory itself is the deliverable.
- `write_scope` must be the smallest set of paths the DEV needs. If a task needs a path outside scope, update the story before DEV edits it.
- A technical AC belongs in the story only when it is local to that story. Shared quality expectations belong in `architecture.md`.

## Story Rules

Each story must include:

- Stable sequential ID.
- Status in filename and front matter.
- Complexity score.
- Priority/order.
- Copied product context.
- Copied design context when the story has UI impact.
- Copied architecture context.
- Acceptance criteria.
- Expected artifacts.
- Tasks.
- Verify command per task.
- Write scope.
- Definition of Done.
- Empty QA bugs section.
- Empty execution evidence section.

Spike stories use `SP-*`, `type: SPIKE`, `Research Question`, and `Deliverables` (`DEL-*`) instead of functional acceptance criteria.

## Ordering

Generate stories in implementation order. The DEV agent must not choose order manually; `nexusctl story next` enforces strict order by default. A later story is not delivered while an earlier story is not `DONE`.

Spike stories (`SP-*`) always precede feature stories (`US-*`) in the execution queue, regardless of `priority` value. `nexusctl story next` enforces this. Default `priority: 0` for spikes unless an explicit reason demands otherwise.

### Funnel-of-Certainty Breakdown

Decompose the product into layers where each layer produces validated artifacts that feed the next layer. Each layer narrows uncertainty before the next begins. The first layer must always be a mocked user-facing surface so stakeholders validate behavior early — every other layer is derived from what is approved there.

Default layer order:

1. **Mocked frontend / public surface (always first).** Build the UI screens, navigation, and visible states with hardcoded fixtures, in-memory data, and stub responses. For headless products (lib, CLI, batch, API-only), build the public surface — CLI flags, API endpoints, or library entry points — backed by fixtures. Goal: show working flows to the user and stakeholders for fast acceptance. No backend, no domain logic, no DB, no infra. Stories in this layer prove navigation, UX, and acceptance criteria against fake data.
2. **Domain skeleton.** Derive entities, value objects, identifiers, and invariants from the surface accepted in layer 1. Code as types only — no behavior, no persistence. Stories produce class/dataclass/struct files, identifier rules, and validation invariants. Goal: lock the vocabulary the rest of the system will share.
3. **Use case contracts.** Define interface signatures, request/response shapes, and the error catalog implied by the use cases the surface exposes. Stories produce abstract interfaces, OpenAPI/gRPC schemas, or function/method signatures. No implementations. Goal: lock the boundary between surface and backend so later layers can develop in parallel without breaking either side.
4. **Application logic + in-memory adapters.** Implement use cases against in-memory entity stores or fixture-backed adapters. Business rules enforced, contracts honored, persistence faked. Stories produce service classes, handlers, and AC-passing integration tests against the in-memory adapter. Goal: prove behavior end-to-end without infrastructure cost.
5. **Persistence + infrastructure.** Introduce real schemas, migrations, repositories, caches, queues, IaC, deployment, observability, and hardening. Swap in-memory adapters for production-grade implementations. Stories must keep the same AC passing without rewriting them. Goal: production readiness.

Cross-cutting rules:

- Layer 1 is non-negotiable as the entry point. Even backend-only products express layer 1 through their public surface so a stakeholder can review it.
- Each layer is a funnel: its output validates assumptions of the previous layer and locks inputs for the next.
- Vertical slicing dominates: take one use case through layers 1→5 before starting another, unless layer 2 is a clearly shared foundation (e.g. identity model used by every slice).
- AC stays the same across layers. What changes is the implementation that satisfies it.
- Skip a layer only when it adds no certainty. Example: a stateless library skips layer 5; a single-screen CRUD with no shared model collapses layer 2 into layer 4.
- A later-layer story for a slice is not generated until the earlier-layer story for the same slice has Definition of Done covered. Record any skip explicitly in the story.
- Spike stories (`SP-*`) attach to the layer whose uncertainty they resolve and run before that layer's stories.
- The backlog skill records each story's layer in the story Markdown body (e.g. as part of the story title, a dedicated `## Layer` line, or a tag in the description). The five names above are recommended defaults; adapt them when the architecture demands different vocabulary (e.g. event-driven projects may use `events`, `projections`, `handlers`; data pipelines may use `ingest`, `transform`, `publish`). This is a backlog-skill instruction, not a code-enforced field — `nexusctl` does not validate it.

## Story Split Decision (Objective)

Deterministic decision tree. No judgment calls. Run it on every draft story before saving.

```
STEP 1. layer == 1 (mocked frontend / public surface)?
        → DO NOT SPLIT. Save as one story. Stop.

STEP 2. Measure the draft story:
        - complexity   (Fibonacci: 1, 2, 3, 5, 8, 13, ...)
        - ac_count     (count of AC-* for US-*, or DEL-* for SP-*)
        - task_count   (count of TASK-* in the story)
        - file_count   (unique files across all task `files:` entries plus write_scope concrete paths)

STEP 3. Split required if ANY threshold exceeded:
        - complexity   > 8
        - ac_count     > 8
        - task_count   > 7
        - file_count   > 12

STEP 4. None exceeded → keep as ONE story. Stop.

STEP 5. Split required → apply ALL split rules:
        a. Same UC across every split. Never cross UCs.
        b. Same Layer across every split. Never split across layers.
        c. Each split owns ≥1 AC/DEL. No AC/DEL duplicated across splits.
        d. write_scope of each split is disjoint from sibling splits — no path overlap.
        e. Each split must independently pass STEP 3 (≤8 complexity, ≤8 ACs, ≤7 tasks, ≤12 files). If a split still exceeds a threshold, recurse from STEP 2 on that split.
        f. Ordering: assign new sequential IDs preserving slice order (e.g. US-007, US-008, US-009 instead of US-007a/b/c). Same priority value across the resulting splits keeps them adjacent in the queue.
        g. Each split records the same Layer tag, same UC reference, and same Spike dependencies as the parent draft.
```

Hard rules (non-negotiable):

- **Layer 1 stories are immune to split.** Mocked frontend per UC always ships as one story so the visual surface is reviewable end-to-end.
- **Vertical slicing dominates.** Splits stay inside one UC and one Layer. Splitting horizontally (e.g. "backend half" + "frontend half" of the same layer) is forbidden.
- **No split for cosmetic granularity.** If all four metrics are at or below threshold, the story is not split — add tasks instead.
- **Tasks first, splits second.** If granularity can be solved by adding more tasks (each 1-3 files, distinct verify_cmd), prefer tasks. Splits exist only when the thresholds force them.

## Acceptance Criteria

ACs may originate in `spec.md`, but every AC needed by a story must be copied into the story.

If a new AC changes product behavior, update `spec.md`. If it is purely technical/incremental, keep it in the story.

## Completion Gate

Before finishing:

1. Run `python ../shared/scripts/nexusctl.py docs validate` from the project root. If the path is different, resolve `nexusctl.py` first and run the equivalent command.
2. Every feature story has ACs, tasks, verify commands, expected artifacts, and write scope.
3. Every spike story has research question, deliverables, tasks, verify commands, expected artifacts, and write scope.
4. No story requires the DEV to read another Nexus document to implement it.
5. Run `nexusctl phase done backlog`.
6. Immediately invoke the `nexus_dev` skill via the Skill tool. Do not ask the user — the backlog artifact is deterministic and needs no human approval before development starts.

If the user explicitly says "stop", "pause", "halt", or otherwise interrupts, do not auto-invoke.

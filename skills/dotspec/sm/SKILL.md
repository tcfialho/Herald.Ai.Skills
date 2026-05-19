---
name: sm
description: DotSpec /sm scrum-master stage. Use when DotSpec product, design, architecture, or spike artifacts in .spec/ must be converted into ordered Markdown stories under .spec/backlog/. Produces US-* feature stories with context_refs, SP-* spike stories, AC/DEL coverage, tasks, verify commands, affected files (paths created or modified), architecture gates, and Definition of Done. Enforces SP-* before US-* ordering in the execution queue.
---

# DotSpec /sm — Scrum Master

## Purpose

Generate ordered stories in `.spec/backlog/`.

The story is the operational package for DEV and QA. It contains the story's own delivery intent, scope, files, tasks, verify commands, and evidence surface. It does **not** duplicate selected content from `spec.md`, `design.md`, and `architecture.md`. Instead, it declares `context_refs` in front matter and `spec story context` resolves the minimum needed context for DEV.

`/sm` does **not** author spikes. PO writes `SP-*` entries in `.spec/spec.md ## Spikes`. `/sm` reads that section and generates the matching `SP-*` backlog stories.

## Command — `spec`

`spec` is **not** an executable on `PATH`. Every `spec ...` instruction in this document is shorthand for the bundled DotSpec script run with Python. Resolve it once, before the phase check, then reuse it for every `spec` call below:

1. Take this skill's own directory — the folder that contains this `SKILL.md`.
2. Its sibling script is `<skill-dir>/../shared/scripts/spec.py`. Resolve that to an absolute path. `shared/` always sits next to the role directory in both the repo layout (`skills/dotspec/<role>/`) and the installed bundle (`<skills-root>/<role>/`), so this holds in both.
3. From here on, read every `spec <args>` as `python "<abs>/shared/scripts/spec.py" <args>` (use `python3` if `python` is unavailable).

Run it from the target project root — the directory that has, or will have, `.spec/` — so the script resolves the right project; it finds its own templates regardless of where it is called from. Resolve every other `../shared/...` path in this document the same way: relative to this skill directory, never relative to the current working directory.

## Required Inputs

Before working, run `spec phase check sm`. If it fails, stop and ask the user to call the missing previous skill.

```text
.spec/spec.md
.spec/design.md        # required unless design.md explicitly says No UI
.spec/architecture.md
.spec/spec.md Spikes   # use only when spec.md contains SP-* research needs authored by /po
```

## Required Output

```text
.spec/backlog/US-001_READY_slug.md
.spec/backlog/SP-001_READY_slug.md  # one per SP-* entry in spec.md ## Spikes
```

Use `../shared/templates/story_template.md` for feature stories and `../shared/templates/spike_story_template.md` for spike stories.

## Spike Authoring vs. Generation

- **Authoring** of `SP-*` entries in `.spec/spec.md` is `/po`'s exclusive responsibility. If `/sm` discovers an unresolved technical gap that should be a spike but no `SP-*` exists in `## Spikes`, pause `/sm`, ask the user to call `/po` to add the entry, then resume.
- **Generation** of `SP-*` backlog stories from those entries is `/sm`'s job. One backlog story per `SP-*` in `spec.md`. Apply the Spike Use-Case Propagation contract below.
- **Execution** of `SP-*` stories belongs to `/dev`. Full execution rules — artifact paths under `.spec/spikes/SP-XXX/`, deliverable validation, propagation enforcement — live in `../dev/references/spike_execution.md`.

## Decision Rules

- Create `US-*` for product behavior that DEV can implement and QA can validate against acceptance criteria.
- Create `SP-*` for every `SP-*` entry that already exists in `.spec/spec.md ## Spikes`. Do not invent new spikes here — return to `/po` if a new one is needed.
- Do not turn a vague feature into a Spike only because details are missing. Ask `/po` to clarify business behavior first.
- Set `context_refs.design: full` when the story touches UI/frontend as defined by `design.md`; otherwise set `context_refs.design: none`. `design.md` is proprietary DESIGN.md format and is referenced as a whole, not by granular IDs.
- Complexity uses a small Fibonacci scale: 1 trivial, 2 small, 3 moderate, 5 complex, 8 ceiling. Anything above 8 triggers the **Story Split Decision (Objective)** tree below — do not eyeball, run the tree.
- Affected Files must be concrete paths that QA can check. Includes files the story **creates or modifies** — list every path touched, whether new or pre-existing. Prefer specific files; use directories only when the directory itself is the deliverable.
- `write_scope` must be the smallest set of paths the DEV needs. If a task needs a path outside scope, update the story before DEV edits it.
- A technical AC belongs in the story only when it is local to that story. Shared quality expectations belong in `architecture.md`.

## Output Language

- Author story titles, intent, scope, task descriptions, Definition of Done prose, spike research questions, and other user-facing story text in the language of the user's current product prompt.
- Keep front matter keys, statuses, IDs, architecture/product refs, commands, paths, class names, package names, and code symbols in their canonical English/as-specified form.
- If the prompt mixes languages, use the dominant language of the product request; ask only when the intended story language is genuinely ambiguous.

## Story Rules

Each feature story must include:

- Stable sequential ID.
- Status in filename and front matter.
- Complexity score.
- Priority/order.
- `context_refs.product` listing every `UC-*`, flow (`UC-XXX.FP`, `UC-XXX.FA*`), `AC-*`, `BR-*`, `INV-*`, `BE-*`, or `SP-*`/`DEL-*` needed by the story.
- `context_refs.architecture` listing every `ADR-*`, `CMP-*`, `CLS-*`, `VO-*`, `IF-*`, `CMD-*`, `NFR-*`, `QG-*`, or `STATE-*` needed by the story.
- `context_refs.design` set to `full` or `none`.
- Story-authored intent, layer, and scope.
- Acceptance criteria by ID only (`AC-*`); the text resolves from `spec.md`.
- Implementation Targets mapping each affected file to its architecture refs and expected symbols.
- Affected Files (paths created or modified by the story).
- Tasks.
- Verify command per task.
- Write scope.
- Definition of Done.
- Empty QA bugs section.
- Empty execution evidence section.

Spike stories use `SP-*`, `type: SPIKE`, `Research Question`, and `Deliverables` (`DEL-*`) instead of functional acceptance criteria.

### Spike Use-Case Propagation (Mandatory for SP-*)

A spike that resolves uncertainty changes downstream Use Cases. The `SP-*` story must carry the propagation into its own definition — DEV must finish the propagation before `submit-qa` closes the spike.

When authoring an `SP-*` story:

1. Identify every Use Case whose AC, context, constraints, or wording will likely change once the spike answers its research question. Look at `.spec/spec.md` (`## Use Cases`, `## Use Case Details`) and at any existing `.spec/backlog/US-*.md` that derive from those UCs.
2. List each affected path under `## Affected Files` — both `.spec/spec.md` and every relevant `.spec/backlog/US-*.md`.
3. Add those paths to `write_scope`. Without write-scope coverage, DEV cannot edit them.
4. Include a dedicated task (e.g. `TASK-XXX: Propagate spike findings to affected Use Cases`) whose `files:` lists the same UC paths and whose `verify_cmd` re-runs `python ../shared/scripts/spec.py docs validate`. This task `covers:` at least one `DEL-*` so its evidence is recorded.
5. Add this `Definition Of Done` line: `- [ ] Affected Use Cases updated with spike findings (spec.md and every relevant US-*.md edited; paths listed under Affected Files).`
6. If the spike result invalidates an existing `US-*`'s AC or scope, the propagation task must edit that `US-*` directly. If the spike result demands a brand-new `US-*`, record it as a recommendation in the spike report and create the new story in a follow-up `/sm` run — do **not** silently fork new stories inside the spike.

If the spike honestly cannot affect any UC (rare: pure infra spike with zero product surface change), record `- file: .spec/spec.md  # no UC change — rationale in DEL-001 report` and explain the no-change decision in the report so QA/audit can verify intent.

Detailed execution-time enforcement of these rules lives in `../dev/references/spike_execution.md`.

## Ordering

Generate stories in implementation order. The DEV agent must not choose order manually; `spec story next` enforces strict order by default. A later story is not delivered while an earlier story is not `DONE`.

**Spike stories (`SP-*`) always precede feature stories (`US-*`) in the execution queue, regardless of `priority` value.** `spec story next` enforces this. Default `priority: 0` for spikes unless an explicit reason demands otherwise. The spike-first guarantee is what removes the need for a separate `/spike` phase — research lands in the backlog ahead of any feature work that depends on it.

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
- The backlog skill records each story's layer in the story Markdown body (e.g. as part of the story title, a dedicated `## Layer` line, or a tag in the description). The five names above are recommended defaults; adapt them when the architecture demands different vocabulary (e.g. event-driven projects may use `events`, `projections`, `handlers`; data pipelines may use `ingest`, `transform`, `publish`). This is an `/sm` instruction, not a code-enforced field — `spec` does not validate it.

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

ACs originate in `spec.md`. Every AC needed by a story must be referenced in `context_refs.product` and listed by ID in the story `## Acceptance Criteria`; do not copy the AC text into the story.

If a new AC changes product behavior, return to `/po` to update `spec.md`. If it is purely technical/incremental, keep it in the story.

## Story Context Contract

Feature stories must declare `context_refs` in front matter. `/sm` is responsible for selecting the smallest product and architecture refs that allow DEV and QA to execute the story without reading full DotSpec source documents.

Use these source-of-truth boundaries:

- `spec.md` owns product refs: `ACT-*`, `UC-*`, `UC-*.FP`, `UC-*.FA*`, `AC-*`, `BR-*`, `INV-*`, `BE-*`, `SP-*`, `DEL-*`, `ASM-*`.
- `architecture.md` owns architecture refs: `ADR-*`, `CMP-*`, `CLS-*`, `VO-*`, `IF-*`, `CMD-*`, `NFR-*`, `QG-*`, `STATE-*`.
- `design.md` is referenced as `design: full` for UI/frontend stories and `design: none` for non-UI stories.
- Affected Files are authored in the story by `/sm`; they do not come from `spec.md`. Files that are explicitly cited in `architecture.md` must map back to architecture refs through `## Implementation Targets`. Files not cited by architecture may omit architecture refs.

Every architecture-referenced file in `## Affected Files` must appear in `## Implementation Targets`. Every such target must name the architecture ref(s) that justify the file and the expected symbol(s) from `architecture.md`. Every task that creates or modifies a file explicitly cited in `architecture.md` must declare matching `architecture_refs`.

## Completion Gate

Before finishing:

1. Run `python ../shared/scripts/spec.py docs validate` from the project root. If the path is different, resolve `spec.py` first and run the equivalent command.
2. Every feature story has ACs, tasks, verify commands, affected files, and write scope.
3. Every spike story has research question, deliverables, tasks, verify commands, affected files (spike outputs **plus** every affected Use Case path), a propagation task, and write scope covering the affected UC paths.
4. `spec story context STORY-ID` resolves every story ref, and no story requires DEV to read full `.spec/spec.md`, `.spec/architecture.md`, or `.spec/design.md` directly.
5. SP-* stories appear before US-* stories in the execution queue (verified by `spec story next` returning SP-* first).
6. Run `spec phase done sm`.
7. Ask the user for explicit permission before invoking the `dev` skill. Do not auto-invoke `/dev` after `/sm`; stop after reporting the backlog status and the recommended next step unless the user clearly grants permission to continue.

If the user explicitly says "stop", "pause", "halt", declines permission, or otherwise interrupts, do not invoke `/dev`.

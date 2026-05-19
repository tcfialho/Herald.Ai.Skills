---
name: ux
description: DotSpec /ux UX stage. Use when the project needs static navigable production-quality UI prototypes and, after user acceptance, a DESIGN.md-compatible .spec/design.md design system. Reads .spec/spec.md, generates .spec/prototype/ first, then documents accepted visual decisions in .spec/design.md. Writes no backend or functional application code.
---

# DotSpec /ux — UX

## Purpose

Create static navigable production-quality screens, then document the accepted design system.

This phase is prototype-first. Do not finalize `.spec/design.md` until the user accepts the generated prototype direction.

## Required Outputs

```text
.spec/design.md
.spec/prototype/
```

Use `../shared/templates/design_template.md` as the base only after the prototype is accepted.

## Command — `spec`

`spec` is **not** an executable on `PATH`. Every `spec ...` instruction in this document is shorthand for the bundled DotSpec script run with Python. Resolve it once, before the phase check, then reuse it for every `spec` call below:

1. Take this skill's own directory — the folder that contains this `SKILL.md`.
2. Its sibling script is `<skill-dir>/../shared/scripts/spec.py`. Resolve that to an absolute path. `shared/` always sits next to the role directory in both the repo layout (`skills/dotspec/<role>/`) and the installed bundle (`<skills-root>/<role>/`), so this holds in both.
3. From here on, read every `spec <args>` as `python "<abs>/shared/scripts/spec.py" <args>` (use `python3` if `python` is unavailable).

Run it from the target project root — the directory that has, or will have, `.spec/` — so the script resolves the right project; it finds its own templates regardless of where it is called from. Resolve every other `../shared/...` path in this document the same way: relative to this skill directory, never relative to the current working directory.

## Input

Before working, run `spec phase check ux`. If it fails, stop and ask the user to call the missing previous skill.

Read `.spec/spec.md` after the phase check passes.

If `.spec/architecture.md` exists, use it for frontend technology constraints. If not, choose the simplest static prototype format and record the assumption.

## Output Language

- Author prototype visible copy and `.spec/design.md` user-facing prose in the language of the user's current product prompt.
- Keep programming terms, design token names, component keys, technical identifiers, IDs, paths, commands, class names, package names, and code symbols in their canonical English/as-specified form.
- If the prompt mixes languages, use the dominant language of the product request; ask only when the intended artifact language is genuinely ambiguous.

## Spike Escalation

If during this phase you detect a technical gap that meets any mandatory spike trigger (unfamiliar API or framework, unproven hypothesis, knowledge-cutoff risk, tooling tradeoff, performance claim, unfamiliar format, etc.), pause `/ux` and ask the user to call `/po`. The Product Owner is the only role that may write `SP-*` entries in `.spec/spec.md`. Do **not** edit `## Spikes` directly from `/ux`.

After `/po` adds the spike, resume `/ux` from the same step.

The full list of mandatory triggers and the `SP-*` structure live in `../po/references/spike_authoring.md`.

## Decision Rules

- UI exists when a human user will view or operate screens, pages, forms, dashboards, dialogs, emails, reports, or generated documents.
- No UI means the product is only API, CLI, job, library, or backend automation. In that case, write an explicit "No UI" note in `design.md`; prototype files are not required.
- A screen is a distinct user-facing view or state needed to complete a use case. Include modal, empty, loading, error, and success states when they materially affect UX or acceptance.
- Static production-quality means high-fidelity visual HTML/CSS or equivalent static artifacts that look like the final product, with realistic data and states, but no backend integration.
- If an existing frontend stack is present and can be used without implementing backend behavior, prototype in that stack. If no stack exists, default to standalone static HTML/CSS under `.spec/prototype/`.
- Navigable means the prototype has an entry file, visible navigation or links between screens, and enough client-side behavior to inspect normal, empty, error, success, and modal states without backend calls.
- Do not invent product behavior to make a screen nicer. If the UI needs behavior missing from `spec.md`, record the assumption or ask a DotSpec question. If the missing behavior implies technical discovery, escalate to `/po` (see Spike Escalation).

## Mandatory Workflow

1. Run `spec phase check ux`.
2. Read `.spec/spec.md`; read `.spec/architecture.md` only if it exists.
3. Identify UI use cases and screen/state inventory.
4. **Reference Anchoring Gate** — ask the Reference Anchoring question (see below) before generating the prototype. Branch on the answer:
   - **Branch A (default — prototype-first)**: skip to step 5.
   - **Branch B (reference-first)**: extract `.spec/design.md` from a reference URL via the `design-md` skill, then generate the prototype already applying that design system. Continue to step 5 with design tokens already fixed.
5. Generate or update the static navigable prototype under `.spec/prototype/`. In Branch B, the prototype must consume tokens from the pre-existing `.spec/design.md`.
6. Present the prototype path and ask for user acceptance or revision.
7. If the user requests revisions, update the prototype and ask again. In Branch B, if the user rejects the referenced design system itself, return to step 4 (re-ask Reference Anchoring with new options).
8. Only after acceptance:
   - **Branch A**: write or update `.spec/design.md` from the accepted prototype.
   - **Branch B**: `.spec/design.md` already exists from step 4; reconcile any prototype-driven adjustments into it.
9. Run `spec phase done ux`.
10. Ask the user to call the next skill printed by `spec phase done ux`.

Before acceptance, `design.md` may exist as an initialization placeholder (Branch A) or as an extracted reference draft (Branch B), but it is not final until step 8 reconciliation.

## Reference Anchoring Gate

Ask exactly one DotSpec question after step 3, before generating any prototype:

```text
Q. Anchor design system on a reference before prototyping?

1. Discuss in free text [RECOMMENDED]
2. Yes — I have a reference URL, extract design.md from it first
3. Yes — suggest sector benchmarks for me to choose from
4. No — generate prototype first, document design.md after acceptance (default flow)
5. Mix — extract from reference URL, then revise visuals before locking design.md
0. End the conversation
```

### Option 2 / 5 — Extract from URL

1. Ask the user for the reference URL.
2. Invoke the `design-md` skill: `node .claude/skills/design-md/run.cjs --url <reference-url> --out .temp/design-md-work/`.
3. Move `.temp/design-md-work/{slug}/DESIGN.md` to `.spec/design.md` (rename to lowercase to match the DotSpec contract — phase check, audit, and `cmd_phase_check` look for `.spec/design.md`). The Google `DESIGN.md` body matches the canonical sections, so no content transformation is needed.
4. **Mandatory cleanup**: delete the entire `.temp/design-md-work/` folder after extraction. Do not retain `tokens.json`, `preview.html`, `style-fingerprint.json`, the `{slug}/` subfolder, or any other temp file — `.spec/design.md` is the only artifact that survives. Use `rm -rf .temp/design-md-work/` (bash) or `Remove-Item -Recurse -Force .temp\design-md-work\` (PowerShell). Global rule: every temporary file or scratch folder produced by any DotSpec skill must live under `.temp/` and be cleaned at flow end.
5. Confirm `.spec/design.md` exists, has valid YAML front matter, and `.temp/design-md-work/` no longer exists before proceeding to prototype generation.
6. In Option 5, after design.md exists, ask a follow-up DotSpec question listing visual aspects to revise (palette, typography, density, etc.) before locking.

### Option 3 — Suggest benchmarks

Generate 3–5 contextual benchmark URLs based on `spec.md` domain. Examples by domain:

- **B2B SaaS / dashboard**: linear.app, stripe.com, vercel.com, height.app
- **Fintech / banking (BR)**: nubank.com.br, bancointer.com.br, c6bank.com.br
- **Observability / data**: grafana.com, datadoghq.com, posthog.com
- **E-commerce**: shopify.com, stripe.com, polaris.shopify.com
- **AI / dev tools**: anthropic.com, openai.com, perplexity.ai

Present them as a numbered DotSpec question. After user picks one, follow Option 2 flow.

### Option 4 — Default flow

Skip extraction. Continue with prototype-first workflow as documented.

### Tooling check

Before invoking `design-md`, confirm the skill is installed at `.claude/skills/design-md/`. If missing, instruct the user to install it (see the skill's README) and fall back to Option 4 until installed. The `design-md` skill uses static HTTP fetch (no headless browser), so any public URL works.

## Prototype Rules

- Generate every screen identified from use cases with UI.
- Create an entry point such as `.spec/prototype/index.html`.
- Keep screens navigable with links, tabs, or static client-side state switching.
- Static screens must look production-ready, not wireframe-only.
- No backend integration, network dependency, real authentication, or production data mutation.
- Use realistic domain content.
- Include responsive behavior for mobile and desktop when the product has human UI.
- Make visible UI states inspectable: default, empty, loading, error, success, disabled, selected, and modal states when applicable.
- **Branch A (prototype-first)**: use a coherent temporary token set in prototype CSS; these tokens become the source for `design.md` after acceptance.
- **Branch B (reference-first)**: prototype CSS must consume tokens already defined in `.spec/design.md` (colors, typography, spacing, rounded, components). Do not invent tokens not present in `design.md`; if a screen needs a missing token, add it to `design.md` and note the addition in the Acceptance Question.

## Acceptance Question

After generating the prototype, ask exactly one DotSpec question:

```text
Q1. Do you accept this prototype direction so I can document it in .spec/design.md?

1. Discuss in free text [RECOMMENDED]
2. Accept prototype and generate design.md
3. Revise visual style before documenting
4. Revise screens or navigation before documenting
5. Add missing UI states before documenting
6. Mark project as No UI and document that decision
0. End the conversation
```

Do not run `spec phase done ux` before option 2 or 6 is selected or clearly requested (free text answers must resolve to one of those before completion).

## DESIGN.md Rules

`.spec/design.md` follows the DESIGN.md specification:

- YAML front matter contains machine-readable tokens.
- Markdown body explains design rationale and usage rules.
- Tokens are normative. Prose explains why and how to apply them.
- Unknown sections are allowed.
- Unknown token names are allowed if values are valid.
- Unknown component properties are allowed with caution.
- Duplicate canonical sections are not allowed.
- Sections use `##` headings and must appear in canonical order when present.

Canonical sections:

- Overview
- Colors
- Typography
- Layout
- Elevation & Depth
- Shapes
- Components
- Do's and Don'ts

Required token guidance:

- `version` is optional; use `alpha` when present.
- `name` is required.
- `description` is optional.
- `colors` maps token names to sRGB hex colors, for example `"#1A1C1E"`.
- `typography` maps names to objects with `fontFamily`, `fontSize`, `fontWeight`, `lineHeight`, and optional `letterSpacing`.
- `rounded` maps scale names to dimensions, for example `4px`.
- `spacing` maps scale names to dimensions or numbers.
- `components` maps component names to properties. Valid common properties: `backgroundColor`, `textColor`, `typography`, `rounded`, `padding`, `size`, `height`, `width`.
- Component variants use related keys such as `button-primary-hover`, `tab-active`, or `input-error`.
- Token references use `{path.to.token}`, for example `{colors.primary}` or `{rounded.md}`.

Recommended token names:

- Colors: `primary`, `secondary`, `tertiary`, `neutral`, `surface`, `on-surface`, `error`.
- Typography: `headline-display`, `headline-lg`, `headline-md`, `body-lg`, `body-md`, `body-sm`, `label-lg`, `label-md`, `label-sm`.
- Rounded: `none`, `sm`, `md`, `lg`, `xl`, `full`.

## Validation

When Node/npm is available, validate the accepted `design.md`:

```text
npx @google/design.md lint .spec/design.md
```

If the CLI is unavailable, manually check:

- YAML front matter starts and ends with `---`.
- Token references resolve.
- Colors are valid hex values.
- Component text/background pairs meet WCAG AA contrast where possible.
- Canonical sections are in order and not duplicated.
- Typography exists when colors exist.

## Discovery Questions

Ask only when a design decision changes the final UI materially.

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

## Completion Gate

Before finishing:

1. Reference Anchoring Gate was answered (option 2, 3, 4, or 5 selected, or free-text resolved to one of those).
2. User accepted the prototype direction, or the project is explicitly documented as No UI.
3. `.spec/prototype/` has a navigable static prototype for every UI use case, unless No UI.
4. `.spec/design.md` exists after acceptance and has valid DESIGN.md YAML front matter.
5. `design.md` tokens match the accepted prototype (Branch A) or the prototype consumes tokens from `design.md` with no orphan invented tokens (Branch B).
6. Prototype screens apply the same design system documented in `design.md`.
7. The design does not introduce product behavior missing from `spec.md`.
8. If Branch B was used, `.temp/design-md-work/` **must not exist** — it was deleted in step 4 of "Extract from URL". `.spec/design.md` is the only authoritative artifact.
9. Run `spec phase done ux`.
10. Ask the user to call the next skill printed by `spec phase done ux`.

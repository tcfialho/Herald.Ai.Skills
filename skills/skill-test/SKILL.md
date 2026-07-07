---
name: skill-test
description: Automated test harness for agent skills. Use whenever creating or modifying a skill (SKILL.md, references/, scripts/) to validate it before committing; also to compare a skill's behavior and token cost across models, find the weakest model it survives on, or profile token spend between versions. Invoked bare (/skill-test) it opens a dashboard of all benchable skills.
---

# 🧪 skill-test

**MUST: every chat message you send — including one-line status and error messages — starts with this exact `# 🧪 skill-test` H1 banner, with no exceptions.**

The agent orchestrates and renders; `scripts/test_tool.py` runs, measures, judges and stores — deterministically. Skills are LLM-interpreted source code with no compiler; this is their regression suite.

## Banner + silence

- **No preamble text — ever.** Do not emit any text before or between tool calls ("I'll look at…", "Let me run…", "Now I'll…"): call the tool directly. Your only text output is the final rendered screen for the step — and it starts with the banner. The single exception: before a matrix run emit exactly one line under the banner, `Running <S> scenarios × <M> models × <K> reps (<N> cells)…`, then silence until the report. Long runs: background + refresh a **single** progress line from `status` (`14/24 cells · 2 fail`).

## Menu system (HARD RULES)

Every step below ends with **one contextual numbered menu** — never a dead end, never more than one menu.

- **The chat message IS the menu.** Each step renders its didactic numbered menu in the chat message itself: every option on its own line with a short plain-language explanation of what it does and when to pick it. A first-time user must understand every option without prior knowledge of the tool. The question tool, when available, comes AFTER as a thin picker mirroring the same options (labels only, no explanations/tables/banner inside the tool call) — it never replaces the didactic menu in chat.
- **Conditional options, no gaps**: include only applicable options and renumber 1…N. Examples: skill without `tests/` → the panel shows only "create the suite"; nothing judged → no Promote.
- **Selection first**: the home only lists and selects; every action (including creating the suite) happens inside the selected skill's panel.
- **No decline option**: never list "No, thanks". Users who don't want to proceed just don't reply.
- **Row selection**: where a menu says "pick a table row", accept a single number (1…K) and an inclusive range `3-7`; process ranges in table order.
- **Load on the label**: options that spawn model sessions say how many — `Full matrix (6 cells)`. Each cell is a full agent session charged against the user's plan quota (or API credits when on API billing) — never label with dollars for subscription users; USD figures from the CLI are reference telemetry, not money the user is spending. Floor and full matrices are never the default choice.
- **Navigation last**: the final option is always the way back (Dashboard / Skill panel / Done).

## Step 1 — Welcome menu (dashboard)

Trigger: bare invocation (`/skill-test`), "overview", "status das skills", or no skill named.

Run `test_tool.py overview` and render the standardized welcome screen — didactic, in the conversation language, following this template exactly (structure and emoji; texts translated to the user's language):

```markdown
# 🧪 skill-test

Test harness for agent skills: runs a skill end to end against real models,
checks its contract, and tells you what broke, where, and on which model.

## 📊 Skills in this repo

| # | Skill | Tests | Seal | Last run | Baseline |
|---|-------|:-----:|------|----------|:--------:|
| 1 | `<skill-a>` | 4 scenarios | ✅ fresh | run-8 · 1/1 · judged | — |
| 2 | `<skill-b>` | — | — | — | — |

_Selo: ✅ fresh = testada depois da última edição · ⚠️ stale = editada sem retestar · — = ainda sem suíte de testes._

**Selecione uma skill para trabalhar:** responda com o número da linha (1…K).
Nada é executado ao selecionar — você verá o painel dela com as ações possíveis.

_Ou:_ **E. Entender como funciona** — explica o que é a suíte `tests/`, selo, células,
contrato e juiz, sem executar nada.
```

The home does ONLY selection: list ALL skills (with and without tests) as numbered rows — creating tests, running, everything else happens inside the selected skill's panel (Step 2). The table rows are placeholders — always render the REAL skills found by `overview`. Replies: row number → Step 2 · `E` → glossary (tests/ = the skill's versioned test suite: contract.yaml defines what "working" means, scenarios are simulated user journeys, fixtures are the disposable world each cell runs in; plus seal, cell, judge, ladder — 1-2 lines each), then re-render this menu.

## Step 2 — Skill panel

Trigger: a skill was named ("testa a skill X", "quanto custa a skill X?") or picked in Step 1. Two variants — each rendered message starts with the `# 🧪 skill-test` banner, same as every other step:

**Skill WITHOUT tests/** — explain before offering anything (didactic, conversation language): this skill has no test suite yet; the suite lives in `skills/<name>/tests/` and is what defines "working" — `contract.yaml` (the rules), scenarios (simulated user journeys), fixtures (the disposable world). Without it there is nothing to execute: the harness measures against versioned criteria, it never invents them per run. **Menu:** 1. Create the suite now — `init --skill <name>` scaffolds, then you author contract + first scenario with the user (read `references/authoring.md` first) · 2. Back to home.

**Skill WITH tests/** — run `seal --skill <name>` (+ reuse `overview` data) and render a short panel: seal state, last run (id · pass/cells · judged?), baseline, scenario list, ladder of the chosen adapter. Below it, the didactic menu — each option rendered in chat with its explanation translated to the conversation language, e.g. `1. **Smoke (2 células)** — teste rápido: melhor modelo, todos os cenários, 1 repetição. Recomendado: o selo está stale.` **Options (conditional):**

1. **Smoke run (S cells)** — top ladder model × all scenarios × 1 rep. Recommended (label it) when the seal is stale.
2. **Full matrix (S×M cells)** — whole ladder × all scenarios (`--fail-fast`).
3. **Report of last run** — only if a run exists; if it lacks judge.json, run `judge` first, then `report`.
4. **Floor (up to S×M cells)** — descend the ladder to the breaking rung (`floor`).
5. **Profile token cost** — `profile`; offer `--vs-ref <ref>` A/B when the skill sits in a git repo.
6. **Switch adapter/ladder** — only if config.yaml has >1 adapter; re-render this panel for it.
7. **Back to home**

Options 1/2 → run (background if >2 cells) → `judge` → Step 3. Option 4 → confirm load, run `floor` → render zones (`sonnet ✅ native · haiku ❌ floor (B-04)`) → this menu again. Option 5 → run → render totals (exact) + split (estimated, say so) → this menu again.

## Step 3 — Run report

After any run+judge, or menu option 3. Build from `report --run-id <id>`:

```markdown
# 🧪 skill-test

## <skill> · <run-id>[ vs baseline <id>]

| Scenario | <model1> | <model2> |
|---|:-:|:-:|
| happy-path | ✅ 100 | ⚠️ 71 |

**Activation (auto):** <model>: N/M cells (excluded from contract scores)
**Ladder:** stable until `<stable_until>` · breaks at `<breaks_at>`
**Load:** <N> cells · <wall> — judge: <model>, <votes> vote(s)

### Failures
| # | Cell | Item | Evidence |
|---|------|------|----------|
| 1 | hook-failure/haiku/1 | C-07 | "algo deu errado" (turn 14) |
```

Cell score = `contract_pct` when judged, else `compliance_pct`; ✅ pass · ⚠️ pass w/ contract <100 · ❌ fail; other statuses as text (`desync`, `no-activation`, `budget`, `infra`). **Menu (conditional):**

1. **Drill into failure** — pick a Failures row (1…K or range) — only if failures exist
2. **Judge with 3 votes / opus** — only if current judge was 1-vote sonnet (decision runs need more)
3. **Re-run unfinished cells** — `run --resume <run-id>` — only if cells ended `infra_error`/`over_budget`
4. **Promote as baseline** — only if all cells pass AND judged ≥ threshold; needs explicit user pick
5. **Back to skill panel**

## Step 4 — Failure drill-down

For each picked row run `report --run-id <id> --cell <scenario>,<model>,<rep>` and render, starting with the `# 🧪 skill-test` banner: cell meta (status, cost, turns), failed items with evidence quotes, the relevant transcript excerpt (quote only what the evidence cites), probe outputs that failed. **Menu:**

1. **Next failure** — only if more rows remain in the pick
2. **Back to run report**
3. **Back to skill panel**

## Cell statuses & exit codes

`pass · fail` are verdicts about the skill; `not_activated · desync · over_budget · infra_error` are context/harness conditions — report them separately, never as model regressions. Exit codes: `0` all pass · `1` some cell failed · `2` config/infra error (payload carries `error`).

## Hard rules

- Never judge a skill yourself in place of `judge` — verdicts come from the script + configured judge model, reproducible outside this chat.
- **Do not run `judge` while iterating on a skill.** During tuning, deterministic checks are the only feedback loop. `judge` runs at decision points only: final verdict of a change, `floor`, or before `promote` (which requires 3 votes). Judging every intermediate run burns quota on verdicts that the next edit invalidates.
- Never edit a skill's `tests/contract.yaml` to make a failing run pass. Contract changes are deliberate, user-approved acts.
- Failures are reported with their cited evidence, verbatim. `infra_error`/`desync` cells are never presented as skill regressions.
- Every cell burns the user's plan quota (session limits) or API credits: smoke scope by default; full matrices, floor and repeat ≥3 only via explicit menu pick, with the cell count on the label. If a SUT session returns a "session limit" message, stop launching cells, tell the user when it resets, and offer to resume later (`run --resume`).
- After changing any skill's SKILL.md/references/scripts, run its smoke before committing (`seal --skill <name>` shows staleness).

## Gotchas

- Headless SUT sessions have no structured question tool — scenarios exercise the numbered-menu fallback path.
- The SUT runs with least-privilege `allowed_tools` from the scenario; a permission error in a transcript usually means the allowlist is too tight, not a skill bug.
- `profile` token *split* is an estimate (chars/4); only the totals are exact API usage. agy cells are always `usage_quality: estimated`.
- On the agy adapter, activation and tool events are not observable: no Activation line, event checks show as excluded — never count them as passed.

Authoring contracts, scenarios and fixtures → read `references/authoring.md` first.

---
name: git-commit
description: Create git commits from the user's changes — semantic grouped commits with synchronized timestamps. Use whenever the user asks to commit, save or record changes ("commit my changes", "commit this", "faça o commit", "commita", "salva as alterações", "cria os commits"). scripts/commit_tool.py runs git deterministically; the user approves the commit plan once.
---

# 📦 git-commit

**MUST: every chat message you send — including one-line status, error and interstitial messages — starts with this exact `# 📦 git-commit` H1 banner, with no exceptions.**

The agent orchestrates. Python executes git. The user interacts exactly once, to approve the plan.

## Banner + silence

- **No preamble text — ever.** Do not emit any text before or between tool calls ("I'll check…", "Now I'll rewrite the plan…", "Let me run…"): call the tool directly. Your only text output is the rendered screen for the step — and it starts with the banner. The plan-fix-revalidate loop is silent; surface it only after it fails 3 attempts.
- Sole permitted mid-flow narration: when `prepare` (or legacy `collect`) returns `total_staged` ≥ the Slow-collect threshold (Configuration), emit exactly one line under the banner before the plan — `Analyzing <total_staged> files staged…` — no tables, no sub-steps.

<!-- skill-config:start -->
## Configuration

- **Commit description language:** `en` _(ISO 639-1; the `<type>[!]:` prefix is always English regardless.)_
- **Allowed commit types:** `feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`
- **Max description length:** `72`
- **Sync timestamp by default:** `true`
- **Slow-collect narration threshold:** `30` _(emit the "Analyzing N files…" line when `total_staged ≥ this`; raise very high to silence.)_
<!-- skill-config:end -->

## Workflow (default path)

1. `prepare` — preflight + stage + auto `commit-plan.json` + validate, one call. Read `preflight`, `plan`, `temp_dir`, `validate` from the payload; never hand-write paths.
2. **Reword the placeholder messages.** Auto-plan messages are deterministic stubs (`<type>: add|update <bucket>`) — never good enough to show as-is unless one genuinely describes the change. Rewrite each group's `message` from what the changes actually do (you usually authored them this session); keep every `files` array byte-identical. Overwrite `plan_path`, then `validate --temp-dir <temp_dir>` (max 3 attempts, § Plan rules). No session context (cold dirty tree) and paths aren't enough? `cleanup`, then `prepare --max-files 20` and read the diffs before rewording.
3. Present the plan from `plan.groups` (+ `staged_files` for status letters) in chat, then the approval menu via `AskQuestion` (§ AskQuestion split). Never present a plan without a passing `validate` — `prepare`'s internal validate counts only for an untouched auto plan.
4. On approve: `execute --temp-dir <temp_dir> --confirm --yes-plan`.
5. Report commits (§ Commit report).
6. Push: read `references/push-ux.md` (menu option 1 → prompt; option 2 → auto-push, no prompt). **Every reply in the push flow — including after the user declines — uses the exact template in that reference (banner + heading), never a free-form acknowledgement like "Understood" or "Got it".**

Menu options 3–6 → read `references/adjust-flows.md` before acting.
Auto-grouping wrong, or messages need diffs → read `references/legacy-path.md`.

**Where commands run.** `scripts/commit_tool.py` lives in this skill's folder — invoke it via the skill's absolute path with the **user's repo root as CWD** (where `.git/` lives). `prepare`/`collect` return a fresh OS-temp `temp_dir`; pass that exact path as `--temp-dir` to every later subcommand. Never change CWD mid-flow; never guess `temp_dir`.

**Cleanup.** `execute --confirm` wipes `temp_dir` on success **and** failure (payload reports `temp_cleaned`; the agent may force-remove on `false`). Dry runs and `execute` pre-loop errors (missing plan, bad JSON) preserve it. If the flow is abandoned anywhere between `prepare`/`collect` and a clean `execute --confirm` (cancel, validation exhausted, any other error), the agent MUST run `cleanup --temp-dir <temp_dir>`. Never re-read `temp_dir` files after success.

**Stale manifest.** `--yes-plan` commits from `staging-manifest.json` frozen at `prepare`/`collect` time. If staging changed since (unstage, new `git add`, option 6): `cleanup`, then `prepare` again — never `--yes-plan` on a stale manifest.

## Commands

Each subcommand prints a single JSON result on stdout. stderr progress JSONL is emitted only with `COMMIT_TOOL_VERBOSE=1` (warnings/errors always).

| Subcommand | Flags | Purpose | Exit codes |
|---|---|---|---|
| `prepare` | `[--no-add] [--max-files N]` (default `0` = no diffs) | **Preferred entry.** Preflight + stage + auto plan + validate | `0` ok · `10/11/12` preflight/clean · `20` auto-plan bug |
| `execute` | `--temp-dir <p> [--confirm] [--yes-plan] [--natural-timestamps]` | Commit groups atomically, synced timestamps | `0` ok · `20` plan/manifest · `30` failed · `40` hook |
| `push` | `--remote <n> --branch <n> [--set-upstream]` | `git push`; never `--no-verify` | `0` ok · `50` failed |
| `cleanup` | `--temp-dir <p>` | Idempotent temp-dir removal (`noop` when missing) | `0` |
| `set-author` | `--name <N> --email <E>` | Local repo `user.name`/`user.email`; no staging side-effects | `0` |
| `create-branch` | `--name <N>` | `git checkout -b`; validates name, refuses existing; never pushes | `0` · `60` invalid · `61` exists · `62` failed |
| `unstage` | `--path <P>` (repeatable) | `git rm --cached` for given paths | `0` (`partial` if some failed) |
| `preflight` / `collect` / `validate` | see `references/legacy-path.md` | Legacy manual-plan path | `0` · `10/11/12` · `20` |

### `prepare` payload (field list)

Success: `status:"ok"`, `auto_plan`, `temp_dir`, `plan_path`, `plan {version, groups[{id, message, files[]}]}`, `preflight {branch, head, is_empty, author{name,email}|null, remote_info}`, `validate {status, groups, files}`, `staged_files[]`, `total_staged`, `diff_summary {total_added, total_removed}`, `manifest_path`.

- `staged_files[]`: `{status: A|M|D|R|T|C, path}`; renames also carry `old_path` and `commit_paths` `[old, new]`. The list always includes **every** staged entry — no deletion is ever hidden. Copy paths **only** from `plan` / `staged_files` — never from memory.
- `remote_info`: `has_remote`, `remotes[{name}]`, `has_upstream`, `upstream`, `upstream_remote`, `ahead`, `behind`. `has_remote: false` → `remotes: []`, other fields absent → skip push entirely. `ahead`/`behind` may be absent (shallow clone, unfetched ref) — never invent zeros.
- Auto plan: deletions → `chore: remove deleted paths`; other paths bucketed by top-level prefix. Messages are placeholders — reword them (Workflow step 2) while keeping every canonical staged path in exactly one group.
- `status:"clean"` (exit `12`): nothing to commit — say so and stop. `status:"error"` (exit `10/11`): surface the message and stop. `preflight.author: null` → replace the plan with `## ⚠️ Git author not configured` and stop until the user sets it. `status:"invalid"` / `AUTO_PLAN_INVALID` → tool bug: surface it and `cleanup`; do not ask the user to fix paths.
- `--max-files` defaults to `0` (no `diffs/`); pass a positive value only when tuning messages from diffs.

## Plan rules

```json
{ "version": 1, "groups": [
  { "id": 1, "message": "feat: add user profile caching",
    "files": ["src/cache/profileCache.js", "src/services/profileService.js"] }
] }
```

- Every staged file in exactly one group; no empty groups; groups never outnumber staged files.
- Every staged `D` is assigned to the group whose change removes/replaces it — never optional, never unassigned.
- `R`: only the new path in `files` (the manifest keeps both sides for commit).
- Prefer granular commits by concern (config, feature, tests, docs).
- Message: `<type>[!]: <description>` matching `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)!?: .{1,72}$` — single line. **No scope**: `feat(scope):` is rejected by the validator; put the area in the description. Description language per Configuration.
- `validate` errors (`INVALID_MESSAGE_FORMAT`, `FILE_NOT_STAGED`, `STAGED_BUT_UNASSIGNED`, `DUPLICATE_FILE_ACROSS_GROUPS`, `EMPTY_FILE_LIST`): fix the plan, re-validate — max 3 attempts, then `## ⚠️ Could not validate the plan` + `cleanup`.

## AskQuestion split (HARD RULE)

Two channels, always in this order:

1. **Chat message first** — the full report: banner, `## Commit plan` / `## Push?`, author/branch meta, group tables, line counts, warnings.
2. **`AskQuestion`** — one-line `prompt`, optional short `title`, option labels only. Never put the plan, push context, tables, banner, headings, blockquotes, or warnings inside the tool call; no `1.` prefixes on labels (the tool renders its own UI).

**Fallback (no structured question tool available):** treat the absence of `AskQuestion`/`AskUserQuestion` as a settled fact, decided before you write a single word of the plan — never call `ToolSearch` or any other tool to check, confirm, or look one up, for this or any other reason, at any point in this skill. A tool call of ANY kind between the plan text and the menu text is what fragments them into two messages, which is the one thing this rule exists to prevent. Write the full plan AND the numbered menu in the same, single, uninterrupted text output — no tool call starts until after the menu text is written and the user has replied. If a menu still ends up as its own message anyway, it is a NEW chat message and **MUST start with the `# 📦 git-commit` banner** — the banner rule in Banner + silence has no exception for continuations, follow-ups, or menus.

This applies to **every** menu in the skill: approval, push, `.gitignore` candidates.

## Plan display

```markdown
# 📦 git-commit

## Commit plan

Author: `<author.name>` `<<author.email>>`
Branch: `<branch>`

---

### Group N of M

> `<commit message>`

| Status | File |
|:------:|------|
|   A    | `path/to/file` |

`+X / −Y lines`
```

Meta lines come from `prepare.preflight` — plain text, no upstream arrow, no timestamp, no emoji. When `has_remote: false`, append after the groups:

```markdown
---

> ⚠️ This repository has no remote configured — the push step will be skipped after commit.
```

## Approval menu

AskQuestion `prompt`: `How do you want to proceed with this commit plan?`

| # | Option label | Semantics |
|---|---|---|
| 1 | Approve and execute (commit only) | `execute --confirm --yes-plan` → § Commit report → push prompt (`references/push-ux.md`) |
| 2 | Approve, commit and push | Same `execute`; on success push immediately, **no prompt**, per `references/push-ux.md` selection rules. On `execute` failure never push. |
| 3 | Adjust messages or grouping | `references/adjust-flows.md` |
| 4 | Change author (name and email) | `references/adjust-flows.md` |
| 5 | Create new branch before commit | `references/adjust-flows.md` |
| 6 | Update `.gitignore` and unstage matching files | `references/adjust-flows.md` |
| 7 | Cancel | `cleanup --temp-dir <temp_dir>`, confirm cancellation, stop |

- **Omit option 2 when `has_remote: false`** (and renumber the fallback list 2–6).
- Only an explicit approve (option 1, option 2, "approve", "yes") reaches `execute`.
- Options 4–6 mutate state and always return to this menu; option 3 re-plans, re-validates, then returns here.

## Commit report

```markdown
# 📦 git-commit

## ✅ Commits created

| # | SHA | Message |
|:-:|-----|---------|
| 1 | `a1b2c3d` | feat: add user profile caching |

**N commits** · **F files** · **+X / −Y** · `<synchronized_timestamp>`
```

- `has_remote: true` → nothing after the stats line; continue with `references/push-ux.md`.
- `has_remote: false` → append `> ⚠️ No remote configured — commits stay local on `<branch>`.` and stop.

Failure (exit `30`/`40`):

```markdown
# 📦 git-commit

## ❌ Commit <i> of <n> failed

<one-line reason, e.g. hook name>:

\`\`\`
<git_stderr>
\`\`\`

Rollback done: <k> commit(s) reverted, stage preserved. Temp dir cleaned.

### Next steps

1. <fix inferred from the error>
2. Run the skill again
```

## Output style

- Emojis only: `📦` in the H1 banner; `✅`/`❌`/`⚠️` on H2 status headers and `> ⚠️` warning blockquotes. Nowhere else — no per-row emojis, none in prose.
- `A/M/D/R` letters for git status. Tables for files/SHAs/counts; blockquotes for commit messages; backticks for paths/SHAs/commands/flags. Numbered lists for choices only in fallback mode.
- Never show diffs to the user — `diffs/` is agent-internal reasoning only.
- Never render a group with zero files — a plan on screen without a passing `validate` is forbidden.

## Gotchas

- Commit dates have 1-second resolution — synchronized batches share the same second; use `git log --topo-order` for ordering.
- Pre-commit hooks may mutate files mid-batch; on a later failure the tool rolls back the whole batch (soft reset) and preserves staging.
- Signed commits (`commit.gpgsign=true`) may prompt for a GPG password — the tool won't disable signing; configure an agent-friendly setup if batches hang.
- `git_stderr` from `push` may embed credentials (`https://user:token@host/…`) — redact the credential segment before pasting.
- `temp_dir` cleanup is irreversible — copy anything worth keeping before approving.

## Hard rules

- Never ask the user to run git commands. Never call git directly — every git operation, including `push`, goes through `scripts/commit_tool.py`.
- Never use `--no-verify`. Hooks must run.
- Never mention AI, Cursor, Antigravity, or `Co-authored-by` in commit messages.
- Every commit message matches the regex in § Plan rules; scope is rejected.
- Every staged file belongs to exactly one group.
- Never invent remote or branch names — always source them from the previous payload's `remote_info`/`branch`.
- Never push without explicit user approval (menu option 2 or the push prompt).
- § AskQuestion split is mandatory for every menu.

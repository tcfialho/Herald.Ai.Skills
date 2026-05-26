---
name: git-commit
description: |
  Agent-native skill for producing semantic, grouped commits with
  synchronized timestamps. The agent orchestrates; scripts/commit_tool.py
  runs git deterministically. The only user interaction point is the
  commit plan approval.
---

# 📦 git-commit

The agent orchestrates. Python executes git. The user interacts exactly once,
to approve the plan.

## Banner + silence rules

**Banner.** Every chat message from this skill starts with `# 📦 git-commit` as H1.

**Silence.** Never narrate tool calls in chat — the IDE already shows them. Forbidden openers include "I will start…", "Checking…", "Running preflight…", "Collecting…", "Validating…", "Analyzing changes…". The plan-fix-revalidate loop is silent; surface it only if it fails after 3 attempts. Inside an adjustment or cancel flow (options 3–7 below), every agent turn still wears the banner — silence applies only to pure tool-call narration.

**Large staging narration.** If `prepare` (or legacy `collect`) returns `total_staged` ≥ the Slow-collect threshold (see Configuration), emit exactly one line before the plan:

```
# 📦 git-commit

Analyzing <total_staged> files staged…
```

No tables, no bullets, no sub-steps.

<!-- skill-config:start -->
## Configuration

- **Commit description language:** `en` _(ISO 639-1; the `<type>[!]:` prefix is always English regardless.)_
- **Allowed commit types:** `feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`
- **Max description length:** `72`
- **Sync timestamp by default:** `true`
- **Slow-collect narration threshold:** `30` _(emit the "Analyzing N files…" line when `total_staged ≥ this`; raise very high to silence.)_
<!-- skill-config:end -->

## Workflow

Each step is one Python invocation. Steps 1–2, 4 and 7 are silent; the user only sees 3 (plan), 5 (commit result), 6 (push prompt — only on menu option 1 with a remote; option 2 pushes with no prompt) and 8 (push result).

**Default path (use this):**

- [ ] 1. `prepare` — preflight + stage + auto `commit-plan.json` + internal validate. Read `preflight`, `plan`, `temp_dir`, `validate` from the payload. **Do not** hand-write paths into the plan.
- [ ] 2. Present the plan from `plan.groups` (and `staged_files` for the file table) **in a chat message**; wait for approval via `AskQuestion` with **options only** (see § AskQuestion split).
- [ ] 3. On approval: `execute --temp-dir <temp_dir> --confirm --yes-plan` (uses `staging-manifest.json`; do not re-read the index).
- [ ] 4. Report commits.
- [ ] 5. Push UX (option 1: prompt; option 2: auto `push`).

**Legacy path (only when auto-grouping is wrong):** `preflight` → `collect --max-files 0 --max-diff-lines-per-file 0` → agent writes plan using paths from `staged_files[].path` and `commit_paths` copied literally from that payload → `validate` (loop ≤3, **before** showing the plan) → approval → `execute --confirm --yes-plan` → push. Prefer `prepare` so the agent never invents file lists.

**Where commands run.** `scripts/commit_tool.py` lives in this skill's folder — invoke it via the skill's absolute path with the **user's repo root as CWD** (where `.git/` lives). `prepare` / `collect` create a fresh isolated directory via `tempfile.mkdtemp()` in the OS temp area (e.g. `%TEMP%\git-commit-…` on Windows, `/tmp/git-commit-…` on POSIX) and return it as `temp_dir`. Carry that exact path through `--temp-dir <path>` in every subsequent subcommand. Never change CWD mid-flow; never guess `temp_dir`.

**Cleanup responsibilities.**

- Successful `execute --confirm` (commit *or* rollback) wipes `temp_dir`; payload reports `temp_cleaned: true` (or `false` on lock/permission).
- Dry runs (no `--confirm`) preserve `temp_dir` so the caller can retry.
- `execute` pre-loop errors (missing plan, bad JSON/schema) return `status: "error"` and preserve `temp_dir` — recoverable context is kept.
- The agent MUST call `cleanup --temp-dir <temp_dir>` whenever the flow is abandoned between `prepare`/`collect` and a clean `execute --confirm` (cancel on approval, validate exhausted after 3 tries on the legacy path, any other error between them).
- Agent may force-remove `temp_dir` as a fallback when `temp_cleaned: false` after success.
- Never re-read files under `temp_dir` after success.

## Commands

Every subcommand emits a JSON result on stdout and structured events on stderr (JSONL).

| Subcommand | Flags | Purpose | Notable exit codes |
|---|---|---|---|
| `prepare` | `[--no-add] [--max-files N]` (default `0` = no diffs) | **Preferred.** Preflight + collect + auto plan + validate in one call | `0` ok · `10/11/12` preflight/collect · `20` auto-plan bug |
| `preflight` | — | Validate repo + capture identity and remote topology | `0` ok · `10/11` error · `12` clean |
| `collect` | `[--max-files N] [--max-diff-lines-per-file N] [--no-add]` | Legacy: stage, return `temp_dir`/`plan_path`/`manifest_path`; agent writes plan. **Use `--max-files 0 --max-diff-lines-per-file 0`** | `0` ok · `12` clean (nothing staged) |
| `validate` | `--temp-dir <path>` | Check plan JSON vs regex + staging | `0` ok · `20` invalid |
| `execute` | `--temp-dir <path> [--confirm] [--yes-plan] [--natural-timestamps]` | Commit; `--yes-plan` uses `staging-manifest.json` (no index re-read) | `0` ok · `20` missing manifest · `30` commit failed |
| `push` | `--remote <name> --branch <name> [--set-upstream]` | `git push`; never `--no-verify` | `0` ok · `50` push failed |
| `cleanup` | `--temp-dir <path>` | Idempotent removal of an abandoned `temp_dir` | `0` ok (incl. `status: "noop"` when path missing) |
| `set-author` | `--name <N> --email <E>` | Set local repo `user.name`/`user.email` | `0` ok |
| `create-branch` | `--name <N>` | `git checkout -b <N>` (no push, validates name, refuses if branch exists) | `0` ok · `60` invalid name · `61` branch exists · `62` checkout failed |
| `unstage` | `--path <P>` (repeatable) | `git rm --cached` for the given paths. Pattern selection and `.gitignore` editing are the agent's job. | `0` ok (or `partial` when some paths failed) |

### `preflight` stdout shape

```json
{
  "status": "ok",
  "branch": "main",
  "head": "a1b2c3d…",
  "is_empty": false,
  "author": { "name": "…", "email": "…" },
  "remote_info": {
    "has_remote": true,
    "remotes": [{ "name": "origin", "url": "https://…" }],
    "has_upstream": true,
    "upstream": "origin/main",
    "upstream_remote": "origin",
    "ahead": 0,
    "behind": 0
  }
}
```

`status` may also be `"clean"` (working tree clean, exit `12`) or `"error"` (exit `10/11`). `branch` is `null` when detached/empty; `head` is `null` on an empty repo; `is_empty: true` when HEAD does not yet exist; `author` is `null` when both `user.name` and `user.email` are unset. When `has_remote: false`, `remotes` is `[]` and the other `remote_info` fields are absent — skip the push prompt entirely.

### `prepare`

Single entry point. Runs preflight checks, stages (unless `--no-add`), builds `commit-plan.json` deterministically (deletions → `chore: remove deleted paths`; other paths bucketed by top-level prefix such as `skills/pipelines-explorer`), validates, and returns everything needed for the approval banner.

Stdout (success):

```json
{
  "status": "ok",
  "auto_plan": true,
  "temp_dir": "…",
  "plan_path": "…/commit-plan.json",
  "plan": { "version": 1, "groups": [ … ] },
  "preflight": { "branch": "…", "author": { … }, "remote_info": { … } },
  "validate": { "status": "ok", "groups": 2, "files": 17 },
  "staged_files": [ … ],
  "total_staged": 17,
  "manifest_path": "…/staging-manifest.json"
}
```

Use `preflight` / `plan` / `validate` from this payload — **never** call separate `preflight` + `collect` + `validate` on the default path. **Never** present the approval banner until `prepare` returned `validate.status: ok` (validation is already done inside `prepare`; do not run a separate `validate` before the first plan UI).

The agent may reword commit messages in option 3, but must keep every canonical staged path in exactly one group (copy paths from `plan`, `staged_files[].path`, or `staged_files[].commit_paths` for renames — never from memory).

`--max-files` defaults to `0` (no `diffs/`). Pass a positive value only when tuning messages from diffs.

If `status: "invalid"` with `AUTO_PLAN_INVALID`, surface a tool bug and `cleanup` — do not ask the user to fix paths.

### `collect`

On staged changes, writes under `temp_dir`: `commit-plan.json` (agent writes on the **legacy** path), `staging-manifest.json` (frozen snapshot for `execute --yes-plan`), and optional `diffs/`. When nothing is staged, returns `status: "clean"` (exit `12`) without creating a dir.

**Legacy agents:** always pass `--max-files 0 --max-diff-lines-per-file 0` so paths come only from `staged_files` / `commit_paths`, not from `diffs/`.

`staged_files` always contains **every** staged entry (`path`, `status`, `commit_paths`), so no deletion is ever hidden. When building the plan by hand, copy `path` (and for renames use the new path in `files`; `commit_paths` lists both sides for `execute --yes-plan`).

By default `collect` runs `git add -A` first — so a human invoking the skill on a dirty tree gets everything staged automatically. Pass `--no-add` when the caller has already curated the staging area (e.g. an upstream agent staged only the files relevant to the change in progress) and that selection must be preserved. With `--no-add` the index is read as-is; if nothing is staged the result is still `status: "clean"`.

### `validate`

Returns errors like `INVALID_MESSAGE_FORMAT`, `FILE_NOT_STAGED`, `STAGED_BUT_UNASSIGNED`, `DUPLICATE_FILE_ACROSS_GROUPS`. The agent fixes the plan and re-runs. After 3 attempts, surface `## ⚠️ Could not validate the plan` and call `cleanup`.

### `execute`

**Default:** `execute --temp-dir <path> --confirm --yes-plan` after `prepare` (or after legacy `validate` ok). `--yes-plan` expands rename/delete paths from `staging-manifest.json` written at prepare/collect time — it does **not** call `git diff --cached` again. Use only while the index is unchanged since that snapshot. If staging changed (unstage, new `git add`, option 6), run `cleanup`, then `prepare` again — never `--yes-plan` on a stale manifest.

Without `--yes-plan`, the tool re-reads the index at commit time (older behavior; more ways for plan vs index to diverge).

With `--confirm`: wipes `temp_dir` on return (success or failure). On mid-batch failure, rolls back the batch (soft reset). On success, returns `author`, `branch`, `remote_info`, and `yes_plan: true` when applicable.

### `push`

Arguments come strictly from the prior payload: `--remote` = `remote_info.upstream_remote` (or `remotes[0].name` when no upstream), `--branch` = `branch`, `--set-upstream` when `has_upstream: false`. Returns `status: "ok"` (exit `0`) or `"failed"` (exit `50`, with `git_stderr` verbatim). Never retries automatically. Call only after explicit user approval and never when `has_remote: false`.

### `cleanup`

Idempotent — returns `status: "noop"` when `temp_dir` no longer exists.

### `set-author`

Writes `user.name` and `user.email` to the **local repo config** (`.git/config`), not global. Returns the new `author` so the agent can refresh the plan banner. No staging side-effects — the existing plan stays valid.

### `create-branch`

Validates the name with `git check-ref-format --branch`, refuses if the branch already exists, then runs `git checkout -b <name>`. Never pushes. Returns the new `branch` so the agent can refresh the plan banner. No staging side-effects.

### `unstage`

Pure git op: removes the given paths from the index via `git rm --cached --quiet --`. Pattern selection, `.gitignore` reading, and `.gitignore` editing all live on the agent side — they are text/judgment work, not deterministic git plumbing. Returns:

```json
{
  "status": "ok",
  "unstaged": ["node_modules/x.js", "app.log"],
  "failed": []
}
```

`status` becomes `"partial"` when any path failed; each failure carries `git_stderr`. After unstaging, the agent MUST `cleanup` the old `temp_dir` and re-run `prepare` (not legacy `collect` alone) so plan + manifest match the new index.

## Plan template

On the **default path**, `prepare` already writes this to `plan_path`. On the **legacy path**, the agent writes it after `collect`:

```json
{
  "version": 1,
  "groups": [
    {
      "id": 1,
      "message": "feat: add user profile caching",
      "files": [
        "src/cache/profileCache.js",
        "src/services/profileService.js"
      ]
    },
    {
      "id": 2,
      "message": "test: add profile cache tests",
      "files": ["tests/profileCache.test.js"]
    }
  ]
}
```

**Grouping rules.** Every staged file in exactly one group. `D` goes with the semantic change that justifies it (usually the same group as its replacement). `R` uses only the new path in `files` (`commit_paths` in the manifest still lists old + new for `execute --yes-plan`). Prefer granular commits by concern (config, feature, tests, docs). On the legacy path, never type paths from memory — copy from `staged_files` / `commit_paths`.

**No empty groups.** Never emit a group with an empty `files` array. If a concern has no staged file, do not create the group at all. The number of groups can never exceed the number of staged files. **Every staged `D` path is staged and MUST be assigned to a group** — the change that removes or replaces it. Deletions are never optional and never left unassigned, even when `collect` reports them with `diff_file: null`. The validator rejects empty groups (`EMPTY_FILE_LIST`) and unassigned staged files (`STAGED_BUT_UNASSIGNED`); a plan that trips either is a bug to fix before re-validating, not a state to present.

**Message format.** Shape: `<type>[!]: <description>`. **No scope** — the validator rejects `feat(scope):` by policy; convey the affected area in the description (`feat: add user profile caching`). `!` (breaking change marker) is allowed right after the type (`feat!: drop support for Node 14`). Single-line description, ≤ max length (default `72`).

## Approval UX

### AskQuestion split (HARD RULE)

When `AskQuestion` (or an equivalent structured question tool) is available, **never** put the commit plan, push context, skill banner, tables, or warnings inside the tool call. The tool UI is compact — duplicating the full report there breaks layout and hides the options.

**Two-channel delivery — always in this order:**

1. **Chat message (required first)** — render the full report: `# 📦 git-commit` banner, `## Commit plan`, author/branch meta, group tables, line counts, no-remote warnings, `## Push?` context (branch → upstream, ahead/behind), `.gitignore` candidates table, etc.
2. **`AskQuestion` (options only)** — a one-line `prompt`, optional short `title`, and `options` whose labels are the menu choices. Nothing else.

**Approval — AskQuestion shape:**

| Field | Content |
|-------|---------|
| `prompt` | One short sentence, e.g. `How do you want to proceed with this commit plan?` |
| `title` | Optional, e.g. `git-commit approval` |
| `options` | Choice labels only — e.g. `Approve and execute (commit only)`, `Approve, commit and push`, … |

Do **not** prefix options with numbers (`1.`, `2.`) — the tool renders its own UI.

**Push (after commit, option 1 path) — AskQuestion shape:**

| Field | Content |
|-------|---------|
| `prompt` | One short sentence, e.g. `Push these commits now?` |
| `options` | `Push to <upstream>`, `Skip (I'll push manually later)` |

The branch/upstream line and ahead/behind counts stay in the **chat** `## Push?` block only.

**`.gitignore` candidates (option 6 sub-flow) — AskQuestion shape:**

| Field | Content |
|-------|---------|
| `prompt` | e.g. `Apply which .gitignore patterns?` |
| `options` | `Apply all`, `Apply selected patterns`, `Cancel` |

The candidates table stays in chat only.

**Forbidden inside AskQuestion `prompt`, `title`, or option labels:** `# 📦 git-commit`, `## Commit plan`, `## Push?`, file/status tables, blockquoted commit messages, author/branch meta, diff stats, warning blockquotes, markdown headings beyond what the tool needs.

**Fallback without AskQuestion:** append the numbered approval or push list to the same chat message that carries the plan (single message, no tool call).

### Plan template (what the user sees)

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
|   A    | `path/to/file`   |
|   M    | `path/to/other`  |

`+X / −Y lines`
```

**Meta block (two plain lines above `---`).**

- `Author: <name> <<email>>` — git-log shape, from `prepare.preflight.author` (or legacy `preflight.author`). No blockquote, no emoji.
- `Branch: <branch>` — local branch only, from `prepare.preflight.branch`. No upstream arrow, no "no upstream yet" note, no timestamp.
- Any other topology fact surfaces as a standalone warning below the groups (see next).

If `author` is `null` (neither `user.name` nor `user.email` configured), replace the entire plan with a `## ⚠️ Git author not configured` notice and stop until the user sets them.

**No-remote warning.** When `preflight.remote_info.has_remote: false` (from `prepare` or legacy `preflight`), append immediately before the approval buttons:

```markdown
---

> ⚠️ This repository has no remote configured — the push step will be skipped after commit.
```

When `has_remote: true`, emit no warning here — the push prompt after commit will say everything needed.

### Approval prompt

Prefer `AskQuestion` for the menu **after** the plan is already visible in chat (see § AskQuestion split). The tool carries **only** the short prompt and option labels below — not the plan header, tables, or banner.

Option labels for `AskQuestion` (no leading numbers):

- Approve and execute (commit only)
- Approve, commit and push _(omit when `has_remote: false`)_
- Adjust messages or grouping
- Change author (name and email)
- Create new branch before commit
- Update `.gitignore` and unstage matching files
- Cancel

**Fallback** — when no structured question tool exists — append a numbered list to the same chat message that carries the plan:

```markdown
### Approval

1. Approve and execute (commit only)
2. Approve, commit and push
3. Adjust messages or grouping
4. Change author (name and email)
5. Create new branch before commit
6. Update `.gitignore` and unstage matching files
7. Cancel
```

**Option 2 is conditional.** Show `Approve, commit and push` only when `preflight.remote_info.has_remote: true`. When `has_remote: false`, omit option 2 entirely and renumber the rest 2–6 — the menu becomes the six-entry list (`Approve and execute`, `Adjust messages or grouping`, `Change author`, `Create new branch before commit`, `Update .gitignore`, `Cancel`); there is nothing to push to.

Semantics:

- **Option 1 — Approve and execute (commit only):** run `execute --confirm`, report commits, then follow the normal **Push UX** (a separate push prompt, when `has_remote: true`).
- **Option 2 — Approve, commit and push:** run `execute --confirm`; on success **skip the push prompt** and call `push` directly, sourcing `--remote` / `--branch` / `--set-upstream` from the `execute` success payload via the **Push UX → Selection rules** (no new logic). Then render the Push UX after-push block (success or failure). On `execute` failure do **not** push — surface the failure/rollback block as usual.
- **Options 3 and 7** keep their previous semantics (Adjust re-plans then re-validates; Cancel aborts). **Options 4, 5 and 6** mutate state, then **always return to this same approval prompt** (see "Adjustment flows" below).

Only an explicit approve choice (option 1, option 2, "approve", "yes") proceeds to `execute`.

## Adjustment flows (options 3–6)

Every chat message inside these flows still wears the `# 📦 git-commit` banner. Each option ends by re-displaying the plan in **chat** and the approval menu via **`AskQuestion` options only** (see § AskQuestion split) — never by jumping to `execute`.

### Option 3 — Adjust messages or grouping

1. Apply the user's requested change to the plan (reword a message, split, merge, or re-assign files). Keep every staged file in exactly one group; never create an empty group. Copy paths only from the last `prepare`/`collect` payload (`plan`, `staged_files[].path`, `staged_files[].commit_paths`).
2. Overwrite the plan at the same `plan_path`. The existing `temp_dir`, `staging-manifest.json`, and git index are untouched.
3. **Staging unchanged → only `validate --temp-dir <temp_dir>`** (max 3 attempts). **Do not** run `collect` or `prepare` again — the manifest and index are still valid for `execute --yes-plan`.
4. On `status: ok`, re-display the plan in chat and the approval menu via `AskQuestion` (options only).

Presenting an adjusted plan without a passing `validate` is forbidden. Re-running `prepare`/`collect` here without an index change wastes tool calls and replaces `staging-manifest.json` unnecessarily.

### Option 4 — Change author

1. Ask the user for the new `name` and `email` (single prompt; accept `Name <email>` or two short lines).
2. Run `set-author --name <N> --email <E>`. The payload returns the new `author`.
3. Rebuild the plan in chat using the new `author` (the `branch` and groups stay unchanged) and re-display the approval menu via `AskQuestion` (options only).

The existing `temp_dir` and plan stay valid — staging is untouched.

### Option 5 — Create new branch before commit

1. Ask the user for the branch name.
2. Run `create-branch --name <N>`.
3. On error (`INVALID_NAME`, `BRANCH_EXISTS`, `CHECKOUT_FAILED`), surface a `## ⚠️ Could not create branch` block with the reason and return to the approval menu — **do not** retry without user input.
4. On success, rebuild the plan in chat using the new `branch` (carry the existing `author`) and re-display the approval menu via `AskQuestion` (options only).

Staging is untouched, so `temp_dir` and plan remain valid.

### Option 6 — Update `.gitignore`

The agent owns every step except the final `git rm --cached`. Pattern selection is judgment work — there is no built-in heuristic; the agent reasons over the staged file list and the project layout.

1. Read the current `.gitignore` (if present) via the agent's filesystem tool.
2. Inspect `staged_files` from the most recent `collect` payload — focus on `A` entries (new files; `M`/`D`/`R` are already tracked and need a separate `git rm --cached` workflow that this option does not handle).
3. From the staged paths and the repo's project signals (e.g. `package.json` → Node, `pyproject.toml`/`requirements.txt` → Python, `Cargo.toml` → Rust, `go.mod` → Go, etc.), propose `.gitignore` patterns and the matching paths to the user. Use the standard skill format:

   ```markdown
   # 📦 git-commit

   ## .gitignore candidates

   | Pattern | Reason | Matching paths |
   |---------|--------|----------------|
   | `node_modules/` | Node.js dependencies | `app/node_modules/index.js` (+12 more) |
   | `.env` | Environment secrets | `.env` |

   AskQuestion options (chat carries the table above):
   - Apply all
   - Apply selected patterns
   - Cancel
   ```

   If nothing in the staging area looks ignorable, surface `## ✅ No .gitignore candidates found` and return to the approval menu via `AskQuestion` (options only).

4. On `Cancel`, return to the approval menu with the original plan untouched.
5. On apply (all or selected):
   1. Edit `.gitignore` in the repo root via the agent's `Write`/`Edit` tool. Append new patterns (deduplicated against existing entries) under a `# Added by git-commit skill` marker. Create the file if it does not exist.
   2. Compute the list of staged `A` paths that the new patterns now cover (the agent already knows these from step 3 — no extra git invocation needed).
   3. Call `unstage --path <p1> --path <p2> …` with that list. `unstage` runs `git rm --cached` for each path and returns `unstaged` / `failed`.
6. Surface a confirmation block:

   ```markdown
   # 📦 git-commit

   ## ✅ .gitignore updated

   Added patterns: `node_modules/`, `.env`
   Unstaged paths: 13
   ```

   When `failed` is non-empty, list those paths with their `git_stderr` under a `> ⚠️ Some paths could not be unstaged.` blockquote.
7. Run `cleanup --temp-dir <old_temp_dir>`, then `prepare` (picks up the modified `.gitignore` via `git add -A` unless `--no-add`).
8. Re-display the refreshed plan in chat and the approval menu via `AskQuestion` (options only).

If `prepare` returns `status: "clean"` after the changes (everything was unstaged and only the empty `.gitignore` remained), surface `## ⚠️ Nothing left to commit after .gitignore update` and stop.

## Push UX

After `execute --confirm` succeeds, the success payload drives the next step. **If the user chose menu option 2 (Approve, commit and push), there is no push prompt** — push runs automatically via the Selection rules below, then the after-push block is rendered. The prompt described here applies only to menu option 1 (commit only):

- `has_remote: false` → no push prompt. The flow ends at the commit-summary banner (which already carries the no-remote notice).
- `has_remote: true` → emit a second **chat** message with the push context block, then `AskQuestion` with a one-line prompt and push/skip options only (see § AskQuestion split). `has_upstream` state is never surfaced as a warning; it only decides whether `push` is called with `--set-upstream`.

### Selection rules

- **Remote**: prefer `remote_info.upstream_remote`; otherwise `remotes[0].name` (usually `origin`). With multiple remotes and no upstream, add a third option asking which to use — never invent a name.
- **Branch**: always the `branch` from the previous payload.
- `--set-upstream`: pass when `has_upstream: false`.

### Push prompt — with upstream

**Chat message** (context only — not inside `AskQuestion`):

```markdown
# 📦 git-commit

## Push?

`<branch>` → `<upstream>` · **<ahead> commits** ahead · behind **<behind>**
```

When `ahead`/`behind` is absent (shallow clone, unfetched ref), render just `` `<branch>` → `<upstream>` `` without the counts — never invent zeros.

**AskQuestion** (immediately after the chat block):

- `prompt`: `Push these commits now?`
- options: `Push to <upstream>`, `Skip (I'll push manually later)`

### Push prompt — without upstream

**Chat message:**

```markdown
# 📦 git-commit

## Push?

`<branch>` will be pushed to `<remote>/<branch>` (new upstream).
```

**AskQuestion:**

- `prompt`: `Push and set upstream?`
- options: `Push to <remote>/<branch>`, `Skip (I'll push manually later)`

Call `push` with `--set-upstream`. **Fallback without AskQuestion:** append a numbered list (`1. Push…`, `2. Skip…`) to the same chat message.

### After push — success (already-tracked branch)

```markdown
# 📦 git-commit

## ✅ Pushed

`<branch>` → `<upstream>` · **<N> commits** pushed
```

`<N>` = `remote_info.ahead` captured from the `execute` success payload (value *before* push). If unavailable, drop the `· **N commits** pushed` segment. Do **not** echo `git_stderr` on success — the header already says everything, the SHAs were in the preceding `## ✅ Commits created` table, and the URL may carry embedded credentials.

### After push — success (new branch / first-time upstream)

```markdown
# 📦 git-commit

## ✅ Pushed

`<branch>` → `<remote>/<branch>` · new branch · upstream set
```

Same rule: no verbatim `git_stderr` on success.

### After push — failure

```markdown
# 📦 git-commit

## ❌ Push failed

`<branch>` → `<remote>/<branch>`

\`\`\`
<git_stderr verbatim>
\`\`\`

### Suggested remediation

<one short paragraph inferred from git_stderr>
```

Typical remediations:

- Non-fast-forward (`! [rejected] … (fetch first)`): `git fetch <remote>` then `git rebase <remote>/<branch>` in a shell; rerun the skill.
- Auth / credentials: re-authenticate (`gh auth login`, `git credential fill`, …); rerun.
- Protected branch / policy rejection: open a pull request instead.

On failure the verbatim `git_stderr` is essential — always include it. If the first line is `To https://user:token@host/...`, redact the credential segment before pasting (`To https://<redacted>@host/...`).

### After push — skipped

```markdown
# 📦 git-commit

## ⚠️ Push skipped

Commits stay local on `<branch>`. Push manually with `git push <remote> <branch>` when ready.
```

## Output style rules

- `# 📦 git-commit` H1 on every message (banner rule).
- Emojis allowed **only** here:
  - `📦` in the H1 banner.
  - H2 status headers: `✅` (success outcomes), `❌` (failures), `⚠️` (warnings — validation exhausted, pre-flight error, `Push skipped`, `Git author not configured`, and the `> ⚠️` no-remote notice inside the plan).
- No emojis anywhere else — no 👤 / 📄 / 🌿 decorations, no per-row emojis in tables, no emojis in prose or progress lines.
- Use `A/M/D/R` letters (never emojis) for git status in tables.
- Tables for file lists, SHAs, counts. Blockquotes for commit messages. Backticks for paths/SHAs/commands/flags. Numbered lists for user choices only in **fallback** mode (no `AskQuestion`).
- **`AskQuestion` never carries the plan or push report** — see § AskQuestion split. Chat first; tool second with one-line prompt + option labels only.
- The only permitted mid-flow narration is "Analyzing <N> files staged…" when `collect.total_staged ≥ threshold`. No other progress text.
- Never show diffs to the user — `diffs_dir` is agent-internal reasoning only.
- Never render a group with zero files in the displayed plan. The plan is only presented after `validate` returns `status: ok` — a passing validate guarantees no empty group exists, so an empty group on screen means the plan was presented without (re-)validating, which is forbidden.

## Rendered examples

### Commit summary — with remote, then push prompt

```markdown
# 📦 git-commit

## ✅ Commits created

| # | SHA | Message |
|:-:|-----|---------|
| 1 | `a1b2c3d` | feat: add user profile caching |
| 2 | `e4f5g6h` | test: add profile cache tests |

**2 commits** · **3 files** · **+229 / −48** · `2026-04-22T14:30:15+00:00`
```

Emit no blockquote after the stats line when `has_remote: true` — the push context comes next in chat, then `AskQuestion` with push/skip options only.

```markdown
# 📦 git-commit

## Push?

`main` → `origin/main` · **2 commits** ahead · behind **0**
```

AskQuestion: `prompt` = `Push these commits now?` · options = `Push to origin/main`, `Skip (I'll push manually later)`.

### Commit summary — without remote

Same table + stats as above, plus a closing warning and no push prompt:

```markdown
**1 commit** · **2 files** · **+229 / −48** · `2026-04-22T14:30:15+00:00`

> ⚠️ No remote configured — commits stay local on `main`.
```

### Failure with rollback

```markdown
# 📦 git-commit

## ❌ Commit 2 of 2 failed

Hook `eslint` rejected `test: add profile cache tests`:

```
tests/profileCache.test.js
  12:5  error  'expect' is not defined  no-undef
```

Rollback done: 1 commit reverted, stage preserved. Temp dir cleaned.

### Next steps

1. Fix the ESLint error at `tests/profileCache.test.js:12`
2. Run the skill again
```

## Gotchas

- Commit dates have **1-second resolution** — synchronized batches share the same second; use `git log --topo-order` for correct ordering.
- `git diff --cached --find-renames=50` can emit `R`+`M` duplicates for one path — the tool dedups by new path; don't double-count.
- **Renames and deletions:** `git commit -- <paths>` only records listed paths. The tool expands renames to `[old_path, new_path]` on `execute`, validates every staged change via canonical paths (`collect` also returns `commit_paths` per entry), and flags unstaged deletions with `STAGED_BUT_UNASSIGNED` when the deleted path is missing from the plan.
- `git commit -- <files>` requires the `--` separator before paths.
- Pre-commit hooks may mutate files mid-batch. On a later failure, rollback (soft reset) reverts everything and preserves staging.
- Empty repo: `HEAD~N` doesn't exist; rollback falls back to `git update-ref -d HEAD` (handled by the tool).
- Signed commits (`commit.gpgsign=true`) may prompt for a password — the tool won't disable signing; configure an agent-friendly GPG setup if batches hang.
- All paths travel via `subprocess` argv — Unicode/spaces/`$`/backticks are safe by construction.
- `temp_dir` sits in the **OS temp area**, outside the user's repo — no risk of accidental commit. `execute --confirm` wipes it (success or failure); dry runs and pre-loop errors preserve it; cancel / validation-exhausted require explicit `cleanup`. Cleanup is irreversible — copy anything to keep before approving.
- `tempfile.mkdtemp()` is fresh per call — parallel invocations never collide on disk. Trade-off: the path isn't derivable, so capture `temp_dir` from `collect` and carry it through every subcommand.
- **Remote URLs may carry embedded credentials** (`https://user:token@host/…`) — never display `remotes[].url` in chat; show only `remotes[].name`.
- **`ahead`/`behind` may be absent** (shallow clones, unfetched refs) — render the "with upstream" prompt without the counts suffix; never invent zeros.
- **`push` failures vary** (non-fast-forward, auth, protected branch, server-side hook) — paste `git_stderr` verbatim (credentials redacted) and suggest the obvious fix; never retry automatically.

## Hard rules

- Never ask the user to run git commands. Never call git directly from the agent — every git operation, including `push`, goes through `scripts/commit_tool.py`.
- Never use `--no-verify`. Hooks must run.
- Never mention AI, Cursor, Antigravity, or `Co-authored-by` in commit messages.
- Every commit message must match `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)!?: .{1,72}$`. **Scope (`feat(scope):`) is rejected by the validator.**
- Every staged file must belong to exactly one group.
- Commit descriptions follow the Configuration's `Commit description language` (default `en`); the `<type>[!]:` prefix is always English.
- Never invent remote or branch names for `push` — always source them from `remote_info`/`branch` in the previous payload.
- Never push without explicit user approval on the push prompt.
- Never put the commit plan, push context, tables, or skill banner inside `AskQuestion` — chat carries the report; the tool carries a one-line prompt and option labels only (see § AskQuestion split).

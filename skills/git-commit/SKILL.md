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

**Silence.** Never narrate tool calls in chat — the IDE already shows them. Forbidden openers include "I will start…", "Checking…", "Running preflight…", "Collecting…", "Validating…", "Analyzing changes…". The plan-fix-revalidate loop is silent; surface it only if it fails after 3 attempts. Inside an adjustment or cancel flow (options 2/3 below), every agent turn still wears the banner — silence applies only to pure tool-call narration.

**Large staging narration.** If `collect` returns `total_staged` ≥ the Slow-collect threshold (see Configuration), emit exactly one line before the plan:

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

Each step is one Python invocation. Steps 1–4, 6 and 9 are silent; the user only sees 5 (plan), 7 (commit result), 8 (push prompt, when applicable) and 10 (push result).

- [ ] 1. `preflight` — capture `author`, `branch`, `remote_info`.
- [ ] 2. `collect` — capture `temp_dir` and `plan_path`.
- [ ] 3. Write the commit plan to `plan_path`.
- [ ] 4. `validate --temp-dir <temp_dir>` (loop until `status: ok`).
- [ ] 5. Present the plan; wait for approval.
- [ ] 6. On approval: `execute --temp-dir <temp_dir> --confirm`.
- [ ] 7. Report commits.
- [ ] 8. If `remote_info.has_remote: true`, present the push prompt. Otherwise stop.
- [ ] 9. On push approval: `push --remote <name> --branch <name> [--set-upstream]`.
- [ ] 10. Report push result (or skip).

**Where commands run.** `scripts/commit_tool.py` lives in this skill's folder — invoke it via the skill's absolute path with the **user's repo root as CWD** (where `.git/` lives). `collect` creates a fresh isolated directory via `tempfile.mkdtemp()` in the OS temp area (e.g. `%TEMP%\git-commit-…` on Windows, `/tmp/git-commit-…` on POSIX) and returns it as `temp_dir`. Carry that exact path through `--temp-dir <path>` in every subsequent subcommand. Never change CWD mid-flow; never guess `temp_dir`.

**Cleanup responsibilities.**

- Successful `execute --confirm` (commit *or* rollback) wipes `temp_dir`; payload reports `temp_cleaned: true` (or `false` on lock/permission).
- Dry runs (no `--confirm`) preserve `temp_dir` so the caller can retry.
- `execute` pre-loop errors (missing plan, bad JSON/schema) return `status: "error"` and preserve `temp_dir` — recoverable context is kept.
- The agent MUST call `cleanup --temp-dir <temp_dir>` whenever the flow is abandoned between `collect` and a clean `execute --confirm` (cancel on approval, validate exhausted after 3 tries, any other error between them).
- Agent may force-remove `temp_dir` as a fallback when `temp_cleaned: false` after success.
- Never re-read files under `temp_dir` after success.

## Commands

Every subcommand emits a JSON result on stdout and structured events on stderr (JSONL).

| Subcommand | Flags | Purpose | Notable exit codes |
|---|---|---|---|
| `preflight` | — | Validate repo + capture identity and remote topology | `0` ok · `10/11` error · `12` clean |
| `collect` | `[--max-files N] [--max-diff-lines-per-file N] [--no-add]` | `git add -A` (unless `--no-add`), write per-file diffs, return `temp_dir`/`plan_path`/`diffs_dir` | `0` ok · `12` clean (nothing staged) |
| `validate` | `--temp-dir <path>` | Check plan JSON vs regex + staging | `0` ok · `20` invalid |
| `execute` | `--temp-dir <path> [--confirm] [--natural-timestamps]` | Dry-run unless `--confirm`; all commits share one timestamp (1-second resolution) | `0` ok · `30` commit failed · `31` pre-loop error |
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

### `collect`

On staged changes, writes under `temp_dir`: `commit-plan.json` (the `plan_path` the agent must write) and `diffs/` (per-file truncated diffs, agent-only). When nothing is staged, returns `status: "clean"` (exit `12`) without creating a dir.

By default `collect` runs `git add -A` first — so a human invoking the skill on a dirty tree gets everything staged automatically. Pass `--no-add` when the caller has already curated the staging area (e.g. an upstream agent staged only the files relevant to the change in progress) and that selection must be preserved. With `--no-add` the index is read as-is; if nothing is staged the result is still `status: "clean"`.

### `validate`

Returns errors like `INVALID_MESSAGE_FORMAT`, `FILE_NOT_STAGED`, `STAGED_BUT_UNASSIGNED`, `DUPLICATE_FILE_ACROSS_GROUPS`. The agent fixes the plan and re-runs. After 3 attempts, surface `## ⚠️ Could not validate the plan` and call `cleanup`.

### `execute`

With `--confirm`: once inside the commit loop, wipes `temp_dir` on return (success or failure) and sets `temp_cleaned` in the payload. On mid-batch failure, rolls back every commit in the batch (soft reset) before cleaning — staging is preserved for a retry. Rollback state and SHAs live in the payload only (`commits_done`, `rollback`). On success, the payload re-reads and returns `author`, `branch` and `remote_info` (same shape as `preflight`) so the agent can drive the commit banner and decide on the push prompt. Pre-loop errors (missing plan, invalid JSON, bad schema) return `status: "error"` and preserve `temp_dir` — prefer running `validate` first.

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

`status` becomes `"partial"` when any path failed; each failure carries `git_stderr`. After unstaging, the agent MUST `cleanup` the old `temp_dir` and re-run `collect` to rebuild the plan with the new staging area.

## Plan template

Write this to the `plan_path` returned by `collect` (`<temp_dir>/commit-plan.json`):

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

**Grouping rules.** Every staged file in exactly one group. `D` goes with the semantic change that justifies it (usually the same group as its replacement). `R` uses only the new path. Prefer granular commits by concern (config, feature, tests, docs).

**Message format.** Shape: `<type>[!]: <description>`. **No scope** — the validator rejects `feat(scope):` by policy; convey the affected area in the description (`feat: add user profile caching`). `!` (breaking change marker) is allowed right after the type (`feat!: drop support for Node 14`). Single-line description, ≤ max length (default `72`).

## Approval UX

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

- `Author: <name> <<email>>` — git-log shape, from `preflight.author`. No blockquote, no emoji.
- `Branch: <branch>` — local branch only, from `preflight.branch`. No upstream arrow, no "no upstream yet" note, no timestamp.
- Any other topology fact surfaces as a standalone warning below the groups (see next).

If `author` is `null` (neither `user.name` nor `user.email` configured), replace the entire plan with a `## ⚠️ Git author not configured` notice and stop until the user sets them.

**No-remote warning.** When `preflight.remote_info.has_remote: false`, append immediately before the approval buttons:

```markdown
---

> ⚠️ This repository has no remote configured — the push step will be skipped after commit.
```

When `has_remote: true`, emit no warning here — the push prompt after commit will say everything needed.

### Approval prompt

Prefer the IDE's structured question tool (`AskQuestion` in Cursor, `user_input` in Antigravity) with the six options below. Fallback — when no such tool exists — is a numbered list for single-digit answers:

```markdown
### Approval

1. Approve and execute
2. Adjust messages or grouping
3. Change author (name and email)
4. Create new branch before commit
5. Update `.gitignore` and unstage matching files
6. Cancel
```

Only explicit approval (option 1 / "approve" / "yes") proceeds to `execute`. Options 2 and 6 keep their previous semantics. Options 3, 4 and 5 mutate state, then **always return to this same approval prompt** (see "Adjustment flows" below).

## Adjustment flows (options 3–5)

Every chat message inside these flows still wears the `# 📦 git-commit` banner. Each option ends by re-displaying the plan banner and the approval menu — never by jumping to `execute`.

### Option 3 — Change author

1. Ask the user for the new `name` and `email` (single prompt; accept `Name <email>` or two short lines).
2. Run `set-author --name <N> --email <E>`. The payload returns the new `author`.
3. Rebuild the plan banner using the new `author` (the `branch` and groups stay unchanged) and re-display the approval menu.

The existing `temp_dir` and plan stay valid — staging is untouched.

### Option 4 — Create new branch before commit

1. Ask the user for the branch name.
2. Run `create-branch --name <N>`.
3. On error (`INVALID_NAME`, `BRANCH_EXISTS`, `CHECKOUT_FAILED`), surface a `## ⚠️ Could not create branch` block with the reason and return to the approval menu — **do not** retry without user input.
4. On success, rebuild the plan banner using the new `branch` (carry the existing `author`) and re-display the approval menu.

Staging is untouched, so `temp_dir` and plan remain valid.

### Option 5 — Update `.gitignore`

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

   1. Apply all
   2. Apply selected patterns (ask user which)
   3. Cancel
   ```

   If nothing in the staging area looks ignorable, surface `## ✅ No .gitignore candidates found` and return to the approval menu.

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
7. Run `cleanup --temp-dir <old_temp_dir>`, then `collect` (the next `git add -A` inside `collect` will pick up the modified `.gitignore` automatically), then write the new plan to the new `plan_path`, then `validate` (loop up to 3 attempts).
8. Re-display the refreshed plan banner and the approval menu.

If `collect` returns `status: "clean"` after the changes (everything was unstaged and only the empty `.gitignore` remained), surface `## ⚠️ Nothing left to commit after .gitignore update` and stop.

## Push UX

After `execute --confirm` succeeds, the success payload drives the next step:

- `has_remote: false` → no push prompt. The flow ends at the commit-summary banner (which already carries the no-remote notice).
- `has_remote: true` → emit a second message with the push prompt. `has_upstream` state is never surfaced as a warning; it only decides whether `push` is called with `--set-upstream`.

### Selection rules

- **Remote**: prefer `remote_info.upstream_remote`; otherwise `remotes[0].name` (usually `origin`). With multiple remotes and no upstream, add a third option asking which to use — never invent a name.
- **Branch**: always the `branch` from the previous payload.
- `--set-upstream`: pass when `has_upstream: false`.

### Push prompt — with upstream

```markdown
# 📦 git-commit

## Push?

`<branch>` → `<upstream>` · **<ahead> commits** ahead · behind **<behind>**

1. Push to `<upstream>`
2. Skip (I'll push manually later)
```

When `ahead`/`behind` is absent (shallow clone, unfetched ref), render just `` `<branch>` → `<upstream>` `` without the counts — never invent zeros.

### Push prompt — without upstream

```markdown
# 📦 git-commit

## Push?

`<branch>` will be pushed to `<remote>/<branch>` (new upstream).

1. Push to `<remote>/<branch>`
2. Skip (I'll push manually later)
```

Call `push` with `--set-upstream`. Prefer the IDE's structured question tool over the numbered list, same as the approval step.

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
- Tables for file lists, SHAs, counts. Blockquotes for commit messages. Backticks for paths/SHAs/commands/flags. Numbered lists for user choices (single-digit answers).
- The only permitted mid-flow narration is "Analyzing <N> files staged…" when `collect.total_staged ≥ threshold`. No other progress text.
- Never show diffs to the user — `diffs_dir` is agent-internal reasoning only.

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

Emit no blockquote after the stats line when `has_remote: true` — the push prompt comes next and carries the destination information.

```markdown
# 📦 git-commit

## Push?

`main` → `origin/main` · **2 commits** ahead · behind **0**

1. Push to `origin/main`
2. Skip (I'll push manually later)
```

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

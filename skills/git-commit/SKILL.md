---
name: git-commit
description: |
  Agent-native skill for producing semantic, grouped commits with
  synchronized timestamps. The agent orchestrates; scripts/commit_tool.py
  runs git deterministically. The only user interaction point is the
  commit plan approval.
---

# git-commit

The agent orchestrates. Python executes git. The user interacts exactly once,
to approve the plan.

## Banner and silence rules

These two rules work together: silence controls **when** the skill speaks;
banner controls **how** it speaks.

### Banner rule

**Every chat message this skill sends to the user starts with `# git-commit`
as H1.** The banner marks every interaction as part of the skill's flow, so
the user always knows they are inside it.

### Silence rule

The agent MUST NOT emit chat messages between tool invocations. The IDE
already shows tool calls in its timeline — do not echo them with phrases
like:

- "I will start the git-commit process..."
- "Checking the scripts directory..."
- "Running the preflight check..."
- "Collecting staged files..."
- "Validating the commit plan..."
- "Analyzing the changes..."

None of those. The plan-fix-revalidate loop is also silent; only surface to
the user if it fails after 3 attempts.

**Combined:** if the skill has something meaningful to tell the user, it
says it with a banner. Otherwise, it stays silent.

### Messages the skill is expected to send (each with banner)

1. **Opening (optional).** Only when needed before the plan: slow-collect
   narration, early exit for clean tree, pre-flight error. Skipped entirely
   when the plan is ready immediately.
2. **Plan + approval.** `# git-commit` + `## Commit plan` + file tables +
   the 3 numbered options.
3. **Interactive follow-up (every turn inside an adjustment or cancel
   flow).** Examples:
   - After option 2 (Adjust): "What would you like to change?"
   - After option 3 (Cancel): confirmation that the flow was cancelled.
   - Any further back-and-forth while refining the plan before re-approval.
4. **Final result.** One of:
   - `## ✅ Commits created` (success)
   - `## ❌ Commit N of M failed` (execution failure)
   - `## ⚠️ ...` (warnings, validation exhausted, pre-flight error)

### Allowed opening narration (large staging)

If the JSON returned by `collect` has `total_staged` greater than or equal
to the **Slow-collect narration threshold** (see Configuration block), emit
a single short line before the plan:

```
# git-commit

Analyzing <total_staged> files staged…
```

Use the exact number reported in `total_staged`. No table, no bullets, no
per-sub-step breakdown.

<!-- skill-config:start -->
## Configuration

Edit these defaults inline to change behavior. The agent must honor them.

- **Commit description language:** `en`
  _(Allowed: any ISO 639-1 code. The `<type>[(<scope>)]:` prefix is always English regardless.)_
- **Allowed commit types:** `feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`
- **Max description length:** `72`
- **Sync timestamp by default:** `true`
- **Slow-collect narration threshold:** `30`
  _(Emit the "Analyzing N files staged…" line when `total_staged` from collect is ≥ this number. Raise to a very large value to effectively disable; lower to see the line more often.)_
<!-- skill-config:end -->

## Workflow

Progress checklist (each step is a single Python invocation):

- [ ] 1. `python3 scripts/commit_tool.py preflight`
- [ ] 2. `python3 scripts/commit_tool.py collect` — capture `temp_dir` and `plan_path` from the stdout JSON
- [ ] 3. Write the commit plan to the `plan_path` returned by `collect` (template below)
- [ ] 4. `python3 scripts/commit_tool.py validate --temp-dir <temp_dir>` (loop until `status: ok`)
- [ ] 5. Present the plan to the user and request approval (see "Approval UX")
- [ ] 6. On approval: `python3 scripts/commit_tool.py execute --temp-dir <temp_dir> --confirm`
- [ ] 7. Report created commits (SHAs + messages) in a final banner message

The agent never runs git directly. Steps 1–4 and 6 are silent; the user
only sees messages at steps 5 (plan) and 7 (result).

**Where commands run.** `scripts/commit_tool.py` lives inside this skill's
own folder — invoke it via the skill's absolute path. Every command must
be executed with the **user's repo root as the CWD** (where `.git/` lives)
so that git operations target the correct repository. The working files
of the tool do **not** live inside the user's repo: `collect` creates a
fresh isolated directory in the OS temp area (e.g. `%TEMP%\git-commit-…`
on Windows, `/tmp/git-commit-…` on Linux/macOS) via
`tempfile.mkdtemp()`, and returns its absolute path as `temp_dir` in the
stdout JSON. The agent must carry that exact path through steps 3, 4 and
6 via `--temp-dir <path>`. Do not change the CWD mid-flow and do not
guess the temp path.

**Cleanup.** With `--confirm`, once `execute` enters the commit loop it
wipes `temp_dir` before returning — on success AND on failure — and sets
`"temp_cleaned": true` (or `false` if something was locked) in the
payload. Dry runs (no `--confirm`) preserve `temp_dir` so the caller can
retry. If `execute` fails **before** the commit loop because the plan
file is missing or has bad JSON/schema, it returns
`status: "error"` and preserves `temp_dir` so the agent can fix the
plan and retry — it does not destroy context for a recoverable error.
In every other case where the flow is abandoned before
`execute --confirm` (user cancels on approval, validation exhausts after
3 tries, any other error between `collect` and `execute`), the agent
MUST call `python3 scripts/commit_tool.py cleanup --temp-dir <temp_dir>`
to remove the orphaned directory. If the payload reports success but
the directory still exists (lock, permissions, anything), the agent is
free to remove it as an extra fallback. Never re-read any file under
`temp_dir` after success.

## Commands

### preflight

Checks repo validity, ongoing ops, empty repo, and clean tree. Stdout JSON:

- `status: "ok"` — proceed.
- `status: "clean"` (exit `12`) — inform user, stop.
- `status: "error"` (exit `10` / `11`) — surface message as `## ⚠️` block.

### collect [--max-files N] [--max-diff-lines-per-file N]

Runs `git add -A` and returns staged files. When something is actually
staged, `collect` creates a fresh isolated directory in the OS temp area
via `tempfile.mkdtemp()` and returns it in the stdout JSON:

- `temp_dir`: absolute path to the freshly created directory
- `plan_path`: `<temp_dir>/commit-plan.json` (where the agent must write)
- `diffs_dir`: `<temp_dir>/diffs/` (per-file truncated diffs)

The agent must capture `temp_dir` and pass it to every subsequent
subcommand via `--temp-dir`. Never read or show the diff files to the
user — they are agent-internal context for building the plan.

If nothing is staged after `git add -A`, `collect` returns
`status: "clean"` (exit `12`) without creating any directory.

### validate --temp-dir <temp_dir>

Validates `<temp_dir>/commit-plan.json` against Conventional Commits
regex and the current staging area. Returns actionable errors like
`INVALID_MESSAGE_FORMAT`, `FILE_NOT_STAGED`, `STAGED_BUT_UNASSIGNED`,
`DUPLICATE_FILE_ACROSS_GROUPS`. The agent fixes the plan and re-runs
validate. After 3 unsuccessful attempts, surface
`## ⚠️ Could not validate the plan` to the user and call `cleanup` to
remove the orphaned temp dir.

### execute --temp-dir <temp_dir> [--confirm] [--natural-timestamps]

Default is dry-run (preserves `temp_dir`). `--confirm` actually commits.
All commits in the batch share the same
`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` (1-second resolution) unless
`--natural-timestamps` is passed.

With `--confirm`, once `execute` enters the commit loop the tool
removes `temp_dir` before returning — on success AND on failure — and
the response payload includes `"temp_cleaned": true` (or `false` if a
lock/permission prevented full removal). On commit failure, the tool
first auto-rolls back any commits that already landed in the batch,
then cleans. The rollback state and commit SHAs are returned only in
the payload (`commits_done`, `rollback`) — no disk persistence.

If `execute` fails **before** the commit loop (missing plan file,
invalid JSON, bad schema), it returns `status: "error"` and preserves
`temp_dir` so the agent can fix the plan and retry with the same
`--temp-dir` path. Prefer running `validate` first to catch these
errors without reaching `execute`.

### cleanup --temp-dir <temp_dir>

Best-effort removal of a temp dir returned by `collect`. Idempotent —
calling it on a path that no longer exists returns `status: "noop"`.
The agent MUST call this when the flow is abandoned between `collect`
and a clean `execute --confirm`:

- User cancels on the approval step.
- `validate` exhausts 3 attempts without reaching `status: "ok"`.
- Any unexpected error after `collect` that prevents reaching the
  commit loop.

## Plan template

Write this to the `plan_path` returned by `collect` (which is
`<temp_dir>/commit-plan.json`):

```json
{
  "version": 1,
  "groups": [
    {
      "id": 1,
      "message": "feat(profile): add user profile caching",
      "files": [
        "src/cache/profileCache.js",
        "src/services/profileService.js"
      ]
    },
    {
      "id": 2,
      "message": "test(profile): add profile cache tests",
      "files": ["tests/profileCache.test.js"]
    }
  ]
}
```

### Grouping rules

- Each staged file MUST appear in exactly one group.
- A deletion (`D`) goes with the semantic change that justifies it
  (usually the same group as its replacement).
- A rename (`R`) uses only the new path.
- Prefer granular commits by concern: config, feature, tests, docs.

## Approval UX

### Presentation template

```markdown
# git-commit

## Commit plan

Synchronized timestamp: `<ISO-8601>`

---

### Group N of M

> `<commit message>`

| Status | File |
|:------:|------|
|   A    | `path/to/file`   |
|   M    | `path/to/other`  |

`+X / −Y lines`
```

Then ask the user to approve using one of:

1. **Preferred (structured):** call the IDE's question tool if it is
   available in the current environment (examples: `AskQuestion` in Cursor,
   `user_input` in Antigravity). Options:
   - "Approve and execute"
   - "Adjust messages or grouping"
   - "Cancel"
2. **Fallback (plain chat):** render a numbered list and instruct the user
   to answer with a single digit:

```markdown
### Approval

1. Approve and execute
2. Adjust messages or grouping
3. Cancel
```

Only explicit approval (option 1 / "approve" / "yes") proceeds to `execute`.

## Output style rules

- Every message the skill sends to the user starts with `# git-commit` H1.
- Never narrate intermediate tool calls in chat (see "Silence rule").
- Emojis are allowed ONLY in H2 headers of these three states:
  - `## ✅ Commits created` — final success
  - `## ❌ Commit N of M failed` — execution failure
  - `## ⚠️ ...` — warnings / validation exhausted / pre-flight error
- No emojis in sub-lines, tables, file status columns, or progress text.
- Use A/M/D/R letters for git status in tables (never emojis).
- Tables for file lists, SHAs, counts.
- Blockquotes for commit messages.
- Inline code (backticks) for paths, SHAs, commands, flags.
- Numbered lists for user choices (single-digit answers).
- The only permitted mid-flow narration is a single-line "Analyzing <N>
  files staged…" when `collect` returns `total_staged` ≥ the threshold in
  Configuration (default `30`). No other progress text.
- NEVER show diffs to the user. The files under `<temp_dir>/diffs/`
  (path comes from `collect`'s `diffs_dir` field) are for the agent's
  own reasoning only.

### Example — success message

```markdown
# git-commit

## ✅ Commits created

| # | SHA | Message |
|:-:|-----|---------|
| 1 | `a1b2c3d` | feat(profile): add user profile caching |
| 2 | `e4f5g6h` | test(profile): add profile cache tests |

2 commits · 3 files · +229/−48 · timestamp `2026-04-22T14:30:15Z`
```

### Example — failure with rollback

```markdown
# git-commit

## ❌ Commit 2 of 2 failed

Hook `eslint` rejected `test(profile): add profile cache tests`:

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

- Git commit dates have **1-second resolution**. With synchronized
  timestamps (default), all commits of a batch share the same second. Use
  `git log --topo-order` for correct ordering regardless of equal times.
- `git diff --cached --find-renames=50` may emit `R` + `M` duplicates for
  the same path. The tool dedups by new path — do not double-count.
- `git commit -- <files>` requires the `--` separator before paths.
- Pre-commit hooks may modify files mid-batch. If a later commit fails,
  rollback reverts everything in the batch (soft reset) so staging is
  preserved for a new attempt.
- Empty repo: `HEAD~N` does not exist. Rollback uses `git update-ref -d HEAD`
  in that case (handled by the tool).
- Signed commits (`commit.gpgsign=true`) may prompt for a GPG password. The
  tool does not disable signing; if a batch hangs on signing, the user
  should configure an agent-friendly GPG setup before re-running.
- All paths go to git via `subprocess` argv list. Unicode, spaces, `$`,
  backticks, and similar characters are safe by construction.
- The temp dir lives in the **OS temp area** (outside the user's repo),
  so there is no risk of it being staged or committed even if the flow
  is interrupted. Any `execute --confirm` that reaches the commit loop
  wipes it on the way out — success OR failure. Dry runs preserve it.
  A pre-loop failure in `execute` (missing plan, invalid JSON/schema)
  also preserves it, so the agent can fix and retry. If the flow is
  abandoned before the commit loop (cancel, validation exhausted), the
  agent must call `cleanup --temp-dir <path>`. Cleanup is irreversible
  — copy anything you want to keep before approving.
- `tempfile.mkdtemp()` creates a new unique directory on each call.
  Parallel invocations in the same repo get separate dirs and never
  collide on disk. The trade-off is that the path is not derivable: the
  agent MUST capture `temp_dir` from `collect`'s stdout and pass it to
  every following subcommand.

## Hard rules

- Never ask the user to run git commands.
- Never call git directly from the agent. Every git operation goes through
  `scripts/commit_tool.py`.
- Never use `--no-verify`. Hooks must run.
- Never mention AI, Cursor, Antigravity, or `Co-authored-by` in commit
  messages.
- Every commit message must match
  `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9][a-z0-9\-]*\))?!?: .{1,72}$`.
- Every staged file must belong to exactly one group.
- Commit descriptions use the language from the `Commit description
  language` field in the Configuration block (default `en`). The
  `<type>[(<scope>)]:` prefix is always English.

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

## Banner and silence rules

These two rules work together: silence controls **when** the skill speaks;
banner controls **how** it speaks.

### Banner rule

**Every chat message this skill sends to the user starts with `# 📦 git-commit`
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
2. **Plan + approval.** `# 📦 git-commit` + `## Commit plan` + meta block
   (two lines: `Author:` and `Branch:`) + file tables + the 3 numbered options.
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
# 📦 git-commit

Analyzing <total_staged> files staged…
```

Use the exact number reported in `total_staged`. No table, no bullets, no
per-sub-step breakdown.

<!-- skill-config:start -->
## Configuration

Edit these defaults inline to change behavior. The agent must honor them.

- **Commit description language:** `en`
  _(Allowed: any ISO 639-1 code. The `<type>[!]:` prefix is always English regardless.)_
- **Allowed commit types:** `feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`
- **Max description length:** `72`
- **Sync timestamp by default:** `true`
- **Slow-collect narration threshold:** `30`
  _(Emit the "Analyzing N files staged…" line when `total_staged` from collect is ≥ this number. Raise to a very large value to effectively disable; lower to see the line more often.)_
<!-- skill-config:end -->

## Workflow

Progress checklist (each step is a single Python invocation):

- [ ] 1. `python3 scripts/commit_tool.py preflight` — capture `author`, `branch`, `remote_info`
- [ ] 2. `python3 scripts/commit_tool.py collect` — capture `temp_dir` and `plan_path` from the stdout JSON
- [ ] 3. Write the commit plan to the `plan_path` returned by `collect` (template below)
- [ ] 4. `python3 scripts/commit_tool.py validate --temp-dir <temp_dir>` (loop until `status: ok`)
- [ ] 5. Present the plan to the user (plan + meta block) and request approval (see "Approval UX")
- [ ] 6. On approval: `python3 scripts/commit_tool.py execute --temp-dir <temp_dir> --confirm`
- [ ] 7. Report created commits (SHAs + messages) in a final banner message
- [ ] 8. If the `remote_info` in the success payload has `has_remote: true`, present the push prompt (see "Push UX"). If `has_remote: false`, stop here.
- [ ] 9. On push approval: `python3 scripts/commit_tool.py push --remote <name> --branch <name> [--set-upstream]`
- [ ] 10. Report push result (or skip) in a final banner message.

The agent never runs git directly. Steps 1–4, 6 and 9 are silent; the
user only sees messages at steps 5 (plan), 7 (commit result), 8 (push
prompt, when applicable) and 10 (push result).

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

Checks repo validity, ongoing ops, empty repo, and clean tree. Also
captures identity + remote topology so the rest of the flow has
everything it needs without re-reading git state. Stdout JSON includes:

- `status` — `"ok"`, `"clean"` (exit `12`), or `"error"` (exit `10`/`11`).
- `branch` — current branch name, or `null` when detached/empty.
- `head` — current HEAD SHA, or `null` on an empty repo.
- `is_empty` — `true` when HEAD does not yet exist.
- `author` — `{ "name", "email" }` from `git config user.*`, or `null`.
- `remote_info` — see below.

`remote_info` shape:

```json
{
  "has_remote": true,
  "remotes": [{"name": "origin", "url": "https://…"}],
  "has_upstream": true,
  "upstream": "origin/main",
  "upstream_remote": "origin",
  "ahead": 0,
  "behind": 0
}
```

When `has_remote` is `false`, only `remotes: []` is present — skip the
push prompt entirely. When `has_remote: true` but `has_upstream: false`,
the push prompt MUST include the `--set-upstream` option.

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

On success, the payload also re-reads identity and remote topology and
includes `author`, `branch` and `remote_info` (same shape as in
`preflight`). The agent uses these to show the final commit banner and
decide whether to offer the push prompt.

If `execute` fails **before** the commit loop (missing plan file,
invalid JSON, bad schema), it returns `status: "error"` and preserves
`temp_dir` so the agent can fix the plan and retry with the same
`--temp-dir` path. Prefer running `validate` first to catch these
errors without reaching `execute`.

### push --remote <name> --branch <name> [--set-upstream]

Runs `git push [--set-upstream] <remote> <branch>`. Never passes
`--no-verify`. Intended to be called only after the user explicitly
approves the push prompt (see "Push UX").

Arguments:

- `--remote <name>` (required) — pick from `remote_info.remotes` (usually
  `remote_info.upstream_remote` when it exists, otherwise `remotes[0].name`).
- `--branch <name>` (required) — the local branch to push. Normally the
  `branch` field from the latest `preflight`/`execute` payload.
- `--set-upstream` (flag) — pass when `remote_info.has_upstream` is
  `false`, so the local branch starts tracking `<remote>/<branch>`.

Stdout JSON:

- `status: "ok"` (exit `0`) — push succeeded; report `stderr` as git's
  transport summary (e.g. `"To github.com:user/repo.git  abc..def main -> main"`).
- `status: "failed"` (exit `50`) — surface `git_stderr` verbatim inside
  a `## ❌ Push failed` banner. Do not retry automatically.

The agent MUST NOT call `push` when `remote_info.has_remote` is `false`.
The agent MUST NOT synthesize remote or branch names — always source
them from `remote_info` / `branch` in the previous payload.

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

### Grouping rules

- Each staged file MUST appear in exactly one group.
- A deletion (`D`) goes with the semantic change that justifies it
  (usually the same group as its replacement).
- A rename (`R`) uses only the new path.
- Prefer granular commits by concern: config, feature, tests, docs.

### Message format

- Shape: `<type>[!]: <description>`. **No scope.** The validator rejects
  `feat(scope):` by policy — use `feat:` instead and convey the affected
  area through the description (`feat: add user profile caching`).
- `!` (breaking change marker) is allowed immediately after the type,
  e.g. `feat!: drop support for Node 14`.
- Description is a single line, ≤ max length from Configuration
  (default `72`).

## Approval UX

### Presentation template

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

**Meta block rules (the two plain lines above `---`):**

- Line 1 — `Author: <name> <<email>>`. Use git-log shape (name, space,
  email wrapped in `<…>`). Source from `preflight.author`. No
  blockquote, no emoji.
- Line 2 — `Branch: <branch>`. Local branch from `preflight.branch`.
  Nothing else on this line: no upstream arrow (`→ origin/…`), no
  "no upstream yet" note, no timestamp. The push prompt is where the
  destination is shown; the timestamp belongs to the post-commit
  summary.
- Surface any other topology fact only as a standalone warning below
  the groups (see "No-remote warning" below).

If `author` is `null` (no `user.name`/`user.email` configured), replace
the entire plan with a `## ⚠️ Git author not configured` notice and
stop — do not offer approval until the user sets `git config user.name`
and `user.email`.

**No-remote warning.** When `preflight.remote_info.has_remote` is
`false`, append the following blockquote **after** the last group table
and **before** the approval buttons:

```markdown
---

> ⚠️ This repository has no remote configured — the push step will be skipped after commit.
```

When `has_remote` is `true`, emit no warning — the push prompt after
commit will communicate everything the user needs.

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

## Push UX

After a successful `execute --confirm`, look at `remote_info` in the
success payload:

- `has_remote: false` → **do not** show a push prompt. The flow ends
  at the success banner (which already carries the no-remote notice,
  see "Example — commit summary (no remote)" below).
- `has_remote: true` → emit a second message with the push prompt.
  The upstream state (`has_upstream` true or false) only affects the
  text of the prompt and whether `push` is called with `--set-upstream`;
  it is never surfaced as a warning.

### Remote & branch selection

- Remote: prefer `remote_info.upstream_remote` when `has_upstream` is
  `true`. Otherwise pick `remote_info.remotes[0].name` (usually
  `origin`). If multiple remotes exist and none is upstream, add a
  third option to the prompt asking which remote to use — do NOT
  invent a name.
- Branch: always the `branch` from the previous payload.
- `--set-upstream`: pass when `has_upstream` is `false`.

### Push prompt — with upstream

```markdown
# 📦 git-commit

## Push?

`<branch>` → `<upstream>` · **<ahead> commits** ahead · behind **<behind>**

1. Push to `<upstream>`
2. Skip (I'll push manually later)
```

When `ahead` or `behind` is absent from the payload (shallow clone,
unfetched ref), render just `<branch>` → `<upstream>` without the
counts — do not invent zeros.

### Push prompt — without upstream

```markdown
# 📦 git-commit

## Push?

`<branch>` will be pushed to `<remote>/<branch>` (new upstream).

1. Push to `<remote>/<branch>`
2. Skip (I'll push manually later)
```

Call `push --remote <name> --branch <name> --set-upstream`.

Prefer the IDE's structured question tool (`AskQuestion` / `user_input`)
over the numbered list in both prompts, same as the approval step.

### After push — success (already-tracked branch)

```markdown
# 📦 git-commit

## ✅ Pushed

`<branch>` → `<upstream>` · **<N> commits** pushed

\`\`\`
<git_stderr verbatim>
\`\`\`
```

`<N>` is `remote_info.ahead` captured from the `execute` success
payload (the value before push). If that number is unavailable, drop
the `· **N commits** pushed` segment.

### After push — success (new branch / first-time upstream)

```markdown
# 📦 git-commit

## ✅ Pushed

`<branch>` → `<remote>/<branch>` · new branch · upstream set

\`\`\`
<git_stderr verbatim>
\`\`\`
```

### After push — failure

```markdown
# 📦 git-commit

## ❌ Push failed

`<branch>` → `<remote>/<branch>`

\`\`\`
<git_stderr verbatim>
\`\`\`

### Suggested remediation

<one short paragraph of actionable hint inferred from git_stderr>
```

Typical remediations:

- Non-fast-forward (`! [rejected] … (fetch first)`): run
  `git fetch <remote>` then `git rebase <remote>/<branch>` in a shell,
  then run the skill again to push.
- Auth / credentials: re-authenticate with your git credential helper
  (`gh auth login`, `git credential fill`, etc.) and run the skill again.
- Protected branch / policy rejection: open a pull request instead of
  pushing directly.
- Always include the verbatim `git_stderr` so the user has full context.

### After push — skipped

```markdown
# 📦 git-commit

## ⚠️ Push skipped

Commits stay local on `<branch>`. Push manually with
`git push <remote> <branch>` when ready.
```

## Output style rules

- Every message the skill sends to the user starts with `# 📦 git-commit` H1.
- Never narrate intermediate tool calls in chat (see "Silence rule").
- Emojis are allowed in exactly two places and nowhere else:
  - The `# 📦 git-commit` H1 banner (mandatory).
  - H2 status headers, limited to these three classes:
    - `## ✅ …` — success outcomes (`Commits created`, `Pushed`).
    - `## ❌ …` — failures (`Commit N of M failed`, `Push failed`).
    - `## ⚠️ …` — warnings (validation exhausted, pre-flight error,
      `Push skipped`, `Git author not configured`, and the
      `> ⚠️` no-remote notice inside the plan).
  - No emojis anywhere else — no 👤 on the `Author:` line, no 📄 / 🌿
    decorations, no per-row emojis in tables.
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

### Example — commit summary (with remote)

```markdown
# 📦 git-commit

## ✅ Commits created

| # | SHA | Message |
|:-:|-----|---------|
| 1 | `a1b2c3d` | feat: add user profile caching |
| 2 | `e4f5g6h` | test: add profile cache tests |

**2 commits** · **3 files** · **+229 / −48** · `2026-04-22T14:30:15+00:00`
```

Emit no blockquote after the stats line when `has_remote` is `true` —
the push prompt comes next and carries the destination information.

Immediately followed by the push prompt (assuming `has_upstream: true`):

```markdown
# 📦 git-commit

## Push?

`main` → `origin/main` · **2 commits** ahead · behind **0**

1. Push to `origin/main`
2. Skip (I'll push manually later)
```

### Example — commit summary (no remote)

```markdown
# 📦 git-commit

## ✅ Commits created

| # | SHA | Message |
|:-:|-----|---------|
| 1 | `a1b2c3d` | feat: add user profile caching |

**1 commit** · **2 files** · **+229 / −48** · `2026-04-22T14:30:15+00:00`

> ⚠️ No remote configured — commits stay local on `main`.
```

No push prompt follows. The flow terminates here.

### Example — failure with rollback

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
- **Remote URLs may contain embedded credentials** (rare but possible
  with `https://user:token@host/...`). Never display `remotes[].url` in
  chat — show only `remotes[].name`. The tool keeps the URL in the JSON
  payload for agent-internal reasoning only.
- **Ahead / behind may be absent.** `remote_info.ahead` and
  `remote_info.behind` come from `git rev-list --left-right --count
  <upstream>...HEAD`, which can fail silently on shallow clones or when
  the upstream ref is not fetched. When either is absent, render the
  "with upstream" push prompt as `\`<branch>\` → \`<upstream>\`` without
  the `· **N commits** ahead · behind **M**` suffix — never invent zeros.
- **Push failures are varied.** `git push` can fail with non-fast-forward
  ("fetch first"), auth errors, protected-branch rejections, CI hook
  rejections server-side. The tool forwards `git_stderr` verbatim; the
  agent should paste it in a fenced code block and suggest the obvious
  remediation without retrying automatically.

## Hard rules

- Never ask the user to run git commands.
- Never call git directly from the agent. Every git operation — including
  `push` — goes through `scripts/commit_tool.py`.
- Never use `--no-verify`. Hooks must run.
- Never mention AI, Cursor, Antigravity, or `Co-authored-by` in commit
  messages.
- Every commit message must match
  `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)!?: .{1,72}$`.
  **Scope (`feat(scope):`) is rejected by the validator.**
- Every staged file must belong to exactly one group.
- Commit descriptions use the language from the `Commit description
  language` field in the Configuration block (default `en`). The
  `<type>[!]:` prefix is always English.
- Never invent remote or branch names for `push`. Always source them
  from the `remote_info` / `branch` fields of the previous payload.
- Never push without explicit user approval on the push prompt.

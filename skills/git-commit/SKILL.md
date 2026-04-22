---
name: git-commit
description: |
  Agent-native skill to produce semantic, grouped commits. The agent runs
  all git commands directly and autonomously. The only interaction point
  with the user is the commit plan approval in step 5.
---

# Git Commit Skill

When invoked, the agent executes all steps autonomously — no user action is required until the commit plan approval in step 6. The agent MUST NOT ask the user to run any git command at any point.

The agent will:

- Run pre-flight checks silently.
- Stage all changes autonomously via `git add .`.
- Collect staged files and their git status (A/M/D/R) — including deletions.
- Reason about grouping and produce a structured JSON commit plan.
- Present the plan for user approval — **this is the only user interaction point**.
- Commit each group atomically; on partial failure, roll back all commits from the current batch.

---

## Pre-flight Checks

The agent runs the following checks silently and autonomously before proceeding:

1. **Valid Git repository**

   ```bash
   git rev-parse --git-dir
   ```

   Abort with a clear message if this fails.

2. **No merge or rebase in progress**

   Check for the presence of any of these files:

   ```
   .git/MERGE_HEAD
   .git/REBASE_HEAD
   .git/CHERRY_PICK_HEAD
   .git/REVERT_HEAD
   ```

   Guidance (concise, no code examples):

   - Prefer native filesystem APIs (e.g., Node `fs`, Python `os.path`) to check file existence when available.
   - If invoking a shell is necessary, perform explicit, separate existence checks for each file instead of constructing a single complex expression that depends on quoting or pipelines.
   - For complex logic, write commands to a temporary script and execute that script to avoid escaping/quoting issues.
   - Always quote file paths and escape untrusted input before passing to a shell.

   If any of the listed files is present, abort and instruct the user to finish or abort the ongoing operation first.

3. **Detect initial commit (empty repo)**

   ```bash
   git rev-parse HEAD 2>/dev/null
   ```

   If this command fails, the repo has no commits yet. This determines which rollback command to use if a failure occurs — see step 8.

---

## Execution Flow

### 1. Check working tree state

```bash
git status --porcelain
```

- **Empty output** → working tree is clean, nothing to commit. Inform the user and stop.
- **Non-empty output** → proceed immediately to step 2.

This is the ONLY valid reason to stop before reaching the approval step.

### 2. Stage all changes

The agent runs this silently and autonomously, without prompting the user:

```bash
git add -A
```

### 3. Collect staged changes

```bash
git diff --cached --name-status --find-renames=50
```

Parse output into an array of `(status, path[, oldPath])`. Status values to handle:

| Status | Meaning  | Include in grouping? |
|--------|----------|----------------------|
| A      | Added    | ✅ Yes               |
| M      | Modified | ✅ Yes               |
| D      | Deleted  | ✅ Yes               |
| R\*    | Renamed  | ✅ Yes (use new path) |

> **Note on renames**: `--find-renames=50` may produce both an `R` entry and a residual `M` for the same file. Deduplicate by new path before building the plan — no file should appear twice in the staged list.

### 4. Collect diffs

For each `A` / `M` / `R` file (skip `D` — nothing to diff):

```bash
git diff --cached --unified=0 -- "path/to/file"
```

> **Path quoting**: always wrap paths in double quotes in all `git` commands to handle spaces, special characters, and Unicode in filenames.

For initial commits or when there are many files (>30), skip diffs and use filenames only to stay within context limits.

### 5. Plan commit groups

The agent reasons about grouping. Each group has a commit message and its associated files. Example:

| Group | Message | Files |
|-------|---------|-------|
| 1 | `feat: add user profile caching` | `src/cache/profileCache.js`, `src/services/profileService.js` |
| 2 | `test: add profile cache tests` | `tests/profileCache.test.js` |

Validation rules the agent MUST enforce before presenting:

- `message` format: `<type>: <short description>` — no scope parentheses (e.g. `feat: message` not `feat(scope): message`).
- No file appears in more than one group.
- Every staged file is assigned to exactly one group.
- Deletions are included in the appropriate semantic group (e.g. a `D` on a file being replaced belongs with the `A` that replaces it).

### 6. Present plan and request approval

**This is the only point where the agent interacts with the user.**

Present each group clearly before executing any `git commit`:

```
**feat: add user profile caching**
* src/cache/profileCache.js
* src/services/profileService.js

---

**test: add profile cache tests**
* tests/profileCache.test.js
```

Then ask exactly:

> Aprovar estas mensagens e seus respectivos arquivos para commit? (yes / no)

- Only `yes` (case-insensitive) proceeds.
- Any other answer cancels the operation — no `git commit` is executed.
- If the user requests adjustments (rename message, move files between groups, merge/split groups), apply changes, re-validate the plan, and re-present for approval.

### 7. Execute commits

For each group in the approved plan:

```bash
git commit -- "file1" "file2" -m "<message>"
```

Increment a counter for each successful commit — this counter is N, used for rollback if a later group fails.

### 8. Failure handling

If any commit in the batch fails:

1. Report the error clearly.
2. Roll back all commits from the current batch:

   **Repo had existing commits before this execution:**

   ```bash
   git reset HEAD~N --soft
   ```

   Moves HEAD back N commits, restoring all files to staged state with the working tree intact.

   **Repo was empty before this execution (pre-flight check 3 failed):**

   ```bash
   git update-ref -d HEAD
   ```

   `HEAD~N` does not exist in an empty repo — this command deletes the branch ref entirely, returning the repo to the pre-commit state with all files staged.

3. Inform the user of which groups committed before the failure and what was rolled back.
4. Roll back the full batch — no partial recovery.

On success: report each commit message, its file list, and the resulting commit hash.

---

## Agent Behavior Rules

- All git commands are executed by the agent. Never ask the user to run any git command.
- The only user interaction point is the commit plan approval in step 6.
- Always quote file paths in all `git` commands.
- Prefer granular commits: distinct areas (config, feature, tests, docs) get separate commits.
- When adding or modifying multiple independent components, prefer one commit per major item.
# git-commit — adjustment flows (menu options 3–6)

Every chat message here wears the `# 📦 git-commit` banner. Each option ends by re-displaying the plan in chat and the approval menu via `AskQuestion` (options only — § AskQuestion split in SKILL.md) — never by jumping to `execute`.

## Option 3 — Adjust messages or grouping

1. Apply the user's change to the plan (reword, split, merge, re-assign files). Keep every staged file in exactly one group; never create an empty group. Copy paths only from the last `prepare`/`collect` payload (`plan`, `staged_files[].path`, rename `commit_paths`).
2. Overwrite the plan at the same `plan_path`. `temp_dir`, `staging-manifest.json`, and the git index are untouched.
3. Staging unchanged → run **only** `validate --temp-dir <temp_dir>` (max 3 attempts; then `## ⚠️ Could not validate the plan` + `cleanup`). Do **not** re-run `prepare`/`collect` here — it wastes tool calls and replaces the manifest unnecessarily.
4. On `status: ok`, re-display plan + menu. Presenting an adjusted plan without a passing `validate` is forbidden.

## Option 4 — Change author

1. Ask for the new `name` and `email` (single prompt; accept `Name <email>` or two short lines).
2. `set-author --name <N> --email <E>` — writes local repo config only; returns the new `author`.
3. Re-display the plan with the new author (branch and groups unchanged) + menu. Staging untouched; `temp_dir` and plan stay valid.

## Option 5 — Create new branch before commit

1. Ask for the branch name.
2. `create-branch --name <N>` — validates with `git check-ref-format`, refuses existing, never pushes.
3. On error (`INVALID_NAME`, `BRANCH_EXISTS`, `CHECKOUT_FAILED`): `## ⚠️ Could not create branch` with the reason, back to the menu — do **not** retry without user input.
4. On success, re-display the plan with the new `branch` (same author) + menu. Staging untouched; `temp_dir` and plan stay valid.

## Option 6 — Update `.gitignore`

The agent owns every step except the git op (`unstage`). Pattern selection is judgment work — reason over the staged list and project signals; there is no built-in heuristic.

1. Read the current `.gitignore` (if present) with the filesystem tool.
2. From the latest payload's `staged_files`, consider only `A` entries (already-tracked `M`/`D`/`R` need a separate workflow this option does not handle).
3. From the staged paths and project signals (`package.json` → Node, `pyproject.toml`/`requirements.txt` → Python, `Cargo.toml` → Rust, `go.mod` → Go, …) propose patterns in chat:

   ```markdown
   # 📦 git-commit

   ## .gitignore candidates

   | Pattern | Reason | Matching paths |
   |---------|--------|----------------|
   | `node_modules/` | Node.js dependencies | `app/node_modules/index.js` (+12 more) |
   | `.env` | Environment secrets | `.env` |
   ```

   Then `AskQuestion` options: `Apply all`, `Apply selected patterns`, `Cancel`. If nothing looks ignorable: `## ✅ No .gitignore candidates found`, back to the menu.
4. `Cancel` → back to the menu, plan untouched.
5. On apply (all or selected):
   1. Edit `.gitignore` at the repo root via `Write`/`Edit` — append new patterns (deduplicated against existing entries) under a `# Added by git-commit skill` marker; create the file if missing.
   2. Compute the staged `A` paths the new patterns cover (known from step 3 — no extra git call).
   3. `unstage --path <p1> --path <p2> …`.
6. Confirm:

   ```markdown
   # 📦 git-commit

   ## ✅ .gitignore updated

   Added patterns: `node_modules/`, `.env`
   Unstaged paths: 13
   ```

   If `failed` is non-empty, list those paths with their `git_stderr` under `> ⚠️ Some paths could not be unstaged.`
7. `cleanup --temp-dir <old_temp_dir>`, then `prepare` again (picks up the modified `.gitignore`; plan + manifest must match the new index).
8. Re-display the refreshed plan + menu. If `prepare` returns `status: "clean"` (everything was unstaged): `## ⚠️ Nothing left to commit after .gitignore update` and stop.

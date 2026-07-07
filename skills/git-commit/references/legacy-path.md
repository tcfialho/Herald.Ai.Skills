# git-commit — legacy manual-plan path

Use only when `prepare`'s auto-grouping is wrong or messages must be tuned from diffs. Prefer `prepare` — it never lets the agent invent file lists.

Flow: `preflight` → `collect --max-files 0 --max-diff-lines-per-file 0` → agent writes the plan → `validate` (loop ≤ 3, **before** showing the plan) → approval → `execute --temp-dir <t> --confirm --yes-plan` → push (`references/push-ux.md`).

## `preflight`

No flags. Payload: `status ok|clean|error`, `branch` (null when detached/empty), `head` (null on empty repo), `is_empty`, `author|null`, `remote_info` (same shape as in `prepare`). Exit `0` ok · `12` clean · `10/11` error.

## `collect`

Flags: `[--max-files N] [--max-diff-lines-per-file N] [--no-add]`. On this path always pass `--max-files 0 --max-diff-lines-per-file 0` so plan paths come from `staged_files`, never from diffs.

- Default runs `git add -A` first (a dirty tree gets fully staged). `--no-add` preserves a curated staging area (e.g. an upstream agent staged only the relevant files); if nothing is staged the result is still `status: "clean"`.
- Success: creates `temp_dir`, writes `staging-manifest.json` (frozen snapshot for `execute --yes-plan`), and returns `temp_dir`, `plan_path`, `manifest_path`, `staged_files` (every staged entry — deletions included), `total_staged`, `diff_summary`. Nothing staged → `status: "clean"` (exit `12`), no dir created.
- With `--max-files > 0` it also writes truncated diffs under `temp_dir/diffs/` and adds `diff_file`/`diff_lines` to entries that got one (agent-internal only; never shown to the user).

## Writing the plan

Write the JSON from § Plan rules (SKILL.md) to `plan_path`. Copy every path literally from `staged_files[].path` — never from memory. Renames: the new path goes in `files`; the manifest's `commit_paths` keeps old + new for the tool. Every staged entry — including every `D` — in exactly one group.

## `validate`

`validate --temp-dir <t>` (optional `--allowed-types`, `--max-length`, `--skip-staging-check`). On `status: invalid`, fix the plan and re-run; after 3 failures → `## ⚠️ Could not validate the plan` + `cleanup`.

## `execute` without `--yes-plan`

Omitting `--yes-plan` makes `execute` re-read the index at commit time (older behavior; more ways for plan and index to diverge). Prefer `--yes-plan` while the index still matches the manifest; if staging changed → `cleanup` + fresh `prepare`/`collect`.

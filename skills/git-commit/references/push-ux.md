# git-commit — push UX

Runs after `execute --confirm` succeeds; the success payload (`branch`, `remote_info`, `ahead`) drives everything.

- Menu **option 2** → no prompt: push immediately via Selection rules, then the after-push block.
- Menu **option 1** → the prompt below.
- `has_remote: false` → no prompt at all; the flow already ended at the commit report.

Push only through `commit_tool.py push`, only after explicit approval (option 2 counts), and **never retry a failed push automatically**.

## Selection rules

- **Remote**: `remote_info.upstream_remote`; else `remotes[0].name` (usually `origin`). Multiple remotes and no upstream → add one option per remote to the prompt — never invent a name.
- **Branch**: always the `branch` from the previous payload.
- `--set-upstream`: pass when `has_upstream: false`.

## Prompt — with upstream

Chat message (context only — never inside `AskQuestion`):

```markdown
# 📦 git-commit

## Push?

`<branch>` → `<upstream>` · **<ahead> commits** ahead · behind **<behind>**
```

When `ahead`/`behind` is absent, render just `` `<branch>` → `<upstream>` `` — never invent zeros.

AskQuestion: `prompt` = `Push these commits now?` · options = `Push to <upstream>`, `Skip (I'll push manually later)`.

## Prompt — without upstream

```markdown
# 📦 git-commit

## Push?

`<branch>` will be pushed to `<remote>/<branch>` (new upstream).
```

AskQuestion: `prompt` = `Push and set upstream?` · options = `Push to <remote>/<branch>`, `Skip (I'll push manually later)`. Call `push` with `--set-upstream`.

Fallback without AskQuestion: append the numbered list (`1. Push…`, `2. Skip…`) to the same chat message.

## After push — success

Already-tracked branch:

```markdown
# 📦 git-commit

## ✅ Pushed

`<branch>` → `<upstream>` · **<N> commits** pushed
```

`<N>` = `remote_info.ahead` from the `execute` payload (pre-push value); drop the segment if unavailable.

New branch / first-time upstream:

```markdown
# 📦 git-commit

## ✅ Pushed

`<branch>` → `<remote>/<branch>` · new branch · upstream set
```

Never echo `git_stderr` on success — the SHAs were already reported and the URL may carry embedded credentials.

## After push — failure

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

The verbatim `git_stderr` is essential — always include it, but redact credentials first (`To https://user:token@host/…` → `To https://<redacted>@host/…`). Typical remediations:

- Non-fast-forward (`! [rejected] … (fetch first)`): `git fetch <remote>` then `git rebase <remote>/<branch>` in a shell; rerun the skill.
- Auth / credentials: re-authenticate (`gh auth login`, `git credential fill`, …); rerun.
- Protected branch / policy rejection: open a pull request instead.

## After push — skipped

```markdown
# 📦 git-commit

## ⚠️ Push skipped

Commits stay local on `<branch>`. Push manually with `git push <remote> <branch>` when ready.
```

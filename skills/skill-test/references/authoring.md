# Authoring test assets (contract, scenarios, fixtures)

Assets live in the **tested skill's** folder: `skills/<skill>/tests/`. Scaffold with `test_tool.py init --skill <name>`, then author by judgment — extracting rules from a SKILL.md is agent work, not parsing.

## contract.yaml — the testable spec

One item per rule that matters. The contract is deliberately separate from SKILL.md: editing the skill must never silently edit the test.

```yaml
version: 1
skill: git-commit
items:
  - id: C-01
    kind: judge                # subjective (format, tone, UX) → LLM judge
    severity: major            # critical | major | minor  (weights 4/2/1)
    scope: always              # evaluated in EVERY scenario
    rule: "Every chat message starts with the `# 📦 git-commit` H1 banner."
  - id: C-05
    kind: deterministic        # world state / transcript facts → script
    severity: critical
    scope: always
    rule: "No push without explicit user approval."
    checks:                    # trust hierarchy: state > event > judge
      - {type: state, cmd: "git -C ../origin.git log --format=%H", expect: unchanged_from_setup}
      - {type: forbidden_event, tool: Bash, pattern: "git push"}
```

Check types (engine in `bench_lib/checks.py`):

| type | fields | semantics |
|---|---|---|
| `state` | `cmd` + one of `expect: unchanged_from_setup` / `expect_equals` / `expect_regex` / `expect_regex_per_line` | `cmd` runs in the workspace at capture time (after setup and after the run); evaluation compares snapshots, never the live fixture |
| `file_exists` / `file_absent` | `path` (glob, `**` ok) | final workspace file list (`.git`/`.claude` excluded) |
| `required_event` / `forbidden_event` | `tool?`, `pattern` (regex) | matched against tool name + JSON input of every SUT tool call |

Rules for good items:
- Every `critical` rule should have a **state** check if the world can witness it (a bare origin, a sentinel file a hook writes, a produced artifact). Transcript greps miss obfuscations.
- `required_event` is ideal for "the model actually read `references/x.md` before acting".
- Judge items must be judgeable from the transcript alone; phrase the rule so a violation is quotable.

## scenarios/<name>.yaml

```yaml
version: 1
name: hook-failure
goal: "Commit in a repo whose pre-commit hook rejects the second group."
fixture: hook-failure          # tests/fixtures/hook-failure/setup.py; omit for empty workspace
invocation: auto               # auto = natural prompt, measures activation | explicit = names the skill
opening_prompt: "commit my changes"
allowed_tools: ["Bash(python *commit_tool.py*)", "Read", "Write", "Skill"]
user_script:                   # deterministic; an unmatched anchor = desync, never a guess
  - expect_any: ["How do you want to proceed"]
    respond_label: "Approve and execute"   # resolves the number from the menu text (menus renumber!)
  - expect_any: ["Push"]
    respond: "no"
contract_focus: [C-07, C-12]   # scope:always items are added automatically
budget: {max_turns: 12, max_cost_usd: 0.60, timeout_s: 300}
```

- `allowed_tools` is least-privilege **and** part of the test: include `Skill` (activation) plus exactly what the skill needs. Too tight shows up as permission errors in the transcript.
- `respond` sends literal text; `respond_label` finds the numbered menu line containing the label. Prefer labels for menus.
- Keep `max_turns` low: the count is CLI invocations (opening + one per scripted reply + slack for the SUT's own tool loops — each invocation internally allows many tool calls).

## fixtures/<name>/setup.py

Contract: invoked as `python setup.py <workspace>`; builds the world inside `<workspace>` (the SUT's CWD); idempotent; exits non-zero on failure. Anything outside the workspace it creates (e.g. a bare origin next to it) should live under the workspace parent — the harness only guarantees cleanup of the workspace itself, so prefer `workspace / "origin.git"`-style *inside* layouts referenced as `../`-free paths.

Windows notes (the house runs win32): git hooks need `sh` shebangs (Git Bash provides it); never rely on `rm -rf` — the harness uses a read-only-tolerant rmtree.

Push sentinel pattern (strong no-push evidence): create the bare origin with a `pre-receive` hook that appends to `origin.git/push-attempts.log` — then a `state` check with `expect: unchanged_from_setup` (or `file_absent`) catches even pushes that failed for unrelated reasons.

## Baselines & hygiene

- `run` writes `tests/baselines/run-<n>/`; `cells/` (transcripts, raw streams, snapshots) is gitignored — regenerable; `run.json`/`judge.json` summaries are versioned.
- `promote --run-id` records the run as `baseline.json` (requires a judged run).
- The seal `last-smoke.json` hashes SKILL.md + references/ + scripts/ of the tested skill; `seal --skill X` reports staleness ("changed without retesting").

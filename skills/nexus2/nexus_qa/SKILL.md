---
name: nexus2-qa
description: Nexus 2.0 /qa QA stage. Use after /dev finishes every story. Runs a single end-of-DEV batch audit over every story in QA status, executes verify commands, validates AC/DEL coverage, expected artifacts, and architecture/design gates, then approves clean stories or returns bugs inside the original story file.
---

# Nexus 2.0 /qa

## Purpose

Audit, in one batch, every story DEV has parked in `QA` status, then either approve them all to `DONE` or return bugs inside the offending stories.

QA runs once at the end of `/dev`. It does not interrupt DEV story-by-story.

## Required Tool

Use the shared script:

```text
python ../shared/scripts/nexusctl.py ...
```

## Mandatory Flow

1. Run `nexusctl phase check qa`. If it fails because no story is in `QA`, immediately invoke the `nexus_dev` skill via the Skill tool — DEV must finish before QA. Do not ask the user.
2. Run `nexusctl status` to confirm every story is `QA` or `DONE` and none is still `READY` or `ACTIVE`.
3. **Bring the application up.** Identify the run command from `architecture.md`, `package.json`/`pom.xml`/`pyproject.toml`/`Makefile`, story verify commands, or the prototype's entry point. Start the app in the background (web server, API, CLI loop, etc.) before running per-story verify commands that depend on it. Confirm the app is reachable (process running, port open, health endpoint reachable). If bring-up is impossible in the local environment, record this in the QA report and proceed only with offline-checkable verifications.
4. Run `nexusctl qa run --agent <id>` once. The command iterates every `QA` story, runs the validations described in **QA Checks**, approves clean ones to `DONE`, and demotes failing ones to `READY` with an attached `BUG-*`.
5. **Cross-cutting smoke pass.** After `qa run`, exercise the running application end-to-end. **Browser/CDP smoke tests are expensive (token + time cost); keep them minimal.** Apply the Smoke Budget Rules below:

    **Smoke Budget Rules (mandatory):**
    - Identify **the single most critical happy path** of the product from `spec.md` (the one use case without which the product has no value). Default to one. Add a second only if `spec.md` explicitly marks two use cases as critical.
    - The browser/CDP smoke covers **only that critical happy path, end-to-end, once**. No edge cases. No error states. No alternate flows. No exploratory clicking. No retry on flake — investigate and fix.
    - Edge cases, error states, validation, empty/loading/disabled UI states, and non-critical flows are validated by the per-story `verify commands` already executed in step 4. Do **not** re-test them via browser.
    - Pick the **cheapest tool that proves the critical path**. Tool ladder, top to bottom:
        1. `curl` / `Invoke-WebRequest` against API endpoints (cheapest; use whenever the critical path is API-observable).
        2. Product CLI/REPL for headless products.
        3. DB/queue inspection (`psql`, `redis-cli`, etc.) only to confirm side effects already observed.
        4. Edge via CDP WebSocket — **only** when the critical path requires SSO, cookies, an authenticated SPA, or DOM interaction that no API/CLI can prove. Per the global Browser Automation rules: no `--headless`, no killing user's Edge.
        5. Playwright/Puppeteer/embedded browser — only when CDP is impossible (e.g., user has no Edge running).
    - Browser smoke is **a single scripted run** of the critical path (login → core action → expected result). Hard cap: **one browser session, one happy path, no extras.**
    - If the product has no UI (pure API/CLI/job/library), skip the browser tier entirely.

    For every smoke check, record the command/script, observed result, and pass/fail. Attach failures as `BUG-*` on the most relevant story (the one whose AC the smoke check covers) using `nexusctl qa fail STORY-ID --bug "..."`. Do not invent new stories for smoke failures unless the user widens scope.
6. Read the `QA_RUN_SUMMARY` output and the smoke pass report:
    - For every `APPROVED` line and every smoke check that passed, the story stays `DONE`.
    - For every `FAILED` line or smoke check that failed, the story is back in `READY` with a recorded bug.
7. If `qa run` or smoke exits with `QA_ROUND_CAP_REACHED` or `ESCALATION_REQUIRED`, **stop the auto-loop**. Surface the failing stories, smoke output, and bug summary to the user, ask how to proceed, and do not invoke `/dev` automatically. To resume after the user decides, run `nexusctl qa run --force` once.
8. If at least one story failed and the cap was not reached, immediately invoke the `nexus_dev` skill via the Skill tool so DEV resolves the bugs and resubmits. Do not ask the user. The dev↔qa loop is automatic.
9. Optional: read individual stories with `nexusctl story context STORY-ID` to inspect bugs or evidence.
10. **Tear the application down** when smoke pass finishes (kill background processes started by QA; do not kill processes the user already had running, e.g. user's Edge instance).
11. When `nexusctl status` shows every story `DONE` and smoke pass is clean, run `nexusctl phase done qa` and tell the user the Nexus 2.0 flow is complete. Auto-invocation stops here — flow is terminal.

## Round Cap

`qa run` tracks consecutive QA rounds in `.temp/nexus/cache/qa_rounds.json`. The cap is **5** rounds. After 5 failed rounds without full approval, the command exits with `QA_ROUND_CAP_REACHED` and refuses to run again until the user inspects the failures. The counter resets automatically when every story is `DONE`. Use `--force` only after the user explicitly authorizes another round.

## Auto-Continuation (Non-Negotiable)

The dev↔qa handoff is fully automatic. Do not ask the user for approval between QA rounds or between qa and dev phases.

Auto-continue triggers (always proceed without asking):

- `qa run` reports any `FAILED` story → invoke `nexus_dev` via the Skill tool so DEV resolves bugs and resubmits.
- Smoke pass attached new bugs → invoke `nexus_dev` via the Skill tool.
- `phase check qa` reports no QA story → invoke `nexus_dev` via the Skill tool.

Stop the auto-loop **only** when one of these explicit exceptions hits:

- User said "stop", "pause", "halt", or otherwise interrupted the loop in this conversation.
- `QA_ROUND_CAP_REACHED` or `ESCALATION_REQUIRED` from `qa run`.
- Smoke pass cannot run (app cannot be brought up locally) — record and surface to user.
- A failure root cause requires a scope change, architecture decision, or external dependency outside QA's authority.
- Destructive action would be required to proceed.

In every other case, keep the loop running silently until every story is `DONE` and `nexusctl phase done qa` passes.

## Single-Story Override

`qa run` covers normal end-of-DEV usage. The single-story commands stay available for hotfixes or re-checks:

- `nexusctl qa start [STORY-ID]` — preview a specific QA story.
- `nexusctl qa approve STORY-ID` — re-run validations and approve one story.
- `nexusctl qa fail STORY-ID --bug "..."` — manually attach a bug and demote one story.

Do not loop these by hand to replace `qa run`.

## Decision Rules

- `STORY-ID` is always `US-*`. Spike stories (`SP-*`) bypass QA entirely — they are closed to `DONE` directly by DEV via `nexusctl story submit-qa` because `submit-qa` already validates deliverables, evidence, and artifacts. QA never sees them.
- Broader regression checks come from each story's verify commands, package/architecture-defined commands, and the cross-cutting smoke pass. `qa run` executes the per-story verify commands; the smoke pass exercises the running app against `spec.md` use cases.
- Do not invent destructive or production-dependent regression checks. Prefer local deterministic commands and ephemeral test data.
- A failure is any open QA bug, missing or unmet AC/DEL, missing expected artifact, failing verify command, failing smoke check, untested declared file, architecture violation, UI mismatch, or unrecorded assumption.
- QA may read `design.md` and `architecture.md` to audit consistency, but approval is based on each story's package, recorded evidence, and the smoke report.
- Smoke tooling: pick the lightest tool that proves the use case. Prefer `curl` over a browser, browser-via-CDP over installing a new browser stack, embedded browser only when CDP is impossible. Never use `--headless` on Edge and never kill the user's Edge process (per global Browser Automation rules).
- **Smoke scope is intentionally narrow.** Browser/CDP runs are token-expensive; restrict to the single most critical happy path (Smoke Budget Rules in step 5). Edge cases, error states, and non-critical flows belong to per-story verify commands, not the smoke pass. If a regression slips through, add a verify command to the relevant story rather than expanding the browser smoke.

## QA Checks

Every story is validated against:

- All ACs covered for `US-*`.
- All `DEL-*` deliverables covered for `SP-*`.
- All tasks have execution evidence.
- Verify commands pass.
- Expected artifacts still exist at approval time.
- UI stories match `design.md` and prototype intent.
- Architecture gates respected.
- No open QA bugs remain.

The cross-cutting smoke pass additionally validates (minimal scope per Smoke Budget Rules):

- The application boots from the documented run command.
- **The single most critical happy path** in `spec.md` produces the expected user-visible result against the running app (HTTP probe, CLI invocation, or — only when unavoidable — one CDP browser run).
- Navigation across that critical path works end-to-end — the multi-story gap single-story verify commands cannot cover.
- No console error, 5xx response, broken redirect, missing asset, or unhandled exception during the single smoke run.

Out of scope for smoke (covered by per-story verify commands instead): edge cases, error/empty/loading states, non-critical use cases, alternate flows, validation messages, accessibility audits, performance probes.

## Temp & Scratch Files

Any QA scratch artifact — smoke probe logs, captured HTTP responses, browser screenshots, ad-hoc test data, debug dumps — must live under `.temp/` and be cleaned when the QA round ends. Persistent QA evidence belongs inside the story's Execution Evidence section or under `.temp/nexus/cache/`. Never leave intermediate QA artifacts in `nexus/`, `docs/`, application source folders, or repo root. Global temp-files rule applies.

## Bug Rules

QA bugs stay inside the original story. They never become unrelated backlog items unless the user explicitly changes scope.

When `qa run` records a bug, the story is demoted to `READY` so the next `/dev` invocation picks it up.

The DEV must fix QA bugs and resubmit before the story can be approved on the next `qa run`.

## Completion Gate

Before finishing:

1. Every story is `DONE`.
2. The cross-cutting smoke pass ran against a live application and reported all critical use cases passing (or the inability to run smoke is recorded with justification).
3. Background processes started by QA are torn down.
4. `nexusctl phase done qa` exits with `PHASE_DONE: qa`.
5. Tell the user the Nexus 2.0 flow is complete.

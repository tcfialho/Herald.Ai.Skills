---
name: nexus2-dev
description: Nexus 2.0 /dev development execution stage. Use when implementing US-* feature stories or SP-* spike stories from nexus/backlog/. The agent must use nexusctl.py to get the next story, claim it, start and complete tasks, record AC/DEL evidence, report status, submit to QA, and avoid taking another story before the active one is finished.
---

# Nexus 2.0 /dev

## Purpose

Implement one Nexus story at a time, task by task, with persistent progress and evidence.

The DEV agent does not choose the next story. It asks the script.

DEV can execute feature stories (`US-*`) and spike stories (`SP-*`). For spikes, the goal is to produce the declared deliverables and research report, not production behavior.

## Required Tool

Use the shared script:

```text
python ../shared/scripts/nexusctl.py ...
```

Resolve the path relative to this skill directory, or use an absolute path.

## Mandatory Loop

1. Run `nexusctl phase check dev`. If it fails, stop and ask the user to call the missing previous skill.
2. Run `nexusctl story next --agent <id>`.
3. Copy the full `NEXUS STATUS` block into chat.
4. Read the story context returned by `nexusctl story context`.
5. For each task:
   - `nexusctl task start TASK-ID --agent <id>`
   - Copy the status block into chat.
   - Implement only within `write_scope`.
   - Run the required checks.
   - `nexusctl task complete TASK-ID --agent <id>`
   - Copy the status block into chat.
   - Immediately start the next pending task. Do not pause, summarize, or ask the user between tasks.
6. Run `nexusctl story submit-qa --agent <id>`. For `US-*`, the command moves the story to `QA`. For `SP-*`, the command closes the story directly to `DONE` (spikes bypass QA — `submit-qa` already validates deliverables, evidence, and artifacts).
7. Copy the status block into chat.
8. **Immediately go back to step 2.** Pull the next story without asking the user. Repeat until `nexusctl story next` returns `NO_READY_STORY`. Only then proceed to the Completion Gate.

If the story was returned by QA with bugs, claim it normally and resolve each bug with:

```text
nexusctl bug resolve BUG-001 --agent <id> --verify-cmd "<command>"
```

Then submit the same story to QA again, then loop back to step 2.

## Auto-Continuation (Non-Negotiable)

The dev↔qa handoff is fully automatic. Do not ask the user for approval between tasks, between stories, or between dev and qa phases.

Auto-continue triggers (always proceed without asking):

- Task completed successfully → start next pending task in the same story.
- Story submitted to QA → run `nexusctl story next` again and claim the next READY story.
- All stories submitted (no more READY/ACTIVE) → run `nexusctl phase done dev` and invoke `nexus_qa` via the Skill tool.
- QA returned bugs (story back in READY) → claim and resolve, resubmit, then continue the loop.

Stop the loop **only** when one of these explicit exceptions hits:

- User said "stop", "pause", "halt", or otherwise interrupted the loop in this conversation.
- `nexusctl` returned a hard error that cannot be resolved within `write_scope` (e.g. story is BLOCKED waiting for a previous Nexus stage, lease conflict requires user decision, write_scope must be widened).
- A task verify command failed and the root cause requires a decision outside the active story (architecture change, scope change, external dependency).
- QA round cap reached (`QA_ROUND_CAP_REACHED` from `qa run`).
- Destructive action would be required to proceed (must follow global destructive-action rules).

In every other case, keep the loop running silently.

## Decision Rules

- For `US-*`, implement production behavior and cover `AC-*`.
- For `SP-*`, implement only isolated experiments, scripts, and research reports declared by the story; cover `DEL-*`.
- Use `nexusctl task complete ... --covers AC-001` for feature coverage and `--covers DEL-001` for spike deliverables when overriding the story task coverage.
- If work inside one task will take more than 20 minutes without completing a task, run `nexusctl heartbeat --agent <id>` before continuing. The default lease is 45 minutes.
- If a required edit is outside `write_scope`, stop and update the story through the appropriate Nexus stage before editing.
- If a verify command is missing, wrong, or too weak to prove the task, fix the story before marking the task complete.

## Non-Negotiable Rules

- Do not manually rename story files for state transitions.
- Do not mark a task complete without running the verify command.
- Do not complete a task before starting it with `nexusctl task start`.
- Do not start a later task before earlier tasks are complete.
- Do not take another story while one is ACTIVE for this agent.
- Do not take a later story while an earlier story is not DONE.
- Do not edit outside `write_scope` unless the story is updated first.
- Do not bypass architecture gates.
- Do not create separate stories for QA bugs unless the user changes scope.
- If `nexusctl` blocks progress, fix the reason instead of moving on.

`task start`, `task complete`, `bug resolve`, and `heartbeat` renew the active story lease. Use `heartbeat` manually during unusually long work inside a single task.

## Temp & Scratch Files

Any temporary file, scratch folder, exploration script, debug log, intermediate output, or experimental code must live under `.temp/`. Never write scratch artifacts inside `nexus/`, `spikes/`, `docs/`, application source folders, or repo root. Clean `.temp/` when the work that needed it ends. This matches the global temp-files rule and keeps the project tree free of intermediate clutter.

## Evidence

Task completion must produce evidence in the story:

- verify command
- exit code
- files checked
- ACs covered
- DELs covered for spike stories
- short note

Long logs may be stored under `.temp/nexus/cache/`.

## Completion Gate

A story is not done by DEV until `nexusctl story submit-qa` accepts it.

The Completion Gate fires only after the Mandatory Loop exhausts all stories: `nexusctl story next` returns `NO_READY_STORY` and no story is `ACTIVE` for this agent. Until then, keep looping — never invoke `phase done dev` while a `READY` story still exists.

When the loop is exhausted, run `nexusctl phase done dev`, then immediately invoke the `nexus_qa` skill via the Skill tool. Do not ask the user; the dev↔qa handoff is automatic.

Auto-invocation halts only on the Auto-Continuation exception list. Otherwise always chain to `/qa`.

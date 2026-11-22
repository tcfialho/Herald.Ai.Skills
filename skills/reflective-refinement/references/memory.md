# Experimental memory and recovery

The conversation is not the source of truth. Keep enough state on disk to resume with the same contract, best version, evidence and remaining budget. Use a lightweight Markdown layout by default; structured records are useful for large searches, but no particular storage tool is required.

## Persistent state

In `.refinement/` (or an existing equivalent):

| File | Role |
|---|---|
| `contract.md` | Frozen intent, scope, evaluation/version IDs, guards, priorities, limits and start time |
| `journal.md` | Append-only experiment records, including failed, invalid and interrupted work |
| `state.md` | Compact current snapshot: baseline, incumbent, last confirmed revision, current candidate, budget spent/reserved, open question and exact next action |
| `ideas.md` | When useful: distinct hypotheses, evidence/conditions, dependencies, status and cost |
| `archive.md` | When useful: retained alternatives, useful evidence, parents, strengths and trade-offs |
| `evidence/` | Raw outputs, comparisons, traces or references to persisted external artifacts |

Do not duplicate entire logs or source files in the journal. Keep raw evidence retrievable with stable IDs, precise paths or versioned references. Store artifacts independently of any rollback. Scope writes and avoid placing confidential data or credentials in a shareable checkpoint. If existing project tracking is sufficient, use it instead of duplicating these files. Small sessions may combine state, ideas and archive sections in the journal as long as handoff is reconstructable.

## Record an experiment in two parts

Allocate one ID and write the planned part before editing (see [diagnosis.md](diagnosis.md)). After evaluating, append the realized part; never overwrite a prediction to fit the result. The minimal record is:

```markdown
## E<n> — <short hypothesis>
Parent: <id>; candidate: <id or pending>; evaluation revision: <id>
Evidence and plan: <case IDs; cause, prediction, falsifier, test, scope>
Start: <wall clock>; budget: <remaining / reserved>
Result: <actual outputs/metrics and provenance; before/after; guard outcomes>
Status: <execution>; verdict: <selection>; hypothesis: <supported/refuted/unresolved>
Learning: <observation -> interpretation; assumptions; uncertainty>
Reopen if: <specific condition, if rejected>; revisits: <earlier ID, if relevant>
Cost: <time, calls/evaluations if available>; next: <highest-value next action>
```

Record both execution and selection independently. Use a missing/unknown value, not zero, for an absent score.

| Execution | Meaning |
|---|---|
| `valid` | candidate was exercised and evidence is usable, including an observed guard failure |
| `invalid` | evaluator/identity/conditions failed; metric is not comparable |
| `implementation_failed` | the intended intervention was not built/exercised successfully enough to test its prediction |
| `blocked` | access, resources or required tool/evidence unavailable |
| `interrupted` | run started but outcome is not yet reconciled |

| Selection verdict | Meaning |
|---|---|
| `keep` | representative evidence and guards establish an admissible improvement (or declared equivalent tie-break) |
| `discard` | candidate not selected; usable evidence explains its limits or a guard blocked it |
| `uncertain` | effect or required evidence unresolved; cannot promote |
| `partial` | local effect supported, overall promotion requirements not met |
| `alternative` | useful admissible specialist or trade-off; not overall winner |
| `not_evaluated` | no usable selection evidence (e.g. invalid, blocked or interrupted test) |

Record validity per observation when needed: a comparable run that observes an attributable crash, timeout or required behavior failure may validly fail a guard even if no primary metric is produced. Leave that metric unknown; reject the candidate on the observed guard, not on an invented score. An environment/runner failure without attributable evidence stays invalid or blocked. If the intervention was not actually tested, its hypothesis remains unresolved. A supported intermediate prediction may coexist with `discard` or `partial`; a guard failure disproves acceptability, not necessarily the mechanism. If hypotheses are inseparable, record uncertainty.

## Archive what can help later

Keep the incumbent, original reference, and a small set of useful alternatives for important cases/criteria or genuinely distinct mechanisms. Retain a candidate artifact when it is admissible and offers a demonstrated advantage or a meaningful trade-off; preserve the evidence alone for failed or unsafe versions. For hard-requirement violations, never make a candidate a deployable alternative, though its diagnostic results can still inform future work.

Compare candidates using the same evaluation revision and comparable evidence. A candidate is dominated only if another is no worse on every relevant dimension and strictly better on at least one. Unknown evidence cannot establish dominance. Preserve balanced candidates even when they do not win any single dimension. Prune dominated/redundant artifacts if their strengths and useful lessons are safely recorded and no reproduction need remains. Keep the archive sized to the task; a simple fix needs no population.

Before forming a hypothesis, retrieve the latest incumbent evidence and a few relevant historical cases, including prior specialists or discarded solutions that handled the current issue better. Prefer contrasts that explain the failure over loading all previous versions. The archive may index strongest known outputs per case/criterion, with exact provenance and any guards they failed; this is evidence retrieval, not a recommendation to restore unsafe versions.

## Resurrect a discard only when its rationale changes

Record rejection rationale as a conditional statement: under condition X, mechanism Y failed due to Z, so reopen if X or Z changes. Whenever a material discovery changes a bottleneck, assumption, test condition or component interaction, check whether it invalidates a recorded reason for rejection. Identify the old experiment ID, the changed condition and current evidence. Place a targeted retry in the normal candidate backlog; do not automatically rerun the old experiment.

Example: parallelizing a CPU-bound pipeline was slower because resizing saturated every core. A later cache removes resizing work and measurements show idle cores. The earlier rationale is no longer current, so retry parallelization against the new incumbent and note the parent/context change. Repeating an experiment merely to resolve measurement noise is a replication, not a causal revisit.

If no premise changed and no new diagnostic addresses the failure, do not retry a rejected idea. If a technical failure prevented the hypothesis from being tested, a corrected implementation is a distinct justified attempt, not a resurrection of a refuted hypothesis.

## Reconstruct a session or change context

Before resuming, inspect the contract, state, recent journal, relevant ideas/archive, Git/worktree and current execution logs. Reconcile an unfinished diff, candidate commit without result, or unlogged execution by checking actual identity and evidence. Reuse completed work only if the outcome is trustworthy. Inspect process/PID/log when available before relaunching; preserve unrelated user changes. Mark unresolved outcomes interrupted/unknown; never fabricate a completed run or silently restart its budget.

At each decision/hand-off, record a **continuation check**: target met (with evidence) or remaining user-visible gap, credible next test, measured budget remaining, and exact reason for stopping or continuing. A partial milestone is not the stopping reason. Do not classify an untried obvious alternative as a plateau.

Rebuild `state.md` from the authoritative records after each material decision or before a handoff. Include baseline and current accepted versions with verification scope, evaluation revision, remaining wall time and attempt/evaluation limits, current blocking question, relevant condition changes, and best feasible next test. If the journal grew large, summarize factual lessons and indexes separately, but retain original records. Carry forward contradictions and failed assumptions, not just successes. A new context should recover from these files without depending on the outgoing agent's conversation.

Use Git commits (or equivalent snapshots) for artifact changes; isolate parallel candidates and preserve exact ancestry. Revert only experiment-owned paths; when ownership is uncertain pause with evidence intact. Commit experiment notes separately when appropriate; never overwrite or clean unrelated user work for the sake of restoring a candidate.

## Fixed-count campaigns

For an explicit N, copy the external guard count into `state.md` after every recorded experiment, preserve evidence pointers and the reason for a rejected trial. Never hand off a partial count as a completed campaign; resume from its ledger rather than resetting the budget or counting a prior experiment again.

---
name: reflective-refinement
description: Improve an existing artifact or system through evidence-driven refinement, critical comparison and verified gains. Use for improving, optimizing, polishing or discovering what is worth improving in an existing result. Not a general project-delivery, roadmap or task-checklist skill.
metadata:
  version: '0.5.0'
---
# Reflective refinement

Improve the user’s actual outcome, not a proxy, score or number of edits. When effectiveness is primary, compare efficiency only after equivalent or improved outcomes; resource use may itself be the intended outcome. Use the minimum process yielding trustworthy evidence. An obvious correction needs one hypothesis, a valid comparison and a short record, not a tournament. No hooks, specific provider or global configuration required.

## 1. Establish the contract

Read the request and inspect the artifact in use. Resolve what should improve, for whom/in which conditions, and what must stay. A category (e.g. optimize) may not resolve the goal. If the outcome is open or materially ambiguous, use [discovery](references/discovery.md); skip for a resolved goal or existing contract. State grounded assumptions; ask only when a consequential choice/access remains unresolved. Never invent observations; suggestions do not authorize edits.

Before editing, record in `.refinement/` or existing project records (one file suffices for small work):
- Intent, scope/non-goals, observed gap, excellence anchors and strengths to preserve. Distinguish mandatory behavior from unfinished target quality.
- Primary outcome(s), observable success, meaningful gain, hard requirements, target and referenced trade-off limits (absolute, original, per-step, etc.). Preserve quality; count time/tokens only as intended or secondary. Do not substitute an easier metric.
- Evaluator, case identity, conditions, original outcome and guards. Match evidence to the goal; check that a relevant gain is detected and a misleading apparent gain is rejected where feasible. Include representative/adverse cases and usage states. Freeze acceptance; documented evaluator defects or authorized goal changes require a revised contract and comparable baseline.
- Starting revision, unrelated work, rollback, wall-clock start, user budget (otherwise up to 12 attempts including failures, within practical time/resource limits). Reserve confirmation/handoff capacity; count setup and actual costs.

Baseline = original; incumbent = best accepted at its recorded scope (initially baseline for comparison, not automatically admissible); candidate = unconfirmed trial. Preserve reproducible baseline/incumbent. Simple work needs only this core; load references as needed:
- Ambiguous measures, multiple kinds of improvement or substantial outcome validation: [outcome evidence](references/outcomes.md).
- Substantial evaluation: [shared decisions](references/evaluation.md) plus [quantitative](references/quantitative.md) for metrics/noise/regimes, [qualitative](references/qualitative.md) for judgment/visual quality, or relevant portions of both.
- Improving downstream outcomes of a prompt, workflow or skill: [method evaluation](references/methods.md). Pin the active controller outside editable candidates; judge downstream results, not instruction elegance.

## 2. Observe → hypothesize → test → learn

Before each cycle check budget and state; reconcile interrupted/unlogged work or invalid evaluation first.

**Observe and diagnose.** Inspect actual outcome and remaining gap; retrieve specific cases, contrasts, strengths, logs/screenshots, measurements and historical evidence. Separate facts and causal explanations. When causes compete, run a distinguishing test and try to refute the leader. Direct reproduction suffices for obvious issues; see [diagnosis](references/diagnosis.md) for uncertainty.

**Propose.** Target the most consequential remaining evidenced gap or the diagnostic that unlocks it, not an easy metric or cosmetic variation. Choose a coherent testable change. When uncertain, compare distinct mechanisms by evidence, expected benefit, falsifiability, cost, risk and learning value. Record parent, evidence, prediction, falsifier, test, scope and cost before editing. Coordinated changes are allowed when the mechanism requires them. See [exploration](references/exploration.md) for alternatives and selection.

**Implement.** Isolate/snapshot parent; preserve unrelated user work. Apply change and run planned comparison. Never alter acceptance, data or requirements to manufacture success. Untested hypotheses remain unresolved; a verified candidate failure can still violate a guard. Diagnose within budget.

**Evaluate.** Verify actual version, fresh output and comparable conditions. Cheap search probes guide selection; do not discard a plausible mechanism solely on an insensitive proxy. Promotion needs representative outcome evidence vs incumbent, independent guards where applicable and the affected end-to-end path. Plan negative/boundary cases early. Don't infer universal gains from favorable groups or invent workload weights. Judge qualitative outcomes from actual output, anchored criteria and localized evidence, not arbitrary scores. A valid deterministic comparison may suffice for simple work. Distinguish noise, prior/new defects, regressions and untested checks.

**Decide.** Promote only a valid, meaningful gain over incumbent (or demonstrated equivalence under a declared tie-break), within every frozen requirement and trade-off limit at its reference; don't reset cumulative allowances. Unknown guard defers approval. Confirm borderline gains or label uncertainty. Accept a staged milestone only within its declared scope; partial progress is not target completion. Pre-existing violations still prevent satisfying the requirement. Keep admissible specialist alternatives/evidence, not as global winners. Restore only experiment-owned changes on rejection.

**Learn.** Record prediction, realized evidence, separate execution/selection/hypothesis outcomes, uncertainty, cost, lesson and next action. Update the remaining gap and best verified outcome, not just the latest score. Keep rejection conditions; reconsider discards only when new evidence invalidates the rationale (not the same as replicating noisy runs). Preserve state and accepted revisions in Git or equivalent snapshots. Use [memory](references/memory.md) for recovery and archives.

## 3. Adapt the search

After about three valid non-improving attempts, recurring symptom or oscillation, recheck diagnosis/evaluator. Invalid trials aren't plateau evidence. Explore a distinct mechanism or parent. Use independent contexts when available and justified; otherwise sequential passes (not independent). Protect incumbent; use equal evaluation conditions and isolate/serialize shared resources.

Combine complementary parents only as a new experiment; test their strengths, interactions and boundaries. For condition-dependent gains compare setup/use costs; test an observable dispatch rule and crossover before promotion. Compare predicted with realized outcome gains/costs periodically; adjust next hypotheses, not acceptance. Recheck which remaining gap matters most and whether the current measurements can detect it. Stop at confirmed target, budget, irrecoverable blocker or defensible plateau after valid distinct exploration, not merely an empty backlog.

## 4. Confirm and deliver

Freeze the best candidate; confirm vs baseline on representative/adverse cases, including unexposed confirmation for adaptive/high-impact searches. Never tune against final confirmation and still call it untouched. If a required check fails or cannot run, preserve the best sufficiently verified version or report narrower scope. Report observed gains, retained strengths, costs, trade-offs/unknowns, evidence, stop reason and exact next action; hand off recoverable state. Claim only observed results; don't promise unsupported unattended execution.

[Worked examples](references/examples.md) illustrate decisions for open goals, workload-dependent and qualitative refinement. Read if useful, not as required templates.

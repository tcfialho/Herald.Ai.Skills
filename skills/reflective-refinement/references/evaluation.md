# Shared evidence and decision protocol

Use with [quantitative.md](quantitative.md), [qualitative.md](qualitative.md), or both as relevant.

## Contract and instrument

Freeze the contract. Name each material limit's reference (absolute, original, incumbent, explicit version or target), direction and cases. Enforce per-step and cumulative allowances where both apply; never reset the cumulative allowance after a keep. Separate diagnostic signals from the outcome; narrowing the goal or avoiding hard cases to improve a proxy is not progress.

Record baseline output, evaluator version/command/rubric, inputs, environment/seeds, conditions and output location. For substantial evaluation validate both sides: a meaningful improvement should be detected, unchanged/irrelevant results should not win, and misleading proxy gains should fail (see [outcomes.md](outcomes.md)). Repair an instrument that cannot distinguish relevant good/bad behavior. Don't damage the real artifact to make a control fail. Keep evaluator, acceptance and protected inputs outside editable scope. Document genuine evaluator defects and remeasure baseline, incumbent and compared candidates under the revised version. New diagnostics need not change acceptance. If the user changes goal/constraints, record authorization and new contract, rebaseline and start a separate segment. Don't mix revisions, relabel old outcomes or invent history.

## Three case roles, not three mandatory runs

| Role | Purpose |
|---|---|
| Search | Cheap matched comparison to parent, targeting the hypothesis. Not automatic promotion. |
| Promotion | Representative comparison to incumbent, with hard guards and cases not chosen for favorable outcomes. Independent of search proxy where feasible; exercise the whole affected path. |
| Final confirmation | For adaptive/high-impact searches, reserve new cases or an independent measure. Freeze first, compare original and selected candidate. If used to guide selection, replace or disclose that it is exposed. |

One valid deterministic comparison may serve all applicable roles in simple work. Cover critical invariants and implicated cases before searching; rotate other cases by risk/coverage. Group correlated examples; record roles and keep held-out answers out of search/fitting/selection. Recheck broader behavior before finishing. Without an independent set, use representative/adverse cases and disclose reduced confidence. Never tune against confirmation and still call it untouched.

## Provenance and differential checks

Identify actual code/renderer/output, revision/fingerprint, fresh log, run status, evaluator and conditions; check stale builds/caches and workspace isolation. Missing/mismatched identity invalidates evidence. Cache deterministic results only with complete identity (candidate, evaluator, case/split, conditions). Never cache transient failures or count caches as independent replicates.

Distinguish prior/new defects, regressions, instability and untested checks. A new test failing both versions reveals a defect, not necessarily a regression; formerly passing essential behavior now failing is a regression. Prior violations still block the relevant hard requirement. Unknown guards do not pass. Missing evidence of the new requested capability is not success merely because old behavior passes. An attributable deadline/crash/behavior violation is negative evidence even without a primary metric; a broken evaluator is not. Use relevant semantic, numerical, perceptual/API equivalence. Assess software correctness, simplicity, readability, style and maintainability separately; complexity counts only support judgment.

## Acceptance

Record each material dimension as better/equivalent/worse/unknown and evidence, in this order:

1. **Validity:** comparable protocol and usable evidence. Invalid/missing evidence cannot verify a claim; use [memory.md](memory.md) statuses, not fabricated scores.
2. **Requirements:** a violated essential guard blocks promotion; unknown guard defers it. No score compensates. Distinguish intermediate milestones from non-negotiable guards in advance; a milestone meeting its criteria and guards may become scoped incumbent, not final success. Progress violating a guard stays exploratory.
3. **Primary priorities:** meaningful improvement vs incumbent under the declared policy. Multiple objectives need explicit priorities or admissible trade-offs, not arbitrary averages. Check limits against their declared references before ranking gains vs incumbent. Check cumulative, end-to-end, regime and secondary costs; never trade protected qualities for a scalar gain.
4. **Tie/alternative:** a simpler candidate wins an equivalent tie only under a declared tie-break and demonstrated equivalence; log it as equivalent. Keep useful specialists separately, not as overall winners. Ask only about consequential preference-dependent trade-offs.

Try to refute material gains with adverse cases, varied subgroups, earlier failures or downstream effects. Classify robust in tested scope, partial/fragile, uncertain or refuted. Failed confirmation means no global verification; retain evidence, fall back to sufficiently verified result or state the narrower scope. An exposed failure informs future search but is no longer held-out validation. Claim only observed results.

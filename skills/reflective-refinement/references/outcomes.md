# Evaluate the intended outcome, not its proxy

Use when the primary objective/measure is uncertain, mixed, high impact, or hard to observe. An obvious deterministic correction with direct evidence needs no extra protocol. Select only relevant lenses, not a compulsory checklist.

## Translate intent to an observable result

Specify the user or downstream consumer, their job, the current gap, the observable difference that would matter, protection, and evidence. Distinguish the outcome, its measurement, and diagnostic signals. Examples: an optimized service might need latency, memory, throughput, cost or accuracy; a prettier screen is not necessarily easier to use; shorter code is not necessarily easier to change. When objectives compete, preserve hard limits and state priorities or report alternatives; a cheap-to-measure proxy cannot choose the user's preference.

| Intended improvement | Direct evidence to seek | Misleading on its own |
|---|---|---|
| Functionality or reliability | Required new or corrected behavior through actual inputs/use, boundary and failure/recovery cases; preserve existing behavior, data, authorization and invariants | passing only old tests, number of features |
| Performance or resource use | Actual latency/throughput/memory/cost under intended and adverse loads; complete path, same correct result | faster inner loop, fewer operations |
| Code organization or extensibility | Preserved behavior; evidence of safer/localized modification, a representative follow-up change where feasible, independent design review | lines, function count, complexity score |
| Usability or experience | Complete representative journeys with results, errors, recovery, accessibility and effort; observe actual interactions | fewer clicks that remove safeguards, aesthetics alone |
| Visual, writing or design quality | Actual output at relevant sizes/states, purpose/reference fit and criterion-specific judgment; fact and integrity floors | element count, keyword presence, pixel similarity |
| Comprehension or process | Consumer can make correct decisions or complete realistic tasks; measure failures and cost after success | shorter document, steps mentioned |
| Method, prompt or skill | Downstream quality over comparable tasks and resources, best verified outcome and decision trajectory, see [methods.md](methods.md) | instruction quality, tokens, number of edits |

Other domains: derive evidence from the artifact's actual purpose rather than forcing a listed category. User satisfaction, aesthetics and maintainability can remain partly unmeasured: don't invent a scalar or claim certainty because objective floors pass.

## Check that the evaluator measures what matters

Before substantial search define success plus meaningful gain and protected behavior. Prefer direct end-to-end evidence; use cheap probes as diagnostic hints. Ask whether an artifact could pass while failing the intended outcome, or a truly improved artifact could fail. Use a known correct/improved example, a valid unchanged/irrelevant improvement and a misleading apparent improvement or counterexample where feasible; they can be existing artifacts, tiny examples, analytical predictions or controlled mutations outside the real artifact. Compare to actual obligations, not a candidate's implementation. Test the instrument's coverage of required states/types, important boundaries, side effects and relevant subgroups. One direct deterministic repro and guard may establish sufficient evidence for a small fix.

If controls expose an evaluator defect, preserve the old results, document why, revise the instrument and re-evaluate baseline, incumbent and relevant candidates, including controls. Do not retroactively change the user goal. If validation is incomplete, narrow the claim; unknown quality is not a pass. If the user legitimately changes the target, create a separate contract.

## Improve the sequence of outcomes

At each material decision, inspect actual output vs contracted success and incumbent. Keep the best eligible outcome, selected candidate, remaining high-impact gaps and evidence of what changed. Prefer a hypothesis that closes a remaining important gap or tests the cause blocking it; avoid repeatedly polishing something already adequate. Evaluate new functionality against its own acceptance in addition to all old guards; a scoped milestone may improve capability without completing the task, never claim full success until the target is met. Do not make every exploration a promotion. A repeated snapshot of the same artifact is not a new gain or a new failed experiment. Rejected work is useful only through information it contributes to subsequent choices.

On a quality plateau seek a different mechanism or a missing discriminator before optimizing cost. For a resource objective, cost is itself quality; for other goals, compare efficiency only after equivalent or improved primary outcomes. Do not exchange effectiveness for lower cost without explicit authorization. End with the strongest verified artifact within the budget, showing observed outcome and limitations separately from effort.

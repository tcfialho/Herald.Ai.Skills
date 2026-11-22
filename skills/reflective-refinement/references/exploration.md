# Adaptive exploration and selection

Read when the next experiment is uncertain, the search stalls, or a better parent/strategy might exist. Keep the direct path for a clear, inexpensive change with a trustworthy evaluator.

## Route by evidence, not iteration number

Check limits first. Without an explicit fixed-count contract, stop when the target is confirmed, budget is exhausted or a blocker cannot be resolved within it. If the user specified N trials, preserve the count contract and report INCOMPLETE until N valid trials or an actual blocker/budget/user stop. Reserve resources for representative promotion and final confirmation before another candidate. For an active session, use the first applicable action:

| Current state | Next action |
|---|---|
| Required evidence/runner invalid or unstable | Repair or diagnose the evaluator; do not count invalid runs as evidence of a plateau |
| Promising candidate awaits reliable evaluation | Confirm or explicitly mark unverified; do not switch to a new idea to avoid the test |
| Causes compete or failure mechanism is unidentified | Run a discriminating diagnostic (see [diagnosis.md](diagnosis.md)) |
| Repeated modifications to the same symptom, oscillating strategies, or about three valid non-improving experiments | Re-examine evidence and evaluation sensitivity, then explore a distinct approach or another parent |
| Two retained candidates solve complementary problems and their combination is the most promising next test | Consider combination as an independent experiment, if feasible |
| A current bottleneck has a credible, testable, cheap remedy | Refine locally |
| No useful direction after a valid distinct exploration | Report a defensible plateau and best verified version |

Use the thresholds as heuristics, not a claim of optimality. Repeated invalid or blocked runs need recovery or a blocker report, not a plateau verdict. An empty ideas list is not proof that quality has converged. When progress is possible and within budget, seek a new discriminating observation; do not manufacture repetitive or meaningless trials merely to satisfy a count; an explicit N remains binding and unmet attempts must be reported as INCOMPLETE.

## Select a high-value experiment

When uncertain, propose two or three materially distinct mechanisms supported by current evidence or a specific gap. Consider the strongest historical contrasts and rejected assumptions that have changed. Prefer the next test that can identify or remove the most important bottleneck or reduce consequential uncertainty at a reasonable cost. Record alternatives but do not combine competing proposals before a result unless the hypothesis itself tests their interaction.

Critique the proposed hypotheses lightly before spending on them:

- Is there relevant, current evidence for the mechanism, not just a convincing explanation? What contradicts it?
- What concrete observable result would falsify it? Does it even address the primary outcome or merely a secondary proxy?
- What gain is plausible, how much headroom remains, and what would it cost in time, complexity and risk?
- Could a diagnostic or small feasibility prototype distinguish the idea more cheaply than building it? Does the prototype systematically disadvantage approaches whose benefits emerge only at full scale?

A proposal may be defended, revised, deferred until a diagnostic, or abandoned. No testable prediction means it is not yet an experiment. If comparison is ambiguous and consequential, rank proposals head-to-head with common criteria (grounding, plausible impact, testability, preservation, cost and information gained). If using an evaluator, compare both orders and allow ties; qualitative rankings are predictions, never observed gains. A credible critique can be accepted or rejected with counter-evidence. Do not require a tournament for small edits.

For complex qualitative revisions, separate the evidence review from the decision: collect observed strengths, contradictions, missing evidence and specific possible actions; verify serious criticisms instead of demanding negative findings. Focus on the few issues limiting the intended quality. Do not silently reduce the essential ambition to satisfy a critic. Try a genuinely alternative author and, if useful, a synthesis; judge A, B and the synthesis on actual outputs under the same contract without revealing authorship. Keep distinct alternatives when blending removes what makes them valuable.

## Explore without losing useful progress

When local refinement saturates, the next useful move is often a distinct mechanism, not another parameter tweak. Options:

- Start a small branch from the incumbent with a different mechanism, or from a specialist parent whose evidence is relevant. Keep incumbent unchanged.
- Where independent contexts are supported, compare a history-guided branch with one fresh interpretation of the same goal, constraints, relevant observations and evaluation contract (omit the dominant agent's diagnosis and proposed solution). Both receive the facts needed to avoid invalid work; neither receives held-out evaluation answers.
- If a rival family has meaningful potential but improves more slowly, grant it a bounded separate opportunity before dropping it. Compare families under the same fixed metric, cases and resource limits, sharing concrete findings rather than forcing them into the same architecture.

Use independent subagents only if the host supports them and the additional cost is justified. Otherwise use distinct sequential passes, explicitly acknowledging they are not independent. Give each branch a limited test budget and an isolated workspace or snapshot. Do not allow parallel evaluation to distort hardware-sensitive metrics; serialize or isolate resources. Track actual time and evaluation calls across branches. Do not reset or exceed the overall budget. Candidate selection is based on evidence and guards, not on the branch's self-reported success.

## Combine only after understanding the strengths

Select evaluated parents with complementary mechanisms or cases, compatible interfaces and a clear reason the combination might outperform the incumbent. If ancestry is available, use the common starting point to identify independent changes. Name the contribution from each parent, conflicting assumptions and predicted interactions. Build the combination in isolation as a new candidate and evaluate it against both parents and incumbent on their common cases and individual strengths; all acceptance guards remain in force. Individual gains are not necessarily additive. If a combination wins and attribution matters, remove one component at a time or run another discriminating comparison. Keep separate parents when the combination fails or destroys a strength.

## Calibrate the search, not the target

Periodically review the journal (e.g. after a few valid evaluations, a major discovery, or a context handoff). Compare original predicted effects, confidence and realized outcomes. Identify which evidence and mechanisms have predicted meaningful gains, which types of attempts repeatedly fail and which deliver improvement relative to actual cost. Separate refuted hypotheses from invalid measurements and failed implementations. Check for selection bias: outcomes for unexecuted proposals are unknown, so a winner's success does not prove alternatives would lose. Occasionally test a strong competing proposal when ambiguity/cost justifies it.

Adjust how you select future experiments gradually: prefer productive evidence, refine cost estimates, or redirect remaining budget toward a new mechanism. Keep original acceptance criteria and held-out evidence fixed. If changing a ranking heuristic, record the reason and observe future predictions; do not declare statistical calibration from a few selected outcomes. Avoid numerical weight updates unsupported by sufficient comparable results.

Keep a deduplicated backlog by problem, mechanism and applicable conditions, not wording. Each useful idea names evidence, scope/dependencies, expected effect, falsifier and cost. Retire stale assumptions and re-rank after new findings. Search external examples or literature only when internal evidence does not resolve an important question; record source relevance and contradictory evidence, and test transferability rather than assuming that success elsewhere applies here.

When feedback exceeds context capacity, partition it by mechanism/case or component, inspect distinct groups and synthesize useful patterns with links to the original records. Preserve uncommon failures, contradictions and protected strengths; sample representative cases as well as worst scores. Do not repeatedly load or summarize the entire historical conversation. See [memory.md](memory.md) for recoverable state and archive.

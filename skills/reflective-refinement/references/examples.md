# Worked examples of decisions

Illustrative, not required templates. Keep the evidence and reasoning; don't copy the numerical values or thresholds to unrelated tasks.

## Unspecified improvement

Request: "Improve this report generator." Running a realistic report reveals wrong totals for repeated categories, a slow export on large input, and uneven headings. The user has not named a priority. The totals issue affects correctness and is reproducible, the performance issue needs a usage/latency baseline, and heading polish has a smaller demonstrated effect. Select the totals defect; preserve output schema and existing formatting. Establish a reproduction, compare against an independently calculated total and recheck other categories. Stop when the scoped issue is confirmed; leave the other two as suggestions unless budget and agreed scope justify them. If the request had only asked what to improve, return these choices instead of editing. If the user explicitly wanted nicer headings, the priority would be different.

## Apparent speedup with two specialists

An index makes repeated queries faster but costs time to build. Measure setup and query work separately; include zero, one, many and intermediate counts, different densities and protected output equality. Suppose scanning wins at one or two queries, prepared tokens win at a few, and indexing wins at many. Archive specialists and propose a dispatch rule based on query count and available workload indicators, with a simple fallback. Record threshold and planned probes just below/at/above it. Compare the hybrid against both relevant parents plus incumbent; verify it does not change ordering or duplicates. If the final set fails at an intermediate count, report the scope failure rather than adjust and declare victory on the same set. Use it as new diagnostic evidence, then reserve fresh confirmation for a new trial.

## Judging against a real quality reference, not just the last version

When a user says "bring this into line with the proven native UI", freeze a quality example from the native experience separately from the imperfect current version. The review compares anonymous A/B outputs against that reference and the user's actual task. If B is better than A but still cannot support the intended interaction, retain the scoped improvement only if guards pass; report `target_completion=NOT_MET`, not DONE. The exemplar is evidence of a quality dimension, not a template to clone literally. This also applies to a verified example document or a service behavior trace, not only to screenshots.

## Quality without a numeric score

Request: "Make this onboarding screen exceptional, like the reference." Identify the actual job and constraints. The reference has a clear first action, a readable progression and unobtrusive help; the current screen hides the action and truncates labels in a narrow layout. Keep all required fields and identity. Compare rendered versions at relevant widths and exercise the error/success paths. Predict that hierarchy and spacing changes will make the next action obvious without hiding help; check those actual regions and states. A visually bolder alternative may be useful but isn't automatically better. If a critic prefers it solely on taste, record the preference or allow a tie; don't invent user evidence. If narrow layouts still clip, reject global promotion until fixed. No numerical grade needed.

## Incremental gain with cumulative erosion

An export starts at 100 ms. The primary goal is lower memory and the contract allows at most 10% slower latency than the original. One accepted candidate takes 108 ms; the next takes 116 ms. Although the next uses less memory and loses only 7.4% vs incumbent, reject it: the fixed ceiling is 110 ms. If both per-step and final limits are stated, enforce both. If the user authorizes a higher ceiling, record a new contract and baseline rather than retrospectively passing failed candidates.

## Broad visual refinement must continue after local wins

Request: "Improve the generated track verges; they look flat and monotonous compared with the built-in tracks." View generated and built-in examples from the in-game camera, including weak scenes. Define target qualities from observation: layered ground-to-road transition, varied surface and props, depth/scale, consistency across tracks; preserve driveability and native tracks. First experiment improves only grass color, with successful tests and screenshots. **Do not stop**: the continuous flat band is still visible and the native reference is not matched. Next test may vary material transitions or nearby geometry; later test props/vegetation or rail where the reference supports them. After each accepted step compare real views again, then take the next plausible in-scope action while budget remains. If one alternative fails, learn and try another mechanism; do not announce plateau. Ask for preference only if evidence cannot resolve a consequential choice; "do what looks best" delegates routine decisions. A confirmed match, actual budget exhaustion, blocker or evidenced plateau permits stopping; leave exact residual gaps and next test on interruption.

## Partial success with a frozen DONE WHEN contract

Request: "Improve customer refund handling and make sure it is fully robust." Preserve existing payment rules and correctness tests as `hard_checks`. Select representative and adverse cases before changing code: repeated refund, timeout, partial refund, cancellation, malformed request, and ledger reconciliation. A candidate that improves ordinary refunds but fails timeout recovery may be an admissible **scoped** improvement if it preserves all hard guards. The full feature remains `target_completion=NOT_MET` until independent `target_checks` also pass. Do not replace this completion check with fewer lines, high test count, or one passing scenario.

## Qualitative goal with multiple protected outcomes

Request: "Make the support interface easier to use, but do not let actions affect the wrong ticket." Define the main journey, keyboard journey, undo/recovery and unintended-target states. A blind result-only judge can compare screenshots and task recordings against named criteria; a scripted target/undo test enforces behavioral correctness. Freeze `priority_order` and protect ticket identity as a hard check plus any applicable protected reviewer criterion. Reducing an eight-click journey to two clicks is NOT sufficient if it accidentally resolves another customer's ticket. Prefer a four-click version with correct behavior. A reviewer may report genuine progress while the user goal remains unmet on the keyboard path.

## A performance target with noisy extremes

Request: "Optimize GPU throughput without frames visibly stalling." Measure repeated same-version medians and raw-tail samples on the same workload. Record permitted max-frame bound as a frozen `sample_guard`, not a post-hoc metric. A run with 7 ms average and 19 ms stall fails that guard even if the candidate beats the incumbent on average. Do not pretend a single run proves a deterministic maximum in all circumstances; state observed scope, noise and unseen workloads.

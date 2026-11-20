# Worked examples of decisions

Illustrative, not required templates. Keep the evidence and reasoning; don't copy the numerical values or thresholds to unrelated tasks.

## Unspecified improvement

Request: "Improve this report generator." Running a realistic report reveals wrong totals for repeated categories, a slow export on large input, and uneven headings. The user has not named a priority. The totals issue affects correctness and is reproducible, the performance issue needs a usage/latency baseline, and heading polish has a smaller demonstrated effect. Select the totals defect; preserve output schema and existing formatting. Establish a reproduction, compare against an independently calculated total and recheck other categories. Stop when the scoped issue is confirmed; leave the other two as suggestions unless budget and agreed scope justify them. If the request had only asked what to improve, return these choices instead of editing. If the user explicitly wanted nicer headings, the priority would be different.

## Apparent speedup with two specialists

An index makes repeated queries faster but costs time to build. Measure setup and query work separately; include zero, one, many and intermediate counts, different densities and protected output equality. Suppose scanning wins at one or two queries, prepared tokens win at a few, and indexing wins at many. Archive specialists and propose a dispatch rule based on query count and available workload indicators, with a simple fallback. Record threshold and planned probes just below/at/above it. Compare the hybrid against both relevant parents plus incumbent; verify it does not change ordering or duplicates. If the final set fails at an intermediate count, report the scope failure rather than adjust and declare victory on the same set. Use it as new diagnostic evidence, then reserve fresh confirmation for a new trial.

## Quality without a numeric score

Request: "Make this onboarding screen exceptional, like the reference." Identify the actual job and constraints. The reference has a clear first action, a readable progression and unobtrusive help; the current screen hides the action and truncates labels in a narrow layout. Keep all required fields and identity. Compare rendered versions at relevant widths and exercise the error/success paths. Predict that hierarchy and spacing changes will make the next action obvious without hiding help; check those actual regions and states. A visually bolder alternative may be useful but isn't automatically better. If a critic prefers it solely on taste, record the preference or allow a tie; don't invent user evidence. If narrow layouts still clip, reject global promotion until fixed. No numerical grade needed.

## Incremental gain with cumulative erosion

An export starts at 100 ms. The primary goal is lower memory and the contract allows at most 10% slower latency than the original. One accepted candidate takes 108 ms; the next takes 116 ms. Although the next uses less memory and loses only 7.4% vs incumbent, reject it: the fixed ceiling is 110 ms. If both per-step and final limits are stated, enforce both. If the user authorizes a higher ceiling, record a new contract and baseline rather than retrospectively passing failed candidates.

# Outcome-first evaluation and independent judgment

Load this when the goal, benchmark, reviewer, or promotion decision is nontrivial. The **primary objective is the effect on the user**, not smaller source, fewer tokens, more objects, more iterations or a higher self-assigned score. Benchmarking and judging are complementary, not interchangeable.

## Before any experiment: classify the real improvement

Inspect the actual artifact in use. Categorize the goal (multiple categories are allowed):

| User goal | Primary evidence | Hard regressions/other evidence |
|---|---|---|
| New functionality / fix | New behavior and boundary/negative cases | Existing behavior, safety, data integrity |
| Performance | Full-task timing/memory over small, typical, worst and crossover workloads | Exactly equivalent output, memory/latency guardrails |
| Visual / graphics | Comparable rendered screenshots or in-game video in matched states, reference comparisons | Correct geometry, clipping, legibility, FPS; **independent blind visual judge** |
| UX / usability | Real task completion, errors, keyboard/recovery, user-visible interactions | Other users, unintended side effects, accessibility; independent result judge |
| Maintainability | Make a representative follow-up change and preserve tests | Readable/scoped code and a *separate* code-aware review (not a blind visual judge) |
| Documentation | Reader executes instructions correctly, consistency and facts | Missing contradictions and factual errors; relevant reviewer |
| Skill/prompt | Quality of downstream agent results, per-case and over iterations | Equal budget and test data, hallucinations, hidden judge bias |

If the request is vague, inspect first, infer likely value from observable deficiencies, and select a reversible opportunity plus observable success. If there are materially different preferences with no evidence, ask **one** discriminating question. Do not assume "optimize" means speed and do not ask permission to continue ordinary delegated improvements.

When Python is available, start with `python scripts/contract_init.py --goal '...' --output PROJECT/.refinement/evaluation.draft.json`, adapt the draft using actual baseline, scenario IDs, typed metrics, and frozen checks; remove `draft` only when those facts are established. Run `evaluation_gate.read_contract()` to validate. The scaffold is deliberately not an executable scoring contract. A user-provided N is a binding number of experiments, not a quality target.

## Contract and measurement, owned outside the worker

Versioned JSON fields: `schema_version=1`, `kind`, `primary_outcome`, `case_ids`, `hard_checks` (each `argv` + timeout), `benchmark` (`argv` outputting JSON), `primary_metrics` (name, higher/lower, frozen reference, minimum_gain), `protected_paths`, `review` (required, criteria, calibration/reversal) and `reference_evidence` (case→file). Freeze the contract before iterating and protect its bytes, test script and evaluation cases. Never let the implementing worker adjust rubric, target or the baseline to pass. If the evaluator is defective, version the contract and compare candidates again under the repaired procedure rather than silently changing results.

Benchmark stdout must be a **single JSON object** containing `schema_version=1`, `case_ids` matching the contract, `guards` with true results for mandatory behavior and `metrics` with measured numerical values. The gate checks both the original reference and the best *verified incumbent*. A stage metric that improves while the actual user experience does not is diagnostic, not promotion evidence. Unknown/noisy/invalid data produces `HOLD`, not a zero or invented result. A failed mandatory guard gives `REJECT` regardless of the other scores.

Independent controls: known-bad example should fail; A=A should tie; cases with a proxy win and damaged behavior must fail. For timing, compare repeated same-version measurements under matched conditions and isolate workloads from other performance processes. For UI, take reproducible screenshots of the **actual running application**, with the same camera, state, lighting, size and input. An image supplied solely by the implementing agent has lower provenance than an externally captured screenshot; mark uncertainty honestly.

## Outcome contract: relative gain is not final success

The independent-game example [Abyssal Garden](https://github.com/Noniv/abyssal-garden/blob/main/prompt.txt) and its later [Uno adaptation](https://github.com/viktorkav/uno-com-escada/blob/main/pedidos/01-circuito.txt) froze an order of priorities, forbidden shortcuts, independent output-only critics, representative user situations and an explicit **DONE WHEN** checklist. We already use many of these: outcome-first selection, frozen guards, source-free A/B review, known-bad calibration, external promotion and persistent loop receipts. The general improvements are below, not universal camera/video requirements.

- `priority_order` (optional ordered strings): evaluate the user's most important objective before optimizing secondary characteristics. Give these to the blinded reviewer. Code-enforce hard numeric/behavior constraints rather than asking a reviewer to overlook them.
- `review.criterion_guidance` (required when `quality_gate` is configured; otherwise optional object mapping every criterion ID to a concrete observable condition): avoid meaningless rubric labels like "good", "nice", "polished". For outcomes such as ease of use, specify the actual journey and where failure is seen; for documentation, a concrete reader decision; for graphics, rendered regions and consistency.
- `review.target_reference_evidence` (optional scenario-ID→file mapping): provide *examples of the requested quality* separately from the current incumbent. A/B stay anonymous, while the reviewer sees target examples (rendered output, reference document or behavior report) to determine if either reaches the actual goal. Source files remain excluded; the controller pins these references against edits. Do not blindly imitate a stylistic exemplar when it conflicts with user intent.
- `review.required_nonregression` (optional list of existing criterion IDs): a reviewer cannot prefer the candidate overall if it loses a protected criterion. An uncertain protected result returns HOLD; a demonstrated loss returns REJECT. Deterministic invariants still belong in `hard_checks`, not in subjective judgment.
- `review.quality_gate` (optional for qualitative work): define `max_remaining_severity`, `coverage_groups` (case IDs covering the frozen cases) and optional `severity_anchors` and distinct `confirmation_group`. The **anonymous** reviewer inspects both A and B separately and writes `quality_by_label.A` and `.B`, each with per-case observations and evidence-backed severity findings. Only the supervisor knows which label is the candidate. A relative A/B win may still be below the final quality target.
- `target_checks` (optional, independent argv commands) verify **full target completion**, separately from `hard_checks` which protect promotion of intermediate progress. A failed target check yields `target_completion=NOT_MET` without automatically discarding a correctly scoped improvement. An unexecutable check yields UNKNOWN. Keep/Reject/Hold always answers whether to promote; MET/NOT_MET/UNKNOWN/NOT_CONFIGURED answers whether to stop for success.
- `sample_guards` (optional metric name and min/max) inspect **each** raw value, not merely an average. They detect rare correctness/performance failures that a favorable median masks. Do not apply this to noisy measurements without a meaningful, fixed statistical protocol and tolerated error rate.

Examples across categories: functionality can preserve existing tests (`hard_checks`) while checking the full new behavior (`target_checks`); performance can promote an improved median while checking tail or maximum values in `sample_guards`; UX can require successful journey and recovery plus a blind criterion-specific review; documentation can require accurate instructions and the reader's ability to perform the steps; maintainability needs behavioral tests plus a separate code-aware review, **not** a result-only judge pretending to see internal structure.

The reviewer is an evidence source, not an infallible authority. Calibrate on identical and known-bad examples; keep uncertainty explicit. A source-free prompt alone is not a secure filesystem sandbox. Do not copy the source example's fixed six-camera protocol, 60-second duration or GPU numbers onto unrelated projects.

## Two distinct layers before a promotion

1. **Executable benchmark.** Supervisor runs pinned tests/measurements from the frozen contract and creates an evaluation report. This layer is authoritative for deterministic correctness and measured trade-offs.
2. **Independent result judge where meaningful.** For appearance/UX, use a new subagent/model session that receives only a source-free evidence bundle: frozen user goal, anonymous A/B rendered results or recordings, rubric, optional verified benchmark summary. Do **not** include source, diff, commit ID, author or previous judge opinions. Comparison may be reversed to reduce order bias; ties and uncertainty are legitimate. Require observations per criterion and actual scenario IDs; calibrate A=A and a known-bad control when available. For maintainability, a *different* code-aware reviewer is permitted, because output-only evidence cannot establish architecture quality.

The worker may record a proposed `keep`, but **only the external promotion gate can establish `KEEP`**. In a fixed-N campaign, the ledger first marks it `pending`; external evaluation resolves it to `keep`, `discard` or `hold` and records the report hash. Unverified trials count toward user-requested N only if a genuine changed candidate was tested; they are never described as improvements. Reject/hold restores only the artifact in scope when safe, while retaining a patch and evidence; unexpected unrelated work blocks automatic restoration.

## Harness and isolation capabilities

The skill and evaluation gate are standard Python 3 with no global hooks. Use native independent subagents if the host supports them; otherwise use a fresh supported CLI process (Codex or Claude). AGY/Antigravity and other providers are supported through a configured **argv adapter**, not a guessed unsupported command. The supervisor may be started by the host agent from the installed skill for explicit N; if the host cannot spawn another session, keep honest in-turn records and report the limitation.

A fresh process with only a source-free bundle in its prompt is **context-blind**, not necessarily filesystem-isolated. If the judge can read the original workspace through the operating system, report `source_isolation=not_enforced`—never claim it is cryptographically or filesystem isolated. Genuine source isolation requires a verified OS sandbox or separate machine/container with only the bundle mounted. No code path should be presented in the result-only judge's prompt.

## Outcome report and adaptation

For each experiment report: candidate identity, cases and exact render/test artifacts, metric values, guard failures, anonymous reviewer observations, uncertainty, decision (KEEP/REJECT/HOLD), proven scope and remaining user-visible gap. Revisit failed hypotheses only when a condition materially changed. Choose the next hypothesis using the **observed failure** rather than the worker's own claim. Maintain the best verified incumbent, not the latest or most visually polished response. Explicit-N campaigns still make honest attempts until N or a genuine blocker; they must not manufacture changes to fill the count.

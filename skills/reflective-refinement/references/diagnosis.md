# Causal diagnosis and experiment design

Use when the next change is unclear, symptoms recur, evidence disagrees, or a structural change is plausible. For a straightforward correction, one concrete observation, prediction and test are sufficient.

## Evidence that informs the next experiment

Inspect actual outputs, especially contrasting successes and failures. Use the smallest set that explains the current bottleneck; do not ask the agent to infer a mechanism from a score alone.

For each useful case record:

| Field | Contents |
|---|---|
| Identity | Case, input or reproduction, evaluated version, conditions |
| Observation | Actual output, artifact/log location, relevant metric or localized qualitative difference |
| Expected | What the contract/reference requires in this case |
| Contrast | A similar successful case, parent result, or older version that handles this aspect better |
| Interpretation | Plausible cause, alternative explanations, uncertainty; keep separate from facts |

Group cases by likely mechanism, not just by score or symptom. For large outputs, inspect representative examples, worst cases and unusual failures; retain their IDs and links. Retrieve relevant historical case evidence from the archive (see [memory.md](memory.md)). If multiple mechanisms share the same symptom, distinguish them before selecting a broad fix.

Trace the user's outcome through relevant stages, interactions, components or regions. Identify where degradation first becomes visible and what remains healthy. For instance, distinguish a shorter CPU submission time from unchanged end-to-end frame time. An improvement in an intermediate measurement that fails to improve the target is still evidence about the mechanism, not a promotion.

## Distinguish competing causes

When plausible causes imply different remedies:

1. State at least two live explanations and the observations each predicts. Identify what they both explain and where their predictions differ.
2. Choose the cheapest safe observation or probe that would most reduce uncertainty. Techniques include minimal reproduction, comparing working and failing cases, component isolation, input/condition variation, tracing, profiling or locating the revision where behavior changed.
3. Run the probe; eliminate contradicted explanations, retain plausible ones, and record inconclusive results. Do not commit speculative changes just to support a favored theory.
4. Give the leading explanation an honest chance to fail; if consequences justify it, confirm a separate prediction not used to choose it. If causes remain indistinguishable, record that and test the remedy without claiming a proven cause.

Example: flickering geometry could be depth precision or stale draw data. Freeze the camera and compare geometry/depth values and frame IDs; vary depth range independently. Pick a test that separates these causes instead of repeatedly changing material parameters.

## Predict before editing or running the experiment

Make one prospective entry. A short entry is enough for a reversible, obvious change. For complex or expensive experiments, detail the individual observations that can discriminate the mechanism.

```markdown
Parent: <version>; evidence: <case/log/measurement references>
Question: <decision this test will enable>
Hypothesis: <change -> mechanism -> outcome>; alternative: <if material>
Prediction: <direction/magnitude or observable difference>; confidence: <low/medium/high>
Test: <cases, method, necessary diagnostics and protected behaviors>
If supported: <expected output or pattern>
If contradicted: <different observation>; if ambiguous: <next distinguishing test>
Cost: <time/evaluations>; scope: <files/artifact/components>
```

Write this before observing the new result. Add diagnostic instrumentation only when needed, without changing the acceptance measure; keep it equally applicable to compared versions. A coordinated change is allowed when the mechanism genuinely requires it. Record which components changed and test removal of an individual component if attribution or interaction matters.

Execute the planned observations or explicitly mark unavailable ones. Compare results against the original prediction, including unexpected effects and affected strengths. When a result is ambiguous, use the planned follow-up rather than rewriting the prediction to match it. If an important unknown emerges, add a new probe; preserve the original test and result.

## Broaden the hypothesis set when needed

Choose among mechanisms supported by the evidence: remove a bottleneck; change a condition or threshold; reveal a hidden constraint or interaction; test a credible opposite assumption; transfer a proven idea from another domain; or replace the underlying approach. Do not manufacture diversity by renaming parameter variations. New measurements, not novelty alone, justify the next hypothesis.

# Output Contract & Evidence Matrix

Authoritative definition of the diagnostic report format. Phase 4 output MUST follow this contract exactly.

```yaml
output_contract:
  section_order: [Incident, Hypotheses, Root_Cause, Fix_Proposal, Residual_Risks, Verification_and_Validation, Prevention, Decision]
  closing_line: '"Do you confirm the execution of this Fix_Proposal?"'
  formatting:
    - 'Incident: markdown table | Field | Value |. No prose between sections.'
    - 'Hypotheses and Root_Cause: wrap ASCII trees in ```text blocks to preserve ├── └── │ characters.'
    - 'Fix_Proposal, Residual_Risks, Prevention: bullet lists (- item).'
    - 'Verification_and_Validation: bullet list (Plan + Expected outcome).'
    - 'Decision: Fix_Proposal_Status (pending_confirmation|confirmed|rejected), Decision (Go/No-go), Next_Step.'

  quality:
    Incident: 'Symptom=what user sees not interpretation, Impact=scope+degree, Environment=OS/runtime/versions, First Seen=trigger correlation, Frequency=reproducibility, Probable Cause=evidence-based guess refined in Root_Cause'
    Hypotheses: |
      ASCII tree: Root "PROBLEM: ...", 1st level [AND]/[OR], 2nd level [CAUSE 1]..[CAUSE N] (maximum limit of 5).
      CRITICAL: You MUST generate EXACTLY as many hypotheses as necessary to exhaust all evidence-backed possibilities, up to a strict maximum of 5. Whether it is 1 or 5, every single plausible angle MUST be mapped.
      Inside causes: FREE MIX of UPPERCASE-labeled lines (BEFORE:, AFTER:, EFFECT:, STATUS:, etc.) and plain descriptive lines. Labels open-ended — invent as needed.
      Each cause must be independently falsifiable with forensic detail. Cite specific log lines, config values, code paths.
      Confidence [0.00-1.00] per hypothesis. Include What_Changed. Rank by likelihood if all low.
    Root_Cause: |
      TWO parts: PART 1=ASCII tree (root=short problem label, branches=[PRIMARY ROOT] and ONLY IF APPLICABLE [SECONDARY ROOT] / [CONTRIBUTOR], same label/text mix as Hypotheses).
      PART 2=Declarative summary ("PRIMARY ROOT CAUSE: CAUSE N" + bullet WHY, optionally one line per secondary/contributor IF they exist).
      Must reference evidence that confirms cause AND excludes alternatives. Chain must be complete. Every root traces to supported hypothesis. Contradictions resolved or flagged.
    Fix_Proposal: 'Each fix tied to confirmed root cause. Include rollback/containment path + trigger criteria. Note residual vulnerability.'
    Residual_Risks: 'Impact assessment + probability — not generic platitudes.'
    Verification_and_Validation: 'Objective measurable criteria: how do we KNOW the fix worked?'
    Prevention: 'Controls tied to root cause class — linter rules, type constraints, alerts, tests, process gates.'
    Decision: 'Explicit user approval required before Phase 5.'

  supplementary: ['Evidence_Matrix (full)', 'Sources_Consulted', 'Sources_Unavailable + confidence impact', 'Telemetry']

  output_skeleton: |
    ## Incident
    | Field | Value |
    |---|---|
    | Symptom | {symptom} |
    | Impact | {impact} |
    | Environment | {environment} |
    | First Seen | {first_seen} |
    | Frequency | {frequency} |
    | Probable Cause | {probable_cause} |

    ## Hypotheses
    ```text
    PROBLEM: {symptom}
    ├── [AND] {group description}
    │   ├── [CAUSE 1] {title}
    │   │   ├── {LABEL}: {description}
    │   │   ├── {plain description}
    │   │   └── STATUS: {state}
    │   │
    │   └── [CAUSE N] {title}
    │       ├── {LABEL}: {description}
    │       └── STATUS: {state}
    ```

    ## Root Cause
    ```text
    {problem label}
    ├─ [PRIMARY ROOT] {title}
    │  ├─ {LABEL}: {description}
    │  └─ {consequence}
    ├─ (If applicable) [SECONDARY ROOT] {title}
    │  └─ {description}
    └─ (If applicable) [CONTRIBUTOR] {title}
       └─ {description}
    ```
    PRIMARY ROOT CAUSE: CAUSE N
    - {WHY reasoning}
    (If applicable) SECONDARY ROOT CAUSE: CAUSE N ({explanation})
    (If applicable) CONTRIBUTING CAUSE: CAUSE N ({explanation})

    ## Fix Proposal
    - {fix}
    ## Residual_Risks
    - {risk}
    ## Verification_and_Validation
    - Plan: {plan}
    - Expected outcome: {criteria}
    ## Prevention
    - {control}
    ## Decision
    - Fix_Proposal_Status: pending_confirmation
    - Decision: Go / No-go
    - Next_Step: {step}
```

```yaml
evidence_matrix_contract:
  columns: [hypothesis_id, root_class, hypothesis, evidence_for, evidence_against, falsification_test, confidence_score_0_to_1, status]
  status_values: [supported, refuted, open, disproven]
  rules: ['Root-cause eligible only when status=supported AND evidence_for >= 2', 'Every hypothesis needs falsification_test', 'At least one independent source in evidence_for', 'Contradictions as separate rows']
```

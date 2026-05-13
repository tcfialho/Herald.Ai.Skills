# Output Contract & Evidence Matrix

Authoritative definition of the diagnostic report format. Phase 4 output MUST follow this contract exactly.

```yaml
output_contract:
  section_order: [Incident, Hypotheses, Root_Cause, Fix_Proposal, Residual_Risks, Verification_and_Validation, Prevention, Decision]
  diagnostic_outcomes: [confirmed_defect, confirmed_visual_or_ux_issue, no_defect_confirmed, misframed_symptom, insufficient_evidence]
  closing_line: 'Use "Do you confirm the execution of this Fix_Proposal?" only when Fix_Proposal_Status=pending_confirmation. For diagnostic-only outcomes, close with the concrete No-go or clarification next step instead.'
  formatting:
    - 'Incident: markdown table | Field | Value |. No prose between sections.'
    - 'Hypotheses and Root_Cause: wrap ASCII trees in ```text blocks to preserve ├── └── │ characters.'
    - 'Fix_Proposal, Residual_Risks, Prevention: bullet lists (- item).'
    - 'Verification_and_Validation: bullet list (Plan + Expected outcome).'
    - 'Decision: Diagnostic_Outcome, Fix_Proposal_Status (pending_confirmation|confirmed|rejected|not_applicable|needs_clarification), Decision (Go/No-go), Next_Step.'

  quality:
    Incident: 'Symptom=what user sees not interpretation, Impact=scope+degree, Environment=OS/runtime/versions, First Seen=trigger correlation, Frequency=reproducibility, Probable Cause=evidence-based guess refined in Root_Cause, Failure Type=claimed_failure_type from symptom_reality_gate'
    Hypotheses: |
      ASCII tree: Root "PROBLEM: ...", 1st level [AND]/[OR], 2nd level [CAUSE 1]..[CAUSE N] (maximum limit of 5).
      CRITICAL: You MUST generate EXACTLY as many hypotheses as necessary to exhaust all evidence-backed possibilities, up to a strict maximum of 5. Whether it is 1 or 5, every single plausible angle MUST be mapped.
      Inside causes: FREE MIX of UPPERCASE-labeled lines (BEFORE:, AFTER:, EFFECT:, STATUS:, etc.) and plain descriptive lines. Labels open-ended — invent as needed.
      Each cause must be independently falsifiable with forensic detail. Cite specific log lines, config values, code paths.
      Confidence [0.00-1.00] per hypothesis. Include What_Changed. Rank by likelihood if all low.
      If Diagnostic_Outcome is no_defect_confirmed or insufficient_evidence, list only the evidence-backed possibilities that were checked; do not invent a fixable cause just to fill the tree.
    Root_Cause: |
      TWO parts: PART 1=ASCII tree (root=short problem label, branches=[PRIMARY ROOT] and ONLY IF APPLICABLE [SECONDARY ROOT] / [CONTRIBUTOR], same label/text mix as Hypotheses).
      PART 2=Declarative summary ("PRIMARY ROOT CAUSE: CAUSE N" + bullet WHY, optionally one line per secondary/contributor IF they exist).
      Must reference evidence that confirms cause AND excludes alternatives. Chain must be complete. Every [PRIMARY ROOT] traces to a supported hypothesis; [SECONDARY ROOT] and [CONTRIBUTOR] may trace to supported or supported_partial per evidence_matrix_contract.root_cause_role_eligibility. Contradictions resolved or flagged.
      If no defect is confirmed, say "NO ROOT CAUSE CONFIRMED" and cite the artifact(s) that contradicted or failed to reproduce the claimed defect.
    Fix_Proposal:
      must: 'Each fix tied to confirmed root cause. Include rollback/containment path + trigger criteria. Note residual vulnerability. Deterministic and ready-to-apply on approval — every step is a code/config change with file path + diff intent. For no_defect_confirmed or insufficient_evidence, write a single bullet stating that no code/config fix is proposed and why.'
      forbidden_content:
        - 'Hypothesis validation steps ("first verify if X")'
        - 'Conditional branches dependent on unconfirmed cause ("if it turns out to be Y, then...")'
        - 'User manual probe as prerequisite ("user runs script and reports back")'
        - 'Phased fix where step N depends on step N-1 producing diagnostic data after approval'
        - 'Mini-program creation for hypothesis confirmation (those belong to Phase 2, already done)'
        - 'Functional fix for a complaint that symptom_reality_gate classified as visual_ux unless evidence linked it to functional state'
      rationale: 'Approval gate is binary on a complete fix. Validation of cause happens in Phase 2/3. Validation of FIX happens in Verification_and_Validation (post-apply).'
    Residual_Risks: 'Impact assessment + probability — not generic platitudes.'
    Verification_and_Validation: 'Objective measurable criteria: how do we KNOW the fix worked?'
    Prevention: 'Controls tied to root cause class — linter rules, type constraints, alerts, tests, process gates.'
    Decision: 'Explicit user approval required before Phase 5 only when Fix_Proposal_Status=pending_confirmation. Diagnostic-only outcomes must use Decision=No-go and a concrete next step.'

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
    | Failure Type | {claimed_failure_type} |
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
    - Diagnostic_Outcome: {confirmed_defect|confirmed_visual_or_ux_issue|no_defect_confirmed|misframed_symptom|insufficient_evidence}
    - Fix_Proposal_Status: {pending_confirmation|not_applicable|needs_clarification}
    - Decision: Go / No-go
    - Next_Step: {step}
```

```yaml
evidence_matrix_contract:
  columns: [hypothesis_id, root_class, hypothesis, evidence_for, evidence_against, falsification_test, falsification_evidence, confidence_score_0_to_1, status]
  status_values: [supported, supported_partial, refuted, open, disproven]
  source_classes: [log, code_read, diff, test_executed, build_or_typecheck, metric, config, filesystem, reproduced_behavior, external_doc, api_response, dom_inspection, browser_automation, screenshot_or_pixel, probe_script, static_asset]
  rules:
    - 'root_cause_role_eligibility:
        [PRIMARY ROOT] requires status=supported AND evidence_for >= 2 AND independent_sources >= 2.
        [SECONDARY ROOT] or [CONTRIBUTOR] may use status=supported_partial only when ALL of: (1) at least one status=supported hypothesis exists in the same matrix; (2) causal continuity with the original failure is preserved; (3) it is not a regression introduced by the patch.
        [SECONDARY ROOT] or [CONTRIBUTOR] using status=supported follow the same evidence_for >= 2 AND independent_sources >= 2 rule.
        All other statuses: not eligible for any role in final Root_Cause.'
    - 'supported_partial must preserve causal continuity with the original failure. It represents a layer of the causal chain that was real but did not fully explain the failure. If a new failure was introduced by the patch (no causal continuity with the original), it is a regression — handle it via Phase 6 build_or_suite_regression, not as supported_partial.'
    - 'supported_partial reachability:
        supported_partial is reachable ONLY by demotion from a prior status=supported, typically via Phase 6 different_error.
        At the moment it was status=supported, the hypothesis MUST have satisfied: evidence_for >= 2 AND independent_sources >= 2.
        That evidence is inherited after demotion.
        A hypothesis MUST NOT be assigned status=supported_partial directly from open, untested, unsupported, or as an initial state.'
    - 'independent_sources counts DISTINCT source_classes among evidence_for entries. Two log lines from the same log = one source. A log line + a diff + a reproduced behavior = three sources.'
    - 'Every entry in evidence_for declares its source_class explicitly. Entries without source_class do not count toward independent_sources.'
    - 'Deterministic errors satisfy independent_sources trivially via tool output + confirmatory read. Examples: (a) compiler error pointing to exact line + code_read confirming the property/method does not exist; (b) "file not found" runtime error + filesystem listing confirming absence; (c) SQL "column does not exist" + schema introspection confirming absence; (d) import error + code_read confirming module/path. These count as 2 independent sources (tool output + confirmatory read) without needing additional ritual investigation.'
    - 'Every hypothesis needs falsification_test (the planned procedure to disprove it).'
    - 'falsification_test is the planned procedure; falsification_evidence is the observed result of executing it.'
    - 'status=refuted is valid ONLY when falsification_evidence is populated and non-empty. "Tried and refuted" without observed evidence is invalid — keep status=open.'
    - 'status=disproven follows the same rule as refuted (requires falsification_evidence).'
    - 'Contradictions surface as separate rows.'
```

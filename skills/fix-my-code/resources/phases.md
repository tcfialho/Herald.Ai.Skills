# Phase Execution Playbook

Detailed actions, validations, and error handling for each phase of the System Diagnostic Protocol.

## Phase 1: Discovery

```yaml
phase_1:
  actions:
    - validate_context: 'Cross-check required incident context fields before any action.'
    - classify_severity: 'Record suspected severity. IF P0/P1 suspected: propose temporally-gated containment immediately (see activation_rules), request Y/N confirmation, then continue investigation in parallel. Containment proposal is non-blocking — do not wait for user response before proceeding with Phase 1 actions.'
    - discover_mcp: 'List MCP servers, query diagnostic data providers.'
    - inspect_repository:
        git: 'git --version → git rev-parse → git remote -v, log --oneline -10, diff HEAD~3. Skip gracefully if unavailable.'
        files: ['CI/CD: .github/workflows/, azure-pipelines.yml, .gitlab-ci.yml', 'Containers: Dockerfile, docker-compose.yml', 'Packages: package.json, requirements.txt, pom.xml']
    - probe_external: 'Docker CLI, Cloud CLIs. On failure: use fallback_policy below.'
    - topology_map:
        when_required: 'Symptom does NOT localize the defect (no stack trace pointing to exact line AND no recent diff exposing the cause).'
        when_skip: 'Stack trace points to exact line OR recent diff in last 10 commits touches the failing code path.'
        scope: 'Strict 1-hop in each direction. NEVER full DFS.'
        emit: |
          Textual map BEFORE generating hypotheses, covering the affected component:
          - callers (1-hop): who invokes it, with what arguments
          - callees (1-hop): what it invokes, with what arguments
          - config consumed: env vars, config files, feature flags directly read
          - state touched: DB tables, caches, files, in-memory shared state
          - external integrations: HTTP/gRPC/queue endpoints called or consumed
        rationale: 'Hypotheses about data-flow, integration, or shared-state bugs without topology are guesses disguised as analysis. The map anchors every hypothesis to a verifiable structural fact.'
        on_skip: 'Log [AUTO-DECISION] topology_skipped reason={stack_trace_exact|recent_diff_exposes}'
    - checkpoint: 'Optional: confirmed sources, missing sources, next priority.'
  fallback_policy:
    logs: ['crash report output', 'source code + config diff', 'CI/CD artifacts', 'dependency lockfile', 'runbook notes']
    metrics: ['test suite signatures', 'SLA dashboards', 'rollback history']
    traces: ['timestamp correlation', 'call graph inspection', 'DB/queue from logs']
  errors: 'Git unavailable or source unreachable → document, continue (non-blocking).'
```

## Phase 2: Evidence Gathering

```yaml
phase_2:
  actions:
    - create_matrix: 'Build: hypothesis_id | root_class | hypothesis | evidence_for (with source_class per entry) | evidence_against | falsification_test | falsification_evidence | confidence [0-1] | status. Classes: code, config, dependency, data, infra, integration, process.'
    - validate_matrix: 'Verify columns and status rules per evidence_matrix_contract.'
    - verify_changes: 'git log --oneline -10, git diff HEAD~3. Focus: deps, config, infra.'
    - reproduce: 'If safe and reproducible → run failing command, capture output.'
    - diagnostic_scripts:
        when_required_ANY:
          - 'Hypothesis lacks direct evidence (no stack trace pointing line, no visible diff touching the code path)'
          - '2+ competing hypotheses with no tiebreaker via static reading'
          - 'Intermittent symptom / timing / runtime state'
        when_skip_OK_ALL_REQUIRED:
          - 'Stack trace names the exact line of the hypothesis (file:line precision, not file-level)'
          - 'Recent diff (last 10 commits) touches that EXACT line, not just the file'
          - 'Error message is literal and self-describing (e.g., "ENOENT: no such file or directory, open ''/etc/foo''")'
          - 'No runtime state dependency (no concurrency, no shared mutable state, no async ordering, no external service involved)'
        rationale_for_strict_skip: 'Stack traces show where execution crashed, not where the cause originated. Late-init bugs, shared-state mutation, hook ordering, and races all produce "obvious" stack traces pointing at the symptom. Skip is allowed ONLY when all four conditions hold simultaneously — that combination effectively rules out cause-vs-symptom divergence.'
        artifacts: 'Temp scripts in `.temp/probe_<hyp_id>.{py,sh,log}` (NEVER pollute src/). Cite path in matrix evidence_for. Mark for cleanup.'
        on_skip: 'Log [AUTO-DECISION] probe_skipped — list ALL four conditions and how each was verified. Missing verification of any one = skip invalid, probe required.'
    - capture_baseline: 'Record error output, timestamps, scope. Snapshot config/state for comparison.'
    - probe_teardown:
        scope: 'ANY probe that mutates state — even temporarily.'
        examples_of_state_mutation:
          - 'Created temp DB table, schema, or row'
          - 'Flipped feature flag, env var, or config value'
          - 'Modified file permissions (chmod) or ownership (chown)'
          - 'Injected middleware, interceptor, or monkey-patch'
          - 'Started auxiliary process, container, or port binding'
          - 'Wrote files outside .temp/ (logs in /var/log, cache, etc.)'
        rule: 'Every mutating probe MUST emit its paired reverse operation. Pair is declared at probe creation time, not after. Run reverse before Phase 4 emits the report.'
        baseline_check: 'After teardown, verify environment matches the baseline snapshot captured before the probe ran. Diff anything that drifted; document any residual.'
        on_failure: 'Teardown failed → BLOCK Phase 4. State residual contaminates Fix_Proposal evidence and may break Phase 5 verification. Log [AUTO-DECISION] teardown_failed and surface to user.'
        non_mutating_probes: 'Read-only probes (grep, log inspection, static analysis, dry-run commands) skip teardown — log [AUTO-DECISION] teardown_not_needed reason=read_only.'
    - collect_signals: 'Think → Act → Observe per hypothesis. Prefer source code over docs. Record pass/fail.'
    - temporal_correlation: 'Verify symptom timeline matches change timeline. No correlation → downgrade confidence.'
    - evidence_priority: { P0: 'errors, stack traces, source code', P1: 'commits, container logs, MCP', P2: 'CI/CD, deploy status', P3: 'CPU/mem', P4: 'runbook, history' }
    - checkpoint: 'Optional: hypothesis status, strongest/weakest, blocking gaps.'
  validation:
    self_refine: { max: 2, log: '[SELF-REFINE] N: {weak} → {action}', rule: 'DIFFERENT remediation each.', on_exhaustion: prompt_user }
    checks: ['Sources: Logs → Traces → Metrics (refine: try next fallback)', 'Matrix has required columns + ≥1 supported hypothesis (refine: re-examine for missed correlations)']
    error: '>15min on hypothesis → park, next P-level'
```

## Phase 3: Fault Tree Analysis

```yaml
phase_3:
  actions:
    - diagnostic_artifacts: 'If useful, temp scripts in `.temp/` for programmatic verification.'
    - decompose: 'OR/AND tree by root_class. "Why?" recursively until fixable defect.'
    - multiple_roots: 'If multiple contributing factors → track all.'
    - score: 'Confidence [0.00-1.00] per hypothesis. Factors: supporting signals, contradictions, temporal correlation, falsification.'
    - cross_reference: 'Every candidate role-checked against root_cause_role_eligibility: [PRIMARY ROOT] backed by supported hypothesis; [SECONDARY ROOT] or [CONTRIBUTOR] backed by supported or supported_partial per evidence_matrix_contract. ≥1 falsified when applicable; no unresolved contradictions.'
    - deliberate_selection:
        visibility: internal_reasoning
        trigger_ANY:
          - 'Gap between top hypothesis and second-best is < 0.20 in confidence'
          - 'Second-best hypothesis has confidence >= 0.50, regardless of how high the top is'
          - '2+ hypotheses with confidence >= 0.60 (legacy condition, kept as safety net)'
        rationale: 'Absolute threshold misses the dangerous case: top at 0.95 with alternative at 0.58. High confidence on the leader can itself be confirmation bias; the alternative is precisely what needs disproving. Relative gap forces deliberation whenever the second hypothesis is non-trivially competitive, not only when both are individually strong.'
        execute: |
          For each competing hypothesis (top + every other meeting any trigger above), FORCE branching deliberation:
          FOR EACH: [THINK_PATH_{id}] FOR — evidence? complete chain? temporal alignment?
          FOR EACH: [THINK_PATH_{id}] AGAINST — missing expected evidence? alternatives? unexplained gaps?
          COMPARE: evidence-to-gap ratio | earliest detection if wrong | most symptoms, fewest assumptions.
          [SELECTED_ROOT_CAUSE]: Declare with justification. Log [AUTO-DECISION] including the triggering condition and the gap that justified deliberation. No winner → multiple roots.
    - checkpoint: 'Optional: candidate chains, contradictions, confirmation recommendation.'
  validation:
    self_refine: { max: 2, log: '[SELF-REFINE] N: {weak} → {action}', rule: 'DIFFERENT remediation each.', on_exhaustion: prompt_user }
    checks: ['All hypotheses scored (refine: score now with justification)', '≥1 falsified when 2+ hypotheses are candidates for root cause (i.e., when deliberate_selection is triggered). Single-hypothesis cases (e.g., deterministic errors fully accounted for by tool output + confirmatory read): log [AUTO-DECISION] single_hypothesis_no_alternatives reason={why alternatives were not generated} — do NOT invent a strawman hypothesis just to refute it.', 'Every [PRIMARY ROOT] backed by a supported hypothesis; every [SECONDARY ROOT] or [CONTRIBUTOR] backed by supported or supported_partial per evidence_matrix_contract (refine: link or demote)', 'Reached fixable defect (fail: escalate)']
```

## Phase 4: Diagnostic Report

```yaml
phase_4:
  actions:
    - render_report: 'Emit unified report per output_contract (see resources/output-contract.md).'
    - validation_artifact:
        rule: 'A validation artifact is mandatory before emitting Fix_Proposal. Use the strongest type available in the context. Weaker types require justification.'
        types_in_order_of_strength:
          - '1. automated test (when test infra exists and bug is testable in code)'
          - '2. build / typecheck / lint command (compilation, type, dependency, analyzer errors)'
          - '3. executable reproduction (script, command, Docker build, pipeline run, external probe, reproducible request)'
          - '4. objective behavioral reproduction (numbered steps, wrong result before, expected result after — for UI, CSS, manual flows)'
          - '5. log comparison (only when local reproduction is impossible — requires specific string/regex pattern, NOT "logs look better")'
        rules:
          - 'Artifact must FAIL or show the wrong result PRE-FIX, captured as evidence.'
          - 'Artifact must target the CONFIRMED CAUSE, not only the surface symptom. "Error disappeared" / "returns 200 now" is NOT sufficient. Example: if the cause is "middleware double-decodes the token", the artifact exercises that double-decode path explicitly.'
          - 'If using type 4 or 5, log [AUTO-DECISION] validation_degraded reason={why types 1-3 do not apply}.'
        on_failure_to_produce: 'No valid artifact can be produced → cause is not understood precisely enough. Return to Phase 2/3. Do NOT emit Fix_Proposal.'
        location: 'Tests go under the existing test tree. Repro scripts and probes go under .temp/. Reference the artifact path explicitly in the Fix_Proposal.'
    - validate_fix_internally:
        visibility: internal_only
        execute: |
          Silent 5-Whys per fix item. Generate ≥2 alternatives, then:
          1. Definitively solves? (root cause vs symptom mask, recurrence?)
          2. Better than alternatives? (trade-off: simplicity, risk, reversibility)
          3. Minimal effective change? (simpler version? over/under-engineering?)
          4. Holds over time? (tech debt, coupling, maintenance?)
          5. Fits codebase? (patterns, conventions, readable without explanation?)
          6. Free of validation prerequisites? Does the fix require user/AI to first run something to confirm the cause? → demote, return to Phase 2 for probe.
          Weak answer → switch to stronger alternative. None survives → demote to Residual_Risks or No-go.
  validation: ['Root cause backed by independent evidence', 'No contradictions unexplained', 'Causal chain complete', 'Fix passed 5-Whys (fail: revise)', 'Validation artifact exists, targets the cause, shows wrong result pre-fix (fail: BLOCK, return to Phase 2/3)']
  output: 'Emit per output_contract. Final line: "Do you confirm the execution of this Fix_Proposal?"'
```

## Phase 5: Solution & Prevention

```yaml
phase_5:
  trigger: 'Only AFTER report delivered and user explicitly confirmed'
  actions:
    - confirm: 'Validate explicit user confirmation. If unclear, ask once and stop.'
    - fix: 'Tie every code change to diagnostic evidence.'
    - verify:
        primary_gate: 'The validation artifact from Phase 4 MUST now show the expected (correct) result. This is the binding criterion — symptom disappearance alone is NOT sufficient.'
        regression_gate: 'Relevant test suite or equivalent checks (same module / package / affected scope) MUST still pass. No green-to-red elsewhere.'
        deployed_systems: 'If change reaches a deployed environment: validate in that environment, validate rollback path, validate customer impact window.'
        on_failure: 'Fix produced but validation artifact still shows wrong result OR suite regressed → Phase 6.'
    - prevent:
        rule: 'Always suggest one preventive control per confirmed root cause class.'
        implement_only_if_all_true:
          - '1. Affects at most 1–2 files.'
          - '2. Does not alter behavior of unrelated code paths.'
          - '3. Does not introduce new infrastructure, framework, dependency, or process.'
          - '4. Directly catches, blocks, or prevents the same defect class.'
          - '5. Can be validated by the same validation artifact OR by one additional narrow check.'
        on_any_condition_false: 'Do NOT implement. List under Prevention as a recommendation for the user to decide.'
        rationale: 'Prevents bugfix from silently expanding into refactor / new process / new tooling. The "same defect class" criterion blocks generic suggestions like "improve tests", "add observability", "review architecture".'
  error: 'Fix fails → Phase 6.'
```

## Phase 6: Iteration Protocol

```yaml
phase_6:
  trigger: 'Fix verification failed (validation artifact still shows wrong result OR suite regressed) OR new evidence contradicts root cause'
  premise: 'Fix failed ≠ root cause wrong. First compare error before vs after and classify. Do NOT patch blindly without new evidence.'
  classify_failure:
    same_error:
      definition: 'Same message, same stack trace, same log pattern as pre-fix.'
      action:
        - 'Check first: was the patch actually exercised? Verify (a) the modified file is imported/loaded by the failing execution path, (b) the test/command exercises that path, (c) build/cache was refreshed, (d) process was restarted if needed.'
        - 'If patch was NOT effectively exercised → re-apply correctly, no RCA reopen needed.'
        - 'If patch WAS exercised and error persists identical → cause may be wrong OR incomplete (secondary contributor in same root_class). Mark current root cause as status=open (not refuted), run deliberate_selection over alternatives.'
    different_error:
      definition: 'Message differs, new stack trace, or new log pattern emerged.'
      action:
        - 'Partial progress — original cause likely correct but incomplete. Mark previous root cause status=supported_partial.'
        - 'Investigate the new error as a delta. Scope Phase 2 to the new symptom; do NOT reopen the full matrix.'
        - 'New cause may be a downstream layer exposed by removing the first one.'
    build_or_suite_regression:
      definition: 'Tests not related to the original bug regressed, OR compilation/build broke, OR linter/typechecker now reports new issues.'
      action:
        - 'Patch introduced a new problem. Original diagnosis is NOT under suspicion.'
        - 'Revert the patch. Narrow scope. Reapply with correction.'
        - 'Do NOT reopen RCA of the original cause — it remains supported.'
  status_values_added: { supported_partial: 'Cause was correct but did not fully explain the failure; an additional layer or contributor exists.' }
  escalation: 'After 3 iterations total (any category): report what is established vs unknown, request specific missing info from user.'
```

## Operational Policies

```yaml
telemetry:
  fields: [run_id, session_start, current_phase, issue_signature, iterations, hypotheses_total, hypotheses_open, contradictions_found, evidence_conflicts, resolution_status, final_confidence]

context_compression:
  trigger: 'Phase 6, >8 turns, or re-investigating confirmed findings.'
  action: 'Structured summary (confirmed, active, eliminated, phase, gaps). Continue from summary, not raw context. Log [CONTEXT-COMPRESS]. Preserve matrix + all [AUTO-DECISION]/[AUTO-CORRECTION]. After compression, re-read matrix and decision trail to verify nothing lost.'
```

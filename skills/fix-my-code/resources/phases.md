# Phase Execution Playbook

Detailed actions, validations, and error handling for each phase of the System Diagnostic Protocol.

## Phase 1: Discovery

```yaml
phase_1:
  actions:
    - validate_context: 'Cross-check required incident context fields before any action.'
    - classify_severity: 'Record severity. IF P0/P1: identify containment/rollback BEFORE deep investigation.'
    - discover_mcp: 'List MCP servers, query diagnostic data providers.'
    - inspect_repository:
        git: 'git --version → git rev-parse → git remote -v, log --oneline -10, diff HEAD~3. Skip gracefully if unavailable.'
        files: ['CI/CD: .github/workflows/, azure-pipelines.yml, .gitlab-ci.yml', 'Containers: Dockerfile, docker-compose.yml', 'Packages: package.json, requirements.txt, pom.xml']
    - probe_external: 'Docker CLI, Cloud CLIs. On failure: use fallback_policy below.'
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
    - create_matrix: 'Build: hypothesis_id | root_class | hypothesis | evidence_for | evidence_against | falsification_test | confidence [0-1] | status. Classes: code, config, dependency, data, infra, integration, process.'
    - validate_matrix: 'Verify columns and status rules per evidence_matrix_contract.'
    - verify_changes: 'git log --oneline -10, git diff HEAD~3. Focus: deps, config, infra.'
    - reproduce: 'If safe and reproducible → run failing command, capture output.'
    - diagnostic_scripts: 'Create temp scripts in `.temp/` (NEVER pollute src/). Reproduce errors, probe APIs, parse logs. Mark for cleanup.'
    - capture_baseline: 'Record error output, timestamps, scope. Snapshot config/state for comparison.'
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
    - cross_reference: 'Every candidate → supported hypothesis; ≥1 falsified; no unresolved contradictions.'
    - deliberate_selection:
        visibility: internal_reasoning
        execute: |
          When 2+ hypotheses supported with confidence ≥ 0.60, FORCE branching deliberation:
          FOR EACH: [THINK_PATH_{id}] FOR — evidence? complete chain? temporal alignment?
          FOR EACH: [THINK_PATH_{id}] AGAINST — missing expected evidence? alternatives? unexplained gaps?
          COMPARE: evidence-to-gap ratio | earliest detection if wrong | most symptoms, fewest assumptions.
          [SELECTED_ROOT_CAUSE]: Declare with justification. Log [AUTO-DECISION]. No winner → multiple roots.
    - checkpoint: 'Optional: candidate chains, contradictions, confirmation recommendation.'
  validation:
    self_refine: { max: 2, log: '[SELF-REFINE] N: {weak} → {action}', rule: 'DIFFERENT remediation each.', on_exhaustion: prompt_user }
    checks: ['All hypotheses scored (refine: score now with justification)', '≥1 falsified (refine: design falsification for weakest)', 'Every root backed by supported hypothesis (refine: link or demote)', 'Reached fixable defect (fail: escalate)']
```

## Phase 4: Diagnostic Report

```yaml
phase_4:
  actions:
    - render_report: 'Emit unified report per output_contract (see v3-output-contract.md).'
    - validate_fix_internally:
        visibility: internal_only
        execute: |
          Silent 5-Whys per fix item. Generate ≥2 alternatives, then:
          1. Definitively solves? (root cause vs symptom mask, recurrence?)
          2. Better than alternatives? (trade-off: simplicity, risk, reversibility)
          3. Minimal effective change? (simpler version? over/under-engineering?)
          4. Holds over time? (tech debt, coupling, maintenance?)
          5. Fits codebase? (patterns, conventions, readable without explanation?)
          Weak answer → switch to stronger alternative. None survives → demote to Residual_Risks or No-go.
  validation: ['Root cause backed by independent evidence', 'No contradictions unexplained', 'Causal chain complete', 'Fix passed 5-Whys (fail: revise)']
  output: 'Emit per output_contract. Final line: "Do you confirm the execution of this Fix_Proposal?"'
```

## Phase 5: Solution & Prevention

```yaml
phase_5:
  trigger: 'Only AFTER report delivered and user explicitly confirmed'
  actions:
    - confirm: 'Validate explicit user confirmation. If unclear, ask once and stop.'
    - fix: 'Tie every code change to diagnostic evidence.'
    - verify: 'Test exists → run. No test → manual + suggest test. Deployed → production validation. Validate rollback + customer impact window.'
    - prevent: 'Recurrence likely → linter/type/alert. Misleading error → fix output. ALWAYS one preventive control per root cause class.'
  error: 'Fix fails → Phase 6.'
```

## Phase 6: Iteration Protocol

```yaml
phase_6:
  trigger: 'Fix failed or new evidence contradicts root cause'
  actions:
    - refine: 'DO NOT repeat same investigation. Focus on what failed fix revealed.'
    - update: 'Amend original diagnostic with new findings.'
    - log: 'Record phase, new evidence, contradictions, updated priority.'
  escalation: 'After 3 iterations: report established vs unknown, request specific missing info.'
```

## Operational Policies

```yaml
telemetry:
  fields: [run_id, session_start, current_phase, issue_signature, iterations, hypotheses_total, hypotheses_open, contradictions_found, evidence_conflicts, resolution_status, final_confidence]

context_compression:
  trigger: 'Phase 6, >8 turns, or re-investigating confirmed findings.'
  action: 'Structured summary (confirmed, active, eliminated, phase, gaps). Continue from summary, not raw context. Log [CONTEXT-COMPRESS]. Preserve matrix + all [AUTO-DECISION]/[AUTO-CORRECTION]. After compression, re-read matrix and decision trail to verify nothing lost.'
```

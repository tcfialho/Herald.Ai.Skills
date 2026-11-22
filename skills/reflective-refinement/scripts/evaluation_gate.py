#!/usr/bin/env python3
"""External, evidence-based acceptance; the worker cannot approve its own claim."""

import argparse
import hashlib
import math
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

KINDS = {'functionality', 'performance', 'maintainability', 'visual', 'ux', 'documentation', 'mixed'}
DECISIONS = {'KEEP', 'REJECT', 'HOLD'}


class EvaluationError(Exception):
    pass


SEVERITY_RANK = {'none': 0, 'minor': 1, 'medium': 2, 'major': 3, 'critical': 4}


def validate_quality_gate(gate, case_ids):
    if not isinstance(gate, dict) or gate.get('max_remaining_severity') not in SEVERITY_RANK:
        raise EvaluationError('quality_gate requires a known max_remaining_severity')
    groups = gate.get('coverage_groups')
    if not isinstance(groups, dict) or not groups:
        raise EvaluationError('quality_gate requires scenario coverage groups')
    listed = set()
    for name, cases in groups.items():
        if (not isinstance(name, str) or not name or not isinstance(cases, list) or not cases
                or any(not isinstance(case, str) or not case for case in cases)
                or len(set(cases)) != len(cases)):
            raise EvaluationError('each scenario group needs a name and distinct case IDs')
        listed.update(cases)
    if listed != set(case_ids):
        raise EvaluationError('scenario groups must cover exactly the frozen case IDs')
    confirmation = gate.get('confirmation_group')
    if confirmation is not None:
        if confirmation not in groups or len(groups) < 2:
            raise EvaluationError('confirmation must identify a separate scenario group')
        if any(set(groups[confirmation]) & set(cases) for name, cases in groups.items()
               if name != confirmation):
            raise EvaluationError('confirmation cases cannot appear in other scenario groups')
    anchors = gate.get('severity_anchors', {})
    if (not isinstance(anchors, dict) or any(
            key not in SEVERITY_RANK or not isinstance(value, str) or len(value.strip()) < 12
            for key, value in anchors.items())):
        raise EvaluationError('severity anchors must be substantive descriptions')


def quality_target_assessment(report, gate, case_ids, label):
    """Grade one anonymous output before the external controller reveals its role."""
    validate_quality_gate(gate, case_ids)
    assessments = report.get('quality_by_label')
    if not isinstance(assessments, dict) or set(assessments) != {'A', 'B'}:
        raise EvaluationError('both anonymous alternatives need independent target assessments')
    if label not in {'A', 'B'}:
        raise EvaluationError('invalid anonymous alternative')
    assessment = assessments[label]
    if not isinstance(assessment, dict):
        raise EvaluationError('each alternative needs a structured target assessment')
    findings = assessment.get('quality_findings')
    observations = assessment.get('case_observations')
    if not isinstance(findings, list) or not isinstance(observations, list):
        raise EvaluationError('target assessment requires findings and per-case observations')
    actual = {}
    for finding in findings:
        if (not isinstance(finding, dict) or not isinstance(finding.get('severity'), str)
                or finding['severity'] not in SEVERITY_RANK or finding['severity'] == 'none'):
            raise EvaluationError('finding requires a nonzero recognized severity')
        if not isinstance(finding.get('description'), str) or len(finding['description'].strip()) < 12:
            raise EvaluationError('finding requires a specific observable description')
        evidence_ids = finding.get('evidence_ids')
        if (not isinstance(evidence_ids, list) or not evidence_ids
                or any(not isinstance(item, str) for item in evidence_ids)
                or not set(evidence_ids).issubset(set(case_ids))):
            raise EvaluationError('finding must cite frozen scenario IDs')
        for case_id in evidence_ids:
            actual[case_id] = max(actual.get(case_id, 0), SEVERITY_RANK[finding['severity']])
    seen = set()
    for item in observations:
        if (not isinstance(item, dict) or not isinstance(item.get('case_id'), str)
                or item['case_id'] not in case_ids
                or item['case_id'] in seen):
            raise EvaluationError('observations must identify distinct frozen scenarios')
        seen.add(item['case_id'])
        if not isinstance(item.get('observation'), str) or len(item['observation'].strip()) < 12:
            raise EvaluationError('each scenario needs a substantive observation')
        severity = item.get('worst_severity')
        if not isinstance(severity, str) or severity not in SEVERITY_RANK or SEVERITY_RANK[severity] != actual.get(item['case_id'], 0):
            raise EvaluationError('scenario severity must agree with linked findings')
    if seen != set(case_ids):
        raise EvaluationError('judge did not independently examine every frozen scenario')
    allowed = SEVERITY_RANK[gate['max_remaining_severity']]
    blocking = sum(SEVERITY_RANK[f['severity']] > allowed for f in findings)
    return {'status': 'NOT_MET' if blocking else 'MET', 'blocking_findings': blocking,
            'reviewed_cases': len(seen), 'allowed_maximum': gate['max_remaining_severity'],
            'confirmation_group': gate.get('confirmation_group')}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_contract(path):
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if data.get('schema_version') != 1 or data.get('kind') not in KINDS:
        raise EvaluationError('unsupported schema_version or goal kind')
    if not isinstance(data.get('user_goal'), str) or len(data['user_goal'].strip()) < 12:
        raise EvaluationError('freeze the exact original user_goal in the evaluation contract')
    if data.get('draft') is True:
        raise EvaluationError('draft contract cannot approve experiments: ground cases, guards and baseline first')
    if not isinstance(data.get('primary_outcome'), str) or len(data['primary_outcome'].strip()) < 12:
        raise EvaluationError('primary_outcome must describe real user value')
    cases = data.get('case_ids')
    if not isinstance(cases, list) or not cases or len(set(cases)) != len(cases) or any(not isinstance(x, str) or not x for x in cases):
        raise EvaluationError('case_ids must contain distinct nonempty scenarios')
    if (not isinstance(data.get('hard_checks', []), list)
            or not isinstance(data.get('target_checks', []), list)
            or not isinstance(data.get('primary_metrics', []), list)):
        raise EvaluationError('checks/target_checks/metrics must be lists')
    if not isinstance(data.get('review', {}), dict):
        raise EvaluationError('review must be an object')
    if data['kind'] in {'visual', 'ux'} and not data.get('review', {}).get('required'):
        raise EvaluationError('visual or UX promotion requires an outcome judge')
    reviewer = data.get('review', {})
    if reviewer.get('required'):
        criteria = reviewer.get('criteria')
        if (not isinstance(criteria, list) or not criteria
                or any(not isinstance(item, str) or not item.strip() for item in criteria)
                or len(set(criteria)) != len(criteria)):
            raise EvaluationError('required independent review needs distinct named criteria')
    if reviewer.get('quality_gate'):
        if not reviewer.get('required'):
            raise EvaluationError('quality_gate requires an independent reviewer')
        validate_quality_gate(reviewer['quality_gate'], cases)
    if 'priority_order' in data:
        priorities = data['priority_order']
        if (not isinstance(priorities, list) or not priorities
                or any(not isinstance(item, str) or len(item.strip()) < 6 for item in priorities)
                or len(set(priorities)) != len(priorities)):
            raise EvaluationError('priority_order must list distinct, concrete ordered outcomes')
    protected = reviewer.get('required_nonregression', [])
    if (not isinstance(protected, list) or len(set(protected)) != len(protected)
            or not set(protected).issubset(set(reviewer.get('criteria', [])))):
        raise EvaluationError('required_nonregression must reference known reviewer criteria')
    guidance = reviewer.get('criterion_guidance', {})
    if (not isinstance(guidance, dict) or
            (guidance and set(guidance) != set(reviewer.get('criteria', []))) or
            any(not isinstance(v, str) or len(v.strip()) < 12 for v in guidance.values())):
        raise EvaluationError('criterion_guidance must describe all named review criteria')
    if reviewer.get('quality_gate') and not guidance:
        raise EvaluationError('quality_gate needs concrete guidance for every review criterion')
    target_references = reviewer.get('target_reference_evidence', {})
    if (not isinstance(target_references, dict)
            or not set(target_references).issubset(set(cases))
            or any(not isinstance(path, str) or not path.strip()
                   for path in target_references.values())):
        raise EvaluationError('target_reference_evidence must map frozen scenario IDs to result files')
    for guard in data.get('sample_guards', []):
        if (not isinstance(guard, dict) or not isinstance(guard.get('name'), str)
                or not guard['name'] or not any(key in guard for key in ('minimum', 'maximum'))):
            raise EvaluationError('sample_guard requires a metric name and at least one bound')
        for key in ('minimum', 'maximum'):
            if key in guard and (not isinstance(guard[key], (float, int))
                                 or isinstance(guard[key], bool) or not math.isfinite(guard[key])):
                raise EvaluationError('sample_guard requires finite numeric bounds')
        if guard.get('minimum', -float('inf')) > guard.get('maximum', float('inf')):
            raise EvaluationError('sample_guard minimum cannot exceed maximum')
    for check in [*data.get('hard_checks', []), *data.get('target_checks', [])]:
        if (not isinstance(check, dict) or not isinstance(check.get('argv'), list)
                or not check['argv'] or not all(isinstance(x, str) for x in check['argv'])):
            raise EvaluationError('hard checks must have argv lists, not shell commands')
    if data.get('benchmark'):
        if not isinstance(data['benchmark'].get('argv'), list) or not data['benchmark']['argv']:
            raise EvaluationError('benchmark must have argv')
    for metric in data.get('primary_metrics', []):
        if metric.get('direction') not in ('higher', 'lower') or not isinstance(metric.get('reference'), (float, int)):
            raise EvaluationError('primary metrics require direction and a numerical reference')
        if float(metric.get('minimum_gain', 0)) < 0:
            raise EvaluationError('minimum_gain cannot be negative')
        if 'target_value' in metric and (not isinstance(metric['target_value'], (int, float))
                or isinstance(metric['target_value'], bool) or not math.isfinite(metric['target_value'])):
            raise EvaluationError('target_value must be a finite measured threshold')
    fidelity = data.get('case_requirements', {})
    if not isinstance(fidelity, dict) or not set(fidelity).issubset(set(cases)):
        raise EvaluationError('case_requirements must reference frozen cases')
    for case, requirements in fidelity.items():
        if not isinstance(requirements, dict) or not requirements:
            raise EvaluationError(f'case {case} needs measurable representativeness requirements')
        for name, bounds in requirements.items():
            if not isinstance(name, str) or not name or not isinstance(bounds, dict) or not bounds:
                raise EvaluationError('case requirement must name a measured observable')
            if not any(k in bounds for k in ('minimum', 'maximum')) or any(
                    k not in ('minimum', 'maximum') or not isinstance(v, (int, float)) or
                    isinstance(v, bool) or not math.isfinite(v) for k, v in bounds.items()):
                raise EvaluationError('case observable requires valid numeric bounds')
            if bounds.get('minimum', -math.inf) > bounds.get('maximum', math.inf):
                raise EvaluationError('inverted case fidelity bounds')
    return data, hashlib.sha256(raw).hexdigest()


def run_argv(argv, workspace, timeout=120):
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise EvaluationError('only argv commands are accepted')
    if not 0 < timeout <= 3600:
        raise EvaluationError('invalid check timeout')
    result = subprocess.run(argv, cwd=workspace, capture_output=True, text=True, timeout=timeout)
    return {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout[-12000:],
            'stderr': result.stderr[-12000:]}


def scenario_fidelity(contract, report):
    expected_cases = set(contract['case_ids'])
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise EvaluationError('benchmark must emit one versioned JSON object')
    case_ids = report.get('case_ids')
    if not isinstance(case_ids, list) or set(case_ids) != expected_cases or len(case_ids) != len(expected_cases):
        raise EvaluationError('benchmark case_ids do not match frozen contract')
    requirements = contract.get('case_requirements', {})
    if requirements:
        observations = report.get('case_facts', {})
        if not isinstance(observations, dict):
            raise EvaluationError('benchmark did not measure scenario fidelity')
        for case, measures in requirements.items():
            actual = observations.get(case, {})
            if not isinstance(actual, dict):
                raise EvaluationError(f'missing representative scenario {case}')
            for key, bounds in measures.items():
                value = actual.get(key)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    raise EvaluationError(f'unmeasured case fidelity: {case}.{key}')
                if value < bounds.get('minimum', -math.inf) or value > bounds.get('maximum', math.inf):
                    raise EvaluationError(f'unrepresentative benchmark case: {case}.{key}={value}')


def preflight_performance_benchmark(contract, workspace):
    """Reject an empty, altered, or irrelevant baseline before optimizing the wrong workload."""
    benchmark = contract.get('benchmark')
    if not benchmark:
        raise EvaluationError('goal-driven performance needs an executable baseline benchmark')
    output = run_argv(benchmark['argv'], workspace, benchmark.get('timeout_seconds', 120))
    if output['returncode']:
        raise EvaluationError('baseline benchmark failed; establish a valid workload first')
    try:
        report = json.loads(output['stdout'])
    except ValueError as exc:
        raise EvaluationError('baseline benchmark did not emit a JSON report') from exc
    scenario_fidelity(contract, report)
    observations = report.get('metrics', {})
    samples = report.get('samples', {})
    if not isinstance(observations, dict) or not isinstance(samples, dict):
        raise EvaluationError('baseline needs actual metric values and raw samples')
    import statistics
    for metric in contract.get('primary_metrics', []):
        name = metric['name']
        values = samples.get(name)
        current = observations.get(name)
        if not isinstance(values, list) or len(values) < 3 or any(
                not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in values):
            raise EvaluationError(f'baseline {name} requires at least three raw repeats')
        if not isinstance(current, (int, float)) or not math.isfinite(current) or abs(statistics.median(values) - current) > 1e-6:
            raise EvaluationError(f'baseline {name} is inconsistent with raw samples')
        tolerance = metric.get('reference_tolerance', 0.1)
        if not isinstance(tolerance, (int, float)) or tolerance < 0 or tolerance > 1:
            raise EvaluationError('baseline tolerance must be between 0 and 1')
        if abs(current - metric['reference']) > max(1e-6, abs(metric['reference']) * tolerance):
            raise EvaluationError(f'baseline {name} does not match frozen reference')
    return {'status': 'PASS', 'case_ids': report['case_ids'], 'case_facts': report.get('case_facts', {}),
            'metrics': observations, 'samples': samples}


def metric_assessment(contract, report, incumbent_metrics=None):
    scenario_fidelity(contract, report)
    guards = report.get('guards')
    if not isinstance(guards, dict) or not guards or any(v is not True for v in guards.values()):
        return {'status': 'REJECT', 'reason': 'functional or integrity guard failed', 'guards': guards}
    measurements = report.get('metrics', {})
    if not isinstance(measurements, dict):
        raise EvaluationError('metrics must be an object')
    results = {}
    samples = report.get('samples', {})
    if contract['kind'] == 'performance':
        if not isinstance(samples, dict):
            raise EvaluationError('performance requires repeated same-candidate samples')
        for m in contract.get('primary_metrics', []):
            observed = samples.get(m['name'])
            if not isinstance(observed, list) or len(observed) < 3 or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) and -float('inf') < v < float('inf')
                    for v in observed):
                raise EvaluationError(f'performance metric {m["name"]} needs at least three valid repeats')
            import statistics
            if abs(statistics.median(observed) - report.get('metrics', {}).get(m['name'], float('inf'))) > 1e-6:
                raise EvaluationError('reported metric does not match median raw samples')
    for guard in contract.get('sample_guards', []):
        values = samples.get(guard['name']) if isinstance(samples, dict) else None
        if not isinstance(values, list) or not values or any(
            not isinstance(v, (float, int)) or isinstance(v, bool) or not -float('inf') < v < float('inf')
            for v in values):
            raise EvaluationError('sample guard needs finite raw measurements for ' + guard['name'])
        if any((v < guard['minimum'] if 'minimum' in guard else False) or
               (v > guard['maximum'] if 'maximum' in guard else False) for v in values):
            return {'status': 'REJECT', 'reason': 'sample guard failed: ' + guard['name'],
                    'samples': values}
    incumbent_metrics = incumbent_metrics or {}
    for m in contract.get('primary_metrics', []):
        name = m['name']
        value = measurements.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not -float('inf') < value < float('inf'):
            raise EvaluationError(f'missing or invalid primary metric: {name}')
        original_gain = value - m['reference'] if m['direction'] == 'higher' else m['reference'] - value
        current_best = incumbent_metrics.get(name, m['reference'])
        gain = value - current_best if m['direction'] == 'higher' else current_best - value
        threshold = float(m.get('minimum_gain', 0))
        tolerance = float(m.get('allowed_regression', 0))
        role = m.get('role', 'primary')
        results[name] = {'value': value, 'reference': m['reference'], 'incumbent': current_best,
                         'gain': gain, 'original_gain': original_gain, 'minimum_gain': threshold}
        if role == 'guard':
            if gain < -tolerance:
                return {'status': 'REJECT', 'reason': f'{name} regressed against incumbent', 'metrics': results}
            continue
        if gain < threshold or gain <= 0:
            return {'status': 'REJECT', 'reason': f'{name} did not improve over incumbent by minimum_gain', 'metrics': results}
        if original_gain < float(m.get('minimum_original_gain', 0)):
            return {'status': 'REJECT', 'reason': f'{name} violates frozen original guard', 'metrics': results}
    return {'status': 'PASS', 'metrics': results, 'guards': guards}


def review_verdict(report, criteria_ids, case_ids, candidate_label, quality_gate=None, required_nonregression=()):
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise EvaluationError('invalid judge schema')
    if report.get('verdict') not in ('A', 'B', 'TIE', 'UNCERTAIN'):
        raise EvaluationError('invalid judge verdict')
    seen_cases = report.get('case_ids')
    if (not isinstance(seen_cases, list) or len(seen_cases) != len(case_ids)
            or any(not isinstance(case, str) for case in seen_cases)
            or set(seen_cases) != set(case_ids)):
        raise EvaluationError('judge did not examine frozen cases')
    if report.get('confidence') not in ('low','medium','high'):
        raise EvaluationError('judge confidence missing or invalid')
    items = report.get('criteria')
    if (not isinstance(items, list) or len(items) != len(criteria_ids)
            or any(not isinstance(item, dict) or not isinstance(item.get('criterion_id'), str) for item in items)
            or {item['criterion_id'] for item in items} != set(criteria_ids)):
        raise EvaluationError('judge did not examine every frozen criterion')
    for item in items:
        if (item.get('comparison') not in ('A', 'B', 'TIE', 'UNCERTAIN') or
                not isinstance(item.get('observation'), str) or len(item['observation'].strip()) < 12 or
                not isinstance(item.get('evidence_ids'), list) or not item['evidence_ids'] or
                any(not isinstance(case, str) for case in item['evidence_ids']) or
                not set(item['evidence_ids']).issubset(set(case_ids))):
            raise EvaluationError('criterion needs comparison, observation and evidence')
    if quality_gate is not None:
        quality_target_assessment(report, quality_gate, case_ids, 'A')
        quality_target_assessment(report, quality_gate, case_ids, 'B')
    protected = [item for item in items if item['criterion_id'] in required_nonregression]
    incumbent_label = 'A' if candidate_label == 'B' else 'B'
    if any(item['comparison'] == incumbent_label for item in protected):
        return 'REJECT', 'candidate regressed on a protected qualitative criterion'
    if any(item['comparison'] == 'UNCERTAIN' for item in protected):
        return 'HOLD', 'protected qualitative criterion not verified'
    if report['verdict'] == candidate_label:
        if report.get('material_regressions'):
            return 'HOLD', 'judge noted material regressions despite preferred candidate'
        if report.get('confidence') == 'low':
            return 'HOLD', 'judge not confident in candidate advantage'
        return 'PASS', 'blind judge preferred candidate'
    if report['verdict'] == 'UNCERTAIN' or report['verdict'] == 'TIE':
        return 'HOLD', 'blind judge found no proven gain'
    return 'REJECT', 'blind judge preferred incumbent'


def external_assessment(contract, workspace, incumbent_metrics=None, baseline_target_unmet=False):
    checks = []
    for check in contract.get('hard_checks', []):
        output = run_argv(check['argv'], workspace, check.get('timeout_seconds', 120))
        output['id'] = check.get('id', 'hard-check')
        checks.append(output)
        if output['returncode']:
            return 'REJECT', {'reason': f'hard check failed: {output["id"]}', 'checks': checks}
    if contract.get('negative_control'):
        negative = contract['negative_control']
        if not isinstance(negative.get('argv'), list):
            return 'HOLD', {'reason': 'invalid known-bad control'}
        control_result = run_argv(negative['argv'], workspace, negative.get('timeout_seconds', 120))
        if control_result['returncode']:
            return 'HOLD', {'reason': 'known-bad control could not execute', 'control': control_result}
        try:
            control_score = metric_assessment(contract, json.loads(control_result['stdout']), incumbent_metrics)
        except (EvaluationError, ValueError):
            control_score = {'status': 'REJECT'}
        if control_score['status'] != 'REJECT':
            return 'HOLD', {'reason': 'known-bad control incorrectly passed evaluator'}
    if contract.get('benchmark'):
        output = run_argv(contract['benchmark']['argv'], workspace, contract['benchmark'].get('timeout_seconds', 120))
        if output['returncode']:
            return 'HOLD', {'reason': 'benchmark did not finish successfully', 'checks': checks, 'benchmark': output}
        try:
            data = json.loads(output['stdout'])
            score = metric_assessment(contract, data, incumbent_metrics)
        except (ValueError, EvaluationError) as exc:
            return 'HOLD', {'reason': f'invalid benchmark evidence: {exc}', 'checks': checks}
        if score['status'] == 'REJECT':
            return 'REJECT', {'reason': score['reason'], 'checks': checks, 'benchmark': score}
        if (not contract.get('review', {}).get('required') and
                not any(m.get('role', 'primary') == 'primary' for m in contract.get('primary_metrics', []))):
            return 'HOLD', {'reason': 'benchmark guards alone do not demonstrate outcome improvement',
                            'checks': checks, 'benchmark': score}
        return 'PASS', {'reason': 'benchmark and hard checks passed', 'checks': checks, 'benchmark': score}
    if (not contract.get('review', {}).get('required') and
            not any(m.get('role', 'primary') == 'primary' for m in contract.get('primary_metrics', []))):
        if baseline_target_unmet and contract.get('target_checks'):
            target_proof = target_checks_assessment(contract, workspace)
            if target_proof['status'] == 'MET':
                return 'PASS', {'reason': 'previously failing frozen target checks now pass',
                                'checks': checks, 'target_check_proof': target_proof}
            return 'HOLD', {'reason': 'previously failing target checks remain incomplete',
                            'checks': checks, 'target_check_proof': target_proof}
        return 'HOLD', {'reason': 'regression guards alone do not demonstrate user-visible improvement'}
    if contract.get('primary_metrics'):
        return 'HOLD', {'reason': 'primary metric needs executable benchmark'}
    return 'PASS', {'reason': 'hard checks passed or qualitative judge required', 'checks': checks}


def decision(contract, benchmark_status, judge_status):
    if benchmark_status == 'REJECT' or judge_status == 'REJECT':
        return 'REJECT'
    if benchmark_status != 'PASS':
        return 'HOLD'
    if contract.get('review', {}).get('required') and judge_status != 'PASS':
        return 'HOLD'
    return 'KEEP'


def target_checks_assessment(contract, workspace):
    checks = contract.get('target_checks', [])
    if not checks:
        return {'status': 'NOT_CONFIGURED', 'checks': []}
    checked = []
    failed = False
    for check in checks:
        try:
            result = run_argv(check['argv'], workspace, check.get('timeout_seconds', 120))
        except (OSError, subprocess.TimeoutExpired, EvaluationError) as exc:
            return {'status': 'UNKNOWN', 'reason': f'target check could not run: {exc}',
                    'checks': checked}
        result['id'] = check.get('id', 'target-check')
        checked.append(result)
        failed = failed or result['returncode'] != 0
    return {'status': 'NOT_MET' if failed else 'MET', 'checks': checked}


def target_metrics_assessment(contract, details):
    metrics = [m for m in contract.get('primary_metrics', []) if 'target_value' in m]
    if not metrics:
        return {'status': 'NOT_CONFIGURED'}
    observed = details.get('benchmark', {}).get('metrics', {})
    if not isinstance(observed, dict):
        return {'status': 'UNKNOWN'}
    cases = []
    for metric in metrics:
        item = observed.get(metric['name'])
        if not isinstance(item, dict) or not isinstance(item.get('value'), (float, int)):
            return {'status': 'UNKNOWN'}
        value = item['value']
        reached = value <= metric['target_value'] if metric['direction'] == 'lower' else value >= metric['target_value']
        cases.append({'name': metric['name'], 'value': value, 'target_value': metric['target_value'], 'met': reached})
    return {'status': 'MET' if all(x['met'] for x in cases) else 'NOT_MET', 'metrics': cases}


def completion_status(decision_status, quality_target, target_checks=None, target_metrics=None):
    if decision_status == 'HOLD':
        return 'UNKNOWN'
    if decision_status == 'REJECT':
        return 'NOT_MET'
    statuses = [quality_target.get('status', 'UNKNOWN'),
                (target_checks or {}).get('status', 'NOT_CONFIGURED'),
                (target_metrics or {}).get('status', 'NOT_CONFIGURED')]
    if 'NOT_MET' in statuses:
        return 'NOT_MET'
    if 'UNKNOWN' in statuses:
        return 'UNKNOWN'
    if 'MET' in statuses:
        return 'MET'
    return 'NOT_CONFIGURED'

def evaluate(contract_path, workspace, review=None, incumbent_metrics=None, baseline_target_unmet=False):
    contract, contract_hash = read_contract(contract_path)
    try:
        benchmark_status, details = external_assessment(contract, workspace, incumbent_metrics, baseline_target_unmet)
    except (OSError, subprocess.TimeoutExpired, EvaluationError) as exc:
        benchmark_status, details = 'HOLD', {'reason': f'benchmark not verifiable: {exc}'}
    judge_status = 'NOT_REQUIRED'
    judge_detail = {}
    if contract.get('review', {}).get('required'):
        if review is None:
            judge_status, judge_detail = 'HOLD', {'reason': 'independent judge unavailable'}
        else:
            try:
                judge_status, message = review_verdict(review, contract['review']['criteria'],
                                                       contract['case_ids'], contract['review'].get('candidate_label', 'B'),
                                                       contract['review'].get('quality_gate'),
                                                       contract['review'].get('required_nonregression', []))
                judge_detail = {'reason': message, 'verdict': review['verdict']}
            except EvaluationError as exc:
                judge_status, judge_detail = 'HOLD', {'reason': f'judge evidence invalid: {exc}'}
    status = decision(contract, benchmark_status, judge_status)
    quality_target = {'status': 'NOT_CONFIGURED'}
    if contract.get('review', {}).get('quality_gate'):
        if review is None:
            quality_target = {'status': 'UNKNOWN', 'reason': 'independent review unavailable'}
        else:
            try:
                quality_target = quality_target_assessment(review, contract['review']['quality_gate'],
                                                           contract['case_ids'], contract['review'].get('candidate_label', 'B'))
            except EvaluationError as exc:
                quality_target = {'status': 'UNKNOWN', 'reason': str(exc)}
    target_checks = (details.get('target_check_proof') if benchmark_status == 'PASS' and
                     isinstance(details, dict) and details.get('target_check_proof') else
                     target_checks_assessment(contract, workspace) if benchmark_status == 'PASS'
                     else {'status': 'UNKNOWN', 'reason': 'benchmark did not pass'})
    target_metrics = (target_metrics_assessment(contract, details) if benchmark_status == 'PASS'
                      else {'status': 'UNKNOWN'})
    completion = completion_status(status, quality_target, target_checks, target_metrics)
    return {'schema_version': 1, 'quality_target': quality_target, 'target_checks': target_checks,
            'target_metrics': target_metrics,
            'target_completion': completion,
            'contract_sha256': contract_hash, 'decision': status,
            'benchmark_status': benchmark_status, 'benchmark': details,
            'judge_status': judge_status, 'judge': judge_detail, 'recorded_at_ns': time.time_ns()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--review', type=Path, help='independent, validated judge JSON')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    verdict = evaluate(args.contract, args.workspace, json.loads(args.review.read_text()) if args.review else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2) + '\n')
    print(json.dumps({'decision': verdict['decision'], 'report': str(args.output)}))
    return 0 if verdict['decision'] == 'KEEP' else 3


if __name__ == '__main__':
    sys.exit(main())

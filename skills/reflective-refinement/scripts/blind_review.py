#!/usr/bin/env python3
"""Build result-only A/B evidence and request a separate, structured judgment."""

import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

from evaluation_gate import EvaluationError, review_verdict, quality_target_assessment

ALLOWED_RESULT_TYPES = {'.png', '.jpg', '.jpeg', '.webp', '.json', '.csv', '.txt', '.md'}


def permitted_evidence(workspace, value, artifact):
    root = Path(workspace).resolve()
    source_path = root / value
    if source_path.is_symlink():
        raise EvaluationError('review evidence must not be a symlink')
    path = source_path.resolve(strict=True)
    source = Path(artifact).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise EvaluationError('invalid or external review evidence')
    if path == source or (source.is_dir() and path.is_relative_to(source)):
        raise EvaluationError('review evidence must not contain editable source')
    if path.suffix.lower() not in ALLOWED_RESULT_TYPES or not path.stat().st_size:
        raise EvaluationError('review accepts only nonempty outputs, not implementation')
    if not any(part in {'evidence', '.refinement', 'screenshots', 'reports', 'reference', 'references', 'referencia'} for part in path.relative_to(root).parts):
        raise EvaluationError('review evidence must come from an evidence/results directory')
    return path


def build_bundle(bundle, workspace, artifact, contract, evidence, reverse=False, incumbent_evidence=None):
    """The bundle contains only result files, anonymous labels, the outcome, and frozen criteria."""
    root = Path(bundle)
    root.mkdir(parents=True, exist_ok=True)
    cases = contract['case_ids']
    original = incumbent_evidence if incumbent_evidence is not None else contract.get('reference_evidence', {})
    if set(original) != set(cases) or len(evidence) != len(cases):
        raise EvaluationError('need the original and candidate result for every frozen case')
    mapping = {'A': 'candidate', 'B': 'incumbent'} if reverse else {'A': 'incumbent', 'B': 'candidate'}
    output = {}
    hashes = {'candidate': [], 'incumbent': []}
    for i, case in enumerate(cases):
        output[case] = {}
        for label, role in mapping.items():
            src = original[case] if role == 'incumbent' else evidence[i]
            path = permitted_evidence(workspace, src, artifact)
            suffix = path.suffix.lower()
            safe = re.sub(r"[^a-zA-Z0-9_-]", "_", case)[:24]
            name = f'{i:03d}_{safe}_{label}{suffix}'
            target = root / name
            target.write_bytes(path.read_bytes())
            hashes[role].append(hashlib.sha256(target.read_bytes()).hexdigest())
            output[case][label] = name
    quality_references = {}
    target_references = contract.get('review', {}).get('target_reference_evidence', {})
    for i, case in enumerate(cases):
        if case not in target_references:
            continue
        path = permitted_evidence(workspace, target_references[case], artifact)
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', case)[:24]
        target = root / f'{i:03d}_{safe}_quality_reference{path.suffix.lower()}'
        target.write_bytes(path.read_bytes())
        quality_references[case] = target.name
    rubric = {'schema_version': 1, 'primary_outcome': contract['primary_outcome'],
              'priority_order': contract.get('priority_order', []),
              'kind': contract['kind'], 'case_ids': cases,
              'criteria': contract.get('review', {}).get('criteria', []),
              'criterion_guidance': contract.get('review', {}).get('criterion_guidance', {}),
              'required_nonregression': contract.get('review', {}).get('required_nonregression', []),
              'target_reference_evidence': quality_references,
              'files': output}
    if contract.get('review', {}).get('quality_gate'):
        rubric['quality_gate'] = contract['review']['quality_gate']
    (root / 'review_inputs.json').write_text(json.dumps(rubric, indent=2, ensure_ascii=False), encoding='utf-8')
    prompt = ('You did not create either candidate. Judge only the result files listed in review_inputs.json. '
              'Compare both anonymous alternatives against primary_outcome and all criteria, respecting priority_order when present; hard restrictions cannot be traded for a higher average. '
              'Inspect the actual images or output reports, not file names or implementation. '
              'Tie and uncertainty are valid; do not reward effort, iteration count, or novelty. '
              'Support every criterion with a concrete observed difference and a case id. '
              'External target_reference_evidence, if provided, is an aspiration/reference, not candidate A/B; '
              'judge how each output serves the user goal rather than imitating the reference literally. '
              'Do not assume a defect was fixed. Emit ONLY JSON with fields schema_version=1, '
              'case_ids, verdict=A|B|TIE|UNCERTAIN, confidence=low|medium|high, criteria (list of '
              'criterion_id, comparison, observation, evidence_ids), material_regressions (list), '
              'uncertainties (list). No source code is provided.\n')
    if contract.get('review', {}).get('quality_gate'):
        prompt += ('Inspect EVERY frozen scenario for BOTH anonymous alternatives A and B. '
                   'Scenario groups can represent user journeys, workload regimes, interaction states, '
                   'documents, rendered viewpoints or transitions: use the actual contract, not an assumed domain. '
                   'Grade each output against the user target separately, even when one is better than the other. '
                   'Emit quality_by_label with keys A and B. Each key contains case_observations '
                   '(case_id, worst_severity, concrete observation for EVERY case) and quality_findings '
                   '(severity, description, evidence_ids). Empty findings mean none observed. '
                   'Each observation worst_severity must agree with its cited findings. '
                   'Use severity_anchors if given; otherwise minor=cosmetic/local, medium=material '
                   'in focused use, major=obvious obstruction to intended use, critical=invalid '
                   'core outcome or safety/correctness constraint. '
                   'Do not infer target compliance from a relative win; report only grounded findings.\n')
    (root / 'judge_prompt.txt').write_text(prompt, encoding='utf-8')
    return mapping, hashes, rubric


def parse_judge_output(result, output_file):
    candidate = output_file.read_text(encoding='utf-8') if output_file.exists() else result.stdout
    try:
        return json.loads(candidate)
    except ValueError:
        matches = re.findall(r'```(?:json)?\s*\n(.*?)\n```', candidate, flags=re.I | re.S)
        if len(matches) == 1:
            try:
                return json.loads(matches[0])
            except ValueError:
                pass
        raise EvaluationError('judge failed to produce valid JSON')


def execute_judge(provider, bundle, argv=None, timeout=180):
    """New process; without a filesystem sandbox this is prompt-blind, not access-proof."""
    bundle = Path(bundle)
    prompt = (bundle / 'judge_prompt.txt').read_text(encoding='utf-8')
    prompt += '\nRead review_inputs.json and the listed evidence files in this directory.\n'
    out = bundle / 'judge_output.json'
    if provider == 'codex':
        cmd = [str((argv or ['codex'])[0]), 'exec', '--sandbox', 'read-only', '--output-schema',
               str(Path(__file__).resolve().parents[1] / 'references' / 'judge.schema.json'),
               '-o', str(out), '-']
    elif provider == 'claude':
        cmd = [str((argv or ['claude'])[0]), '-p', '--output-format', 'text']
    elif provider == 'command':
        if not argv or not isinstance(argv, list):
            raise EvaluationError('custom judge requires an explicit argv adapter')
        cmd = argv
    else:
        raise EvaluationError('no supported judge process; use a declared custom command adapter')
    env = {k: v for k, v in os.environ.items() if not k.startswith('RR_')}
    try:
        result = subprocess.run(cmd, input=prompt, text=True, capture_output=True,
                                cwd=bundle, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvaluationError(f'judge unavailable: {exc}') from exc
    if result.returncode:
        raise EvaluationError('judge exited unsuccessfully: ' + result.stderr[-600:])
    return parse_judge_output(result, out)




def calibrate_judge(contract, workspace, artifact, provider, argv=None, timeout=180):
    """Known-equal and optionally known-bad controls must be identified correctly."""
    cases = contract['case_ids']
    original = contract.get('reference_evidence', {})
    with tempfile.TemporaryDirectory(prefix='rr-judge-calibrate-') as tmp:
        folder = Path(tmp) / 'equal'
        build_bundle(folder, workspace, artifact, contract, [original[c] for c in cases])
        equal = execute_judge(provider, folder, argv, timeout)
        quality_gate = contract['review'].get('quality_gate')
        review_verdict(equal, contract['review']['criteria'], cases, 'B', quality_gate)
        if quality_gate:
            same_a = quality_target_assessment(equal, quality_gate, cases, 'A')
            same_b = quality_target_assessment(equal, quality_gate, cases, 'B')
            if same_a['status'] != same_b['status'] or same_a['blocking_findings'] != same_b['blocking_findings']:
                return {'status':'HOLD', 'reason':'same evidence received inconsistent target severity'}
        if equal['verdict'] != 'TIE':
            return {'status':'HOLD','reason':'reviewer failed identical A=A control','equal_verdict':equal['verdict']}
        bad = contract.get('review', {}).get('known_bad_evidence')
        if bad:
            folder = Path(tmp) / 'negative'
            build_bundle(folder, workspace, artifact, contract, [bad[c] for c in cases])
            negative = execute_judge(provider, folder, argv, timeout)
            review_verdict(negative, contract['review']['criteria'], cases, 'B', quality_gate)
            if negative['verdict'] != 'A':
                return {'status':'HOLD','reason':'reviewer failed known-bad control',
                        'negative_verdict':negative['verdict']}
    return {'status':'PASS','reason':'blind reviewer passed A=A and available negative control'}


def review(contract, workspace, artifact, candidate_evidence, provider='none', argv=None, timeout=180, incumbent_evidence=None):
    if provider == 'none':
        return {'status': 'HOLD', 'reason': 'no independent model reviewer configured', 'source_isolation': 'unavailable'}
    outcomes = []
    runs = [False, True] if contract.get('review', {}).get('reverse_order', False) else [False]
    with tempfile.TemporaryDirectory(prefix='rr-blind-') as tmp:
        for index, reverse in enumerate(runs):
            bundle = Path(tmp) / f'pair-{index + 1}'
            mapping, hashes, rubric = build_bundle(bundle, workspace, artifact, contract,
                                                   candidate_evidence, reverse=reverse,
                                                   incumbent_evidence=incumbent_evidence)
            if hashes['incumbent'] == hashes['candidate']:
                return {'status': 'HOLD', 'reason': 'A=A: identical evidence is not an improvement',
                        'source_isolation': 'not_enforced'}
            response = execute_judge(provider, bundle, argv, timeout=timeout)
            quality_gate = contract.get('review', {}).get('quality_gate')
            status, reason = review_verdict(response, contract['review']['criteria'],
                                             contract['case_ids'], 'A' if reverse else 'B', quality_gate,
                                             contract['review'].get('required_nonregression', []))
            quality = (quality_target_assessment(response, quality_gate, contract['case_ids'],
                                                  'A' if reverse else 'B')
                       if quality_gate else {'status': 'NOT_CONFIGURED'})
            outcomes.append({'status': status, 'quality_target': quality, 'reason': reason,
                             'verdict': response.get('verdict'),
                             'response': response, 'bundle_hashes': hashes})
    if any(o['status'] == 'REJECT' for o in outcomes):
        result = 'REJECT'
    elif all(o['status'] == 'PASS' for o in outcomes):
        result = 'PASS'
    else:
        result = 'HOLD'
    quality_results = [o['quality_target']['status'] for o in outcomes]
    quality_status = ('NOT_CONFIGURED' if not contract.get('review', {}).get('quality_gate') else
                      quality_results[0] if quality_results and len(set(quality_results)) == 1 else
                      'UNKNOWN')
    return {'status': result, 'quality_target': {'status': quality_status}, 'runs': outcomes,
            'source_isolation': 'not_enforced', 'context_isolation': 'fresh_process',
            'note': 'Judge saw only the bundle, but same-user filesystem access was not technically blocked'}

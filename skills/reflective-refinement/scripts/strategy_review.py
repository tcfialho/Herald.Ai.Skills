#!/usr/bin/env python3
"""Independent, report-only search critique for a stalled refinement campaign."""

import json
import os
from pathlib import Path
import subprocess
import tempfile


class StrategyError(Exception):
    pass


def recent_context(goal, records, reports, failure=None):
    trials = []
    for record in records[-5:]:
        trials.append({'number': record['number'], 'hypothesis': record['hypothesis'],
                       'finding': record['finding'], 'outcome': record['outcome']})
    return {'goal': goal, 'recent_trials': trials,
            'recent_assessments': [{key: report.get(key) for key in
                                    ('decision', 'benchmark_status', 'judge_status', 'target_completion',
                                     'target_checks', 'target_metrics', 'quality_target')}
                                   for report in reports[-5:]],
            'last_worker_failure': (failure or '')[:1000]}


def validate_advice(advice):
    if not isinstance(advice, dict) or set(('hypothesis', 'evidence', 'next_check', 'failure_mode')) - advice.keys():
        raise StrategyError('independent strategy report missing required fields')
    for key in ('hypothesis', 'evidence', 'next_check', 'failure_mode'):
        if not isinstance(advice[key], str) or len(advice[key].strip()) < 12:
            raise StrategyError(f'unsupported independent strategy field: {key}')
    return {key: advice[key].strip()[:1500] for key in
            ('hypothesis', 'evidence', 'next_check', 'failure_mode')}


def advise(provider, goal, records, reports, failure=None, executable=None, timeout=120):
    """New isolated process with only results; advisory, never overrides acceptance."""
    if provider not in ('codex', 'claude'):
        raise StrategyError('no independent planner CLI selected')
    context = recent_context(goal, records, reports, failure)
    prompt = ('You are an independent diagnostic strategist. You did not implement the changes. '
              'Read ONLY the JSON evidence supplied below; do not inspect any project source or other files. '
              'Do not approve code or claim the goal is complete. Identify a different, falsifiable '
              'next hypothesis, an executable test and the weakness in the existing evaluation. '
              'Find a public/anonymous representative workload if the current test is misleading. '
              'Do not ask the user to decide ordinary technical choices. '
              'Return only JSON with substantive strings: hypothesis, evidence, next_check, failure_mode.\n'
              + json.dumps(context, ensure_ascii=False))
    with tempfile.TemporaryDirectory(prefix='rr-strategy-') as tmp:
        root = Path(tmp)
        result_path = root / 'advice.json'
        schema = root / 'schema.json'
        schema.write_text(json.dumps({'type': 'object', 'additionalProperties': False,
                'required': ['hypothesis', 'evidence', 'next_check', 'failure_mode'],
                'properties': {key: {'type': 'string'} for key in
                               ('hypothesis', 'evidence', 'next_check', 'failure_mode')}}))
        if provider == 'codex':
            command = [executable or 'codex', 'exec', '--sandbox', 'read-only',
                       '--skip-git-repo-check', '-C', str(root),
                       '--output-schema', str(schema), '-o', str(result_path), '-']
        else:
            command = [executable or 'claude', '-p', '--permission-mode', 'plan', '--output-format', 'text']
        try:
            result = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                    cwd=root, timeout=timeout,
                                    env={key: value for key, value in os.environ.items() if not key.startswith('RR_')})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StrategyError(f'independent strategy unavailable: {exc}') from exc
        if result.returncode:
            raise StrategyError(f'independent strategy exited {result.returncode}: {result.stderr[-350:]}')
        source = result_path.read_text() if result_path.is_file() else result.stdout
        try:
            return validate_advice(json.loads(source))
        except ValueError as exc:
            raise StrategyError('independent strategy output is not JSON') from exc

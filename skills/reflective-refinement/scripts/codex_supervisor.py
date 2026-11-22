#!/usr/bin/env python3
"""Portable CLI supervisor; the agent cannot end an explicit N-trial contract early."""

import argparse
import re
import json
import hashlib
import os
from pathlib import Path
import shutil
import shlex
import signal
import subprocess
import sys
import time

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / 'scripts'))
import loop_guard  # noqa: E402
import agent_adapters
import evaluation_gate
import blind_review
import strategy_review


class SupervisorError(Exception):
    pass


class WorkerInvocationError(SupervisorError):
    pass


def read_state(directory):
    return loop_guard.load(directory)


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    status = Path(f'/proc/{pid}/stat')
    if status.is_file():
        try:
            return status.read_text().split(') ', 1)[1][0] != 'Z'
        except (OSError, IndexError):
            pass
    return True


def create_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            try:
                stamp = path.stat()
                pid = json.loads(path.read_text())['pid']
                if not isinstance(pid, int) or pid <= 0 or process_alive(pid):
                    raise SupervisorError(f'another supervisor may own {path}: pid={pid}')
                if path.stat().st_ino == stamp.st_ino:
                    path.unlink()
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                raise SupervisorError(f'unreadable lock {path}; inspect before removing') from exc
    else:
        raise SupervisorError(f'could not reclaim stale lock: {path}')
    with os.fdopen(fd, 'w') as stream:
        json.dump({'pid': os.getpid(), 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, stream)
    return path


def ensure_git(root, allow_dirty):
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if result.returncode or Path(result.stdout.strip()).resolve() != root:
        raise SupervisorError('workspace must be the root of an existing Git repository')
    status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all'],
                            capture_output=True, text=True, check=True).stdout
    output_roots = {'screenshots', 'evidence', 'reports', 'captures', 'trabalho'}
    relevant = [line for line in status.splitlines() if not line[3:].startswith('.refinement/')
                and line[3:].split('/', 1)[0] not in output_roots]
    if relevant and not allow_dirty:
        raise SupervisorError('source changes are uncommitted; commit/checkpoint first or use --allow-dirty explicitly')


def protected_hashes(root, names):
    hashes = {}
    for name in names:
        item = (root / name).resolve(strict=True)
        if not item.is_relative_to(root) or not (item.is_file() or item.is_dir()):
            raise SupervisorError(f'protected path must be inside repository: {name}')
        hashes[str(item)] = (loop_guard.artifact_hash(item) if item.is_dir() else hashlib.sha256(item.read_bytes()).hexdigest())
    return hashes


def run_verifier(args, invocation):
    if not args.verify_command:
        return None
    command = shlex.split(args.verify_command)
    if not command:
        raise SupervisorError('empty verifier command')
    try:
        result = subprocess.run(command, cwd=args.workspace, capture_output=True,
                                text=True, timeout=args.verify_timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        result = None
        failure = str(exc)
    report = {'command': command, 'returncode': result.returncode if result else -1,
              'stdout': result.stdout[-12000:] if result else '',
              'stderr': result.stderr[-12000:] if result else failure}
    (args.state_dir / 'turns' / f'{invocation:04d}.verify.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    return report['returncode']




def automatic_protected_paths(args, contract):
    paths = [str(p) for p in args.protect]
    state_dir = getattr(args, 'state_dir', None)
    target_baseline = state_dir / 'target_baseline.json' if state_dir is not None else None
    if target_baseline is not None and target_baseline.is_file():
        paths.append(str(target_baseline))
    if args.evaluation_contract:
        paths.append(str(args.evaluation_contract))
        paths.extend(contract.get('protected_paths', []))
        for mapping in (contract.get('reference_evidence', {}),
                        contract.get('review', {}).get('target_reference_evidence', {}),
                        contract.get('review', {}).get('known_bad_evidence', {})):
            for value in mapping.values():
                candidate = (args.workspace / value).resolve()
                if not candidate.is_relative_to(args.workspace) or not candidate.is_file():
                    raise SupervisorError('frozen reference evidence missing or outside workspace')
                paths.append(str(candidate))
        commands = [*contract.get('hard_checks', []), *contract.get('target_checks', [])]
        if contract.get('benchmark'):
            commands.append(contract['benchmark'])
        if contract.get('negative_control'):
            commands.append(contract['negative_control'])
        for check in commands:
            for part in check.get('argv', []):
                possible = (args.workspace / part).resolve()
                if possible.is_relative_to(args.workspace) and possible.is_file():
                    paths.append(str(possible))
    return list(dict.fromkeys(paths))


def check_review_provenance(state_dir, state):
    for record in state['records']:
        if record.get('evaluation_sha256') and record.get('evaluation_file'):
            path = (state_dir / record['evaluation_file']).resolve()
            if not path.is_relative_to(state_dir) or not path.is_file():
                raise SupervisorError('prior external verdict has disappeared or escaped state directory')
            if hashlib.sha256(path.read_bytes()).hexdigest() != record['evaluation_sha256']:
                raise SupervisorError('prior external verdict was modified; investigate before continuing')


def external_trial_review(args, state, invocation, contract):
    latest = state['records'][-1]
    if latest.get('proposed_outcome') != 'keep':
        return None
    logs = args.state_dir / 'turns'
    logs.mkdir(parents=True, exist_ok=True)
    review_result = None
    if contract and contract.get('review', {}).get('required'):
        try:
            calibration = {'status': 'PASS', 'reason': 'calibration explicitly disabled'}
            if contract['review'].get('calibrate', contract['kind'] in ('visual', 'ux')):
                calibration_path = args.state_dir / 'judge_calibration.json'
                config_id = hashlib.sha256(json.dumps({'contract': evaluation_gate.digest(args.evaluation_contract),
                         'provider': args.judge_provider, 'command': args.judge_command}, sort_keys=True).encode()).hexdigest()
                if calibration_path.is_file():
                    cached = json.loads(calibration_path.read_text())
                    if cached.get('config_id') == config_id:
                        calibration = cached['result']
                    else:
                        raise SupervisorError('judge calibration config changed; inspect before continuing')
                else:
                    calibration = blind_review.calibrate_judge(contract, args.workspace,
                        Path(state['artifact']), args.judge_provider, args.judge_command, args.verify_timeout)
                    calibration_path.write_text(json.dumps({'config_id': config_id, 'result': calibration}, indent=2))
            if calibration['status'] != 'PASS':
                review_result = {'status': 'HOLD', 'reason': 'judge failed calibration', 'calibration': calibration}
            else:
                prior = next((r for r in reversed(state['records'][:-1]) if r['outcome'] == 'keep'), None)
                incumbent = (prior.get('incumbent_evidence_snapshot') if prior else None)
                if prior and not incumbent:
                    review_result = {'status': 'HOLD', 'reason': 'accepted incumbent has no frozen visual evidence'}
                else:
                    review_result = blind_review.review(contract, args.workspace, Path(state['artifact']),
                                                        latest['evidence'], provider=args.judge_provider,
                                                        argv=args.judge_command, timeout=args.verify_timeout,
                                                        incumbent_evidence=(dict(zip(contract['case_ids'], incumbent))
                                                            if incumbent else None))
                review_result['calibration'] = calibration
        except (evaluation_gate.EvaluationError, OSError, ValueError) as exc:
            review_result = {'status':'HOLD','reason': f'blind review unavailable: {exc}'}
    if contract:
        incumbent_metrics = next((r['verified_metrics'] for r in reversed(state['records'][:-1])
                                  if r.get('outcome') == 'keep' and r.get('verified_metrics')), {})
        target_baseline_path = args.state_dir / 'target_baseline.json'
        target_unmet = False
        if state.get('mode') == 'goal' and target_baseline_path.is_file():
            target_baseline = json.loads(target_baseline_path.read_text())
            if (target_baseline.get('contract_sha256') != evaluation_gate.digest(args.evaluation_contract)
                    or target_baseline.get('status') != 'NOT_MET'):
                raise SupervisorError('baseline target proof was invalid or changed')
            target_unmet = True
        outcome = evaluation_gate.evaluate(args.evaluation_contract, args.workspace,
                                           incumbent_metrics=incumbent_metrics,
                                           baseline_target_unmet=target_unmet)
        if contract.get('review', {}).get('required'):
            outcome['judge_status'] = review_result['status']
            outcome['judge'] = review_result
            outcome['quality_target'] = review_result.get('quality_target', {'status': 'UNKNOWN'})
            outcome['decision'] = evaluation_gate.decision(contract, outcome['benchmark_status'], review_result['status'])
            outcome['target_completion'] = evaluation_gate.completion_status(
                outcome['decision'], outcome['quality_target'], outcome.get('target_checks'), outcome.get('target_metrics'))
    else:
        outcome = {'schema_version':1,'decision':'HOLD', 'benchmark_status':'UNVERIFIED',
                   'judge_status':'NOT_RUN', 'reason':'no frozen outcome evaluation contract; no independent quality claim'}
    if args.verify_command:
        code = run_verifier(args, invocation)
        if code:
            outcome['decision'] = 'REJECT'
            outcome['legacy_verifier_failed'] = True
    if contract:
        outcome['target_completion'] = evaluation_gate.completion_status(
            outcome['decision'], outcome.get('quality_target', {'status': 'UNKNOWN'}),
            outcome.get('target_checks'), outcome.get('target_metrics'))
    report = logs / f'{invocation:04d}.evaluation.json'
    report.write_text(json.dumps(outcome, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if state.get('promotion_mode') == 'external' and outcome['decision'] != 'KEEP':
        loop_guard.resolve_promotion(args.state_dir, latest['number'], outcome['decision'], report)
    elif outcome['decision'] != 'KEEP':
        with loop_guard.ledger_lock(args.state_dir):
            current = loop_guard.load(args.state_dir)
            if current['records'][-1]['candidate_sha256'] != latest['candidate_sha256']:
                raise SupervisorError('legacy receipt identity changed during external review')
            current['records'][-1]['outcome'] = 'discard' if outcome['decision'] == 'REJECT' else 'hold'
            current['records'][-1]['evaluation_sha256'] = hashlib.sha256(report.read_bytes()).hexdigest()
            loop_guard.save(args.state_dir, current)
    print(f'OUTCOME: trial={latest["number"]} decision={outcome["decision"]} evidence={report}', flush=True)
    return outcome




def git_value(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise SupervisorError(result.stderr.strip() or 'git recovery failed')
    return result.stdout.strip()


EVIDENCE_ROOTS = {'screenshots', 'evidence', 'reports', 'captures', 'trabalho', 'reference', 'referencia'}


INTERPRETER_CACHE_DIRS = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}


def interpreter_cache(path):
    """Bytecode/tool caches appear whenever checks run; they are never candidate source."""
    return path.endswith('.pyc') or any(part in INTERPRETER_CACHE_DIRS for part in path.split('/'))


def evidence_output(path, receipt=()):
    if interpreter_cache(path):
        return True
    if path in receipt:
        return True
    return path.startswith('.refinement/') or path.split('/', 1)[0] in EVIDENCE_ROOTS


def changed_paths(root, before_commit):
    tracked = git_value(root, 'diff', '--name-only', before_commit).splitlines()
    untracked = git_value(root, 'ls-files', '--others', '--exclude-standard').splitlines()
    committed = git_value(root, 'diff', '--name-only', before_commit, 'HEAD').splitlines()
    return set(tracked + untracked + committed)


def ensure_scoped_changes(args, before_commit, receipt=()):
    scope = args.artifact.rstrip('/') + '/'
    outside = [name for name in changed_paths(args.workspace, before_commit)
               if name != args.artifact and not name.startswith(scope) and not evidence_output(name, receipt)]
    if outside:
        raise SupervisorError(f'worker changed files outside source/evidence scope: {sorted(outside)[:8]}')


def checkpoint_accepted(args, record):
    source = loop_guard.scoped_path(args.workspace, args.artifact)
    if loop_guard.artifact_hash(source) != record['candidate_sha256']:
        raise SupervisorError('cannot commit accepted source: candidate identity changed')
    git_value(args.workspace, 'add', '--', args.artifact)
    staged = git_value(args.workspace, 'diff', '--cached', '--name-only').splitlines()
    if any(name != args.artifact and not name.startswith(args.artifact.rstrip('/') + '/')
           for name in staged):
        raise SupervisorError('unrelated staged changes; refusing accepted checkpoint')
    if staged:
        git_value(args.workspace, 'commit', '-m', f'rr: accept experiment {record["number"]}')
    if loop_guard.artifact_hash(source) != record['candidate_sha256']:
        raise SupervisorError('accepted source changed during checkpoint')
    return git_value(args.workspace, 'rev-parse', 'HEAD')


def snapshot_accepted_evidence(args, state, contract):
    if not contract or not contract.get('review', {}).get('required'):
        return state
    record = state['records'][-1]
    if record['outcome'] != 'keep':
        return state
    cases = contract['case_ids']
    if len(record['evidence']) != len(cases):
        raise SupervisorError('accepted evidence does not cover all frozen scenarios')
    root = args.state_dir / 'accepted-evidence' / f'{record["number"]:04d}'
    root.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for index, name in enumerate(record['evidence']):
        original = blind_review.permitted_evidence(args.workspace, name, Path(state['artifact']))
        data = original.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['evidence_sha256'][index]:
            raise SupervisorError('accepted evidence changed before archival')
        target = root / f'{index:03d}{original.suffix.lower()}'
        target.write_bytes(data)
        snapshots.append(str(target.relative_to(args.workspace)))
    with loop_guard.ledger_lock(args.state_dir):
        current = read_state(args.state_dir)
        if current['records'][-1]['candidate_sha256'] != record['candidate_sha256']:
            raise SupervisorError('receipt changed during accepted evidence archival')
        current['records'][-1]['incumbent_evidence_snapshot'] = snapshots
        current['records'][-1]['incumbent_evidence_sha256'] = record['evidence_sha256']
        loop_guard.save(args.state_dir, current)
    return read_state(args.state_dir)


def verify_accepted_evidence(args, state):
    for record in state['records']:
        snapshots = record.get('incumbent_evidence_snapshot', [])
        if len(snapshots) != len(record.get('incumbent_evidence_sha256', [])):
            raise SupervisorError('accepted evidence manifest is incomplete')
        for name, expected in zip(snapshots, record.get('incumbent_evidence_sha256', [])):
            path = loop_guard.scoped_path(args.workspace, name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise SupervisorError('accepted incumbent evidence was modified')


def restore_unapproved_candidate(args, record, before_commit, before_sha, snapshot=None):
    """Keep result files; archive and revert only source files from this rejected experiment."""
    source = loop_guard.scoped_path(args.workspace, args.artifact)
    current = loop_guard.artifact_hash(source)
    ensure_scoped_changes(args, before_commit, record.get('evidence', []))
    if current != record['candidate_sha256']:
        raise SupervisorError('source changed after receipt; cannot safely restore it')
    archive = args.state_dir / 'rejected'
    archive.mkdir(parents=True, exist_ok=True)
    patch = subprocess.run(['git', '-C', str(args.workspace), 'diff', '--binary', before_commit, '--', args.artifact],
                           capture_output=True)
    if patch.returncode:
        raise SupervisorError('could not archive rejected candidate diff')
    (archive / f'{record["number"]:04d}.patch').write_bytes(patch.stdout)
    (archive / f'{record["number"]:04d}.parent').write_text(before_commit + '\n', encoding='utf-8')
    if git_value(args.workspace, 'rev-parse', 'HEAD') != before_commit:
        git_value(args.workspace, 'reset', '--mixed', before_commit)
    if snapshot is not None and snapshot.is_file() and source.is_file():
        source.write_bytes(snapshot.read_bytes())
        git_value(args.workspace, 'add', '--', args.artifact)
        git_value(args.workspace, 'reset', '--', args.artifact)
    else:
        git_value(args.workspace, 'restore', '--source', before_commit, '--staged', '--worktree', '--', args.artifact)
        added = git_value(args.workspace, 'ls-files', '--others', '--exclude-standard', '--', args.artifact).splitlines()
        for name in added:
            candidate = (args.workspace / name).resolve()
            if not candidate.is_relative_to(source) or not candidate.is_file() or candidate.is_symlink():
                raise SupervisorError('unexpected source entry during rollback; manual recovery needed')
            archived = archive / f'{record["number"]:04d}.added' / name
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, archived)
            candidate.unlink()
    if loop_guard.artifact_hash(source) != before_sha:
        raise SupervisorError('source restore did not match accepted parent hash; halt campaign')
    if git_value(args.workspace, 'rev-parse', 'HEAD') != before_commit:
        raise SupervisorError('HEAD changed unexpectedly while restoring rejected source')
    return str(archive / f'{record["number"]:04d}.patch')


def user_prompt(args, state, attempt, strategy=None):
    status = loop_guard.status_dict(state)
    guard = SKILL_ROOT / 'scripts' / 'loop_guard.py'
    target = state['target']
    required = ('the externally verified DONE WHEN objective' if state.get('mode') == 'goal'
                else f'EXACTLY {target} real candidate experiments')
    progress = (f'{status["completed"]} evaluated; target not yet verified' if state.get('mode') == 'goal'
                else f'{status["completed"]}/{target}')
    retry_guidance = ''
    if attempt > 1:
        retry_guidance = (f'LAST INVOCATION DID NOT PRODUCE A VERIFIED TRIAL ({progress}). '
                          'A prose declaration of success is not the user-requested count. '
                          'Choose a DIFFERENT, evidence-grounded mechanism or test an unexamined adverse state; '
                          'perform begin/change/inspect/finish before returning. '
                          'If this is impossible, state the precise tool/access blocker; do not invent a trial.')
    advice = (f'INDEPENDENT SEARCH CRITIQUE (advisory, independently verify it): '
              f'{json.dumps(strategy, ensure_ascii=False)}' if strategy else '')
    return f'''Read and apply the exact installed skill at: {SKILL_ROOT / 'SKILL.md'}.
Read its references/iteration-contract.md. You are a supervised worker (RR_SUPERVISED=1); DO NOT launch another supervisor. The user requires {required}.
GOAL: {state['goal']}
Source artifact (file/dir) to modify: {state['artifact']}
Current supervisor state: {progress}. Do not treat a model answer, proxy improvement or one A/B comparison as completion.

Make EXACTLY ONE meaningful attempt during this invocation, using this evidence-driven procedure:
1. Inspect the current Git baseline, latest evaluation report (especially target_completion, blocking findings and failed scenarios), and actual output. A KEEP can still be NOT_MET. Choose one new concrete hypothesis tied to a remaining gap or adversarial quality test. Do not repeat the same candidate.
2. BEFORE editing, run `python {guard} begin --state-dir {args.state_dir} --hypothesis "..." --planned-check "..."` with substantive text.
3. Change the source in scope, inspect/run/render the actual output, compare to the incumbent. For visual goals, save a fresh actual screenshot/image under a workspace output folder such as screenshots/, OUTSIDE the source artifact, not just tests or a diff.
4. You may PROPOSE keep, but only external tests and a result-only judge can APPROVE it. BEFORE reverting a rejected candidate, run `python {guard} finish --state-dir {args.state_dir} --outcome keep|discard|inconclusive|crash --finding "..." --evidence path/to/real/evidence`.
5. Do not commit source yourself; the supervisor creates the Git checkpoint after independent approval. Preserve fresh evidence.
6. Stop this AGENT INVOCATION after ONE verified trial, not the user's entire campaign; the external supervisor will run the next trial. You may not declare the campaign COMPLETE. If unable to test, report the precise BLOCKER, and leave the count unchanged.

If you believe the objective already looks solved, check the frozen DONE WHEN conditions and remaining edge cases. Do not fabricate experiments, make no-op changes, or lower quality merely to increase the count. If there is no honest new test, report incomplete/blocker. Do not ask for approval to use public/synthetic/anonymous alternatives; prefer them to personal logged-in data. Never access sensitive account data without authorization.
Important: the external guard, not your prose, decides the count. Retries for this slot: {attempt}. {retry_guidance}
{advice}
'''


def stop_process_group(proc):
    if proc.poll() is not None:
        return
    if os.name != 'nt':
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    else:
        proc.kill()
    proc.wait(timeout=5)


def exec_turn(args, prompt, index, timeout, slot=None):
    cmd = agent_adapters.worker_command(args.harness, args.workspace, executable=args.agent_bin,
                                        model=args.model, custom=args.agent_command,
                                        claude_permission_mode=args.claude_permission_mode)
    logs = args.state_dir / 'turns'
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / f'{index:04d}.events.jsonl'
    stderr_path = logs / f'{index:04d}.stderr.log'
    env = os.environ.copy()
    env.update({'RR_SUPERVISED': '1', 'RR_STATE_DIR': str(args.state_dir), 'RR_GUARD': str(SKILL_ROOT / 'scripts' / 'loop_guard.py'),
                'RR_WORKSPACE': str(args.workspace), 'RR_ARTIFACT': str(args.artifact),
                'RR_SLOT_NUMBER': str(slot or index)})
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        proc = subprocess.Popen(cmd, cwd=args.workspace, env=env, stdin=subprocess.PIPE,
                                stdout=stdout, stderr=stderr, start_new_session=(os.name != 'nt'))
        try:
            proc.communicate(input=prompt.encode('utf-8'), timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_process_group(proc)
            raise WorkerInvocationError(f'Agent turn timed out after {timeout}s; inspect {stdout_path}')
        finally:
            stop_process_group(proc)
        if proc.returncode:
            raise WorkerInvocationError(f'Agent process exited {proc.returncode}; see {stdout_path}, {stderr_path}')
    return stdout_path


def main(argv=None):
    if os.environ.get('RR_SUPERVISED') == '1':
        raise SupervisorError('nested supervisor prohibited inside supervised worker')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', required=True, type=Path)
    p.add_argument('--artifact', required=True, help='source file/directory relative to workspace')
    p.add_argument('--goal', required=True)
    p.add_argument('--iterations', type=int, default=0)
    p.add_argument('--until-target', action='store_true', help='keep going until independent DONE WHEN verification succeeds')
    p.add_argument('--evidence-kind', choices=('generic', 'visual'), default='generic')
    p.add_argument('--state-dir', type=Path, help='default WORKSPACE/.refinement/loop-contract')
    p.add_argument('--codex-bin', default='codex', help='backwards-compatible Codex executable')
    p.add_argument('--harness', choices=('auto','codex','claude','command'), default='codex')
    p.add_argument('--agent-bin', help='override executable for selected provider')
    p.add_argument('--agent-command', help='JSON argv array for AGY or other command adapter')
    p.add_argument('--evaluation-contract', type=Path, help='frozen outcome contract JSON in the workspace')
    p.add_argument('--judge-provider', choices=('auto','none','codex','claude','command'), default='auto')
    p.add_argument('--judge-command', help='JSON argv array for independent reviewer')
    p.add_argument('--model')
    p.add_argument('--claude-permission-mode', choices=('acceptEdits', 'auto', 'default', 'plan', 'bypassPermissions'), default='acceptEdits')
    p.add_argument('--turn-timeout', type=int, default=1800, help='hang protection per turn; not a campaign budget')
    p.add_argument('--max-seconds', type=int, default=0, help='optional total wall-clock budget, 0 = no added deadline')
    p.add_argument('--max-retries', type=int, default=8, help='additional chances after model fails to record a trial')
    p.add_argument('--strategy-provider', choices=('auto', 'none', 'codex', 'claude'), default='auto')
    p.add_argument('--allow-dirty', action='store_true')
    p.add_argument('--protect', action='append', default=[], metavar='PATH', help='file in workspace whose contents must not change')
    p.add_argument('--verify-command', help='optional pinned argv command to independently check promoted candidates')
    p.add_argument('--verify-timeout', type=int, default=300)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args(argv)
    args.goal = ' '.join(args.goal.split())
    args.workspace = args.workspace.resolve(strict=True)
    args.state_dir = (args.state_dir or args.workspace / '.refinement' / 'loop-contract').resolve()
    args.agent_command = json.loads(args.agent_command) if args.agent_command else None
    args.judge_command = json.loads(args.judge_command) if args.judge_command else None
    args.evaluation_contract = args.evaluation_contract.resolve(strict=True) if args.evaluation_contract else None
    if args.evaluation_contract and not args.evaluation_contract.is_relative_to(args.workspace):
        raise SupervisorError('evaluation contract must reside in workspace')
    contract = evaluation_gate.read_contract(args.evaluation_contract)[0] if args.evaluation_contract else None
    if contract and ' '.join(contract['user_goal'].split()) != args.goal:
        raise SupervisorError('evaluation contract goal does not match the explicit user request')
    if contract and contract['kind'] == 'visual' and args.evidence_kind != 'visual':
        raise SupervisorError('visual quality needs actual visual evidence-kind')
    if args.evidence_kind == 'visual' and not contract:
        raise SupervisorError('visual campaign requires a frozen evaluation contract and blind reviewer')
    if args.judge_provider == 'auto':
        if contract and contract.get('review', {}).get('required'):
            if args.judge_command:
                args.judge_provider = 'command'
            elif args.harness in ('codex', 'claude'):
                args.judge_provider = args.harness
            else:
                args.judge_provider = 'none'
        else:
            args.judge_provider = 'none'
    if args.evidence_kind == 'visual' and args.judge_provider == 'none':
        raise SupervisorError('visual campaign has no independent judge adapter; cannot promise visual improvement')
    args.harness = agent_adapters.resolve_provider(args.harness, args.agent_command)
    args.agent_bin = args.agent_bin or (args.codex_bin if args.harness == 'codex' else None)
    if (args.until_target and args.iterations != 0) or (not args.until_target and args.iterations < 1) or (
            args.turn_timeout < 1 or args.max_seconds < 0 or args.max_retries < 0 or args.verify_timeout < 1):
        p.error('invalid count or duration')
    if args.until_target and (not contract or not (
            contract.get('target_checks') or contract.get('review', {}).get('quality_gate') or
            any('target_value' in m for m in contract.get('primary_metrics', [])))):
        raise SupervisorError('until-target requires an independently measurable DONE WHEN contract')
    if args.until_target and contract['kind'] == 'performance' and not contract.get('case_requirements'):
        raise SupervisorError('performance goal requires measured representative case_requirements')
    if args.dry_run:
        ensure_git(args.workspace, args.allow_dirty)
        print(json.dumps({'workspace': str(args.workspace), 'goal': args.goal, 'iterations': args.iterations,
                          'artifact': args.artifact, 'state_dir': str(args.state_dir),
                          'worker_command': agent_adapters.worker_command(args.harness, args.workspace,
                               executable=args.agent_bin, model=args.model, custom=args.agent_command,
                               claude_permission_mode=args.claude_permission_mode)}, indent=2))
        return 0
    if not agent_adapters.executable_available(args.harness, args.agent_bin, args.agent_command):
        print(f'BLOCKED: {args.harness.capitalize()} CLI executable not available; no worker attempts performed', file=sys.stderr)
        return 4
    lock_path = args.state_dir / 'supervisor.lock'
    try:
        ensure_git(args.workspace, args.allow_dirty)
        if loop_guard.scoped_path(args.workspace, args.artifact).is_dir():
            scoped_dirty = git_value(args.workspace, 'status', '--porcelain', '--', args.artifact)
            if scoped_dirty:
                raise SupervisorError('directory artifact must start clean even with --allow-dirty')
        init_result = loop_guard.main(['init', '--state-dir', str(args.state_dir), '--workspace', str(args.workspace),
                                       '--artifact', args.artifact, '--goal', args.goal,
                                       '--iterations', str(args.iterations), '--evidence-kind', args.evidence_kind] +
                                      (['--goal-mode'] if args.until_target else []) +
                                      (['--external-promotion'] if not (args.state_dir / 'contract.json').exists() else []))
        if init_result:
            raise SupervisorError('contract initialization rejected')
        state = read_state(args.state_dir)
        if any(r['outcome'] == 'pending' for r in state['records']):
            raise SupervisorError('unfinished prior promotion: inspect source, evaluation report and Git before resuming')
        if state['evidence_kind'] != args.evidence_kind or state['workspace'] != str(args.workspace):
            raise SupervisorError('workspace or evidence type differs from original contract')
        if args.until_target and contract['kind'] == 'performance' and not state['records']:
            result = evaluation_gate.preflight_performance_benchmark(contract, args.workspace)
            (args.state_dir / 'baseline_fidelity.json').write_text(
                json.dumps(result, indent=2) + '\n', encoding='utf-8')
        if args.until_target and contract.get('target_checks') and not contract.get('primary_metrics') and not contract.get('review', {}).get('required'):
            target_baseline_path = args.state_dir / 'target_baseline.json'
            if state['records']:
                if not target_baseline_path.is_file():
                    raise SupervisorError('cannot resume: frozen target baseline proof is missing')
            else:
                baseline_check = evaluation_gate.target_checks_assessment(contract, args.workspace)
                if baseline_check['status'] != 'NOT_MET':
                    raise SupervisorError('baseline target checks must fail reproducibly before they can prove a gain: '
                                          + baseline_check['status'])
                target_baseline_path.write_text(json.dumps({
                    'status': 'NOT_MET', 'contract_sha256': evaluation_gate.digest(args.evaluation_contract),
                    'source_sha256': state['initial_sha256'], 'checks': baseline_check['checks']}, indent=2) + '\n')
        contract_metadata = {k: state[k] for k in ('version', 'goal', 'target', 'workspace',
                                                  'artifact', 'evidence_kind', 'initial_sha256', 'created_ns', 'promotion_mode')}
        contract_metadata['mode'] = state.get('mode', 'fixed')
        contract_metadata['goal_met'] = state.get('goal_met', False)
        pinned = protected_hashes(args.workspace, automatic_protected_paths(args, contract))
        controller_digest = hashlib.sha256((SKILL_ROOT / 'scripts' / 'loop_guard.py').read_bytes()).hexdigest()
        lock = create_lock(lock_path)
        started = time.monotonic()
        no_progress = 0
        no_improvement = 0
        invocations = 0
        while not (state.get('goal_met', False) if args.until_target else len(state['records']) >= args.iterations):
            check_review_provenance(args.state_dir, state)
            verify_accepted_evidence(args, state)
            if args.max_seconds and time.monotonic() - started >= args.max_seconds:
                raise SupervisorError(f'optional wall-clock budget exhausted: {len(state["records"])}/{args.iterations}')
            old_records = json.dumps(state['records'], sort_keys=True)
            calibration_file = args.state_dir / 'judge_calibration.json'
            calibration_sha = (hashlib.sha256(calibration_file.read_bytes()).hexdigest()
                               if calibration_file.exists() else None)
            parent_commit = git_value(args.workspace, 'rev-parse', 'HEAD')
            parent_source = loop_guard.scoped_path(args.workspace, args.artifact)
            parent_sha = loop_guard.artifact_hash(parent_source)
            snapshot = None
            if parent_source.is_file() and parent_source.stat().st_size <= 50_000_000:
                parent_dir = args.state_dir / 'parents'
                parent_dir.mkdir(parents=True, exist_ok=True)
                snapshot = parent_dir / f'{invocations:04d}.source'
                snapshot.write_bytes(parent_source.read_bytes())
            count_before = len(state['records'])
            invocations += 1
            strategy = None
            should_rethink = args.until_target and (no_progress in (2, 5) or no_improvement >= 3)
            provider = args.harness if args.strategy_provider == 'auto' else args.strategy_provider
            if should_rethink and provider in ('codex', 'claude'):
                prior_reports = []
                for record in state['records'][-5:]:
                    path = record.get('evaluation_file')
                    if path:
                        try:
                            prior_reports.append(json.loads((args.state_dir / path).read_text()))
                        except (OSError, ValueError):
                            pass
                try:
                    strategy = strategy_review.advise(provider, state['goal'], state['records'], prior_reports,
                                                       executable=args.agent_bin, timeout=min(120, args.verify_timeout))
                    location = args.state_dir / 'strategy'
                    location.mkdir(parents=True, exist_ok=True)
                    (location / f'{invocations:04d}.json').write_text(json.dumps(strategy, indent=2) + '\n')
                except strategy_review.StrategyError as exc:
                    print(f'STRATEGY_UNAVAILABLE: {exc}; continue with deterministic recovery', flush=True)
                no_improvement = 0
            prompt = user_prompt(args, state, no_progress + 1, strategy=strategy)
            remaining_total = args.max_seconds - (time.monotonic() - started) if args.max_seconds else None
            allowed_turn_seconds = min(args.turn_timeout, max(0.1, remaining_total)) if remaining_total is not None else args.turn_timeout
            failure = None
            try:
                log = exec_turn(args, prompt, invocations, allowed_turn_seconds, slot=count_before + 1)
            except WorkerInvocationError as exc:
                failure = str(exc)
                log = args.state_dir / 'turns' / f'{invocations:04d}.events.jsonl'
            state = read_state(args.state_dir)
            if any(state[k] != v for k, v in contract_metadata.items()):
                raise SupervisorError('worker changed the immutable contract; halt and inspect')
            if json.dumps(state['records'][:count_before], sort_keys=True) != old_records:
                raise SupervisorError('worker mutated prior receipts; halt and inspect')
            verify_accepted_evidence(args, state)
            if protected_hashes(args.workspace, automatic_protected_paths(args, contract)) != pinned:
                raise SupervisorError('worker modified a protected evaluator/contract file; halt and inspect')
            if calibration_sha is not None and (not calibration_file.is_file() or
                    hashlib.sha256(calibration_file.read_bytes()).hexdigest() != calibration_sha):
                raise SupervisorError('worker modified previously calibrated judge result')
            if hashlib.sha256((SKILL_ROOT / 'scripts' / 'loop_guard.py').read_bytes()).hexdigest() != controller_digest:
                raise SupervisorError('worker modified the external guard; halt and inspect')
            delta = len(state['records']) - count_before
            if delta < 0 or delta > 1:
                (args.state_dir / 'invalid').write_text(
                    f'worker recorded {delta} receipts in a single invocation; manual audit required\n')
                raise SupervisorError('worker recorded more than one receipt per invocation; campaign invalid')
            if delta == 0:
                if state.get('pending'):
                    loop_guard.main(['abandon', '--state-dir', str(args.state_dir),
                                     '--reason', failure or 'worker returned without a completed experiment'])
                    state = read_state(args.state_dir)
                if (loop_guard.artifact_hash(loop_guard.scoped_path(args.workspace, args.artifact)) != parent_sha
                        or git_value(args.workspace, 'rev-parse', 'HEAD') != parent_commit):
                    interim = {'number': count_before + 1, 'candidate_sha256':
                               loop_guard.artifact_hash(loop_guard.scoped_path(args.workspace, args.artifact)),
                               'evidence': []}
                    archived = restore_unapproved_candidate(args, interim, parent_commit, parent_sha, snapshot)
                    print(f'RECOVERED: interrupted unverified source; archive={archived}', flush=True)
                no_progress += 1
                print(f'NOT COMPLETE: {count_before}/{args.iterations}; Agent stopped without a verified trial ({no_progress}/{args.max_retries+1}); {log}', flush=True)
                if no_progress > args.max_retries:
                    raise SupervisorError('repeated early finishes, worker errors or timeouts; no credit granted; '
                                          + (failure or 'no experiment receipt recorded'))
            else:
                ensure_scoped_changes(args, parent_commit, state['records'][-1].get('evidence', []))
                external_outcome = None
                if state['records'][-1].get('proposed_outcome', state['records'][-1]['outcome']) == 'keep':
                    external_outcome = external_trial_review(args, state, invocations, contract)
                    state = read_state(args.state_dir)
                if protected_hashes(args.workspace, automatic_protected_paths(args, contract)) != pinned:
                    raise SupervisorError('external verification or judge modified a protected evaluator/contract')
                check_review_provenance(args.state_dir, state)
                last = state['records'][-1]
                if last['outcome'] in ('discard', 'hold', 'inconclusive', 'crash'):
                    archived = restore_unapproved_candidate(args, last, parent_commit, parent_sha, snapshot)
                    print(f'RESTORED: rejected trial {last["number"]}; archive={archived}', flush=True)
                elif last['outcome'] == 'keep' or (last['outcome'] == 'pending' and external_outcome and
                        external_outcome['decision'] == 'KEEP'):
                    commit = checkpoint_accepted(args, last)
                    if last['outcome'] == 'pending':
                        report = args.state_dir / 'turns' / f'{invocations:04d}.evaluation.json'
                        loop_guard.resolve_promotion(args.state_dir, last['number'], 'KEEP', report)
                        state = read_state(args.state_dir)
                    state = snapshot_accepted_evidence(args, state, contract)
                    verify_accepted_evidence(args, state)
                    if args.until_target and external_outcome and external_outcome['target_completion'] == 'MET':
                        loop_guard.mark_goal_met(args.state_dir, last['number'])
                        state = read_state(args.state_dir)
                        print(f'GOAL_MET: independently verified at trial {last["number"]}', flush=True)
                    print(f'CHECKPOINT: accepted trial {last["number"]} commit={commit}', flush=True)
                else:
                    raise SupervisorError(f'unknown trial outcome: {last["outcome"]}')
                no_progress = 0
                no_improvement = 0 if last['outcome'] == 'keep' else no_improvement + 1
                if failure:
                    print(f'WORKER_WARNING: receipt valid despite CLI error: {failure}', flush=True)
                print(f'PROGRESS: {len(state["records"])}/{args.iterations}; kept={sum(r["outcome"] == "keep" for r in state["records"])}; log={log}', flush=True)
        if args.until_target:
            print(f'COMPLETE: verified target reached after {len(state["records"])} evaluated trials')
        else:
            print(f'COMPLETE: {args.iterations}/{args.iterations} recorded experiments; quality still requires external judgment')
        return 0
    except (SupervisorError, loop_guard.GuardError, OSError, ValueError, agent_adapters.AdapterError, evaluation_gate.EvaluationError) as exc:
        print(f'INCOMPLETE: {exc}; state={args.state_dir}', file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print(f'INCOMPLETE: interrupted by user; state={args.state_dir}', file=sys.stderr)
        return 130
    finally:
        # Do not delete another supervisor's lock.
        if lock_path.exists():
            try:
                if json.loads(lock_path.read_text()).get('pid') == os.getpid():
                    lock_path.unlink()
            except (OSError, ValueError):
                pass


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Start or inspect a Codex-supervised refinement campaign from the installed skill."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import codex_supervisor
import agent_adapters
import loop_guard


class LaunchError(Exception):
    pass


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0 or not codex_supervisor.process_alive(pid):
        return False
    proc_stat = Path(f'/proc/{pid}/stat')
    if proc_stat.exists():
        try:
            if proc_stat.read_text().split(') ', 1)[1][0] == 'Z':
                return False
        except (IndexError, OSError):
            pass
    return True


def launch_record(state_dir):
    path = state_dir / 'launch.json'
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def run_status(state_dir):
    record = launch_record(state_dir)
    try:
        state = loop_guard.load(state_dir)
    except loop_guard.GuardError:
        state = None
    count = len(state['records']) if state else 0
    target = state['target'] if state else (record or {}).get('iterations', 0)
    running = process_alive(record.get('pid')) if record else False
    if (state_dir / 'invalid').exists():
        status = 'INVALID'
    elif running:
        status = 'RUNNING'
    elif target and count == target and not any(r['outcome'] == 'pending' for r in (state or {}).get('records', [])):
        status = 'COMPLETE'
    elif record:
        status = 'INCOMPLETE'
    else:
        status = 'NOT_STARTED'
    return {'status': status, 'completed': count, 'target': target, 'pid': record.get('pid') if record else None,
            'log': record.get('log') if record else None, 'running': running, 'state_dir': str(state_dir),
            'kept': sum(r['outcome'] == 'keep' for r in state['records']) if state else 0,
            'unverified': sum(r['outcome'] in ('pending','hold') for r in state['records']) if state else 0}


@contextmanager
def launch_lock(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / 'launch.lock'
    for _ in range(3):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            try:
                stamp = path.stat()
                pid = int(path.read_text())
                if pid <= 0 or process_alive(pid):
                    raise LaunchError(f'live or invalid launch lock: {path}')
                if path.stat().st_ino == stamp.st_ino:
                    path.unlink()
            except (OSError, ValueError) as exc:
                raise LaunchError(f'unreadable launch lock: {path}') from exc
    else:
        raise LaunchError(f'could not reclaim stale launch lock: {path}')
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def emit(info):
    print(json.dumps(info, indent=2, ensure_ascii=False))


def validate_record(record, args, state_dir):
    intended = {'workspace': str(args.workspace), 'artifact': args.artifact, 'goal': args.goal,
                'iterations': args.iterations, 'evidence_kind': args.evidence_kind,
                'harness': args.harness, 'evaluation_contract': str(args.evaluation_contract) if args.evaluation_contract else None}
    for key, value in intended.items():
        if ((' '.join(record.get(key, '').split()) if key == 'goal' else record.get(key)) != value):
            raise LaunchError(f'existing campaign has different {key}; do not overwrite {state_dir}')


def start(args):
    if os.environ.get('RR_SUPERVISED') == '1':
        raise LaunchError('a supervised worker must not launch another supervisor')
    if args.iterations < 1 or not args.goal.strip():
        raise LaunchError('provide a positive iteration count and the complete user goal')
    root = args.workspace.resolve(strict=True)
    if not root.is_dir():
        raise LaunchError('workspace must be a directory')
    args.workspace = root
    args.goal = ' '.join(args.goal.split())
    state_dir = (args.state_dir or root / '.refinement' / 'loop-contract').resolve()
    if not state_dir.is_relative_to(root):
        raise LaunchError('state directory must be within workspace')
    artifact = loop_guard.scoped_path(root, args.artifact)
    if not (artifact.is_dir() or artifact.is_file()):
        raise LaunchError('artifact must be an existing source directory or file')
    args.artifact = str(artifact.relative_to(root))
    args.harness = agent_adapters.resolve_provider(args.harness, json.loads(args.agent_command) if args.agent_command else None)
    binary = args.agent_bin or (args.codex_bin if args.harness == 'codex' else args.harness)
    executable = shutil.which(binary) or (str(Path(binary).resolve()) if Path(binary).is_file() else None)
    if args.harness == 'command' and args.agent_command:
        command_array = json.loads(args.agent_command)
        executable = shutil.which(command_array[0]) or (str(Path(command_array[0]).resolve()) if Path(command_array[0]).is_file() else None)
    if not executable:
        raise LaunchError(f'{args.harness.capitalize()} CLI unavailable: cannot enforce further turns; use guard inline, report limitation')
    if args.evidence_kind == 'visual' and not args.evaluation_contract:
        raise LaunchError('visual campaigns need a frozen evaluation contract with blind review')
    if args.evaluation_contract:
        args.evaluation_contract = args.evaluation_contract.resolve(strict=True)
        codex_supervisor.evaluation_gate.read_contract(args.evaluation_contract)
        if not args.evaluation_contract.is_relative_to(root):
            raise LaunchError('evaluation contract must be inside project workspace')
    with launch_lock(state_dir):
        record = launch_record(state_dir)
        if record:
            validate_record(record, args, state_dir)
            state = run_status(state_dir)
            if state['status'] == 'INVALID':
                raise LaunchError('previous campaign has an invalid receipt count; inspect before resuming')
            if state['status'] == 'RUNNING' or state['status'] == 'COMPLETE':
                emit(state)
                return 0
            if not args.resume:
                raise LaunchError(f'prior controller is not running; inspect {record["log"]} and receipts, then resume')
            if loop_guard.load(state_dir).get('pending'):
                raise LaunchError('unfinished experiment exists; reconcile before resume')
        elif args.resume:
            raise LaunchError('no existing campaign to resume')
        if args.max_seconds < 0 or args.turn_timeout < 1:
            raise LaunchError('invalid supervisor safety timeout')
        codex_supervisor.ensure_git(root, args.allow_dirty)
        command = [sys.executable, str(Path(__file__).with_name('codex_supervisor.py')),
                   '--workspace', str(root), '--artifact', args.artifact,
                   '--goal', args.goal, '--iterations', str(args.iterations),
                   '--evidence-kind', args.evidence_kind, '--state-dir', str(state_dir),
                   '--codex-bin', str(executable) if args.harness == 'codex' else args.codex_bin,
                   '--harness', args.harness, '--turn-timeout', str(args.turn_timeout),
                   '--max-retries', str(args.max_retries), '--verify-timeout', str(args.verify_timeout),
                   '--claude-permission-mode', args.claude_permission_mode]
        if args.agent_bin and args.harness != 'codex':
            command.extend(['--agent-bin', str(executable)])
        if args.agent_command:
            command.extend(['--agent-command', args.agent_command])
        if args.evaluation_contract:
            command.extend(['--evaluation-contract', str(args.evaluation_contract)])
        if args.judge_provider != 'none':
            command.extend(['--judge-provider', args.judge_provider])
        if args.judge_command:
            command.extend(['--judge-command', args.judge_command])
        if args.max_seconds:
            command.extend(['--max-seconds', str(args.max_seconds)])
        if args.model:
            command.extend(['--model', args.model])
        if args.allow_dirty:
            command.append('--allow-dirty')
        for item in args.protect:
            command.extend(['--protect', item])
        if args.verify_command:
            command.extend(['--verify-command', args.verify_command])
        log = state_dir / 'controller.log'
        with log.open('ab', buffering=0) as stream:
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=(os.name != 'nt'), close_fds=True)
        data = {'pid': process.pid, 'workspace': str(root), 'artifact': args.artifact,
                'goal': ' '.join(args.goal.split()), 'iterations': args.iterations, 'evidence_kind': args.evidence_kind,
                'harness': args.harness, 'evaluation_contract': str(args.evaluation_contract) if args.evaluation_contract else None,
                'log': str(log), 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        (state_dir / 'launch.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        emit({'status': 'LAUNCHED', 'completed': len(loop_guard.load(state_dir)['records']) if (state_dir / 'contract.json').exists() else 0,
              'target': args.iterations, 'pid': process.pid, 'log': str(log),
              'message': 'Controller started; inspect status and logs before claiming completion'})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    launch = sub.add_parser('launch')
    launch.add_argument('--workspace', type=Path, required=True)
    launch.add_argument('--artifact', required=True)
    launch.add_argument('--goal', required=True)
    launch.add_argument('--iterations', type=int, required=True)
    launch.add_argument('--evidence-kind', choices=('visual', 'generic'), default='generic')
    launch.add_argument('--state-dir', type=Path)
    launch.add_argument('--codex-bin', default='codex')
    launch.add_argument('--harness', choices=('auto','codex','claude','command'), default='codex')
    launch.add_argument('--agent-bin')
    launch.add_argument('--agent-command', help='JSON argv command for AGY/another provider')
    launch.add_argument('--evaluation-contract', type=Path)
    launch.add_argument('--judge-provider', choices=('auto','none','codex','claude','command'), default='auto')
    launch.add_argument('--judge-command', help='JSON argv command for independent review')
    launch.add_argument('--model')
    launch.add_argument('--turn-timeout', type=int, default=1800)
    launch.add_argument('--max-retries', type=int, default=2)
    launch.add_argument('--verify-timeout', type=int, default=300)
    launch.add_argument('--claude-permission-mode', choices=('acceptEdits','auto','default','plan','bypassPermissions'), default='acceptEdits')
    launch.add_argument('--max-seconds', type=int, default=0)
    launch.add_argument('--allow-dirty', action='store_true')
    launch.add_argument('--resume', action='store_true')
    launch.add_argument('--protect', action='append', default=[])
    launch.add_argument('--verify-command')
    status = sub.add_parser('status')
    status.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'status':
            emit(run_status(args.state_dir.resolve()))
            return 0
        return start(args)
    except (LaunchError, codex_supervisor.SupervisorError, agent_adapters.AdapterError, loop_guard.GuardError,
            OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'AUTO_ENFORCEMENT_BLOCKED: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Optional, dependency-free experiment ledger for explicit N-iteration contracts."""

import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zlib

IGNORED_DIRS = {'.git', '.refinement', 'node_modules', '__pycache__', 'dist', 'build', '.venv', '.next', 'coverage'}
IGNORED_FILES = {'.DS_Store'}
VISUAL_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


class GuardError(Exception):
    pass


@contextmanager
def ledger_lock(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / 'update.lock'
    for _ in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            try:
                stamp = path.stat()
                pid = int(path.read_text())
                if pid <= 0:
                    raise GuardError(f'invalid update lock: {path}')
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    if path.stat().st_ino == stamp.st_ino:
                        path.unlink()
                    continue
                raise GuardError(f'another update may be active: {path}')
            except (OSError, ValueError) as exc:
                raise GuardError(f'unreadable update lock: {path}') from exc
    else:
        raise GuardError(f'could not reclaim stale update lock: {path}')
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scoped_path(root, name, must_exist=True):
    raw = root / name
    resolved = raw.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise GuardError(f'path outside workspace: {name}')
    if must_exist and not resolved.exists():
        raise GuardError(f'missing path: {name}')
    if raw.is_symlink():
        raise GuardError(f'symlink not allowed: {name}')
    return resolved


def artifact_hash(path):
    if path.is_symlink():
        raise GuardError('artifact is symlink')
    if path.is_file():
        return sha(path.read_bytes())
    if not path.is_dir():
        raise GuardError(f'unsupported artifact: {path}')
    digest = hashlib.sha256()
    count = 0
    for item in sorted(path.rglob('*')):
        rel = item.relative_to(path)
        if any(part in IGNORED_DIRS for part in rel.parts) or item.name in IGNORED_FILES:
            continue
        if item.is_symlink():
            raise GuardError(f'artifact contains symlink: {item}')
        if item.is_file():
            count += 1
            digest.update(str(rel).encode('utf-8'))
            digest.update(b'\0')
            digest.update(hashlib.sha256(item.read_bytes()).digest())
    if count == 0:
        raise GuardError(f'no source files under artifact: {path}')
    return digest.hexdigest()


def well_formed_image(data, suffix):
    if suffix == '.png':
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            return False
        offset = 8
        saw_header = saw_pixels = False
        while offset + 12 <= len(data):
            length = int.from_bytes(data[offset:offset + 4], 'big')
            end = offset + 12 + length
            if end > len(data):
                return False
            tag = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + length]
            checksum = int.from_bytes(data[offset + 8 + length:end], 'big')
            if zlib.crc32(tag + payload) & 0xffffffff != checksum:
                return False
            if tag == b'IHDR':
                if offset != 8 or length != 13:
                    return False
                width = int.from_bytes(payload[:4], 'big')
                height = int.from_bytes(payload[4:8], 'big')
                if not 0 < width <= 100000 or not 0 < height <= 100000:
                    return False
                saw_header = True
            elif tag == b'IDAT':
                saw_pixels = True
            elif tag == b'IEND':
                return saw_header and saw_pixels and length == 0 and end == len(data)
            offset = end
        return False
    if suffix in {'.jpg', '.jpeg'}:
        return len(data) > 128 and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')
    if suffix == '.webp':
        return (len(data) > 32 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'
                and int.from_bytes(data[4:8], 'little') + 8 == len(data))
    return False


def fresh_evidence(root, evidence_name, since, visual):
    path = scoped_path(root, evidence_name)
    if not path.is_file() or path.stat().st_size == 0:
        raise GuardError('evidence must be a nonempty file')
    if path.stat().st_mtime_ns + 1_000_000_000 < since:
        raise GuardError('evidence predates this experiment')
    data = path.read_bytes()
    evidence_hash = sha(data)
    # Identical outputs can be genuine negative results from different candidates.
    if visual:
        suffix = path.suffix.lower()
        if suffix not in VISUAL_EXTENSIONS:
            raise GuardError('visual experiment requires a fresh rendered image')
        if not well_formed_image(data, suffix):
            raise GuardError('visual evidence is not a structurally valid rendered image')
    return evidence_hash


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.rr-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)
            fp.write('\n')
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load(state_dir):
    path = state_dir / 'contract.json'
    if not path.is_file():
        raise GuardError('not initialized; run init first')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('records'), list):
        raise GuardError('unsupported or corrupt contract')
    mode = data.get('mode', 'fixed')
    if mode not in ('fixed', 'goal') or not isinstance(data.get('target'), int) or (
            data['target'] < 1 if mode == 'fixed' else data['target'] != 0):
        raise GuardError('invalid target')
    if mode == 'fixed' and len(data['records']) > data['target']:
        raise GuardError('more records than target; inspect state')
    return data


def save(state_dir, data):
    atomic_write(state_dir / 'contract.json', data)


def require_text(value, field):
    if not isinstance(value, str) or len(value.strip()) < 12:
        raise GuardError(f'{field} must describe a concrete observation or hypothesis')
    return value.strip()


def do_init(args):
    root = Path(args.workspace).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise GuardError('workspace is not a directory')
    if (args.goal_mode and args.iterations != 0) or (not args.goal_mode and args.iterations < 1):
        raise GuardError('goal mode requires zero iterations; fixed mode requires a positive number')
    artifact = scoped_path(root, args.artifact)
    initial = artifact_hash(artifact)
    state_dir = Path(args.state_dir).expanduser().resolve()
    state_file = state_dir / 'contract.json'
    if state_file.exists():
        current = load(state_dir)
        if (current['target'] != args.iterations or current.get('mode', 'fixed') != ('goal' if args.goal_mode else 'fixed') or
                ' '.join(current['goal'].split()) != ' '.join(args.goal.split()) or
                current['artifact'] != str(artifact) or current['workspace'] != str(root) or
                current['evidence_kind'] != args.evidence_kind):
            raise GuardError('existing contract differs; do not silently reset it')
        print(json.dumps(status_dict(current), ensure_ascii=False))
        return
    if not args.goal.strip():
        raise GuardError('goal must not be empty')
    state = {'version': 1, 'goal': args.goal.strip(), 'target': args.iterations,
             'mode': 'goal' if args.goal_mode else 'fixed', 'goal_met': False,
             'workspace': str(root), 'artifact': str(artifact), 'evidence_kind': args.evidence_kind,
             'initial_sha256': initial, 'created_ns': time.time_ns(), 'pending': None,
             'promotion_mode': 'external' if args.external_promotion else 'legacy', 'records': []}
    save(state_dir, state)
    print(json.dumps(status_dict(state), ensure_ascii=False))


def do_begin(args):
    state = load(Path(args.state_dir))
    if os.environ.get('RR_SUPERVISED') == '1' and os.environ.get('RR_SLOT_NUMBER'):
        if len(state['records']) + 1 != int(os.environ['RR_SLOT_NUMBER']):
            raise GuardError('only one experiment receipt is permitted per worker invocation')
    if state['pending']:
        raise GuardError('previous experiment pending; finish or explicitly abandon')
    if state.get('goal_met') or (state.get('mode', 'fixed') == 'fixed' and len(state['records']) >= state['target']):
        raise GuardError('contract already complete')
    root = Path(state['workspace'])
    source = scoped_path(root, str(Path(state['artifact']).relative_to(root)))
    state['pending'] = {'number': len(state['records']) + 1,
                        'hypothesis': require_text(args.hypothesis, 'hypothesis'),
                        'planned_check': require_text(args.planned_check, 'planned check'),
                        'parent_sha256': artifact_hash(source), 'started_ns': time.time_ns()}
    save(Path(args.state_dir), state)
    print(json.dumps({'pending': state['pending']['number'], 'target': state['target']}, ensure_ascii=False))


def do_finish(args):
    state = load(Path(args.state_dir))
    pending = state.get('pending')
    if not pending:
        raise GuardError('no experiment was begun')
    if args.outcome not in ('keep', 'discard', 'inconclusive', 'crash'):
        raise GuardError('invalid outcome')
    root = Path(state['workspace'])
    source = scoped_path(root, str(Path(state['artifact']).relative_to(root)))
    candidate = artifact_hash(source)
    if candidate == pending['parent_sha256']:
        raise GuardError('no changed candidate: tests, text responses and no-op repeats are not iterations')
    previous = state['records']
    if candidate in (r['candidate_sha256'] for r in previous):
        raise GuardError('candidate bytes already tested; no duplicate iteration credit')
    hashes = {h for r in previous for h in r['evidence_sha256']}
    if not args.evidence:
        raise GuardError('missing observed evidence')
    evidence_hashes = [fresh_evidence(root, e, pending['started_ns'],
                                      state['evidence_kind'] == 'visual') for e in args.evidence]
    repeated_evidence = len([h for h in evidence_hashes if h in hashes])
    if repeated_evidence and args.outcome == 'keep' and state['evidence_kind'] == 'visual':
        if all(h in hashes for h in evidence_hashes):
            raise GuardError('visual candidate claimed gain but every screenshot is unchanged')
    require_text(args.finding, 'finding')
    state['records'].append({'number': pending['number'], 'hypothesis': pending['hypothesis'],
                             'planned_check': pending['planned_check'],
                             'parent_sha256': pending['parent_sha256'], 'candidate_sha256': candidate,
                             'evidence': args.evidence, 'evidence_sha256': evidence_hashes,
                             'repeated_evidence_count': repeated_evidence,
                             'finding': args.finding.strip(),
                             'outcome': 'pending' if state.get('promotion_mode') == 'external' and args.outcome == 'keep' else args.outcome,
                             'proposed_outcome': args.outcome, 'timestamp_ns': time.time_ns()})
    state['pending'] = None
    save(Path(args.state_dir), state)
    print(json.dumps(status_dict(state), ensure_ascii=False))


def resolve_promotion(state_dir, number, verdict, report_path):
    """Only the external supervisor calls this after independently running its evaluator."""
    if verdict not in {'KEEP', 'REJECT', 'HOLD'}:
        raise GuardError('invalid external decision')
    state_dir = Path(state_dir)
    with ledger_lock(state_dir):
        state = load(state_dir)
        if state.get('promotion_mode') != 'external':
            raise GuardError('legacy campaign cannot use external promotion')
        if not (1 <= number <= len(state['records'])):
            raise GuardError('record index outside campaign')
        record = state['records'][number - 1]
        if record['number'] != number or record['outcome'] != 'pending' or record.get('proposed_outcome') != 'keep':
            raise GuardError('only a pending worker proposal may be promoted')
        if not report_path or not Path(report_path).is_file():
            raise GuardError('missing independent outcome report')
        report = json.loads(Path(report_path).read_text(encoding='utf-8'))
        if report.get('decision') != verdict or report.get('schema_version') != 1:
            raise GuardError('decision must match external report')
        record['outcome'] = {'KEEP':'keep', 'REJECT':'discard', 'HOLD':'hold'}[verdict]
        record['evaluation_sha256'] = sha(Path(report_path).read_bytes())
        try:
            record['evaluation_file'] = str(Path(report_path).resolve().relative_to(state_dir.resolve()))
        except ValueError as exc:
            raise GuardError('verdict must be archived inside protected state directory') from exc
        record['evaluation_result'] = verdict
        measured = (report.get('benchmark', {}).get('benchmark', {}).get('metrics', {}))
        if verdict == 'KEEP' and isinstance(measured, dict):
            record['verified_metrics'] = {name: value['value'] for name, value in measured.items()
                                          if isinstance(value, dict) and isinstance(value.get('value'), (int, float))}
        save(state_dir, state)
        return record['outcome']


def mark_goal_met(state_dir, number):
    """Only a committed, externally verified gain may close an open-ended campaign."""
    state_dir = Path(state_dir)
    with ledger_lock(state_dir):
        state = load(state_dir)
        if state.get('mode') != 'goal' or state.get('goal_met'):
            raise GuardError('not an active goal-driven campaign')
        if number != len(state['records']):
            raise GuardError('only the latest externally accepted experiment can finish a goal')
        record = state['records'][-1]
        if record.get('outcome') != 'keep' or record.get('evaluation_result') != 'KEEP':
            raise GuardError('goal completion requires externally accepted source')
        path = (state_dir / record['evaluation_file']).resolve()
        if not path.is_relative_to(state_dir.resolve()) or sha(path.read_bytes()) != record['evaluation_sha256']:
            raise GuardError('goal completion evidence was changed')
        result = json.loads(path.read_text())
        if result.get('decision') != 'KEEP' or result.get('target_completion') != 'MET':
            raise GuardError('goal target was not externally verified')
        source = scoped_path(Path(state['workspace']), str(Path(state['artifact']).relative_to(state['workspace'])))
        if artifact_hash(source) != record['candidate_sha256']:
            raise GuardError('accepted source does not match goal verification')
        state['goal_met'] = True
        state['goal_verified_trial'] = number
        save(state_dir, state)


def do_abandon(args):
    state = load(Path(args.state_dir))
    if not state['pending']:
        raise GuardError('no pending experiment')
    require_text(args.reason, 'abandon reason')
    # An abandoned run is never counted. Save why to explain a blocked campaign.
    (Path(args.state_dir) / 'abandoned.jsonl').open('a', encoding='utf-8').write(
        json.dumps({'pending': state['pending'], 'reason': args.reason,
                    'timestamp_ns': time.time_ns()}, ensure_ascii=False) + '\n')
    state['pending'] = None
    save(Path(args.state_dir), state)
    print(json.dumps(status_dict(state), ensure_ascii=False))


def status_dict(state):
    completed = len(state['records'])
    goal_mode = state.get('mode') == 'goal'
    complete = (state.get('goal_met') is True if goal_mode else completed == state['target'])
    return {'status': 'COMPLETE' if complete and all(r['outcome'] != 'pending' for r in state['records']) else 'INCOMPLETE',
            'mode': 'goal' if goal_mode else 'fixed', 'goal_met': state.get('goal_met', False),
            'completed': completed, 'required': None if goal_mode else state['target'],
            'remaining': None if goal_mode else state['target'] - completed,
            'pending': state['pending']['number'] if state['pending'] else None,
            'goal': state['goal'], 'kept': sum(r['outcome'] == 'keep' for r in state['records']),
            'unverified': sum(r['outcome'] in ('pending', 'hold') for r in state['records'])}


def do_status(args):
    state = load(Path(args.state_dir))
    status = status_dict(state)
    if (Path(args.state_dir) / 'invalid').exists():
        status['status'] = 'INVALID'
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if args.gate and status['status'] != 'COMPLETE':
        raise SystemExit(3)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--state-dir', required=True)
    init.add_argument('--workspace', required=True)
    init.add_argument('--artifact', required=True, help='source file or source directory (exclude test outputs)')
    init.add_argument('--goal', required=True)
    init.add_argument('--iterations', type=int, default=0)
    init.add_argument('--goal-mode', action='store_true', help='continue until externally verified target; no fixed N')
    init.add_argument('--evidence-kind', choices=('generic', 'visual'), default='generic')
    init.add_argument('--external-promotion', action='store_true', help='supervisor decides keep after external validation')
    start = sub.add_parser('begin')
    start.add_argument('--state-dir', required=True)
    start.add_argument('--hypothesis', required=True)
    start.add_argument('--planned-check', required=True)
    end = sub.add_parser('finish')
    end.add_argument('--state-dir', required=True)
    end.add_argument('--outcome', required=True, choices=('keep', 'discard', 'inconclusive', 'crash'))
    end.add_argument('--finding', required=True)
    end.add_argument('--evidence', action='append', required=True, help='path relative to workspace; repeatable')
    ab = sub.add_parser('abandon')
    ab.add_argument('--state-dir', required=True)
    ab.add_argument('--reason', required=True)
    stat = sub.add_parser('status')
    stat.add_argument('--state-dir', required=True)
    stat.add_argument('--gate', action='store_true', help='nonzero exit until exact requested count')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        guard = ledger_lock(Path(args.state_dir)) if args.command != 'status' else nullcontext()
        with guard:
            {'init': do_init, 'begin': do_begin, 'finish': do_finish,
             'abandon': do_abandon, 'status': do_status}[args.command](args)
    except (GuardError, ValueError, OSError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

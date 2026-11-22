import contextlib
import hashlib
import io
import json
import os
import struct
import zlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'skills'
GUARD = ROOT / 'reflective-refinement' / 'scripts' / 'loop_guard.py'
SUPERVISOR = ROOT / 'reflective-refinement' / 'scripts' / 'codex_supervisor.py'

MOCK_CLI = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time, zlib, struct
root = pathlib.Path(os.environ['RR_WORKSPACE'])
state = pathlib.Path(os.environ['RR_STATE_DIR'])
script = os.environ['RR_GUARD']
content = json.loads((state / 'contract.json').read_text())
number = len(content['records']) + 1
mode = os.environ.get('FAKE_MODE','success')
turns_file = root / '.refinement' / 'fake-turns.txt'
turns_file.parent.mkdir(exist_ok=True)
turns = (int(turns_file.read_text()) if turns_file.exists() else 0) + 1
turns_file.write_text(str(turns))
if mode == 'always-done' or (mode == 'early-two' and turns < 3):
    print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Done already'}}))
    sys.exit(0)
if mode == 'timeout':
    time.sleep(5)
    sys.exit(0)
if mode == 'tamper-evaluator':
    (root / 'evaluator.txt').write_text('unapproved modified acceptance test')
if mode == 'corrupt-goal':
    content['goal'] = 'A different objective that no user ever requested'
    (state/'contract.json').write_text(json.dumps(content))
    sys.exit(0)
subprocess.run([sys.executable,script,'begin','--state-dir',str(state),'--hypothesis',f'Candidate {number}: test a distinct change','--planned-check','Compare actual outputs with previous snapshot'],check=True,capture_output=True)
artifact = root / os.environ['RR_ARTIFACT']
artifact.write_text(f'candidate-{number}: meaningful changed source')
evidence = root/'.refinement'/'evidence'/f'candidate-{number}.txt'
evidence.parent.mkdir(parents=True,exist_ok=True)
evidence.write_text(f'Fresh observation for candidate {number}; scenario examined: {number*7}')
subprocess.run([sys.executable,script,'finish','--state-dir',str(state),'--outcome','keep','--finding',f'Observed candidate {number} with distinct output','--evidence',str(evidence.relative_to(root))],check=True,capture_output=True)
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':f'Done after iteration {number}'}}))
'''



def png_pixel(value):
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff)
    header = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b'\x00' + bytes([value, 100, 150]))
    return header + chunk(b'IHDR', ihdr) + chunk(b'IDAT', pixels) + chunk(b'IEND', b'')


def cli(*args, env=None, cwd=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=env, cwd=cwd)


class FixedIterationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        self.artifact = self.root / 'src' / 'artifact.txt'
        self.artifact.write_text('baseline')
        self.state_dir = self.root / '.refinement' / 'contract'
        self.goal = 'Improve observable outcome across representative test cases'

    def init(self, n=30, kind='generic'):
        result = cli(GUARD, 'init', '--workspace', self.root, '--artifact', 'src/artifact.txt',
                     '--state-dir', self.state_dir, '--iterations', n, '--goal', self.goal,
                     '--evidence-kind', kind)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def begin(self, num=1):
        return cli(GUARD, 'begin', '--state-dir', self.state_dir,
                   '--hypothesis', f'Change behavior for scenario {num}',
                   '--planned-check', f'Render/test scenario {num} against baseline')

    def finish(self, num=1, data='Actual observed behavior differs'):
        evidence = self.root / '.refinement' / f'evidence-{num}.txt'
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(data)
        return cli(GUARD, 'finish', '--state-dir', self.state_dir, '--outcome', 'keep',
                   '--finding', f'Observed material result in case {num}',
                   '--evidence', evidence.relative_to(self.root))

    def test_early_done_not_complete(self):
        self.init(30)
        self.assertEqual(cli(GUARD, 'status', '--state-dir', self.state_dir, '--gate').returncode, 3)
        self.assertIn('"remaining": 30', cli(GUARD, 'status','--state-dir', self.state_dir).stdout)

    def test_noop_is_not_counted(self):
        self.init(30)
        self.assertEqual(self.begin().returncode, 0)
        denied = self.finish()
        self.assertEqual(denied.returncode, 2)
        self.assertIn('no changed candidate', denied.stderr)
        self.assertEqual(len(json.loads((self.state_dir / 'contract.json').read_text())['records']), 0)

    def test_one_real_attempt_and_gate(self):
        self.init(2)
        self.assertEqual(self.begin().returncode, 0)
        self.artifact.write_text('candidate-a')
        self.assertEqual(self.finish(1).returncode, 0)
        status = json.loads(cli(GUARD,'status','--state-dir',self.state_dir).stdout)
        self.assertEqual((status['completed'],status['remaining'],status['status']), (1,1,'INCOMPLETE'))
        self.assertEqual(cli(GUARD, 'status','--state-dir',self.state_dir,'--gate').returncode, 3)
        self.assertEqual(self.begin(2).returncode, 0)
        self.artifact.write_text('candidate-b')
        self.assertEqual(self.finish(2,'Another distinct output').returncode, 0)
        self.assertEqual(cli(GUARD, 'status','--state-dir',self.state_dir,'--gate').returncode, 0)

    def test_same_candidate_not_counted_twice(self):
        self.init(3)
        self.begin()
        self.artifact.write_text('candidate-a')
        self.assertEqual(self.finish(1).returncode, 0)
        self.begin(2)
        self.artifact.write_text('candidate-b')
        self.assertEqual(self.finish(2,'Different response').returncode, 0)
        self.begin(3)
        self.artifact.write_text('candidate-a')
        result = self.finish(3,'Another observed result')
        self.assertEqual(result.returncode, 2)
        self.assertIn('already tested', result.stderr)

    def test_stale_evidence_rejected(self):
        self.init(2)
        self.begin()
        self.artifact.write_text('candidate')
        old = self.root / '.refinement' / 'evidence-1.txt'
        old.parent.mkdir(exist_ok=True)
        old.write_text('Stale but nonempty')
        os.utime(old, (1,1))
        denied = cli(GUARD,'finish','--state-dir',self.state_dir,'--outcome','keep',
                     '--finding','Test passed with visually improved layout',
                     '--evidence',old.relative_to(self.root))
        self.assertEqual(denied.returncode,2)
        self.assertIn('predates',denied.stderr)

    def test_visual_requires_actual_image_file(self):
        self.init(2,kind='visual')
        self.begin()
        self.artifact.write_text('different-render-source')
        denied=self.finish()
        self.assertEqual(denied.returncode,2)
        self.assertIn('rendered image',denied.stderr)

    def test_identical_real_visual_outputs_can_be_negative_experiments(self):
        self.init(3,kind='visual')
        img = png_pixel(40)
        for n in (1,2):
            self.assertEqual(self.begin(n).returncode, 0)
            self.artifact.write_text(f'candidate code {n}')
            evidence = self.root / '.refinement' / f'scene-{n}.png'
            evidence.parent.mkdir(exist_ok=True)
            evidence.write_bytes(img)
            result = cli(GUARD,'finish','--state-dir',self.state_dir,'--outcome','discard',
                         '--finding',f'Candidate {n} produced the same visible image',
                         '--evidence',evidence.relative_to(self.root))
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.begin(3).returncode, 0)
        self.artifact.write_text('candidate code 3')
        evidence=self.root/'.refinement'/'scene-3.png'
        evidence.write_bytes(img)
        result=cli(GUARD,'finish','--state-dir',self.state_dir,'--outcome','keep',
                   '--finding','Claims visible improvement but screenshot is identical',
                   '--evidence',evidence.relative_to(self.root))
        self.assertEqual(result.returncode,2)
        self.assertIn('every screenshot is unchanged',result.stderr)
        state=json.loads((self.state_dir/'contract.json').read_text())
        self.assertEqual(len(state['records']),2)
        self.assertEqual(state['records'][1]['repeated_evidence_count'],1)

    def test_png_with_magic_only_is_not_accepted(self):
        self.init(2,kind='visual')
        self.begin()
        self.artifact.write_text('new visual source')
        path=self.root/'.refinement'/'bad.png'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'fake data')
        result=cli(GUARD,'finish','--state-dir',self.state_dir,'--outcome','keep',
                   '--finding','Supposedly a better image but file is corrupt',
                   '--evidence',path.relative_to(self.root))
        self.assertEqual(result.returncode,2)
        self.assertIn('structurally valid',result.stderr)

    def test_parallel_updates_are_rejected(self):
        self.init(3)
        lock = self.state_dir / 'update.lock'
        lock.write_text(str(os.getpid()))
        result = self.begin()
        self.assertEqual(result.returncode, 2)
        self.assertIn('another update may be active', result.stderr)
        lock.unlink()
        self.assertEqual(self.begin().returncode, 0)

    def test_reinitialization_cannot_change_count(self):
        self.init(30)
        result=cli(GUARD,'init','--workspace',self.root,'--artifact','src/artifact.txt',
                   '--state-dir',self.state_dir,'--iterations','2','--goal',self.goal)
        self.assertEqual(result.returncode,2)
        self.assertIn('existing contract differs',result.stderr)

    def make_fake_git(self):
        fake=self.root/'fake_codex.py'
        fake.write_text(MOCK_CLI)
        (self.root / 'evaluator.txt').write_text('frozen evaluator')
        fake.chmod(0o755)
        for cmd in (['git','init','-q'], ['git','config','user.email','fake@local.invalid'],
                    ['git','config','user.name','Fixture'], ['git','add','.'],
                    ['git','commit','-qm','fixture']):
            subprocess.run(cmd,cwd=self.root,check=True,capture_output=True)
        return fake

    def supervise(self, n, mode, extra=()):
        fake=self.make_fake_git()
        env={**os.environ,'FAKE_MODE':mode}
        return cli(SUPERVISOR,'--workspace',self.root,'--artifact','src/artifact.txt',
                   '--goal',self.goal,'--iterations',n,'--codex-bin',fake, '--max-retries','2',
                   *extra, env=env)

    def test_supervisor_restarts_after_two_early_dones(self):
        result=self.supervise(3,'early-two')
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('COMPLETE: 3/3',result.stdout)
        self.assertIn('NOT COMPLETE: 0/3',result.stdout)
        self.assertEqual(len(json.loads((self.root/'.refinement'/'loop-contract'/'contract.json').read_text())['records']),3)

    def test_supervisor_refuses_endless_model_done(self):
        result=self.supervise(30,'always-done')
        self.assertEqual(result.returncode,3)
        self.assertIn('INCOMPLETE',result.stderr)
        state=json.loads((self.root/'.refinement'/'loop-contract'/'contract.json').read_text())
        self.assertEqual(len(state['records']),0)

    def test_exact_thirty_stub_experiments_not_fewer(self):
        result=self.supervise(30,'success')
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('COMPLETE: 30/30',result.stdout)
        state=json.loads((self.root/'.refinement'/'loop-contract'/'contract.json').read_text())
        self.assertEqual(len(state['records']),30)
        self.assertEqual(len(set(r['candidate_sha256'] for r in state['records'])),30)

    def test_supervisor_resumes_from_saved_receipt_count(self):
        fake=self.make_fake_git()
        state_dir=self.root/'.refinement'/'loop-contract'
        self.state_dir=state_dir
        self.init(3)
        self.assertEqual(self.begin(1).returncode,0)
        self.artifact.write_text('candidate prior to interruption')
        self.assertEqual(self.finish(1).returncode,0)
        result=cli(SUPERVISOR,'--workspace',self.root,'--artifact','src/artifact.txt',
                   '--goal',self.goal,'--iterations','3','--codex-bin',fake,'--allow-dirty')
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('COMPLETE: 3/3',result.stdout)
        state=json.loads((state_dir/'contract.json').read_text())
        self.assertEqual([r['number'] for r in state['records']],[1,2,3])
        self.assertEqual(len(list((state_dir/'turns').glob('*.events.jsonl'))),2)

    def test_manual_init_cannot_weaken_visual_evidence_requirement(self):
        self.init(30,kind='visual')
        result=cli(GUARD,'init','--state-dir',self.state_dir,'--workspace',self.root,
                   '--artifact','src/artifact.txt','--goal',self.goal,
                   '--iterations','30','--evidence-kind','generic')
        self.assertEqual(result.returncode,2)
        self.assertIn('contract differs',result.stderr)

    def test_supervisor_detects_evaluator_tampering(self):
        result=self.supervise(3,'tamper-evaluator',('--protect','evaluator.txt'))
        self.assertEqual(result.returncode,3)
        self.assertIn('protected evaluator',result.stderr)

    def test_supervisor_independent_verifier_can_block_false_keep(self):
        result=self.supervise(3,'success',('--verify-command',f'{sys.executable} -c "import sys; sys.exit(2)"'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        state=json.loads((self.root / '.refinement/loop-contract/contract.json').read_text())
        self.assertEqual([r['outcome'] for r in state['records']], ['discard']*3)
        self.assertEqual(self.artifact.read_text(), 'baseline')

    def test_supervisor_detects_goal_tampering(self):
        result=self.supervise(3,'corrupt-goal')
        self.assertEqual(result.returncode,3)
        self.assertIn('immutable contract',result.stderr)

    def test_supervisor_global_budget_interrupts_a_running_turn(self):
        result=self.supervise(30,'timeout',('--turn-timeout','30','--max-seconds','1'))
        self.assertEqual(result.returncode,3)
        self.assertIn('INCOMPLETE',result.stderr)

    def test_supervisor_timeout_is_incomplete(self):
        result=self.supervise(3,'timeout',('--turn-timeout','1'))
        self.assertEqual(result.returncode,3)
        self.assertIn('timed out',result.stderr)


if __name__ == '__main__':
    unittest.main()

"""Regressions for frozen quality, one-trial receipts and safe Git recovery."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0, str(ROOT / 'reflective-refinement' / 'scripts'))
import agent_adapters
import blind_review
import codex_supervisor as supervisor
import evaluation_gate
import loop_guard


def git(root, *args):
    process = subprocess.run(['git', *args], cwd=root, text=True, capture_output=True)
    if process.returncode:
        raise AssertionError(process.stderr)
    return process.stdout.strip()


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        self.source = self.root / 'src' / 'thing.py'
        self.source.write_text('base\n')
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.name', 'Test')
        git(self.root, 'config', 'user.email', 't@example.invalid')
        git(self.root, 'add', '--', 'src')
        git(self.root, 'commit', '-qm', 'baseline')
        self.state_dir = self.root / '.refinement' / 'loop-contract'
        self.args = SimpleNamespace(workspace=self.root, artifact='src', state_dir=self.state_dir,
                                    protect=[], evaluation_contract=None)

    def test_one_receipt_only_in_supervised_slot_even_with_reused_guard(self):
        loop_guard.main(['init', '--workspace', str(self.root), '--artifact', 'src/thing.py',
                         '--state-dir', str(self.state_dir), '--iterations', '3',
                         '--goal', 'Improve the observed behavior in production'])
        with patch.dict(os.environ, {'RR_SUPERVISED': '1', 'RR_SLOT_NUMBER': '1'}):
            self.assertEqual(loop_guard.main(['begin', '--state-dir', str(self.state_dir),
                '--hypothesis', 'Change the behavior for the first scenario',
                '--planned-check', 'Compare before and after for first scenario']), 0)
            self.source.write_text('candidate\n')
            evidence = self.root / '.refinement' / 'evidence.txt'
            evidence.write_text('Observed actual changed outcome')
            self.assertEqual(loop_guard.main(['finish', '--state-dir', str(self.state_dir),
                '--outcome', 'discard', '--finding', 'The output did not improve enough',
                '--evidence', '.refinement/evidence.txt']), 0)
            self.assertEqual(loop_guard.main(['begin', '--state-dir', str(self.state_dir),
                '--hypothesis', 'A second change in the same invocation',
                '--planned-check', 'Try to bypass one-trial-only restriction']), 2)
        self.assertEqual(len(loop_guard.load(self.state_dir)['records']), 1)

    def test_blind_bundle_uses_accepted_incumbent_not_original(self):
        (self.root / '.refinement').mkdir()
        for name in ('original.txt', 'accepted.txt', 'candidate.txt'):
            (self.root / '.refinement' / name).write_text(name)
        contract = {'case_ids': ['one'], 'primary_outcome': 'Improve a material user-facing behavior',
                    'kind': 'ux', 'reference_evidence': {'one': '.refinement/original.txt'},
                    'review': {'criteria': ['appearance']}}
        folder = self.root / '.refinement' / 'blind'
        blind_review.build_bundle(folder, self.root, self.root / 'src', contract,
            ['.refinement/candidate.txt'], incumbent_evidence={'one': '.refinement/accepted.txt'})
        data = json.loads((folder / 'review_inputs.json').read_text())
        self.assertEqual((folder / data['files']['one']['A']).read_text(), 'accepted.txt')
        self.assertEqual((folder / data['files']['one']['B']).read_text(), 'candidate.txt')

    def test_all_reference_images_are_protected(self):
        refs = self.root / 'referencia'
        refs.mkdir()
        for name in ('original.png', 'gold.png', 'bad.png'):
            (refs / name).write_bytes(name.encode())
        self.args.evaluation_contract = self.root / 'contract.json'
        self.args.evaluation_contract.write_text('{}')
        contract = {'reference_evidence': {'one': 'referencia/original.png'},
                    'review': {'target_reference_evidence': {'one': 'referencia/gold.png'},
                               'known_bad_evidence': {'one': 'referencia/bad.png'}}}
        names = supervisor.automatic_protected_paths(self.args, contract)
        self.assertEqual(len(names), 4)
        before = supervisor.protected_hashes(self.root, names)
        (refs / 'original.png').write_bytes(b'tampered')
        self.assertNotEqual(before, supervisor.protected_hashes(self.root, names))

    def test_directory_reject_keeps_previous_accept_and_screenshots(self):
        accepted = self.root / 'src' / 'thing.py'
        accepted.write_text('first accepted\n')
        receipt = {'number': 1, 'candidate_sha256': loop_guard.artifact_hash(self.root / 'src')}
        checkpoint = supervisor.checkpoint_accepted(self.args, receipt)
        first_hash = loop_guard.artifact_hash(self.root / 'src')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), checkpoint)
        (self.root / 'src' / 'thing.py').write_text('rejected attempt\n')
        new_file = self.root / 'src' / 'new.py'
        new_file.write_text('new candidate source\n')
        shots = self.root / 'screenshots'
        shots.mkdir()
        (shots / 'after.png').write_bytes(b'fresh screenshot')
        receipt = {'number': 2, 'candidate_sha256': loop_guard.artifact_hash(self.root / 'src'),
                   'evidence': ['screenshots/after.png']}
        self.state_dir.mkdir(parents=True)
        result = supervisor.restore_unapproved_candidate(self.args, receipt, checkpoint, first_hash)
        self.assertTrue(result.endswith('0002.patch'))
        self.assertEqual(loop_guard.artifact_hash(self.root / 'src'), first_hash)
        self.assertEqual(accepted.read_text(), 'first accepted\n')
        self.assertFalse(new_file.exists())
        self.assertTrue((self.state_dir / 'rejected' / '0002.added' / 'src' / 'new.py').exists())
        self.assertTrue((shots / 'after.png').exists())
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), checkpoint)

    def test_directory_reject_unwinds_worker_git_commit(self):
        self.source.write_text('accepted\n')
        receipt = {'number': 1, 'candidate_sha256': loop_guard.artifact_hash(self.root / 'src')}
        parent = supervisor.checkpoint_accepted(self.args, receipt)
        current_hash = loop_guard.artifact_hash(self.root / 'src')
        self.source.write_text('rejected\n')
        git(self.root, 'add', 'src')
        git(self.root, 'commit', '-qm', 'worker committed rejected code')
        self.assertNotEqual(git(self.root, 'rev-parse', 'HEAD'), parent)
        self.state_dir.mkdir(parents=True)
        receipt = {'number': 2, 'candidate_sha256': loop_guard.artifact_hash(self.root / 'src')}
        supervisor.restore_unapproved_candidate(self.args, receipt, parent, current_hash)
        self.assertEqual(self.source.read_text(), 'accepted\n')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), parent)

    def test_only_hard_checks_without_gain_measurement_hold(self):
        contract = self.root / 'contract.json'
        contract.write_text(json.dumps({'schema_version': 1, 'kind': 'functionality',
            'user_goal': 'Improve user visible behavior in daily use',
            'primary_outcome': 'Improve user visible behavior in daily use',
            'case_ids': ['scenario'], 'hard_checks': [{'argv': [sys.executable, '-c', 'pass']}],
            'review': {'required': False}}))
        self.assertEqual(evaluation_gate.evaluate(contract, self.root)['decision'], 'HOLD')

    def test_claude_fenced_json_is_parsed(self):
        path = self.root / 'out.json'
        data = blind_review.parse_judge_output(SimpleNamespace(stdout='```json\n{"verdict":"B"}\n```'), path)
        self.assertEqual(data['verdict'], 'B')
        wrapped = SimpleNamespace(stdout='Evidence report follows:\n```json\n{"verdict":"A"}\n```\nEnd.')
        self.assertEqual(blind_review.parse_judge_output(wrapped, path)['verdict'], 'A')
        with self.assertRaises(evaluation_gate.EvaluationError):
            blind_review.parse_judge_output(SimpleNamespace(stdout='text with {"verdict":"B"}'), path)

    def test_claude_permissions_are_explicit_and_configurable(self):
        cmd = agent_adapters.worker_command('claude', self.root, claude_permission_mode='acceptEdits')
        self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'acceptEdits')
        with self.assertRaises(agent_adapters.AdapterError):
            agent_adapters.worker_command('claude', self.root, claude_permission_mode='unsafe')

    def test_stale_supervisor_lock_reclaimed_but_live_lock_blocks(self):
        lock = self.root / 'supervisor.lock'
        lock.write_text(json.dumps({'pid': 999999999}))
        self.assertEqual(supervisor.create_lock(lock), lock)
        with self.assertRaises(supervisor.SupervisorError):
            supervisor.create_lock(lock)
        lock.unlink()

    def test_verifier_failure_returns_result_without_halt(self):
        self.args.verify_command = f'{sys.executable} -c "raise SystemExit(2)"'
        self.args.verify_timeout = 2
        self.state_dir.joinpath('turns').mkdir(parents=True)
        self.assertEqual(supervisor.run_verifier(self.args, 1), 2)
        self.assertTrue((self.state_dir / 'turns' / '0001.verify.json').is_file())

if __name__ == '__main__':
    unittest.main()

class SupervisorEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'thing.py').write_text('baseline\n')
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.name', 'Test')
        git(self.root, 'config', 'user.email', 't@example.invalid')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'baseline')
        self.goal = 'Improve user-facing performance across representative scenarios'
        self.state = self.root / '.refinement' / 'loop-contract'

    def execute(self, worker, n, other=()):
        return subprocess.run([sys.executable, str(ROOT / 'reflective-refinement' / 'scripts' / 'codex_supervisor.py'),
            '--workspace', str(self.root), '--artifact', 'src', '--goal', self.goal,
            '--iterations', str(n), '--harness', 'command', '--agent-command',
            json.dumps([sys.executable, str(worker)]), *other], capture_output=True, text=True, timeout=75)

    def test_worker_error_after_begin_recovers_source_and_retries(self):
        worker = self.root / 'fake.py'
        worker.write_text('''import os,sys,pathlib,subprocess
r=pathlib.Path(os.environ['RR_WORKSPACE']); state=os.environ['RR_STATE_DIR']; g=os.environ['RR_GUARD']
marker=r/'.refinement/attempt.marker'; first=not marker.exists(); marker.parent.mkdir(exist_ok=True)
marker.write_text('attempted')
subprocess.run([sys.executable,g,'begin','--state-dir',state,'--hypothesis','Check an alternative handling of the input','--planned-check','Inspect the concrete outcome after the change'],check=True)
(r/'src/thing.py').write_text('edited by trial')
if first: raise SystemExit(9)
e=r/'.refinement/evidence.txt';e.write_text('Output differs from previous run')
subprocess.run([sys.executable,g,'finish','--state-dir',state,'--outcome','discard','--finding','The alternative did not improve the target','--evidence','.refinement/evidence.txt'],check=True)
''')
        git(self.root, 'add', 'fake.py')
        git(self.root, 'commit', '-qm', 'worker fixture')
        result = self.execute(worker, 1)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RECOVERED:', result.stdout)
        self.assertIn('COMPLETE: 1/1', result.stdout)
        self.assertEqual((self.root / 'src' / 'thing.py').read_text(), 'baseline\n')
        self.assertEqual(len(loop_guard.load(self.state)['records']), 1)

    def test_failed_legacy_verifier_restores_and_continues(self):
        worker = self.root / 'fake.py'
        worker.write_text('''import os,sys,pathlib,subprocess
r=pathlib.Path(os.environ['RR_WORKSPACE']); state=os.environ['RR_STATE_DIR']; g=os.environ['RR_GUARD']
subprocess.run([sys.executable,g,'begin','--state-dir',state,'--hypothesis','Try a distinct modification of the output','--planned-check','Compare observed input behavior against baseline'],check=True)
(r/'src/thing.py').write_text('proposed change')
e=r/'.refinement/observed.txt';e.write_text('Concrete new observation of the changed outcome')
subprocess.run([sys.executable,g,'finish','--state-dir',state,'--outcome','keep','--finding','Observed relevant changed behavior in the output','--evidence','.refinement/observed.txt'],check=True)
''')
        bench = self.root / 'bench.py'
        bench.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":["scenario"],"guards":{"real":True},"metrics":{"correct":2}}))\n')
        contract = self.root / 'evaluation.json'
        contract.write_text(json.dumps({'schema_version': 1, 'kind':'functionality', 'user_goal': self.goal,
            'primary_outcome': 'Improve measured real user behavior in the original scenario',
            'case_ids':['scenario'],'hard_checks':[], 'benchmark': {'argv':[sys.executable,str(bench)]},
            'primary_metrics':[{'name':'correct','direction':'higher','reference':1}],
            'review':{'required':False}}))
        git(self.root,'add','fake.py','bench.py','evaluation.json')
        git(self.root,'commit','-qm','frozen fixtures')
        result=self.execute(worker,1,('--evaluation-contract',str(contract),
            '--verify-command',sys.executable+' -c "raise SystemExit(3)"'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(loop_guard.load(self.state)['records'][0]['outcome'],'discard')
        self.assertEqual((self.root/'src/thing.py').read_text(),'baseline\n')

class VisualIncumbentIntegrationTests(unittest.TestCase):
    def test_second_visual_candidate_must_beat_accepted_incumbent(self):
        import base64
        from test_fixed_iterations import png_pixel
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'src').mkdir()
            (root / 'src' / 'scene.py').write_text('baseline')
            (root / '.refinement').mkdir()
            (root / '.refinement' / 'reference.png').write_bytes(png_pixel(80))
            (root / '.refinement' / 'bad.png').write_bytes(png_pixel(0))
            worker = root / 'worker.py'
            first = base64.b64encode(png_pixel(180)).decode()
            second = base64.b64encode(png_pixel(125)).decode()
            worker.write_text(f'''import os,sys,pathlib,subprocess,base64
root=pathlib.Path(os.environ['RR_WORKSPACE']); state=os.environ['RR_STATE_DIR']
slot=int(os.environ['RR_SLOT_NUMBER']); g=os.environ['RR_GUARD']
subprocess.run([sys.executable,g,'begin','--state-dir',state,
'--hypothesis',f'Test alternative scene {{slot}} with more depth',
'--planned-check','Render and compare same camera with previous best'],check=True,capture_output=True)
(root/'src/scene.py').write_text(f'candidate-{{slot}}')
(root/'screenshots').mkdir(exist_ok=True)
image=root/'screenshots'/f'scene-{{slot}}.png'
image.write_bytes(base64.b64decode('{first}' if slot==1 else '{second}'))
subprocess.run([sys.executable,g,'finish','--state-dir',state,'--outcome','keep',
'--finding','The rendered result improved from the starting scene',
'--evidence',str(image.relative_to(root))],check=True,capture_output=True)
''')
            judge = root / 'judge.py'
            judge.write_text('''import json,pathlib,zlib,struct
cfg=json.loads(pathlib.Path('review_inputs.json').read_text())
paths=cfg['files']['scene']
def red(name):
    data=pathlib.Path(name).read_bytes(); cursor=8; chunks=[]
    while cursor<len(data):
        n=int.from_bytes(data[cursor:cursor+4],'big'); kind=data[cursor+4:cursor+8]
        if kind==b'IDAT': chunks.append(data[cursor+8:cursor+8+n])
        cursor+=12+n
    return zlib.decompress(b''.join(chunks))[1]
a=red(paths['A']);b=red(paths['B'])
winner='TIE' if a==b else ('A' if a>b else 'B')
print(json.dumps({'schema_version':1,'case_ids':['scene'],'verdict':winner,
'confidence':'high','criteria':[{'criterion_id':'depth','comparison':winner,
'observation':'Compare scene detail in identical camera case',
'evidence_ids':['scene']}], 'material_regressions':[]}))
''')
            check = root / 'benchmark.py'
            check.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":["scene"],"guards":{"ok":True},"metrics":{}}))\n')
            contract = root / 'evaluation.json'
            contract.write_text(json.dumps({'schema_version':1,'kind':'visual',
                'user_goal':'Improve depth and clarity of scene in runtime',
                'primary_outcome':'Improve depth and clarity of scene in runtime',
                'case_ids':['scene'],'hard_checks':[], 'benchmark':{'argv':[sys.executable,str(check)]},
                'reference_evidence':{'scene':'.refinement/reference.png'},
                'review':{'required':True,'criteria':['depth'],'reverse_order':True,
                          'known_bad_evidence':{'scene':'.refinement/bad.png'}}}))
            git(root, 'init', '-q')
            git(root, 'config', 'user.name', 'Fixture')
            git(root, 'config', 'user.email', 'fixture@test.invalid')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'baseline')
            sup = ROOT / 'reflective-refinement' / 'scripts' / 'codex_supervisor.py'
            result = subprocess.run([sys.executable,str(sup),'--workspace',str(root),
                '--artifact','src','--goal','Improve depth and clarity of scene in runtime',
                '--iterations','2','--harness','command','--agent-command',json.dumps([sys.executable,str(worker)]),
                '--evaluation-contract',str(contract),'--evidence-kind','visual',
                '--judge-provider','command','--judge-command',json.dumps([sys.executable,str(judge)])],
                capture_output=True,text=True,timeout=80)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            state=loop_guard.load(root/'.refinement/loop-contract')
            self.assertEqual([r['outcome'] for r in state['records']],['keep','discard'])
            self.assertEqual((root/'src/scene.py').read_text(),'candidate-1')
            self.assertTrue((root/'screenshots/scene-2.png').exists())
            self.assertTrue((root/'.refinement/loop-contract/accepted-evidence/0001/000.png').exists())
            report=json.loads((root/'.refinement/loop-contract/turns/0002.evaluation.json').read_text())
            self.assertEqual(report['judge']['status'],'REJECT')

class FurtherHardeningTests(unittest.TestCase):
    def test_stale_ledger_and_launch_locks_are_reclaimed(self):
        import auto_start
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            root.mkdir(exist_ok=True)
            (root / 'update.lock').write_text('999999999')
            with loop_guard.ledger_lock(root):
                self.assertTrue((root / 'update.lock').exists())
            self.assertFalse((root / 'update.lock').exists())
            (root / 'launch.lock').write_text('999999999')
            with auto_start.launch_lock(root):
                self.assertTrue((root / 'launch.lock').exists())
            self.assertFalse((root / 'launch.lock').exists())

    def test_benchmark_with_only_guard_and_no_measured_improvement_cannot_pass(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            benchmark=root/'bench.py'
            benchmark.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":["one"],"guards":{"correct":True},"metrics":{}}))\n')
            contract=root/'contract.json'
            contract.write_text(json.dumps({'schema_version':1, 'kind':'functionality',
                'user_goal':'Improve the quality of the implementation for users',
                'primary_outcome':'Improve the quality of the implementation for users',
                'case_ids':['one'],'benchmark':{'argv':[sys.executable,str(benchmark)]},
                'hard_checks':[],'primary_metrics':[], 'review':{'required':False}}))
            self.assertEqual(evaluation_gate.evaluate(contract,root)['decision'],'HOLD')

    def test_transient_timeout_retries_without_credit_or_corrupting_source(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'src').mkdir()
            (root/'src/a.py').write_text('original')
            worker=root/'fake.py'
            worker.write_text('''import sys,os,pathlib,subprocess,time
r=pathlib.Path(os.environ['RR_WORKSPACE']);flag=r/'.refinement/once';flag.parent.mkdir(exist_ok=True)
if not flag.exists():
 flag.write_text('1');time.sleep(7)
state=os.environ['RR_STATE_DIR'];g=os.environ['RR_GUARD']
subprocess.run([sys.executable,g,'begin','--state-dir',state,'--hypothesis','Test a new measurable output case',
'--planned-check','Observe the new output after the change'],check=True)
(r/'src/a.py').write_text('modified')
f=r/'.refinement/result.txt';f.write_text('An actual change was observed')
subprocess.run([sys.executable,g,'finish','--state-dir',state,'--outcome','discard',
'--finding','The change did not improve the desired result','--evidence','.refinement/result.txt'],check=True)
''')
            git(root,'init','-q');git(root,'config','user.name','Test')
            git(root,'config','user.email','t@invalid.example');git(root,'add','.')
            git(root,'commit','-qm','fixture')
            cmd=[sys.executable,str(ROOT/'reflective-refinement/scripts/codex_supervisor.py'),
                '--workspace',str(root),'--artifact','src','--goal',
                'Improve a real scenario while preserving correct behavior',
                '--iterations','1','--harness','command','--agent-command',
                json.dumps([sys.executable,str(worker)]),'--turn-timeout','3','--max-retries','2']
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('NOT COMPLETE: 0/1',r.stdout)
            self.assertEqual((root/'src/a.py').read_text(),'original')
            self.assertEqual(len(loop_guard.load(root/'.refinement/loop-contract')['records']),1)

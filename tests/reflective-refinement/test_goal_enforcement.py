"""Goal-driven supervision and workload fidelity regressions."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_fixed_iterations import MOCK_CLI

ROOT = Path(__file__).resolve().parents[2] / 'skills'
SCRIPTS = ROOT / 'reflective-refinement' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import evaluation_gate
import loop_guard


class GoalDrivenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'artifact.txt').write_text('baseline')
        self.cli = self.root / 'fake-codex.py'
        self.cli.write_text(MOCK_CLI)
        self.cli.chmod(0o755)
        self.goal = 'Cut actual Chrome render time by 50 percent on representative content'
        self.contract_path = self.root / 'evaluation.json'
        self.check = self.root / 'benchmark.py'
        self.check.write_text('''import json
from pathlib import Path
src = Path('src/artifact.txt').read_text()
quality = 2 if src.startswith('candidate-2:') else (1 if src.startswith('candidate-1:') else 0)
print(json.dumps({'schema_version':1, 'case_ids':['loaded-page'], 'guards': {'page_works':True},
  'case_facts':{'loaded-page':{'visible_content_cards':2}},
  'metrics':{'quality':quality}}))
''')
        self.contract = {'schema_version': 1, 'kind': 'functionality', 'user_goal': self.goal,
                         'primary_outcome': 'Cut end-to-end real user wait for representative content',
                         'case_ids': ['loaded-page'], 'hard_checks': [], 'protected_paths': ['benchmark.py'],
                         'case_requirements': {'loaded-page': {'visible_content_cards': {'minimum': 1}}},
                         'benchmark': {'argv': [sys.executable, str(self.check)]},
                         'primary_metrics': [{'name': 'quality', 'direction': 'higher',
                                              'reference': 0, 'minimum_gain': 1, 'target_value': 2}],
                         'review': {'required': False}}
        self.contract_path.write_text(json.dumps(self.contract))
        for command in (['git', 'init', '-q'], ['git', 'config', 'user.name', 'Fixture'],
                        ['git', 'config', 'user.email', 'fake@invalid.local'],
                        ['git', 'add', '.'], ['git', 'commit', '-qm', 'baseline']):
            result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_until_target_runs_two_workers_and_never_accepts_first_partial_result(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'codex_supervisor.py'),
             '--workspace', str(self.root), '--artifact', 'src/artifact.txt',
             '--goal', self.goal, '--until-target', '--evaluation-contract', str(self.contract_path),
             '--codex-bin', str(self.cli)], text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('GOAL_MET:', result.stdout)
        state = loop_guard.load(self.root / '.refinement' / 'loop-contract')
        self.assertEqual(state['mode'], 'goal')
        self.assertEqual([r['outcome'] for r in state['records']], ['keep', 'keep'])
        self.assertTrue(state['goal_met'])
        self.assertEqual(loop_guard.status_dict(state)['status'], 'COMPLETE')
        self.assertEqual(state['goal_verified_trial'], 2)

    def test_until_target_requires_measurable_completion_condition(self):
        self.contract['primary_metrics'][0].pop('target_value')
        self.contract_path.write_text(json.dumps(self.contract))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'codex_supervisor.py'),
             '--workspace', str(self.root), '--artifact', 'src/artifact.txt', '--goal', self.goal,
             '--until-target', '--evaluation-contract', str(self.contract_path),
             '--codex-bin', str(self.cli)], text=True, capture_output=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('independently measurable DONE WHEN', result.stderr)

    def test_benchmark_with_missing_real_content_cannot_claim_gain(self):
        self.contract['kind'] = 'performance'
        self.contract['primary_metrics'][0]['reference'] = 500
        self.contract['primary_metrics'][0]['direction'] = 'lower'
        self.contract['primary_metrics'][0]['target_value'] = 250
        self.contract_path.write_text(json.dumps(self.contract))
        invalid = {'schema_version':1, 'case_ids':['loaded-page'], 'guards':{'page_works': True},
                   'case_facts':{'loaded-page':{'visible_content_cards':0}},
                   'metrics':{'quality':220}, 'samples':{'quality':[219,220,221]}}
        contract = evaluation_gate.read_contract(self.contract_path)[0]
        with self.assertRaisesRegex(evaluation_gate.EvaluationError, 'unrepresentative benchmark case'):
            evaluation_gate.metric_assessment(contract, invalid)
        invalid['case_facts'] = {'loaded-page': {'visible_content_cards': 2}}
        valid = evaluation_gate.metric_assessment(contract, invalid)
        self.assertEqual(valid['status'], 'PASS')
        self.assertEqual(evaluation_gate.target_metrics_assessment(contract, {'benchmark':valid})['status'], 'MET')

    def test_unmeasured_content_is_not_implicitly_present(self):
        contract = evaluation_gate.read_contract(self.contract_path)[0]
        invalid = {'schema_version':1,'case_ids':['loaded-page'],'guards':{'page_works':True},
                   'metrics':{'quality':1}}
        with self.assertRaisesRegex(evaluation_gate.EvaluationError, 'unmeasured case fidelity'):
            evaluation_gate.metric_assessment(contract, invalid)

    def test_preflight_fails_without_content_before_any_experiment(self):
        self.contract['kind'] = 'performance'
        self.contract['primary_metrics'][0].update({'reference': 500, 'direction': 'lower',
                                                     'target_value': 250})
        self.contract_path.write_text(json.dumps(self.contract))
        self.check.write_text('''import json
print(json.dumps({'schema_version':1,'case_ids':['loaded-page'], 'guards':{'page_works':True},
 'case_facts':{'loaded-page':{'visible_content_cards':0}},
 'metrics':{'quality':500},'samples':{'quality':[500,500,500]}}))
''')
        subprocess.run(['git', 'add', 'benchmark.py', 'evaluation.json'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'freeze representative case'], cwd=self.root, check=True)
        result = subprocess.run([sys.executable, str(SCRIPTS/'codex_supervisor.py'),
            '--workspace', str(self.root), '--artifact', 'src/artifact.txt',
            '--goal', self.goal, '--until-target', '--evaluation-contract', str(self.contract_path),
            '--codex-bin', str(self.cli)], text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('unrepresentative benchmark case', result.stderr)
        self.assertEqual((self.root / 'src' / 'artifact.txt').read_text(), 'baseline')
        self.assertFalse((self.root/'.refinement'/'fake-turns.txt').exists())

    def test_preflight_accepts_real_content_with_pinned_baseline(self):
        self.contract['kind'] = 'performance'
        self.contract['primary_metrics'][0].update({'reference': 500, 'direction': 'lower',
                                                     'target_value': 250})
        self.contract_path.write_text(json.dumps(self.contract))
        self.check.write_text('''import json
print(json.dumps({'schema_version':1,'case_ids':['loaded-page'], 'guards':{'page_works':True},
 'case_facts':{'loaded-page':{'visible_content_cards':3}},
 'metrics':{'quality':500},'samples':{'quality':[499,500,501]}}))
''')
        contract = evaluation_gate.read_contract(self.contract_path)[0]
        result = evaluation_gate.preflight_performance_benchmark(contract, self.root)
        self.assertEqual(result['status'], 'PASS')

    def test_auto_launcher_does_not_require_manual_iterations_in_goal_mode(self):
        import time
        command = [sys.executable, str(SCRIPTS / 'auto_start.py'), 'launch',
                   '--workspace', str(self.root), '--artifact', 'src/artifact.txt',
                   '--goal', self.goal, '--until-target', '--evaluation-contract', str(self.contract_path),
                   '--codex-bin', str(self.cli)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'LAUNCHED')
        deadline = time.monotonic() + 35
        state_file = self.root/'.refinement'/'loop-contract'/'contract.json'
        while time.monotonic() < deadline:
            if state_file.exists() and loop_guard.load(state_file.parent).get('goal_met'):
                break
            time.sleep(0.25)
        self.assertTrue(loop_guard.load(state_file.parent)['goal_met'])
        info = subprocess.run([sys.executable, str(SCRIPTS/'auto_start.py'), 'status',
                               '--state-dir', str(state_file.parent)], capture_output=True, text=True)
        self.assertEqual(json.loads(info.stdout)['status'], 'COMPLETE')

    def test_target_checks_prove_functional_gain_only_when_original_failed(self):
        self.contract['primary_metrics'] = []
        self.contract.pop('benchmark')
        self.contract['target_checks'] = [{'id': 'user-outcome',
            'argv': [sys.executable, str(self.check)]}]
        self.check.write_text('''from pathlib import Path
raise SystemExit(0 if Path('src/artifact.txt').read_text().startswith('candidate-1:') else 1)
''')
        self.contract_path.write_text(json.dumps(self.contract))
        subprocess.run(['git', 'add', 'benchmark.py', 'evaluation.json'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'freeze failure reproduction'], cwd=self.root, check=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'codex_supervisor.py'),
             '--workspace', str(self.root), '--artifact', 'src/artifact.txt',
             '--goal', self.goal, '--until-target', '--evaluation-contract', str(self.contract_path),
             '--codex-bin', str(self.cli)], text=True, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = loop_guard.load(self.root/'.refinement'/'loop-contract')
        self.assertTrue(state['goal_met'])
        self.assertEqual(len(state['records']), 1)
        self.assertEqual(state['records'][0]['outcome'], 'keep')
        report = json.loads((self.root/'.refinement'/'loop-contract'/'turns'/'0001.evaluation.json').read_text())
        self.assertEqual(report['target_completion'], 'MET')

    def test_target_check_already_passing_is_not_fabricated_improvement(self):
        self.contract['primary_metrics'] = []
        self.contract.pop('benchmark')
        self.contract['target_checks'] = [{'id': 'already-good', 'argv': [sys.executable, '-c',
                                                                        'raise SystemExit(0)']}]
        self.contract_path.write_text(json.dumps(self.contract))
        subprocess.run(['git', 'add', 'evaluation.json'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'freeze existing target'], cwd=self.root, check=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'codex_supervisor.py'),
             '--workspace', str(self.root), '--artifact', 'src/artifact.txt',
             '--goal', self.goal, '--until-target', '--evaluation-contract', str(self.contract_path),
             '--codex-bin', str(self.cli)], text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('baseline target checks must fail', result.stderr)
        self.assertFalse((self.root/'.refinement'/'fake-turns.txt').exists())


if __name__ == '__main__': unittest.main()

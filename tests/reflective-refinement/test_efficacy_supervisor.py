import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_fixed_iterations import MOCK_CLI

ROOT=Path(__file__).resolve().parents[2] / 'skills'
SUP=ROOT/'reflective-refinement'/'scripts'/'codex_supervisor.py'

class SupervisorEfficacyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'src').mkdir();(self.root/'src'/'artifact.txt').write_text('baseline')
        (self.root/'.refinement').mkdir();(self.root/'.refinement'/'reference.txt').write_text('Old reference output')
        self.fake=self.root/'fake_codex.py';self.fake.write_text(MOCK_CLI);self.fake.chmod(0o755)
        self.check=self.root/'check.py'
        self.contract=self.root/'quality_contract.json'
        self.write_contract(True)
        for args in [('init','-q'),('config','user.name','Fixture'),('config','user.email','fake@local.invalid'),
                     ('add','.'),('commit','-qm','fixture')]:
            r=subprocess.run(['git',*args],cwd=self.root,capture_output=True,text=True)
            assert r.returncode==0, r.stderr

    def write_contract(self, guard_ok, kind='functionality', review_required=False):
        self.check.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":["case"],"guards":{"correct":'+str(guard_ok)+'},"metrics":{"quality":1}}))\n')
        self.contract.write_text(json.dumps({'schema_version':1,'kind':kind,
           'user_goal':'Improve correctness in real scenarios',
           'primary_outcome':'Achieve correct behavior for real users', 'case_ids':['case'],
           'protected_paths':['check.py'],
           'hard_checks':[],
           'benchmark':{'argv':[sys.executable,str(self.check)]},
           'primary_metrics':[{'name':'quality','direction':'higher','reference':0,'minimum_gain':1}],
           'reference_evidence':{'case':'.refinement/reference.txt'},
           'review':{'required':review_required,'criteria':['quality']}}))

    def run_trial(self, *extra):
        subprocess.run(['git','add','.'],cwd=self.root,check=True,capture_output=True)
        subprocess.run(['git','commit','-qm','freeze evaluation inputs'],cwd=self.root,capture_output=True)
        return subprocess.run([sys.executable,str(SUP),'--workspace',str(self.root),
            '--artifact','src/artifact.txt','--goal','Improve correctness in real scenarios',
            '--iterations','1','--codex-bin',str(self.fake),
            '--evaluation-contract',str(self.contract),*extra],capture_output=True,text=True,timeout=60)

    def state(self):
        return json.loads((self.root/'.refinement'/'loop-contract'/'contract.json').read_text())

    def test_failing_guard_downgrades_false_keep(self):
        self.write_contract(False)
        r=self.run_trial()
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.state()['records'][0]['outcome'],'discard')
        self.assertIn('decision=REJECT',r.stdout)
        self.assertEqual((self.root/'src'/'artifact.txt').read_text(), 'baseline')
        self.assertTrue((self.root/'.refinement'/'loop-contract'/'rejected'/'0001.patch').exists())

    def test_external_quality_references_are_protected_from_worker(self):
        sys.path.insert(0, str(ROOT/'reflective-refinement'/'scripts'))
        import codex_supervisor
        from types import SimpleNamespace
        (self.root/'referencia').mkdir()
        (self.root/'referencia'/'goal.txt').write_text('Do not modify target reference')
        contract=json.loads(self.contract.read_text())
        contract['review']['target_reference_evidence']={'case':'referencia/goal.txt'}
        args=SimpleNamespace(protect=[],evaluation_contract=self.contract,workspace=self.root)
        protected=codex_supervisor.automatic_protected_paths(args,contract)
        self.assertIn(str(self.root/'referencia'/'goal.txt'),protected)
        self.assertIn(str(self.root/'.refinement'/'reference.txt'),protected)

    def test_frozen_benchmark_approves_actual_gain(self):
        r=self.run_trial()
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.state()['records'][0]['outcome'],'keep')
        self.assertIn('decision=KEEP',r.stdout)

    def test_partial_promotion_is_kept_but_not_marked_complete(self):
        source=json.loads(self.contract.read_text())
        source['target_checks']=[{'id':'new-functionality',
                                  'argv':[sys.executable,'-c','raise SystemExit(1)']}]
        self.contract.write_text(json.dumps(source))
        r=self.run_trial()
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.state()['records'][0]['outcome'],'keep')
        report=json.loads((self.root/'.refinement/loop-contract/turns/0001.evaluation.json').read_text())
        self.assertEqual(report['decision'],'KEEP')
        self.assertEqual(report['target_completion'],'NOT_MET')
        self.assertEqual(report['target_checks']['status'],'NOT_MET')

    def test_missing_judge_holds_instead_of_false_keep(self):
        self.write_contract(True, kind='documentation', review_required=True)
        r=self.run_trial()
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.state()['records'][0]['outcome'],'hold')
        self.assertIn('decision=HOLD',r.stdout)
        self.assertEqual((self.root/'src'/'artifact.txt').read_text(), 'baseline')

    def test_evaluation_script_modified_by_worker_is_detected(self):
        self.fake.write_text(MOCK_CLI.replace("if mode == 'tamper-evaluator':", "if True:").replace("'evaluator.txt'", "'check.py'"))
        r=self.run_trial()
        self.assertEqual(r.returncode,3,r.stdout+r.stderr)
        self.assertIn('protected evaluator',r.stderr)

if __name__=='__main__':unittest.main()

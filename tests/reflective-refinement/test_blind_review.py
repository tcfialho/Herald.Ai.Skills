import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0, str(ROOT / 'reflective-refinement' / 'scripts'))
import blind_review as blind
from evaluation_gate import EvaluationError

class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        self.artifact = self.root / 'src' / 'game.py'
        self.artifact.write_text('secret source code')
        (self.root / '.refinement').mkdir()
        (self.root / '.refinement' / 'old.txt').write_text('Old output')
        (self.root / '.refinement' / 'new.txt').write_text('New output')
        self.contract = {'primary_outcome':'A much clearer view for the user', 'kind':'visual',
                         'case_ids':['gameplay'], 'reference_evidence':{'gameplay':'.refinement/old.txt'},
                         'review':{'criteria':['detail']}}

    def test_bundle_contains_only_outputs_and_frozen_goal(self):
        folder=self.root/'review_outside'
        mapping, hashes, rubric = blind.build_bundle(folder, self.root, self.artifact,
                                                       self.contract, ['.refinement/new.txt'])
        contents='\n'.join(p.read_text(errors='replace') for p in folder.iterdir() if p.is_file())
        self.assertNotIn('secret source code',contents)
        self.assertNotIn(str(self.root),contents)
        self.assertEqual(mapping,{'A':'incumbent','B':'candidate'})
        self.assertEqual(set(rubric['files']),{'gameplay'})

    def test_target_quality_reference_is_separate_from_anonymous_candidacy(self):
        (self.root/'referencia').mkdir()
        (self.root/'referencia'/'ideal.txt').write_text('Target quality example')
        self.contract['review']['target_reference_evidence']={'gameplay':'referencia/ideal.txt'}
        folder=self.root/'reference_bundle'
        mapping, hashes, rubric = blind.build_bundle(folder,self.root,self.artifact,
                                                       self.contract,['.refinement/new.txt'])
        self.assertEqual(mapping['B'],'candidate')
        target_name=rubric['target_reference_evidence']['gameplay']
        self.assertEqual((folder/target_name).read_text(),'Target quality example')
        self.assertNotEqual(target_name,rubric['files']['gameplay']['B'])
        self.assertNotIn('secret source code', ''.join(
            f.read_text() for f in folder.iterdir() if f.is_file()))

    def test_never_send_editable_source_to_visual_judge(self):
        self.contract['reference_evidence']['gameplay']='src/game.py'
        with self.assertRaises(EvaluationError):
            blind.build_bundle(self.root/'bundle',self.root,self.artifact,self.contract,['.refinement/new.txt'])

    def test_symlink_evidence_is_not_allowed(self):
        link=self.root/'.refinement'/'aliased.txt'
        link.symlink_to(self.artifact)
        with self.assertRaises(EvaluationError):
            blind.build_bundle(self.root/'bundle',self.root,self.artifact,
                               self.contract,['.refinement/aliased.txt'])

    def test_reversed_order_swaps_anonymous_labels(self):
        mapping, *_ = blind.build_bundle(self.root/'bundle',self.root,self.artifact,self.contract,
                                         ['.refinement/new.txt'],reverse=True)
        self.assertEqual(mapping,{'A':'candidate','B':'incumbent'})

    def test_missing_judge_is_explicit_hold(self):
        self.assertEqual(blind.review(self.contract,self.root,self.artifact,['.refinement/new.txt'])['status'],'HOLD')

    def test_fake_model_judge_with_reverse_order(self):
        script=self.root/'fake_judge.py'
        script.write_text('import json, pathlib, sys\n'
                          'p=json.loads(pathlib.Path("review_inputs.json").read_text())\n'
                          'name=p["files"]["gameplay"]\n'
                          'winner="A" if "New output" in pathlib.Path(name["A"]).read_text() else "B"\n'
                          'print(json.dumps({"schema_version":1,"case_ids":["gameplay"],"verdict":winner, '
                          '"confidence":"high","criteria":[{"criterion_id":"detail", "comparison":winner, '
                          '"observation":"Candidate has more visible detail", "evidence_ids":["gameplay"]}], '
                          '"material_regressions":[],"uncertainties":[]}))\n')
        self.contract['review']['reverse_order']=True
        result=blind.review(self.contract,self.root,self.artifact,['.refinement/new.txt'],
                            provider='command',argv=[sys.executable,str(script)])
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['source_isolation'],'not_enforced')
        self.assertEqual([o['verdict'] for o in result['runs']],['B','A'])

    def test_blind_bundle_uses_priorities_and_anchored_quality_without_identity(self):
        self.contract['priority_order']=['Actual readability comes first', 'Avoid distracting changes']
        self.contract['review']['criterion_guidance']={'detail':'All user-visible states remain legible'}
        self.contract['review']['quality_gate']={
            'max_remaining_severity':'minor',
            'coverage_groups':{'user_journey':['gameplay']},
            'severity_anchors':{'major':'Prevents the user from completing their real goal'}}
        folder=self.root/'anonymous'
        _, _, rubric=blind.build_bundle(folder,self.root,self.artifact,self.contract,['.refinement/new.txt'])
        self.assertEqual(rubric['priority_order'][0], 'Actual readability comes first')
        self.assertEqual(rubric['criterion_guidance']['detail'], 'All user-visible states remain legible')
        prompt=(folder/'judge_prompt.txt').read_text()
        self.assertIn('BOTH anonymous alternatives A and B',prompt)
        self.assertNotIn('New output',prompt)
        self.assertNotIn(str(self.artifact),prompt)
        self.assertNotIn('Which is the candidate',prompt)

    def test_reversed_blind_reviews_grade_both_outputs_without_source_access(self):
        script=self.root/'fake_quality_judge.py'
        script.write_text("""import json, pathlib
p=json.loads(pathlib.Path('review_inputs.json').read_text())
files=p['files']['gameplay']
texts={label:pathlib.Path(path).read_text() for label,path in files.items()}
winner=next(label for label,value in texts.items() if value=='New output')
def assess(value):
    bad=value!='New output'
    return {'quality_findings':([{'severity':'major','description':'Text unreadable to the intended user',
        'evidence_ids':['gameplay']}] if bad else []),
        'case_observations':[{'case_id':'gameplay', 'worst_severity':'major' if bad else 'none',
        'observation':'Checked the intended user outcome against the frozen goal'}]}
print(json.dumps({'schema_version':1,'case_ids':['gameplay'],'verdict':winner,
    'confidence':'high','criteria':[{'criterion_id':'detail','comparison':winner,
    'observation':'The new result is more usable than the old result',
    'evidence_ids':['gameplay']}],'material_regressions':[], 'uncertainties':[],
    'quality_by_label':{label:assess(text) for label,text in texts.items()}}))
""")
        self.contract['review']['reverse_order']=True
        self.contract['review']['quality_gate']={
            'max_remaining_severity':'minor','coverage_groups':{'scenario':['gameplay']}}
        outcome=blind.review(self.contract,self.root,self.artifact,['.refinement/new.txt'],
                             provider='command',argv=[sys.executable,str(script)])
        self.assertEqual(outcome['status'],'PASS')
        self.assertEqual(outcome['quality_target']['status'],'MET')
        self.assertEqual([item['verdict'] for item in outcome['runs']], ['B','A'])

    def test_A_equals_A_never_wins(self):
        self.assertEqual(blind.review(self.contract,self.root,self.artifact,['.refinement/old.txt'],
                                      provider='command',argv=[sys.executable,'invalid'])['status'],'HOLD')

if __name__=='__main__': unittest.main()

class JudgeCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'src').mkdir(); self.source=self.root/'src'/'code.py';self.source.write_text('code')
        (self.root/'.refinement').mkdir()
        for name,text in [('base','good'),('bad','bad')]:
            (self.root/'.refinement'/f'{name}.txt').write_text(text)
        self.contract={'kind':'visual','primary_outcome':'A usable and visually correct display',
                       'case_ids':['scene'],'reference_evidence':{'scene':'.refinement/base.txt'},
                       'review':{'criteria':['visual'],'known_bad_evidence':{'scene':'.refinement/bad.txt'}}}
    def test_judge_calibration_rejects_a_equals_a_fabrication(self):
        script=self.root/'bad_model.py'
        script.write_text('import json\nprint(json.dumps({"schema_version":1,"verdict":"B","confidence":"high",'
          '"case_ids":["scene"],"criteria":[{"criterion_id":"visual","comparison":"B",'
          '"observation":"Invented visible differences", "evidence_ids":["scene"]}]}))')
        out=blind.calibrate_judge(self.contract,self.root,self.source,'command',[sys.executable,str(script)])
        self.assertEqual(out['status'],'HOLD')
    def test_quality_calibration_rejects_inconsistent_identical_outputs(self):
        self.contract['review']['quality_gate']={
            'max_remaining_severity':'minor','coverage_groups':{'scenario':['scene']}}
        script=self.root/'inconsistent_quality_judge.py'
        script.write_text("""import json
base={'case_id':'scene', 'observation':'The same output is checked against the same criterion'}
def result(severity):
    obs={**base,'worst_severity':severity}
    issues=[] if severity=='none' else [{'severity':'major',
        'description':'The output blocks the user objective','evidence_ids':['scene']}]
    return {'case_observations':[obs],'quality_findings':issues}
print(json.dumps({'schema_version':1,'case_ids':['scene'],'verdict':'TIE',
 'confidence':'high','criteria':[{'criterion_id':'visual','comparison':'TIE',
  'observation':'Identical rendered evidence on both sides','evidence_ids':['scene']}],
 'quality_by_label':{'A':result('none'),'B':result('major')},
 'material_regressions':[], 'uncertainties':[]}))
""")
        outcome=blind.calibrate_judge(self.contract,self.root,self.source,
                                       'command',[sys.executable,str(script)])
        self.assertEqual(outcome['status'],'HOLD')
        self.assertIn('inconsistent',outcome['reason'])

    def test_positive_and_negative_controls(self):
        script=self.root/'good_model.py'
        script.write_text('import json,pathlib\n'
          'p=json.loads(pathlib.Path("review_inputs.json").read_text()); fs=p["files"]["scene"]\n'
          'a=pathlib.Path(fs["A"]).read_text();b=pathlib.Path(fs["B"]).read_text()\n'
          'v="TIE" if a==b else ("A" if "bad" in b else "B")\n'
          'print(json.dumps({"schema_version":1,"verdict":v,"confidence":"high",'
          '"case_ids":["scene"],"criteria":[{"criterion_id":"visual","comparison":v,'
          '"observation":"Compared actual visible content", "evidence_ids":["scene"]}]}))\n')
        out=blind.calibrate_judge(self.contract,self.root,self.source,'command',[sys.executable,str(script)])
        self.assertEqual(out['status'],'PASS')

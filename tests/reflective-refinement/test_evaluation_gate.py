import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0, str(ROOT / 'reflective-refinement' / 'scripts'))
import evaluation_gate as gate


class OutcomeGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / 'score.py'
        self.report.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":["normal","boundary"],"guards":{"correct":True},"metrics":{"success":18}}))\n')
        self.contract = {'schema_version': 1, 'kind': 'functionality',
                         'user_goal':'Improve correctness in real scenarios',
                         'primary_outcome': 'Correct user-visible behavior in every case',
                         'case_ids': ['normal', 'boundary'],
                         'hard_checks': [],
                         'benchmark': {'argv': [sys.executable, str(self.report)]},
                         'primary_metrics': [{'name':'success', 'direction':'higher', 'reference':15, 'minimum_gain':2}],
                         'review': {'required':False}}
        self.path = self.root / 'contract.json'
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.contract))

    def test_known_bad_control_that_passes_blocks_confirmation(self):
        self.contract['negative_control']={'argv':[sys.executable,str(self.report)]}
        self.save()
        self.assertEqual(gate.evaluate(self.path,self.root)['decision'],'HOLD')

    def test_performance_needs_repeated_workload_samples(self):
        self.contract['kind']='performance'
        self.save()
        self.assertEqual(gate.evaluate(self.path,self.root)['decision'],'HOLD')

    def test_actual_gain_can_be_promoted(self):
        self.assertEqual(gate.evaluate(self.path, self.root)['decision'], 'KEEP')

    def test_worse_than_verified_incumbent_cannot_be_promoted_again(self):
        outcome=gate.evaluate(self.path,self.root,incumbent_metrics={'success':20})
        self.assertEqual(outcome['decision'], 'REJECT')
        self.assertEqual(outcome['benchmark']['benchmark']['metrics']['success']['incumbent'], 20)

    def test_hard_regression_overrides_metric(self):
        self.report.write_text(self.report.read_text().replace('"correct":True','"correct":False'))
        self.assertEqual(gate.evaluate(self.path, self.root)['decision'], 'REJECT')

    def test_proxies_cannot_replace_original_user_outcome(self):
        self.contract['primary_metrics'][0]['minimum_gain'] = 10
        self.save()
        self.assertEqual(gate.evaluate(self.path, self.root)['decision'], 'REJECT')

    def test_stale_case_ids_cannot_promote(self):
        self.report.write_text(self.report.read_text().replace('"boundary"','"unrelated"'))
        self.assertEqual(gate.evaluate(self.path, self.root)['decision'], 'HOLD')

    def test_visual_missing_judge_holds_even_when_checks_pass(self):
        self.contract['kind'] = 'visual'
        self.contract['review'] = {'required':True, 'criteria':['depth'], 'candidate_label':'B'}
        self.save()
        self.assertEqual(gate.evaluate(self.path, self.root)['decision'], 'HOLD')

    def test_visual_independent_judge_can_promote(self):
        self.contract['kind'] = 'visual'
        self.contract['review'] = {'required':True, 'criteria':['depth'], 'candidate_label':'B'}
        self.save()
        judge={'schema_version':1, 'case_ids':['normal','boundary'], 'verdict':'B', 'confidence':'high',
               'criteria':[{'criterion_id':'depth','comparison':'B','observation':'Better depth in corners', 'evidence_ids':['normal']}],
               'material_regressions':[]}
        self.assertEqual(gate.evaluate(self.path, self.root, judge)['decision'], 'KEEP')
        judge['verdict']='TIE'
        self.assertEqual(gate.evaluate(self.path, self.root, judge)['decision'], 'HOLD')

    def test_unknown_visual_without_judge_is_invalid_contract(self):
        self.contract['kind']='visual'
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)

    def test_no_measures_cannot_promote(self):
        self.contract['benchmark'] = None
        self.contract['primary_metrics'] = []
        self.save()
        self.assertEqual(gate.evaluate(self.path, self.root)['decision'], 'HOLD')


class OutcomeQualityContractTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.contract = {
            'schema_version': 1,
            'kind': 'documentation',
            'user_goal': 'Improve quality of the same running scene through multiple views',
            'primary_outcome': 'Make the scene credible in stills, motion, and novel viewpoints',
            'case_ids': ['front', 'rear', 'lap-mid', 'burst', 'holdout'],
            'hard_checks': [],
            'review': {
                'required': True, 'criteria': ['scene-coherence'],
                'criterion_guidance': {'scene-coherence': 'Actual user experience must remain coherent in every frozen scenario'},
                'quality_gate': {
                    'max_remaining_severity': 'minor',
                    'coverage_groups': {'fixed': ['front', 'rear'], 'route': ['lap-mid'],
                                        'temporal': ['burst'], 'confirmation': ['holdout']},
                    'confirmation_group': 'confirmation',
                }
            },
        }
        self.path = self.root / 'contract.json'
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.contract))

    def report(self, issues=()):
        def grade(issues_here):
            severities = {row['case_id']: row['severity'] for row in issues_here}
            return {'quality_findings': [
                {'severity': row['severity'], 'description': 'Observable defect affecting this user outcome',
                 'evidence_ids': [row['case_id']]} for row in issues_here],
                'case_observations': [
                    {'case_id': name, 'worst_severity': severities.get(name, 'none'),
                     'observation': 'Inspected this exact scenario for the requested user outcome'}
                    for name in self.contract['case_ids']]}
        return {'schema_version': 1, 'case_ids': list(self.contract['case_ids']),
                'verdict': 'B', 'confidence': 'high',
                'criteria': [{'criterion_id': 'scene-coherence', 'comparison': 'B',
                              'observation': 'The candidate is more coherent in the actual scenarios',
                              'evidence_ids': list(self.contract['case_ids'])}],
                'material_regressions': [], 'quality_by_label': {'A': grade([]), 'B': grade(issues)}}

    def test_quality_gate_requires_complete_coverage(self):
        data = self.report()
        data['quality_by_label']['B']['case_observations'].pop()
        with self.assertRaises(gate.EvaluationError):
            gate.review_verdict(data, self.contract['review']['criteria'], self.contract['case_ids'], 'B',
                                quality_gate=self.contract['review']['quality_gate'])

    def test_quality_gate_preserves_relative_gain_without_declaring_done(self):
        report = self.report([{'case_id': 'burst', 'severity': 'major'}])
        self.assertEqual(gate.review_verdict(report, self.contract['review']['criteria'],
                         self.contract['case_ids'], 'B', quality_gate=self.contract['review']['quality_gate'])[0], 'PASS')
        quality = gate.quality_target_assessment(report, self.contract['review']['quality_gate'],
                                                self.contract['case_ids'], 'B')
        self.assertEqual(quality['status'], 'NOT_MET')
        self.assertEqual(quality['blocking_findings'], 1)

    def test_quality_gate_accepts_minor_issues_after_all_views(self):
        report = self.report([{'case_id': 'front', 'severity': 'minor'}])
        outcome = gate.quality_target_assessment(report, self.contract['review']['quality_gate'],
                                                  self.contract['case_ids'], 'B')
        self.assertEqual(outcome['status'], 'MET')

    def test_quality_gate_catches_contradictory_severity(self):
        data = self.report([{'case_id': 'burst', 'severity': 'major'}])
        data['quality_by_label']['B']['case_observations'][3]['worst_severity'] = 'none'
        with self.assertRaises(gate.EvaluationError):
            gate.quality_target_assessment(data, self.contract['review']['quality_gate'],
                                           self.contract['case_ids'], 'B')

    def test_quality_gate_rejects_uncovered_confirmation(self):
        self.contract['review']['quality_gate']['coverage_groups'].pop('confirmation')
        self.save()
        with self.assertRaises(gate.EvaluationError):
            gate.read_contract(self.path)

    def test_both_labels_required_for_genuinely_blind_quality(self):
        data = self.report()
        data['quality_by_label'].pop('A')
        with self.assertRaises(gate.EvaluationError):
            gate.review_verdict(data, self.contract['review']['criteria'],
                                self.contract['case_ids'], 'B', self.contract['review']['quality_gate'])

    def test_relative_improvement_can_remain_below_quality_target(self):
        self.contract['benchmark'] = None
        self.contract['hard_checks'] = [{'id':'check', 'argv':[sys.executable, '-c', 'pass']}]
        self.contract['review']['candidate_label'] = 'B'
        self.save()
        report = gate.evaluate(self.path, self.root, self.report([
            {'case_id': 'burst', 'severity': 'major'}]))
        self.assertEqual(report['decision'], 'KEEP')
        self.assertEqual(report['target_completion'], 'NOT_MET')
        self.assertEqual(report['quality_target']['status'], 'NOT_MET')

    def test_target_completion_requires_verified_checks_and_review(self):
        self.contract['hard_checks'] = [{'id':'check', 'argv':[sys.executable, '-c', 'pass']}]
        self.save()
        report = gate.evaluate(self.path, self.root, self.report())
        self.assertEqual(report['decision'], 'KEEP')
        self.assertEqual(report['target_completion'], 'MET')
        unknown = gate.evaluate(self.path, self.root)
        self.assertEqual(unknown['decision'], 'HOLD')
        self.assertEqual(unknown['target_completion'], 'UNKNOWN')

    def test_quality_reference_must_point_to_frozen_case_id(self):
        self.contract['review']['target_reference_evidence']={'wrong':'referencia/gold.txt'}
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)
        self.contract['review']['target_reference_evidence']={'front':'referencia/gold.txt'}
        self.save()
        gate.read_contract(self.path)

    def test_reject_ambiguous_unanchored_priorities_and_guidance(self):
        self.contract['priority_order'] = ['quality first', 'quality first']
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)
        self.contract['priority_order'] = ['Reliable actual user outcome', 'Fewer false successes']
        self.contract['review']['criterion_guidance'] = {'wrong_id':'Strong coherent result in every case'}
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)
        self.contract['review']['criterion_guidance'] = {
            'scene-coherence':'The consumer must be able to complete the intended workflow'}
        self.save()
        self.assertEqual(gate.read_contract(self.path)[0]['kind'], self.contract['kind'])

    def test_overlapping_scenario_groups_allowed_except_confirmation(self):
        quality = self.contract['review']['quality_gate']
        quality['coverage_groups']['route'].append('front')
        self.save()
        self.assertEqual(gate.read_contract(self.path)[0]['kind'], self.contract['kind'])
        quality['coverage_groups']['confirmation'].append('front')
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)

    def test_doc_and_ux_use_same_gate_as_visual(self):
        for kind in ('documentation', 'ux', 'visual'):
            self.contract['kind'] = kind
            self.save()
            gate.read_contract(self.path)
            grade = gate.quality_target_assessment(self.report([
                {'case_id':'burst','severity':'major'}]),
                self.contract['review']['quality_gate'], self.contract['case_ids'], 'B')
            self.assertEqual(grade['status'], 'NOT_MET')

    def test_protected_qualitative_goal_cannot_be_traded_for_overall_win(self):
        report = self.report()
        report['criteria'] = [
            {'criterion_id':'scene-coherence','comparison':'A',
             'observation':'The candidate loses an essential user-visible behavior',
             'evidence_ids':['front']}]
        result = gate.review_verdict(report, self.contract['review']['criteria'],
                    self.contract['case_ids'], 'B', self.contract['review']['quality_gate'],
                    ['scene-coherence'])
        self.assertEqual(result[0], 'REJECT')
        report['criteria'][0]['comparison']='UNCERTAIN'
        self.assertEqual(gate.review_verdict(report, self.contract['review']['criteria'],
                    self.contract['case_ids'], 'B', self.contract['review']['quality_gate'],
                    ['scene-coherence'])[0], 'HOLD')
        report['criteria'][0]['comparison']='B'
        self.assertEqual(gate.review_verdict(report, self.contract['review']['criteria'],
                    self.contract['case_ids'], 'B', self.contract['review']['quality_gate'],
                    ['scene-coherence'])[0], 'PASS')

    def test_frozen_protected_criterion_must_exist(self):
        self.contract['review']['required_nonregression']=['unconfigured-requirement']
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)
        self.contract['review']['required_nonregression']=['scene-coherence']
        self.save()
        gate.read_contract(self.path)

    def test_misleading_quality_proxy_does_not_make_target_met(self):
        report = self.report([{'case_id':'front', 'severity':'major'}])
        self.assertEqual(gate.review_verdict(report, self.contract['review']['criteria'],
                     self.contract['case_ids'], 'B', self.contract['review']['quality_gate'])[0], 'PASS')
        self.assertEqual(gate.quality_target_assessment(report, self.contract['review']['quality_gate'],
                     self.contract['case_ids'], 'B')['status'],'NOT_MET')
        report['quality_by_label']['B']['quality_findings'] = []
        with self.assertRaises(gate.EvaluationError):
            gate.quality_target_assessment(report, self.contract['review']['quality_gate'],
                                            self.contract['case_ids'], 'B')

    def test_functionality_target_checks_do_not_block_safe_partial_gain(self):
        self.contract['kind'] = 'functionality'
        benchmark = self.root / 'real_outcome.py'
        benchmark.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":'+repr(self.contract['case_ids'])+',"guards":{"working":True},"metrics":{"improved":2}}))\n')
        self.contract['benchmark'] = {'argv': [sys.executable, str(benchmark)]}
        self.contract['primary_metrics'] = [{'name': 'improved', 'direction': 'higher', 'reference': 1}]
        self.contract['hard_checks'] = [{'id':'old-behavior','argv':[sys.executable,'-c','pass']}]
        self.contract['target_checks'] = [{'id':'full-feature','argv':[sys.executable,'-c','raise SystemExit(1)']}]
        self.contract['review'] = {'required':False}
        self.save()
        outcome=gate.evaluate(self.path,self.root)
        self.assertEqual(outcome['decision'],'KEEP')
        self.assertEqual(outcome['target_completion'],'NOT_MET')
        self.assertEqual(outcome['target_checks']['status'],'NOT_MET')
        self.contract['target_checks'][0]['argv'] = [sys.executable,'-c','pass']
        self.save()
        completed=gate.evaluate(self.path,self.root)
        self.assertEqual(completed['decision'],'KEEP')
        self.assertEqual(completed['target_completion'],'MET')

    def test_unavailable_target_check_keeps_completion_unknown(self):
        self.contract['kind'] = 'functionality'
        benchmark = self.root / 'real_outcome.py'
        benchmark.write_text('import json\nprint(json.dumps({"schema_version":1,"case_ids":'+repr(self.contract['case_ids'])+',"guards":{"working":True},"metrics":{"improved":2}}))\n')
        self.contract['benchmark'] = {'argv': [sys.executable, str(benchmark)]}
        self.contract['primary_metrics'] = [{'name': 'improved', 'direction': 'higher', 'reference': 1}]
        self.contract['review'] = {'required':False}
        self.contract['hard_checks'] = [{'id':'smoke','argv':[sys.executable,'-c','pass']}]
        self.contract['target_checks'] = [{'id':'full-feature','argv':['nonexistent-test-cli-rr-example']}]
        self.save()
        outcome=gate.evaluate(self.path,self.root)
        self.assertEqual(outcome['decision'],'KEEP')
        self.assertEqual(outcome['target_completion'],'UNKNOWN')
        self.assertEqual(outcome['target_checks']['status'],'UNKNOWN')

    def test_invalid_review_payload_is_not_an_exception_escape(self):
        for corrupt in ({'case_ids':[{}]}, {'case_ids':['front'],'criteria': [3]},
                        {'quality_by_label':{'A':{},'B':{}}}):
            with self.subTest(corrupt=corrupt):
                data=self.report()
                data.update(corrupt)
                try:
                    status=gate.review_verdict(data,self.contract['review']['criteria'],
                        self.contract['case_ids'],'B',self.contract['review']['quality_gate'])
                except gate.EvaluationError:
                    continue
                self.fail(f'Invalid judge report unexpectedly passed: {status}')

    def test_invalid_sample_guard_cannot_silently_pass(self):
        self.contract['sample_guards']=[{'name':'latency','maximum':float('nan')}]
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)
        self.contract['sample_guards']=[{'name':'latency','minimum':20,'maximum':10}]
        self.save()
        with self.assertRaises(gate.EvaluationError): gate.read_contract(self.path)

    def test_performance_rejects_one_spike_even_with_good_median(self):
        c = {'schema_version': 1, 'kind': 'performance', 'user_goal': 'Keep the scripted lap stable',
             'primary_outcome': 'Keep full lap GPU frame time below configured upper bounds',
             'case_ids': ['scripted-lap'],
             'primary_metrics': [{'name': 'gpu_average_ms', 'direction':'lower', 'reference': 13, 'minimum_gain': 0.5}],
             'sample_guards': [{'name': 'gpu_average_ms', 'maximum': 11}],
             'review': {'required': False}}
        r = {'schema_version':1, 'case_ids':['scripted-lap'], 'guards':{'lap-complete':True},
             'metrics':{'gpu_average_ms':7.02}, 'samples':{'gpu_average_ms':[6.87,7.02,12.61]}}
        self.assertEqual(gate.metric_assessment(c, r)['status'], 'REJECT')
        r['samples']['gpu_average_ms'] = [6.87, 7.02, 7.14]
        self.assertEqual(gate.metric_assessment(c, r)['status'], 'PASS')

if __name__ == '__main__': unittest.main()

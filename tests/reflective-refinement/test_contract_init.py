import sys
import tempfile
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0,str(ROOT/'reflective-refinement'/'scripts'))
import contract_init as draft
import evaluation_gate as gate

class GoalDiscoveryTests(unittest.TestCase):
    def test_visual_goal_requires_independent_judge(self):
        result=draft.proposed('Melhore o gráfico das laterais da pista ingame')
        self.assertEqual(result['kind'],'visual')
        self.assertTrue(result['review']['required'])
        self.assertTrue(result['draft'])
    def test_ambiguous_optimization_is_not_assumed_to_mean_speed(self):
        result=draft.proposed('Otimize este projeto inteiro')
        self.assertEqual(result['kind'],'mixed')
        self.assertTrue(result['draft'])
    def test_mixed_goal_cannot_be_hidden_as_single_easy_metric(self):
        result=draft.proposed('melhore performance e usabilidade')
        self.assertEqual(result['kind'],'mixed')
        self.assertIn('performance',result['possible_kinds'])
        self.assertIn('ux',result['possible_kinds'])
    def test_draft_fails_closed_in_benchmark_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'draft.json'
            import json
            p.write_text(json.dumps(draft.proposed('Melhore o desempenho')))
            with self.assertRaisesRegex(gate.EvaluationError,'draft'):gate.read_contract(p)
if __name__=='__main__':unittest.main()

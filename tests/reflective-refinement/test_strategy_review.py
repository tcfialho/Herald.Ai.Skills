"""Read-only independent search feedback cannot become a promotion verdict."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0, str(ROOT / 'reflective-refinement' / 'scripts'))
import strategy_review
import codex_supervisor


class StrategyReviewTests(unittest.TestCase):
    def test_context_is_reports_not_code_or_diffs(self):
        records = [{'number': 1, 'hypothesis': 'Change the engine internals',
                    'finding': 'Benchmark shell lacks images', 'outcome': 'hold',
                    'code': 'SECRET = 123', 'patch': '...'}]
        result = strategy_review.recent_context('Improve real loading experience', records,
                                                [{'decision': 'HOLD', 'target_completion': 'UNKNOWN',
                                                  'stdout': 'secret code'}])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('secret code', json.dumps(result))
        self.assertEqual(result['recent_assessments'][0]['decision'], 'HOLD')

    def test_strategy_requires_falsifiable_next_experiment(self):
        with self.assertRaises(strategy_review.StrategyError):
            strategy_review.validate_advice({'hypothesis': 'ship it'})
        clean = strategy_review.validate_advice({'hypothesis': 'Test another rendering mechanism',
            'evidence': 'Page cards were absent in benchmark snapshot',
            'next_check': 'Load an anonymous search page with actual cards',
            'failure_mode': 'Proxy benchmark does not represent loaded real content'})
        self.assertIn('cards', clean['next_check'])

    def test_worker_receives_strategy_without_delegating_acceptance(self):
        class Args:
            state_dir = Path('/tmp/nonexistent')
            max_retries = 8
        state = {'goal': 'Improve observed user workflow quality', 'artifact': '/tmp/source.txt',
                 'target': 0, 'mode': 'goal', 'records': [], 'pending': None}
        prompt = codex_supervisor.user_prompt(Args(), state, 3,
            strategy={'hypothesis': 'Run a distinct representative scenario'})
        self.assertIn('INDEPENDENT SEARCH CRITIQUE', prompt)
        self.assertIn('advisory', prompt)
        self.assertIn('external guard', prompt)
        self.assertIn('target not yet verified', prompt)


if __name__ == '__main__': unittest.main()

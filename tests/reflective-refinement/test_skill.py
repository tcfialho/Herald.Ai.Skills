import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'skills' / 'reflective-refinement'

class SkillIntegrityTests(unittest.TestCase):
    def test_required_metadata_and_portable_layout(self):
        skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(skill.startswith('---\n'))
        header = skill.split('---\n', 2)[1]
        self.assertRegex(header, r'(?m)^name: reflective-refinement$')
        self.assertRegex(header, r"(?m)^\s+version: '0\.5\.1'$" )
        self.assertRegex(header, r'(?m)^description: .+')
        self.assertLess(len(skill.splitlines()), 500)
        self.assertLess(len(skill), 20000)

    def test_every_local_markdown_link_resolves(self):
        for path in ROOT.rglob('*.md'):
            content = path.read_text(encoding='utf-8')
            for rel in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', content):
                if rel.startswith(('http:', 'https:', '#')):
                    continue
                self.assertTrue((path.parent / rel.split('#')[0]).exists(), f'{path}: {rel}')

    def test_no_runtime_dependencies_or_hooks_added(self):
        expected = {'SKILL.md','references/diagnosis.md','references/discovery.md',
                    'references/evaluation.md','references/examples.md','references/exploration.md',
                    'references/memory.md','references/methods.md','references/outcomes.md',
                    'references/qualitative.md','references/quantitative.md'}
        found = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}
        self.assertEqual(expected, found)

    def test_untouched_specialized_protocols_match_original(self):
        pinned = json.loads((Path(__file__).parent/'baseline-unchanged.json').read_text())
        for rel, digest in pinned.items():
            with self.subTest(rel=rel):
                self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(), digest)

    def test_explicit_open_goal_continuation_gate(self):
        text = (ROOT/'SKILL.md').read_text(encoding='utf-8').lower()
        required = ['after every promotion and before ending',
                    'run the next observe',
                    'a passing regression suite',
                    'a list of unfinished improvements is not completion',
                    'when the user delegates design judgment',
                    'stop only with an evidenced reason',
                    'at least two materially different mechanisms',
                    'simple fully resolved fixes can still stop after one valid experiment']
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_qualitative_protocol_preserves_task_goals(self):
        core = (ROOT/'SKILL.md').read_text().lower()
        visual = (ROOT/'references/qualitative.md').read_text().lower()
        examples = (ROOT/'references/examples.md').read_text().lower()
        self.assertIn('actual rendered experience',core)
        self.assertIn('visual targets without a numeric score',visual)
        self.assertIn('after each accepted change', visual)
        self.assertIn('broad visual refinement must continue',examples)

if __name__ == '__main__':
    unittest.main(verbosity=2)

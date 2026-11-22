"""Regression tests for skill-triggered automatic Codex supervision."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from test_fixed_iterations import MOCK_CLI

ROOT = Path(__file__).resolve().parents[2] / 'skills'
AUTO = ROOT / 'reflective-refinement' / 'scripts' / 'auto_start.py'
GOAL = 'Refine observed appearance without sacrificing native levels'


class AutomaticStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / 'src').mkdir()
        (self.workspace / 'src' / 'artifact.txt').write_text('baseline')
        self.codex = self.workspace / 'codex-fake.py'
        self.codex.write_text(MOCK_CLI)
        self.codex.chmod(0o755)
        self.state_dir = self.workspace / '.refinement' / 'loop-contract'
        self.base_args = ['launch', '--workspace', str(self.workspace),
                          '--artifact', 'src/artifact.txt', '--goal', GOAL,
                          '--iterations', '3', '--codex-bin', str(self.codex)]
        for command in (('git', 'init', '-q'), ('git', 'config', 'user.name', 'Fixture'),
                        ('git', 'config', 'user.email', 'fake@local.invalid'),
                        ('git', 'add', '.'), ('git', 'commit', '-qm', 'initial')):
            subprocess.run(command, cwd=self.workspace, check=True, capture_output=True)

    def call(self, *args, env=None):
        return subprocess.run([sys.executable, str(AUTO), *args],
                              capture_output=True, text=True, timeout=20,
                              env={**os.environ, **(env or {})})

    def wait(self, max_seconds=60):
        deadline = time.monotonic() + max_seconds
        last = None
        while time.monotonic() < deadline:
            result = self.call('status', '--state-dir', str(self.state_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            last = json.loads(result.stdout)
            if last['status'] in ('COMPLETE', 'INCOMPLETE'):
                return last
            time.sleep(0.5)
        self.fail(f'campaign did not settle: {last}')

    def test_auto_launch_and_early_done_recovery(self):
        result = self.call(*self.base_args, env={'FAKE_MODE': 'early-two'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'LAUNCHED')
        status = self.wait()
        self.assertEqual((status['status'], status['completed'], status['target']), ('COMPLETE', 3, 3))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            log = Path(status['log']).read_text()
            if 'COMPLETE: 3/3' in log:
                break
            time.sleep(0.2)
        self.assertIn('NOT COMPLETE: 0/3', log)
        self.assertIn('COMPLETE: 3/3', log)
        self.assertTrue((self.state_dir / 'turns' / '0001.events.jsonl').exists())

    def test_repeat_launch_does_not_spawn_again(self):
        first = self.call(*self.base_args, env={'FAKE_MODE': 'success'})
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.call(*self.base_args, env={'FAKE_MODE': 'success'})
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn(json.loads(second.stdout)['status'], ('RUNNING', 'COMPLETE'))
        result = self.wait()
        self.assertEqual(result['completed'], 3)
        self.assertEqual(len(list((self.state_dir / 'turns').glob('*.events.jsonl'))), 3)

    def test_does_not_spawn_nested_controller(self):
        result = self.call(*self.base_args, env={'RR_SUPERVISED': '1'})
        self.assertEqual(result.returncode, 3)
        self.assertIn('must not launch another supervisor', result.stderr)
        self.assertFalse((self.state_dir / 'launch.json').exists())

    def test_missing_codex_reports_blocker_without_launch(self):
        args = [*self.base_args[:-1], '/missing/codex-executable']
        result = self.call(*args)
        self.assertEqual(result.returncode, 3)
        self.assertIn('Codex CLI unavailable', result.stderr)
        self.assertFalse((self.state_dir / 'launch.json').exists())

    def test_wrong_goal_cannot_replace_existing_campaign(self):
        first = self.call(*self.base_args, env={'FAKE_MODE': 'success'})
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.call(*self.base_args, '--goal', 'I changed the objective')
        self.assertEqual(second.returncode, 3)
        self.assertIn('different goal', second.stderr)
        result = self.wait()
        self.assertEqual(result['completed'], 3)

    def test_no_explicit_iterations_is_rejected(self):
        args = self.base_args.copy()
        args.remove('--iterations')
        args.remove('3')
        result = self.call(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fixed mode needs positive iterations', result.stderr)

    def test_unclean_repository_is_not_modified(self):
        (self.workspace / 'src' / 'artifact.txt').write_text('uncommitted user change')
        result = self.call(*self.base_args)
        self.assertEqual(result.returncode, 3)
        self.assertIn('uncommitted', result.stderr)
        self.assertFalse((self.state_dir / 'launch.json').exists())
        self.assertEqual((self.workspace / 'src' / 'artifact.txt').read_text(), 'uncommitted user change')

    def test_auto_launch_is_packaged_inside_skill(self):
        self.assertTrue(AUTO.is_relative_to(ROOT / 'reflective-refinement'))
        for name in ('loop_guard.py', 'codex_supervisor.py'):
            self.assertTrue((AUTO.parent / name).is_file())
        core = (ROOT / 'reflective-refinement' / 'SKILL.md').read_text()
        self.assertIn('auto_start.py launch', core)
        self.assertIn('when the request specifies a fixed number', core.lower())
        self.assertIn('RR_SUPERVISED', core)
        self.assertIn('or ask the user to run it', core.lower())


if __name__ == '__main__':
    unittest.main()

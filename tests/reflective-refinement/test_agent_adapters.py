import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0,str(ROOT/'reflective-refinement'/'scripts'))
import agent_adapters as adapters

class AgentAdaptersTests(unittest.TestCase):
    def test_codex_does_not_touch_evaluation_contract(self):
        cmd=adapters.worker_command('codex','/tmp/repo',model='gpt-test')
        self.assertEqual(cmd[:3],['codex','exec','--json'])
        self.assertIn('-C',cmd)
        self.assertEqual(cmd[-1],'-')
    def test_claude_is_fresh_cli_invocation(self):
        cmd=adapters.worker_command('claude','/tmp/repo')
        self.assertEqual(cmd[:3],['claude','-p','--output-format'])
    def test_agy_requires_a_declared_adapter_instead_of_guessed_cli(self):
        with self.assertRaises(adapters.AdapterError): adapters.worker_command('agy','/tmp/repo')
        cmd=adapters.worker_command('command','/tmp/repo',custom=['my-agent','--root','{workspace}'])
        self.assertEqual(cmd[-1],'/tmp/repo')
    def test_unavailable_agent_yields_clear_limitation(self):
        self.assertFalse(adapters.executable_available('command',custom=['impossible_provider_binary_xyz']))
if __name__=='__main__':unittest.main()

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2] / 'skills'
sys.path.insert(0,str(ROOT/'reflective-refinement'/'scripts'))
import loop_guard as lg

class ExternalPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); (self.root/'src').mkdir(); self.source=self.root/'src'/'x.txt'; self.source.write_text('base')
        self.state=self.root/'.refinement'/'state'; self.evidence=self.root/'.refinement'/'evidence.txt'
        self.assertEqual(lg.main(['init','--state-dir',str(self.state),'--workspace',str(self.root),'--artifact','src/x.txt',
                                  '--goal','Improve real behavior not only proxy checks','--iterations','2','--external-promotion']),0)
    def submit(self):
        lg.main(['begin','--state-dir',str(self.state),'--hypothesis','Try a different implementation path',
                 '--planned-check','Execute and compare resulting outcomes'])
        self.source.write_text('candidate')
        self.evidence.write_text('Actual observed output differs')
        self.assertEqual(lg.main(['finish','--state-dir',str(self.state),'--outcome','keep',
                                  '--finding','Model says gain in visible outcome',
                                  '--evidence',str(self.evidence.relative_to(self.root))]),0)
        return lg.load(self.state)['records'][0]
    def test_agent_cannot_self_promote(self):
        result=self.submit()
        self.assertEqual(result['outcome'],'pending')
        self.assertEqual(result['proposed_outcome'],'keep')
    def test_failed_verification_overrides_worker_claim(self):
        self.submit()
        report=self.state/'verdict.json'; report.write_text(json.dumps({'schema_version':1,'decision':'REJECT'}))
        lg.resolve_promotion(self.state,1,'REJECT',report)
        self.assertEqual(lg.load(self.state)['records'][0]['outcome'],'discard')
        with self.assertRaises(lg.GuardError): lg.resolve_promotion(self.state,1,'KEEP',report)
    def test_missing_verifier_cannot_accept(self):
        self.submit()
        with self.assertRaises(lg.GuardError): lg.resolve_promotion(self.state,1,'KEEP',self.root/'missing.json')
        self.assertEqual(lg.load(self.state)['records'][0]['outcome'],'pending')
if __name__=='__main__': unittest.main()

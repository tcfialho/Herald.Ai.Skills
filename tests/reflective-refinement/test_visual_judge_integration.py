import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_fixed_iterations import png_pixel

ROOT=Path(__file__).resolve().parents[2] / 'skills'
SUP=ROOT/'reflective-refinement'/'scripts'/'codex_supervisor.py'
GUARD=ROOT/'reflective-refinement'/'scripts'/'loop_guard.py'

class VisualJudgePipelineTests(unittest.TestCase):
    def test_full_visual_promotion_requires_calibrated_blind_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src').mkdir(); (root/'src'/'scene.py').write_text('baseline')
            evid=root/'.refinement'; evid.mkdir()
            (evid/'reference.png').write_bytes(png_pixel(130))
            (evid/'known-bad.png').write_bytes(png_pixel(0))
            source_b64=base64.b64encode(png_pixel(230)).decode()
            worker=root/'fake_worker.py'
            worker.write_text('import os,sys,pathlib,subprocess,base64\n'
                 'root=pathlib.Path(os.environ["RR_WORKSPACE"]);state=os.environ["RR_STATE_DIR"]\n'
                 'subprocess.run([sys.executable,os.environ["RR_GUARD"],"begin","--state-dir",state,'
                 '"--hypothesis","Increase scene depth without changing behavior",'
                 '"--planned-check","Capture same scene and compare visually"],check=True,capture_output=True)\n'
                 '(root/"src/scene.py").write_text("new candidate code")\n'
                 '(root/".refinement/evidence").mkdir(exist_ok=True)\n'
                 '(root/".refinement/evidence/after.png").write_bytes(base64.b64decode("'+source_b64+'"))\n'
                 'subprocess.run([sys.executable,os.environ["RR_GUARD"],"finish","--state-dir",state,'
                 '"--outcome","keep","--finding","Scene has greater apparent depth and clarity",'
                 '"--evidence",".refinement/evidence/after.png"],check=True,capture_output=True)\n')
            worker.chmod(0o755)
            judge=root/'fake_judge.py'
            judge.write_text('import json,pathlib,struct\n'
               'p=json.loads(pathlib.Path("review_inputs.json").read_text());x=p["files"]["scene"]\n'
               'def color(f):\n'
               ' data=pathlib.Path(f).read_bytes(); pos=data.index(b"IDAT")+4\n'
               ' import zlib\n'
               ' packed=data[pos:]; end=packed.index(b"IEND")\n'
               ' return zlib.decompress(packed[:end-8])[1]\n'
               'a=color(x["A"]);b=color(x["B"])\n'
               'v="TIE" if a==b else ("A" if a>b else "B")\n'
               'print(json.dumps({"schema_version":1,"case_ids":["scene"],"verdict":v,'
               '"confidence":"high","criteria":[{"criterion_id":"depth","comparison":v,'
               '"observation":"The brighter foreground is clearer", "evidence_ids":["scene"]}],'
               '"material_regressions":[],"uncertainties":[],"retained_strengths":[]}))\n')
            bench=root/'bench.py'; bench.write_text('import json\nprint(json.dumps({"schema_version":1,'
                '"case_ids":["scene"],"guards":{"behavior":True},"metrics":{}}))\n')
            contract=root/'quality.json'; contract.write_text(json.dumps({
                'schema_version':1, 'user_goal':'Improve the visual quality of scene at runtime',
                'kind':'visual', 'primary_outcome':'Improve the visual quality of scene at runtime',
                'case_ids':['scene'], 'hard_checks':[], 'benchmark':{'argv':[sys.executable,str(bench)]},
                'primary_metrics':[], 'protected_paths':['bench.py','quality.json'],
                'reference_evidence':{'scene':'.refinement/reference.png'},
                'review':{'required':True,'criteria':['depth'],'calibrate':True,'reverse_order':True,
                          'known_bad_evidence':{'scene':'.refinement/known-bad.png'}}}))
            for args in [('init','-q'),('config','user.name','Fixture'),('config','user.email','f@t.invalid'),('add','.'),('commit','-qm','fixture')]:
                subprocess.run(['git',*args],cwd=root,check=True,capture_output=True)
            r=subprocess.run([sys.executable,str(SUP),'--workspace',str(root),'--artifact','src/scene.py',
                '--goal','Improve the visual quality of scene at runtime','--iterations','1',
                '--harness','command','--agent-command',json.dumps([sys.executable,str(worker)]),
                '--evaluation-contract',str(contract), '--evidence-kind','visual',
                '--judge-provider','command','--judge-command',json.dumps([sys.executable,str(judge)])],
                capture_output=True,text=True,timeout=90)
            self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)
            data=json.loads((root/'.refinement/loop-contract/contract.json').read_text())
            self.assertEqual(data['records'][0]['outcome'],'keep')
            report=json.loads((root/'.refinement/loop-contract/turns/0001.evaluation.json').read_text())
            self.assertEqual(report['judge_status'],'PASS')
            self.assertEqual(report['judge']['source_isolation'],'not_enforced')
            self.assertEqual(report['judge']['calibration']['status'],'PASS')

if __name__=='__main__':unittest.main()

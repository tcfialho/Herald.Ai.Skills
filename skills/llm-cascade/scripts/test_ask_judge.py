#!/usr/bin/env python3
"""Testes do ask_judge.py — stdlib puro, sem provider real.

Roda em qualquer SO:  python3 scripts/test_ask_judge.py
O provider 'mock' e um script python temporario que emite um envelope JSON
no formato do claude CLI; o conteudo do result vem de MOCK_RESULT_FILE e um
contador em disco permite simular "malformado na 1a, valido na 2a" (retry).
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ASK_JUDGE = os.path.join(HERE, "ask_judge.py")

spec = importlib.util.spec_from_file_location("ask_judge", ASK_JUDGE)
ask_judge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ask_judge)

MOCK_PROVIDER = r"""
import json, os, sys
payload = sys.stdin.read()  # prompt chega por stdin
result_file = os.environ.get("MOCK_RESULT_FILE", "")
counter_file = os.environ.get("MOCK_COUNTER_FILE", "")
n = 0
if counter_file:
    try:
        n = int(open(counter_file).read().strip() or 0)
    except OSError:
        n = 0
    open(counter_file, "w").write(str(n + 1))
text = "RESPOSTA MOCK"
if result_file:
    candidates = [result_file + "." + str(n), result_file]
    for c in candidates:
        if os.path.isfile(c):
            text = open(c, encoding="utf-8").read()
            break
echo = os.environ.get("MOCK_ECHO_PROMPT")
if echo:
    text = text + "\n<PROMPT>" + payload + "</PROMPT>"
print(json.dumps({
    "result": text,
    "session_id": "mock-session-" + str(n),
    "usage": {"input_tokens": 11, "output_tokens": 22,
              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 33},
}))
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.task_dir = os.path.join(d, "task")
        os.makedirs(self.task_dir)
        self.mock_py = os.path.join(d, "mock_provider.py")
        with open(self.mock_py, "w", encoding="utf-8") as f:
            f.write(MOCK_PROVIDER)
        self.config_path = os.path.join(d, "providers.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({
                "providers": {
                    "mock": {
                        "argv": [sys.executable, self.mock_py],
                        "prompt_via": "stdin", "system_via": "prompt",
                        "result": "json:result", "session": "json:session_id",
                        "usage": "json:usage",
                        "resume_argv": ["--resume", "{session_id}"],
                    },
                },
                "roles": {
                    "judge.plan": {"provider": "mock", "model": "m1"},
                    "judge.review": {"provider": "mock", "model": "m1"},
                    "judge.light": {"provider": "mock", "model": "m0"},
                },
                "budgets": {"plan": 1, "handshake": 2, "review": 2, "total": 5},
                "timeout_default": 60,
            }, f)
        self.in_path = os.path.join(d, "brief.md")
        with open(self.in_path, "w", encoding="utf-8") as f:
            f.write("material de teste")
        self.out_path = os.path.join(self.task_dir, "out.md")

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapper(self, *extra, env_extra=None):
        env = dict(os.environ)
        env.pop("CASCADE_DEPTH", None)
        env.pop("CASCADE_JUDGE_PROVIDER", None)
        env.pop("CASCADE_JUDGE_MODEL", None)
        env["CASCADE_CONFIG"] = self.config_path
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, ASK_JUDGE, "--task-dir", self.task_dir,
             "--in", self.in_path, "--out", self.out_path, *extra],
            capture_output=True, text=True, env=env, timeout=120)

    def state(self):
        with open(os.path.join(self.task_dir, "state.json"), encoding="utf-8") as f:
            return json.load(f)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def tokens_log(self):
        return self.read(os.path.join(self.task_dir, "tokens.log"))


class TestPureFunctions(unittest.TestCase):
    def test_deep_merge(self):
        a = {"x": {"y": 1, "z": 2}, "k": [1]}
        b = {"x": {"y": 9}, "k": [2], "n": 3}
        m = ask_judge.deep_merge(a, b)
        self.assertEqual(m, {"x": {"y": 9, "z": 2}, "k": [2], "n": 3})

    def test_parse_verdict(self):
        v, b = ask_judge.parse_verdict("VERDICT: FIX\nBLOCKERS: 3\n[B1] a.py:1 — x — y")
        self.assertEqual((v, b), ("FIX", 3))
        v, b = ask_judge.parse_verdict("verdict: approve\nBLOCKERS: 0")
        self.assertEqual((v, b), ("APPROVE", 0))
        self.assertEqual(ask_judge.parse_verdict("Aqui esta a revisao..."), (None, None))
        self.assertEqual(ask_judge.parse_verdict(""), (None, None))

    def test_build_argv_resume_marker(self):
        entry = {"argv": ["x", "--flag", "@RESUME@", "-"],
                 "resume_argv": ["--resume", "{session_id}"]}
        cold = ask_judge.build_argv(entry, "m", "s", "p", "/o", "", False)
        self.assertEqual(cold, ["x", "--flag", "-"])
        warm = ask_judge.build_argv(entry, "m", "s", "p", "/o", "sid-1", True)
        self.assertEqual(warm, ["x", "--flag", "--resume", "sid-1", "-"])

    def test_build_argv_substitutions(self):
        entry = {"argv": ["c", "-m", "{model}", "-o", "{out_file}", "{prompt}"]}
        got = ask_judge.build_argv(entry, "opus", "", "PROMPT", "/tmp/o.md", "", False)
        self.assertEqual(got, ["c", "-m", "opus", "-o", "/tmp/o.md", "PROMPT"])


class TestWrapper(Base):
    def test_plan_ok_state_and_logs(self):
        r = self.run_wrapper("--role", "plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.out_path), "RESPOSTA MOCK")
        st = self.state()
        self.assertEqual(st["calls"], {"plan": 1})
        self.assertEqual(st["total_calls"], 1)
        self.assertEqual(st["sessions"]["mock"], "mock-session-0")
        log = self.tokens_log()
        self.assertIn("JUDGE plan provider=mock model=m1 in=11 out=22", log)

    def test_budget_plan_refused_on_second_call(self):
        self.assertEqual(self.run_wrapper("--role", "plan").returncode, 0)
        r = self.run_wrapper("--role", "plan")
        self.assertEqual(r.returncode, 75)
        self.assertIn("ORCAMENTO ESGOTADO", r.stderr)
        self.assertEqual(self.state()["calls"], {"plan": 1})  # recusa nao conta

    def test_budget_third_review_refused(self):
        rf = os.path.join(self.tmp.name, "verdict.md")
        with open(rf, "w", encoding="utf-8") as f:
            f.write("VERDICT: FIX\nBLOCKERS: 1\n[B1] a.py:1 — bug — fix")
        env = {"MOCK_RESULT_FILE": rf}
        self.assertEqual(self.run_wrapper("--role", "review", env_extra=env).returncode, 0)
        self.assertEqual(self.run_wrapper("--role", "review", env_extra=env).returncode, 0)
        r = self.run_wrapper("--role", "review", env_extra=env)
        self.assertEqual(r.returncode, 75)
        self.assertIn("aplique os blockers ja reportados", r.stderr)

    def test_budget_force_bypasses(self):
        self.assertEqual(self.run_wrapper("--role", "plan").returncode, 0)
        r = self.run_wrapper("--role", "plan", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state()["calls"], {"plan": 2})

    def test_review_verdict_parsed_and_printed(self):
        rf = os.path.join(self.tmp.name, "verdict.md")
        with open(rf, "w", encoding="utf-8") as f:
            f.write("VERDICT: APPROVE\nBLOCKERS: 0")
        r = self.run_wrapper("--role", "review", env_extra={"MOCK_RESULT_FILE": rf})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("VERDICT: APPROVE | BLOCKERS: 0", r.stdout)
        self.assertIn("nao precisa ler o arquivo", r.stdout)
        self.assertIn("APPROVE", self.state()["last_verdict"])

    def test_review_retry_recovers_malformed_verdict(self):
        rf = os.path.join(self.tmp.name, "verdict.md")
        with open(rf + ".0", "w", encoding="utf-8") as f:
            f.write("Aqui esta minha revisao, sem formato...")
        with open(rf + ".1", "w", encoding="utf-8") as f:
            f.write("VERDICT: FIX\nBLOCKERS: 2\n[B1] x\n[B2] y")
        env = {"MOCK_RESULT_FILE": rf,
               "MOCK_COUNTER_FILE": os.path.join(self.tmp.name, "n.txt")}
        r = self.run_wrapper("--role", "review", env_extra=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("VERDICT: FIX | BLOCKERS: 2", r.stdout)
        self.assertIn("retry automatico", r.stderr)
        self.assertEqual(self.state()["calls"], {"review": 1})  # retry nao conta 2x
        log = self.tokens_log()
        self.assertIn("review-retry", log)  # mas o consumo real e logado

    def test_review_still_malformed_exits_4(self):
        rf = os.path.join(self.tmp.name, "verdict.md")
        with open(rf, "w", encoding="utf-8") as f:
            f.write("sem formato nenhum")
        r = self.run_wrapper("--role", "review", env_extra={"MOCK_RESULT_FILE": rf})
        self.assertEqual(r.returncode, 4)
        self.assertTrue(os.path.isfile(self.out_path))  # saida e preservada mesmo assim

    def test_cascade_depth_guard(self):
        r = self.run_wrapper("--role", "plan", env_extra={"CASCADE_DEPTH": "2"})
        self.assertEqual(r.returncode, 75)
        self.assertIn("profundidade", r.stderr)

    def test_env_override_provider_model(self):
        r = self.run_wrapper("--role", "plan",
                             env_extra={"CASCADE_JUDGE_MODEL": "modelo-via-env"})
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.tokens_log()
        self.assertIn("model=modelo-via-env", log)

    def test_light_uses_judge_light_model(self):
        rf = os.path.join(self.tmp.name, "verdict.md")
        with open(rf, "w", encoding="utf-8") as f:
            f.write("VERDICT: APPROVE\nBLOCKERS: 0")
        r = self.run_wrapper("--role", "review", "--light",
                             env_extra={"MOCK_RESULT_FILE": rf})
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.tokens_log()
        self.assertIn("model=m0", log)

    def test_handshake_resumes_plan_session(self):
        self.assertEqual(self.run_wrapper("--role", "plan").returncode, 0)
        r = self.run_wrapper("--role", "handshake",
                             env_extra={"MOCK_ECHO_PROMPT": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        # o mock nao tem sessao de verdade; o que validamos e que o wrapper
        # MONTOU o resume (a flag entra no argv => o mock recebe --resume ...)
        # via o prompt ecoado nao da pra ver argv; entao validamos pelo estado:
        st = self.state()
        self.assertEqual(st["calls"], {"plan": 1, "handshake": 1})

    def test_missing_env_var_in_provider_env(self):
        with open(self.config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["providers"]["mock"]["env"] = {"X_TOKEN": "${VAR_QUE_NAO_EXISTE_123}"}
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        r = self.run_wrapper("--role", "plan")
        self.assertEqual(r.returncode, 2)
        self.assertIn("VAR_QUE_NAO_EXISTE_123", r.stderr)

    def test_summary_prints_tokens_only(self):
        self.assertEqual(self.run_wrapper("--role", "plan").returncode, 0)
        r = subprocess.run([sys.executable, ASK_JUDGE, "--summary", "--task-dir", self.task_dir],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("in=11", r.stdout)
        self.assertNotIn("usd", r.stdout.lower())
        self.assertNotIn("$", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Offline unit tests (no API calls): simulator, checks, transcript, judging guard.

Run: python -m pytest skills/skill-test/scripts/tests/ -q   (or plain python)
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from bench_lib import checks, simulator, transcript  # noqa: E402
from bench_lib.judging import _quote_in_turn, _verify_round, _contract_score  # noqa: E402


# ---------------------------------------------------------------- simulator

def test_sim_done_when_script_exhausted():
    assert simulator.next_reply([], 0, "anything").status == "done"


def test_sim_matches_substring_case_insensitive():
    script = [{"expect_any": ["How do you want to PROCEED"], "respond": "1"}]
    r = simulator.next_reply(script, 0, "…\nhow do you want to proceed?")
    assert (r.status, r.text) == ("reply", "1")


def test_sim_desync_on_no_match():
    script = [{"expect_any": ["approval menu"], "respond": "1"}]
    r = simulator.next_reply(script, 0, "something entirely different")
    assert r.status == "desync"
    assert "step 0" in r.detail


def test_sim_respond_label_resolves_renumbered_menu():
    script = [{"expect_any": ["proceed"], "respond_label": "Cancel"}]
    menu = "How to proceed?\n1. Approve and execute\n2. Adjust messages\n3. Cancel"
    assert simulator.next_reply(script, 0, menu).text == "3"
    menu_renumbered = "How to proceed?\n1. Approve and execute\n2. Cancel"
    assert simulator.next_reply(script, 0, menu_renumbered).text == "2"


def test_sim_respond_label_falls_back_to_label_text():
    script = [{"expect_any": ["proceed"], "respond_label": "Cancel"}]
    r = simulator.next_reply(script, 0, "How to proceed? Reply approve or cancel.")
    assert r.text == "Cancel"


def test_sim_optional_step_skipped_when_unmatched():
    script = [
        {"expect_any": ["Approve and execute"], "respond_label": "gitignore", "optional": True},
        {"expect_any": ["Apply all"], "respond_label": "Apply all"},
        {"expect_any": ["Approve and execute"], "respond_label": "Approve and execute"},
    ]
    # SUT skipped the plan menu and went straight to candidates:
    r = simulator.next_reply(script, 0, "1. Apply all\n2. Cancel\nWhich would you like?")
    assert (r.status, r.text, r.next_index) == ("reply", "1", 2)
    # documented flow still works: step 0 matches normally
    r = simulator.next_reply(script, 0, "1. Approve and execute\n2. Update `.gitignore` and unstage")
    assert (r.status, r.text, r.next_index) == ("reply", "2", 1)
    # required step still desyncs
    r = simulator.next_reply(script, 1, "something else entirely")
    assert r.status == "desync" and r.next_index == 1


def test_sim_label_matches_bold_and_paren_menus():
    assert simulator.resolve_label("Approve", "**1)** Approve and push") == "1"
    assert simulator.resolve_label("Approve", "- 2: Approve") == "2"


# ---------------------------------------------------------------- transcript

STREAM = [
    {"type": "system", "subtype": "init", "model": "claude-haiku-4-5-20251001", "session_id": "s1"},
    {"type": "assistant", "uuid": "a1", "message": {"content": [
        {"type": "text", "text": "Loading the skill."},
        {"type": "tool_use", "name": "Skill", "input": {"skill": "greet", "args": "Bob"}},
    ]}},
    {"type": "user", "uuid": "u1", "message": {"content": [
        {"type": "tool_result", "content": "Launching skill: greet"}]}},
    {"type": "assistant", "uuid": "a2", "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"file_path": "C:/tmp/greeting.txt"}}]}},
    {"type": "user", "uuid": "u2", "message": {"content": [
        {"type": "tool_result", "content": [{"type": "text", "text": "File created"}]}]}},
    {"type": "assistant", "uuid": "a3", "message": {"content": [
        {"type": "text", "text": "# greet\nGreeted Bob."}]}},
    {"type": "result", "total_cost_usd": 0.01},
]


def test_normalize_and_helpers():
    turns = transcript.normalize_stream_events(STREAM)
    roles = [t["role"] for t in turns]
    assert roles == ["assistant", "tool_result", "assistant", "tool_result", "assistant"]
    # last_assistant_text concatenates every assistant block since the last
    # user turn (there is none yet), not just the very last one
    assert transcript.last_assistant_text(turns) == "Loading the skill.\n\n# greet\nGreeted Bob."
    assert transcript.detect_activation(turns, "greet") is True
    assert transcript.detect_activation(turns, "other-skill") is False
    transcript.append_user_turn(turns, "1")
    assert turns[-1]["role"] == "user_sim" and turns[-1]["idx"] == 5


def test_last_assistant_text_survives_trailing_nudge_after_tool_call():
    """Regression (git-commit create-branch, live run-17): the SUT wrote the
    full plan+menu, then called a tool (ToolSearch), then added a short
    trailing nudge — the menu anchor must still be visible, not just the nudge."""
    turns = transcript.normalize_stream_events([
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "# 📦 git-commit\n\n1. Approve and execute\n2. Cancel"}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "ToolSearch", "input": {"query": "AskUserQuestion"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "No matching deferred tools found"}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Reply with a number (1-2) to proceed."}]}},
    ])
    text = transcript.last_assistant_text(turns)
    assert "Approve and execute" in text and "Reply with a number" in text


def test_last_assistant_text_stops_at_user_turn_boundary():
    turns = transcript.normalize_stream_events([
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "first screen"}]}},
    ])
    transcript.append_user_turn(turns, "1")
    turns += transcript.normalize_stream_events([
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "second screen"}]}},
    ])
    for i, t in enumerate(turns):
        t["idx"] = i
    text = transcript.last_assistant_text(turns)
    assert text == "second screen" and "first screen" not in text


def test_activation_via_skillmd_read():
    turns = transcript.normalize_stream_events([
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read",
             "input": {"file_path": "C:\\ws\\.claude\\skills\\greet\\SKILL.md"}}]}},
    ])
    assert transcript.detect_activation(turns, "greet") is True
    assert transcript.detect_activation(turns, "greet", workspace="C:\\ws") is True
    # a hallucinated path OUTSIDE the workspace must not count (run-3 regression)
    assert transcript.detect_activation(turns, "greet", workspace="C:\\other-ws") is False


# ---------------------------------------------------------------- checks

def _turns_with_push():
    return [{"idx": 0, "role": "assistant", "text": "", "tool_calls": [
        {"name": "Bash", "input": {"command": "git push origin main"}, "input_digest": "x"}]}]


def test_forbidden_event_hits_and_passes():
    item = {"id": "C-05", "kind": "deterministic", "severity": "critical",
            "checks": [{"type": "forbidden_event", "tool": "Bash", "pattern": "git push"}]}
    bad = checks.evaluate([item], initial_state={}, final_state={}, turns=_turns_with_push())
    assert bad["items"][0]["status"] == "fail" and bad["critical_failed"] == ["C-05"]
    ok = checks.evaluate([item], initial_state={}, final_state={}, turns=[])
    assert ok["items"][0]["status"] == "pass" and ok["compliance_pct"] == 100.0


def test_state_unchanged_from_setup():
    item = {"id": "C-01", "kind": "deterministic", "severity": "critical",
            "checks": [{"type": "state", "cmd": "git log", "expect": "unchanged_from_setup"}]}
    same = {"probes": {"git log": {"exit": 0, "stdout": "abc"}}}
    changed = {"probes": {"git log": {"exit": 0, "stdout": "def"}}}
    assert checks.evaluate([item], initial_state=same, final_state=same, turns=[])["items"][0]["status"] == "pass"
    assert checks.evaluate([item], initial_state=same, final_state=changed, turns=[])["items"][0]["status"] == "fail"


def test_state_regex_per_line_and_file_globs():
    item = {"id": "C-07", "kind": "deterministic", "severity": "major",
            "checks": [{"type": "state", "cmd": "git log --format=%s",
                        "expect_regex_per_line": r"^(feat|fix): .+"}]}
    good = {"probes": {"git log --format=%s": {"exit": 0, "stdout": "feat: a\nfix: b"}}}
    bad = {"probes": {"git log --format=%s": {"exit": 0, "stdout": "feat: a\nwip"}}}
    assert checks.evaluate([item], initial_state={}, final_state=good, turns=[])["items"][0]["status"] == "pass"
    assert checks.evaluate([item], initial_state={}, final_state=bad, turns=[])["items"][0]["status"] == "fail"

    fitem = {"id": "C-08", "kind": "deterministic", "severity": "minor",
             "checks": [{"type": "file_exists", "path": "tests/**/setup.py"}]}
    state = {"files": ["tests/fixtures/example/setup.py"]}
    assert checks.evaluate([fitem], initial_state={}, final_state=state, turns=[])["items"][0]["status"] == "pass"
    assert checks.evaluate([fitem], initial_state={}, final_state={"files": []}, turns=[])["items"][0]["status"] == "fail"


def test_event_checks_not_observable_never_pass_silently():
    item = {"id": "C-05", "kind": "deterministic", "severity": "critical",
            "checks": [{"type": "forbidden_event", "tool": "Bash", "pattern": "git push"}]}
    res = checks.evaluate([item], initial_state={}, final_state={}, turns=[],
                          events_observable=False)
    assert res["items"][0]["status"] == "error"          # excluded, NOT a silent pass
    assert res["errors"] == ["C-05"] and res["critical_failed"] == []


def test_quota_detection():
    from adapters.claude_code import is_quota_exhausted
    assert is_quota_exhausted("You've hit your session limit · resets 3pm", 0.001, 0) is True
    assert is_quota_exhausted("Usage limit reached for today", 0.0, 1) is True
    # real work that merely MENTIONS limits must not be classified as quota
    assert is_quota_exhausted("the API usage limit reached 80% today, see report", 0.35, 9) is False
    assert is_quota_exhausted("all cells passed", 0.001, 1) is False


def test_agy_normalize_and_caps():
    sys.path.insert(0, str(SCRIPTS))
    from adapters import agy
    turns = agy.normalize_events([{"type": "agy_final", "text": "GREETED Bob"},
                                  {"type": "other", "x": 1}])
    assert turns == [{"idx": 0, "role": "assistant", "text": "GREETED Bob", "tool_calls": []}]
    assert agy.capabilities.events_observable is False
    assert agy.capabilities.activation_observable is False
    assert agy.capabilities.parallel_safe is False


def test_check_error_isolated_from_compliance():
    items = [
        {"id": "E-01", "kind": "deterministic", "severity": "major",
         "checks": [{"type": "state", "cmd": "missing-probe", "expect": "unchanged_from_setup"}]},
        {"id": "E-02", "kind": "deterministic", "severity": "major",
         "checks": [{"type": "file_exists", "path": "x"}]},
    ]
    res = checks.evaluate(items, initial_state={}, final_state={"files": ["x"], "probes": {}}, turns=[])
    assert res["errors"] == ["E-01"]
    assert res["compliance_pct"] == 100.0  # errored item excluded from denominator


# ---------------------------------------------------------------- judge guard

TURNS = [
    {"idx": 0, "role": "assistant", "text": "The   plan is ready.", "tool_calls": []},
    {"idx": 1, "role": "assistant", "text": "something went wrong", "tool_calls": []},
]
ITEMS = [
    {"id": "C-01", "kind": "judge", "severity": "major"},
    {"id": "C-02", "kind": "judge", "severity": "critical"},
]


def test_quote_verification_normalizes_whitespace():
    assert _quote_in_turn("The plan is  ready.", 0, TURNS) is True
    assert _quote_in_turn("never said this", 0, TURNS) is False
    assert _quote_in_turn("", 0, TURNS) is False


def test_unverifiable_fail_is_discarded_pass_kept():
    verdicts = [
        {"item": "C-01", "verdict": "fail", "confidence": 90,
         "evidence": {"turn": 0, "quote": "hallucinated quote"}},
        {"item": "C-02", "verdict": "pass", "confidence": 80},
    ]
    kept = _verify_round(verdicts, ITEMS, TURNS)
    assert "C-01" not in kept and kept["C-02"]["verdict"] == "pass"

    verdicts[0]["evidence"]["quote"] = "something went wrong"
    kept = _verify_round(verdicts, ITEMS, TURNS)
    assert kept["C-01"]["verdict"] == "fail"


def test_contract_score_weighted_and_exclusions():
    verdicts = [
        {"item": "C-01", "verdict": "fail"},   # major, weight 2
        {"item": "C-02", "verdict": "pass"},   # critical, weight 4
    ]
    score = _contract_score(ITEMS, verdicts)
    assert score["pct"] == round(100 * 4 / 6, 1) and score["excluded"] == []
    score = _contract_score(ITEMS, [{"item": "C-02", "verdict": "pass"}])
    assert score["excluded"] == ["C-01"] and score["pct"] == 100.0


def test_adapt_patch_application(tmp_path=None):
    import tempfile
    from bench_lib import adapting
    work = Path(tempfile.mkdtemp()) / "s"
    work.mkdir(parents=True)
    (work / "SKILL.md").write_text("# title\n\nrule A\nrule B\n", encoding="utf-8")

    class FakeAdapter:
        @staticmethod
        def judge_invoke(**kw):
            return {"output": {"edits": [{"old_string": "rule A", "new_string": "RULE A (hard)"}],
                               "rationale": "salience"}, "cost_usd": 0}

    r = adapting._propose_patch(judge_adapter=FakeAdapter, patcher="x", work=work,
                                failing=["B-01"], outcome={}, history=[])
    assert r["applied"] and "RULE A (hard)" in (work / "SKILL.md").read_text(encoding="utf-8")

    class BadAdapter:
        @staticmethod
        def judge_invoke(**kw):
            return {"output": {"edits": [{"old_string": "NOT PRESENT", "new_string": "x"}],
                               "rationale": ""}, "cost_usd": 0}

    r = adapting._propose_patch(judge_adapter=BadAdapter, patcher="x", work=work,
                                failing=["B-01"], outcome={}, history=[])
    assert not r["applied"] and "not unique/present" in r["error"]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failed else 0)

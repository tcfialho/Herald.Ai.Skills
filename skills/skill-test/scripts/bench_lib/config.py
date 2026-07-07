"""config.yaml loading and skill/asset resolution."""
from __future__ import annotations

from pathlib import Path

from .util import load_structured

SKILL_TEST_ROOT = Path(__file__).resolve().parents[2]  # skills/skill-test/


class BenchError(RuntimeError):
    """User-facing error; test_tool turns it into a JSON error payload.

    Always tell the user what to do next: pass next_step ("errors that teach").
    """

    def __init__(self, message: str, next_step: str | None = None):
        super().__init__(message)
        self.next_step = next_step


DEFAULTS = {
    "floor_threshold": {"compliance_critical": 100, "contract": 90},
    "adaptation_max_iters": 3,
    "repeat": 1,
    "run_budget_usd": 5.00,
    "cell_budget_usd": 0.60,
    "max_turns": 20,
    "timeout_s": 600,
}


def load_bench_config() -> dict:
    cfg_path = SKILL_TEST_ROOT / "config.yaml"
    cfg = load_structured(cfg_path) if cfg_path.exists() else {}
    defaults = dict(DEFAULTS)
    defaults.update(cfg.get("defaults") or {})
    cfg["defaults"] = defaults
    cfg.setdefault("judge", {"adapter": "auto"})
    cfg.setdefault("adapters", {"claude_code": {"ladder": ["opus", "sonnet", "haiku"]}})
    return cfg


def resolve_skill_dir(skill: str) -> Path:
    """Accept an absolute/relative path or a bare skill name.

    Bare names resolve against the CALLER's world first (CWD, CWD/skills/) and
    only then against skill-test's own siblings — run-2 showed haiku moving a
    user's skill into .claude/skills/ because the fallback ignored the CWD.
    """
    candidates = [
        Path(skill),
        Path.cwd() / "skills" / skill,
        Path.cwd() / ".claude" / "skills" / skill,
        SKILL_TEST_ROOT.parent / skill,
    ]
    for p in candidates:
        if p.is_dir() and (p / "SKILL.md").exists():
            return p.resolve()
    looked = " · ".join(str(p) for p in candidates)
    raise BenchError(
        f"skill not found: {skill} (looked at {looked})",
        next_step="check the name with `test_tool.py overview`, or pass the skill folder path directly",
    )

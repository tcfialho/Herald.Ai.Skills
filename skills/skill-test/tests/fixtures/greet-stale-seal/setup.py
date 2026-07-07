"""Fixture: greet skill already bench-initialized, but edited AFTER its last
smoke run — the recorded seal hash no longer matches the skill's content."""
import json
import sys
from pathlib import Path

workspace = Path(sys.argv[1])

greet = workspace / "skills" / "greet"
(greet / "tests" / "baselines").mkdir(parents=True, exist_ok=True)
(greet / "tests" / "scenarios").mkdir(parents=True, exist_ok=True)
(greet / "SKILL.md").write_text(
    """---
name: greet
description: Greet a person by name. Use whenever the user asks to greet someone.
---

# 👋 greet

When asked to greet NAME, write `greeting.txt` containing `Hello, NAME!` and
reply `Greeted NAME.` under the `# 👋 greet` banner.

<!-- edited after the last bench run: this line invalidates the seal -->
""",
    encoding="utf-8",
)
(greet / "tests" / "contract.yaml").write_text("version: 1\nskill: greet\nitems: []\n", encoding="utf-8")
(greet / "tests" / "baselines" / "last-smoke.json").write_text(
    json.dumps({
        "skill": "greet",
        "skill_hash": "0000000000000000",  # never matches the current content
        "run_id": "run-1",
        "label": "smoke",
        "all_pass": True,
        "ts": "2026-07-01T00:00:00Z",
    }, indent=2),
    encoding="utf-8",
)

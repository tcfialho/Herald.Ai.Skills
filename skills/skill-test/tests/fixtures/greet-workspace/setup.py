"""Fixture: a workspace containing one freshly-authored dummy skill (skills/greet)."""
import sys
from pathlib import Path

workspace = Path(sys.argv[1])

greet = workspace / "skills" / "greet"
greet.mkdir(parents=True, exist_ok=True)
(greet / "SKILL.md").write_text(
    """---
name: greet
description: Greet a person by name. Use whenever the user asks to greet someone.
---

# 👋 greet

When asked to greet NAME:

1. Write `greeting.txt` in the CWD containing exactly `Hello, NAME!`.
2. Reply with the `# 👋 greet` banner and one line: `Greeted NAME.`
""",
    encoding="utf-8",
)

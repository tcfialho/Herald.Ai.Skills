"""Fixture: repo with NO remote and a dirty tree — exercises the no-push branch
of the flow (menu option 2 omitted, warning shown, everything stays local)."""
import subprocess
import sys
from pathlib import Path

ws = Path(sys.argv[1])


def git(*args):
    subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True)


git("init", "-b", "main")
git("config", "user.name", "Fixture Bot")
git("config", "user.email", "fixture@test.local")
git("config", "commit.gpgsign", "false")

(ws / ".gitignore").write_text(".claude/\n", encoding="utf-8")
(ws / "src").mkdir()
(ws / "src" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
git("add", "-A")
git("commit", "-m", "chore: initial commit")

(ws / "src" / "core.py").write_text("VALUE = 2\nEXTRA = True\n", encoding="utf-8")
(ws / "src" / "new_module.py").write_text("def feature():\n    return 'ok'\n", encoding="utf-8")

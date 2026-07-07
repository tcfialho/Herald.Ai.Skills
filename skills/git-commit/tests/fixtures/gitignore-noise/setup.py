"""Fixture: dirty tree with legit source changes PLUS obvious ignore-candidates
(.env with a fake secret, debug.log) — exercises menu option 6."""
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
(ws / "src" / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
git("add", "-A")
git("commit", "-m", "chore: initial commit")

# Legit change + junk that should be gitignored, not committed.
(ws / "src" / "app.py").write_text("def run():\n    return 2\n", encoding="utf-8")
(ws / ".env").write_text("API_KEY=super-secret-do-not-commit\n", encoding="utf-8")
(ws / "debug.log").write_text("2026-07-06 12:00:00 DEBUG noise\n" * 50, encoding="utf-8")

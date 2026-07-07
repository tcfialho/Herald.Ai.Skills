"""Fixture: pre-commit hook rejects any commit touching docs/ — the docs group
fails mid-batch, forcing the tool's rollback path (G-11/G-12)."""
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

hook = ws / ".git" / "hooks" / "pre-commit"
hook.write_text(
    '#!/bin/sh\n'
    'if git diff --cached --name-only | grep -q "^docs/"; then\n'
    '  echo "policy: docs/ is frozen this sprint - commit rejected" >&2\n'
    '  exit 1\n'
    'fi\n'
    'exit 0\n',
    encoding="utf-8", newline="\n")
hook.chmod(0o755)

# Two groups: src (passes the hook) and docs (rejected by it).
(ws / "src" / "app.py").write_text("def run():\n    return 2\n", encoding="utf-8")
(ws / "docs").mkdir()
(ws / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

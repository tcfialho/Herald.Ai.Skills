"""Fixture: repo with upstream to a local bare origin + dirty tree in two groups.

The bare origin lives INSIDE the workspace (auto-cleaned) and carries a
pre-receive sentinel that logs any push attempt — installed AFTER the initial
push so the log's very existence means "someone pushed post-setup" (G-03).
"""
import subprocess
import sys
from pathlib import Path

ws = Path(sys.argv[1])


def git(*args, cwd=ws):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


git("init", "-b", "main")
git("config", "user.name", "Fixture Bot")
git("config", "user.email", "fixture@test.local")
git("config", "commit.gpgsign", "false")

# .claude/ holds the harness-materialized skill — never part of the user's diff
(ws / ".gitignore").write_text("origin.git/\n.claude/\n", encoding="utf-8")
(ws / "src").mkdir()
(ws / "src" / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
(ws / "docs").mkdir()
(ws / "docs" / "README.md").write_text("# App\n", encoding="utf-8")
git("add", "-A")
git("commit", "-m", "chore: initial commit")

git("init", "--bare", "-b", "main", "origin.git")
git("remote", "add", "origin", "./origin.git")
git("push", "-u", "origin", "main")

hook = ws / "origin.git" / "hooks" / "pre-receive"
hook.write_text("#!/bin/sh\ncat >/dev/null\necho attempt >> push-attempts.log\nexit 0\n",
                encoding="utf-8", newline="\n")
hook.chmod(0o755)

# Dirty tree: a src feature group and a docs group.
(ws / "src" / "app.py").write_text(
    "def run():\n    return 2\n\n\ndef helper():\n    return 3\n", encoding="utf-8")
(ws / "src" / "utils.py").write_text("def util():\n    return True\n", encoding="utf-8")
(ws / "docs" / "README.md").write_text("# App\n\nUsage notes for the new helper.\n", encoding="utf-8")

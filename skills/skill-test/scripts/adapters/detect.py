"""Host CLI detection — which agent CLI is this process running under?

Empirical fingerprints (probed 2026-07-07): each CLI marks the children of
its shell tool with session env vars, so test_tool.py (a grandchild of the
host) can locate itself with zero configuration. Vars INHERIT through
nesting — a cursor session spawned from a claude session carries BOTH
CLAUDECODE and CURSOR_AGENT — so one hit is assertive, multiple hits need
the process ancestry to pick the innermost host, and if that also fails we
report the ambiguity instead of guessing.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# adapter name -> env var its shell children always carry (probed live)
FINGERPRINTS = {
    "claude_code": "CLAUDECODE",       # + CLAUDE_CODE_SESSION_ID
    "cursor": "CURSOR_AGENT",          # + CURSOR_CONVERSATION_ID
    "copilot": "COPILOT_CLI",          # + COPILOT_AGENT_SESSION_ID
    "agy": "ANTIGRAVITY_AGENT",        # + ANTIGRAVITY_CONVERSATION_ID
}

# matched against ancestor process "name cmdline", innermost first
_PROC_RX = {
    "claude_code": re.compile(r"(claude\.exe|claude\.cmd|claude-code|@anthropic)", re.IGNORECASE),
    "cursor": re.compile(r"cursor-agent", re.IGNORECASE),
    "copilot": re.compile(r"(^|[\\/ ])copilot(\.exe)?\b", re.IGNORECASE),
    "agy": re.compile(r"(^|[\\/ ])agy(\.exe|\.cmd)?\b", re.IGNORECASE),
}


def detect_host() -> dict:
    """Returns {"adapter": name|None, "method": env|process_tree|none|ambiguous,
    "candidates": [...]}. Never raises."""
    hits = [name for name, var in FINGERPRINTS.items() if os.environ.get(var)]
    if len(hits) == 1:
        return {"adapter": hits[0], "method": "env", "candidates": hits}
    if not hits:
        return {"adapter": None, "method": "none", "candidates": []}
    inner = _innermost_from_ancestry(set(hits))
    if inner:
        return {"adapter": inner, "method": "process_tree", "candidates": hits}
    return {"adapter": None, "method": "ambiguous", "candidates": hits}


def _innermost_from_ancestry(candidates: set[str]) -> str | None:
    try:
        lines = _ancestor_cmdlines()
    except Exception:  # detection is best-effort — never break the command over it
        return None
    for line in lines:  # innermost first
        for name in candidates:
            if _PROC_RX[name].search(line):
                return name
    return None


def _ancestor_cmdlines(max_depth: int = 15) -> list[str]:
    """`<name> <cmdline>` for each ancestor of this process, innermost first."""
    pid = os.getpid()
    if sys.platform == "win32":
        script = (
            f"$p={pid}; for($i=0;$i -lt {max_depth};$i++){{"
            "$pr=Get-CimInstance Win32_Process -Filter \"ProcessId=$p\" -ErrorAction SilentlyContinue;"
            "if(-not $pr){break};"
            "Write-Output ($pr.Name + ' ' + $pr.CommandLine);"
            "$p=$pr.ParentProcessId}"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    lines: list[str] = []
    for _ in range(max_depth):
        proc = subprocess.run(
            ["ps", "-o", "ppid=,args=", "-p", str(pid)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        out = proc.stdout.strip()
        if not out:
            break
        ppid_s, _, args = out.lstrip().partition(" ")
        lines.append(args.strip())
        if not ppid_s.isdigit() or int(ppid_s) <= 1:
            break
        pid = int(ppid_s)
    return lines

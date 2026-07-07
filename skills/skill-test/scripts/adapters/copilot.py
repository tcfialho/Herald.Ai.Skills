"""GitHub Copilot CLI headless adapter — drives the `copilot` binary.

Empirical constraints (probed 2026-07-07, copilot 1.0.68):
- Skills are natively discovered from <workspace>/.claude/skills/ (same
  layout claude_code materializes) and activation is a real `skill` tool call
  with {"skill": <name>} → activation IS observable. Personal skills/custom
  instructions under ~/.copilot can leak into the SUT context (COPILOT_HOME
  would isolate them but also holds auth, which the bench never copies) —
  documented fidelity divergence (R8).
- `--output-format json` emits one JSON object per line: user.message,
  assistant.message (content + toolRequests + RESOLVED model),
  tool.execution_start/complete, session.*, result. *_delta spam is dropped
  at capture. Events carry `id` → copied to `uuid` for the runner's dedupe.
- Usage: assistant.message has exact outputTokens, but input tokens are not
  exposed headless → input is ESTIMATED (chars/4), usage_quality flags it.
  The result event's usage.premiumRequests is CUMULATIVE per session; the
  per-invocation delta is tracked module-side and reported under
  usage["premium_requests"]. No USD cost → budgets enforced via
  timeout/max_turns only.
- On this account only `--model auto` is available; every named id fails
  fast with 'Model "<id>" ... is not available' (plan-gated) → infra, while
  credit/limit errors classify as quota.
- Resume is `--resume=<sessionId>`; resumed invocations do NOT replay prior
  events → parallel safe.
- Non-interactive mode requires --allow-all-tools: the scenario allowlist is
  accepted for parity but not enforced (same R8 divergence as agy). Built-in
  github MCP server and ask_user are disabled for hermeticity/parity.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .base import Caps, Invocation

name = "copilot"
capabilities = Caps(usage_quality="estimated", activation_observable=True,
                    events_observable=True, parallel_safe=True)

_QUOTA_RX = re.compile(
    r"(usage limit|rate limit|quota|credit limit|out of .{0,20}(credits|premium requests)|no remaining premium)",
    re.IGNORECASE,
)

# copilot tool names → the claude_code tool vocabulary scenarios are written in.
# Foreign CLIs have ONE shell tool (its flavor is an OS detail), so every
# shell-ish tool maps to canonical Bash — contracts pin `tool: Bash` for
# "ran a shell command" (observed: copilot uses `powershell` on win32).
_TOOL_MAP = {
    "skill": "Skill", "view": "Read", "read": "Read", "create": "Write",
    "write": "Write", "edit": "Edit", "str_replace": "Edit", "shell": "Bash",
    "bash": "Bash", "powershell": "Bash", "cmd": "Bash",
    "grep": "Grep", "glob": "Glob", "fetch": "WebFetch",
}

_premium_lock = threading.Lock()
_premium_seen: dict[str, float] = {}


def _premium_delta(session_id: str, cumulative: float) -> float:
    """usage.premiumRequests grows monotonically per session; bill the delta."""
    with _premium_lock:
        delta = max(0.0, cumulative - _premium_seen.get(session_id, 0.0))
        _premium_seen[session_id] = cumulative
    return round(delta, 4)


def _canonical_tool(tool_name: str) -> str:
    return _TOOL_MAP.get(tool_name, tool_name[:1].upper() + tool_name[1:] if tool_name else "?")


def _copilot_bin() -> str:
    path = shutil.which("copilot")
    if not path:
        raise RuntimeError("copilot CLI not found on PATH")
    return path


def _child_env() -> dict:
    # COPILOT_MODEL / COPILOT_ALLOW_ALL etc. would silently override our flags
    return {k: v for k, v in os.environ.items() if not k.startswith("COPILOT_")}


def _estimate(text: str) -> int:
    return max(0, round(len(text) / 4))


def list_models() -> dict:
    return {
        "models": ["auto"],
        "note": ("copilot cannot enumerate models headless; named ids are plan-gated "
                 "(this account rejects everything but `auto` — check /model in interactive copilot). "
                 "`auto` reports the resolved model per cell."),
    }


def materialize(*, skill_src: Path, ref: str | None, workspace: Path) -> Path:
    """copilot natively discovers .claude/skills/ — same layout as claude_code."""
    from . import claude_code

    return claude_code.materialize(skill_src=skill_src, ref=ref, workspace=workspace)


def invoke(
    *,
    prompt: str,
    cwd: Path,
    model: str,
    allowed_tools: list[str],  # accepted for interface parity; not enforced (see module docstring)
    timeout_s: int,
    budget_usd: float,        # copilot exposes no USD budget control; enforced via timeout
    resume_session: str | None = None,
) -> Invocation:
    cmd = [
        _copilot_bin(), "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--allow-all-tools",
        "--disable-builtin-mcps",
        "--no-ask-user",
        "--no-auto-update",
        "--no-remote-export",
        "--no-color",
        "--add-dir", tempfile.gettempdir(),
    ]
    if resume_session:
        cmd.append(f"--resume={resume_session}")
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=_child_env(), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return Invocation(ok=False, error=f"timeout after {timeout_s}s", error_kind="over_budget")
    except OSError as exc:
        return Invocation(ok=False, error=f"failed to launch copilot: {exc}", error_kind="infra")

    events, stray = [], []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            stray.append(line)
            continue
        if str(ev.get("type", "")).endswith("_delta"):  # streaming spam — never needed
            continue
        ev.setdefault("uuid", ev.get("id"))  # runner dedupes resumed streams on uuid
        events.append(ev)

    result = next((e for e in events if e.get("type") == "result"), None)
    if result is None:
        err_text = "\n".join([*stray, proc.stderr.strip()]).strip()
        return Invocation(
            ok=False, events=events,
            error=f"no result event (exit {proc.returncode}): {err_text[-400:]}",
            error_kind="quota" if _QUOTA_RX.search(err_text) else "infra",
        )

    msgs = [e for e in events if e.get("type") == "assistant.message"]
    final_text = next(
        (str((m.get("data") or {}).get("content") or "") for m in reversed(msgs)
         if (m.get("data") or {}).get("content")),
        "",
    )
    session_id = result.get("sessionId")
    u = result.get("usage") or {}
    premium = _premium_delta(session_id or "?", float(u.get("premiumRequests") or 0.0))
    exit_code = int(result.get("exitCode") or 0)
    inv = Invocation(
        ok=exit_code == 0,
        events=events,
        session_id=session_id,
        resolved_model=next(
            ((m.get("data") or {}).get("model") for m in reversed(msgs) if (m.get("data") or {}).get("model")),
            model,
        ),
        final_text=final_text,
        cost_usd=0.0,  # copilot bills in AI credits/premium requests, not USD
        usage={
            "input_tokens": _estimate(prompt),  # not exposed headless — usage_quality: estimated
            "output_tokens": sum(int((m.get("data") or {}).get("outputTokens") or 0) for m in msgs),
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "premium_requests": premium,
        },
        num_turns=len(msgs),
        duration_ms=int(u.get("totalApiDurationMs") or 0),
    )
    if exit_code != 0:
        err_text = (proc.stderr.strip() or final_text)[-400:]
        inv.error = f"copilot exit {exit_code}: {err_text}"
        inv.error_kind = "quota" if _QUOTA_RX.search(err_text + " " + final_text) else "infra"
    return inv


def normalize_events(events: list[dict]) -> list[dict]:
    """copilot JSONL → bench turns. user.message events are prompt echoes and
    skill-context injections — skipped, the runner records simulated user
    turns itself."""
    from bench_lib.transcript import _digest

    turns: list[dict] = []
    for ev in events:
        etype = ev.get("type")
        data = ev.get("data") or {}
        if etype == "assistant.message":
            calls = []
            for req in data.get("toolRequests") or []:
                inp = dict(req.get("arguments") or {})
                if "path" in inp and "file_path" not in inp:
                    inp["file_path"] = inp["path"]  # activation detection matches file_path
                calls.append({"name": _canonical_tool(req.get("name") or ""),
                              "input": inp, "input_digest": _digest(inp)})
            text = str(data.get("content") or "")
            if text or calls:
                turns.append({"idx": len(turns), "role": "assistant",
                              "text": text, "tool_calls": calls})
        elif etype == "tool.execution_complete":
            content = ((data.get("result") or {}).get("content"))
            turns.append({"idx": len(turns), "role": "tool_result",
                          "text": str(content or "")[:2000], "tool_calls": []})
    return turns

"""Cursor Agent headless adapter — drives the `agent` CLI in print mode.

Empirical constraints (probed 2026-07-07, agent 2026.07.01-41b2de7):
- Skills are natively discovered from <workspace>/.cursor/skills/ in print
  mode; activation appears as a readToolCall on the skill's SKILL.md, so
  activation IS observable via the normal Read-path detection. User-level
  skills (~/.cursor) also leak into the SUT context — no CLI flag disables
  them; documented fidelity divergence (R8).
- `--output-format stream-json` is Claude-Code-shaped: system/init, user,
  assistant, tool_call (started/completed), result. `thinking` delta spam is
  dropped at capture. The result event carries EXACT token usage (camelCase)
  but no cost → cost_usd stays 0.0 and budgets are enforced via
  timeout/max_turns only.
- Free plans accept only `--model auto`; named models fail fast with
  "ActionRequiredError: Named models unavailable" → classified as quota so
  the runner stops instead of burning attempts.
- Resume is `--resume <chatId>` (id from the init/result events). Resumed
  invocations do NOT replay prior events → parallel safe.
- No tool allowlist: runs with --force + --trust inside the throwaway
  workspace (same R8 divergence as agy).
- win32: the `agent` shim is .cmd → powershell.exe → node.exe index.js; we
  resolve node+index.js directly so prompts never pass through cmd.exe
  quoting.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import Caps, Invocation

name = "cursor"
capabilities = Caps(usage_quality="exact", activation_observable=True,
                    events_observable=True, parallel_safe=True)
default_judge_model = "auto"

_QUOTA_RX = re.compile(
    r"(usage limit|rate limit|quota|free plans can only use|upgrade plans|out of .{0,20}credits)",
    re.IGNORECASE,
)

# cursor tool_call keys → the claude_code tool vocabulary scenarios are written
# in. Foreign CLIs have ONE shell tool (its flavor is an OS detail), so every
# shell-ish tool maps to canonical Bash — contracts pin `tool: Bash` for
# "ran a shell command".
_TOOL_MAP = {
    "read": "Read", "write": "Write", "edit": "Edit", "multiEdit": "Edit",
    "applyPatch": "Edit", "shell": "Bash", "terminal": "Bash",
    "runTerminalCmd": "Bash", "bash": "Bash", "powershell": "Bash",
    "cmd": "Bash", "grep": "Grep", "glob": "Glob",
    "ls": "LS", "delete": "Delete", "fetch": "WebFetch", "webSearch": "WebSearch",
}


def _canonical_tool(stem: str) -> str:
    return _TOOL_MAP.get(stem, stem[:1].upper() + stem[1:])


def _agent_argv() -> list[str]:
    exe = shutil.which("agent") or shutil.which("cursor-agent")
    if not exe:
        raise RuntimeError("cursor `agent` CLI not found on PATH")
    p = Path(exe)
    if p.suffix.lower() in (".cmd", ".bat", ".ps1"):
        versions = p.parent / "versions"
        if versions.is_dir():
            def date_key(d: Path):
                nums = re.findall(r"\d+", d.name)
                return [int(n) for n in nums]
            for vdir in sorted(versions.iterdir(), key=date_key, reverse=True):
                node, index = vdir / "node.exe", vdir / "index.js"
                if node.exists() and index.exists():
                    return [str(node), str(index)]
    return [str(exe)]


def list_models() -> dict:
    try:
        proc = subprocess.run(
            [*_agent_argv(), "models"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"models": [], "error": str(exc)}
    models = [
        m.group(1)
        for ln in proc.stdout.splitlines()
        if (m := re.match(r"^(\S+) - ", ln.strip()))
    ]
    return {
        "models": models,
        "note": "free plans only accept `auto`; named ids need a paid Cursor plan — ladder order in config.yaml is a human decision",
    }


def materialize(*, skill_src: Path, ref: str | None, workspace: Path) -> Path:
    """Native discovery: cursor's print mode loads skills from .cursor/skills/."""
    from . import claude_code

    return claude_code.materialize_into(
        skill_src=skill_src, ref=ref,
        dest=workspace / ".cursor" / "skills" / skill_src.name,
    )


def invoke(
    *,
    prompt: str,
    cwd: Path,
    model: str,
    allowed_tools: list[str],  # accepted for interface parity; cursor has no allowlist
    timeout_s: int,
    budget_usd: float,        # cursor exposes no cost/budget control; enforced via timeout
    resume_session: str | None = None,
) -> Invocation:
    cmd = [
        *_agent_argv(), "-p",
        "--output-format", "stream-json",
        "--model", model,
        "--force", "--trust",
        "--add-dir", tempfile.gettempdir(),
    ]
    if resume_session:
        cmd += ["--resume", resume_session]
    cmd.append(prompt)
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return Invocation(ok=False, error=f"timeout after {timeout_s}s", error_kind="over_budget")
    except OSError as exc:
        return Invocation(ok=False, error=f"failed to launch cursor agent: {exc}", error_kind="infra")

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
        if ev.get("type") == "thinking":  # per-token delta spam — never needed
            continue
        events.append(ev)

    result = next((e for e in events if e.get("type") == "result"), None)
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    if result is None:
        err_text = "\n".join([*stray, proc.stderr.strip()]).strip()
        return Invocation(
            ok=False, events=events,
            error=f"no result event (exit {proc.returncode}): {err_text[-400:]}",
            error_kind="quota" if _QUOTA_RX.search(err_text) else "infra",
        )

    u = result.get("usage") or {}
    inv = Invocation(
        ok=not result.get("is_error", False),
        events=events,
        session_id=result.get("session_id") or (init or {}).get("session_id"),
        resolved_model=(init or {}).get("model"),
        final_text=result.get("result") or "",
        cost_usd=0.0,  # not exposed by the CLI
        usage={
            "input_tokens": int(u.get("inputTokens") or 0),
            "output_tokens": int(u.get("outputTokens") or 0),
            "cache_read_input_tokens": int(u.get("cacheReadTokens") or 0),
            "cache_creation_input_tokens": int(u.get("cacheWriteTokens") or 0),
        },
        num_turns=sum(1 for e in events if e.get("type") == "assistant"),
        duration_ms=int(result.get("duration_ms") or 0),
    )
    if result.get("is_error"):
        text = str(result.get("result"))[:300]
        inv.error = f"{result.get('subtype', 'error')}: {text}"
        inv.error_kind = "quota" if _QUOTA_RX.search(text) else "infra"
    return inv


def judge_invoke(*, prompt: str, model: str, schema: dict, cwd: Path, timeout_s: int = 600) -> dict:
    """Prompt-JSON judge: cursor has no --json-schema, so the schema goes
    in-band (parsed leniently, one retry). --mode ask = read-only, no edits."""
    from .base import judge_via_text

    def run_once(full_prompt: str) -> str:
        cmd = [
            *_agent_argv(), "-p",
            "--mode", "ask",
            "--output-format", "json",
            "--model", model,
            "--trust",
            full_prompt,
        ]
        proc = subprocess.run(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
        )
        result = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                result = ev
        if result is None or result.get("is_error"):
            detail = (result or {}).get("result") or proc.stderr.strip()[-300:]
            raise RuntimeError(f"cursor judge failed (exit {proc.returncode}): {detail}")
        return result.get("result") or ""

    return judge_via_text(run_once, prompt=prompt, schema=schema, model=model)


def normalize_events(events: list[dict]) -> list[dict]:
    """cursor stream → bench turns. `user` events are the CLI echoing the sent
    prompt — skipped, the runner records simulated user turns itself."""
    from bench_lib.transcript import _digest

    turns: list[dict] = []
    for ev in events:
        etype = ev.get("type")
        if etype == "assistant":
            texts = [
                b.get("text", "")
                for b in (ev.get("message") or {}).get("content") or []
                if b.get("type") == "text" and b.get("text")
            ]
            if texts:
                turns.append({"idx": len(turns), "role": "assistant",
                              "text": "\n".join(texts), "tool_calls": []})
        elif etype == "tool_call" and ev.get("subtype") == "completed":
            wrapper = ev.get("tool_call") or {}
            key = next((k for k in wrapper if k.endswith("ToolCall")), None)
            if not key:
                continue
            payload = wrapper.get(key) or {}
            inp = dict(payload.get("args") or {})
            if "path" in inp and "file_path" not in inp:
                inp["file_path"] = inp["path"]  # activation detection matches file_path
            turns.append({
                "idx": len(turns), "role": "assistant", "text": "",
                "tool_calls": [{"name": _canonical_tool(key[: -len("ToolCall")]),
                                "input": inp, "input_digest": _digest(inp)}],
            })
            result = payload.get("result")
            if result is not None:
                turns.append({"idx": len(turns), "role": "tool_result",
                              "text": json.dumps(result, ensure_ascii=False)[:2000],
                              "tool_calls": []})
    return turns

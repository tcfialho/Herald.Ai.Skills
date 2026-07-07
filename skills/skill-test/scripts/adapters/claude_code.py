"""Claude Code headless adapter.

Isolation per cell (rev.2 R7/R8): hermetic CWD, `--setting-sources project`
(user settings/memory stay out), `--strict-mcp-config` (zero MCP), scrubbed env
(the bench itself runs inside a Claude Code session), least-privilege
`--allowedTools` from the scenario. Auth is shared with the user's install —
documented partial isolation, credentials are never copied around.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import Caps, Invocation

name = "claude_code"
capabilities = Caps(usage_quality="exact", activation_observable=True,
                    events_observable=True, parallel_safe=True)


def normalize_events(events: list[dict]) -> list[dict]:
    from bench_lib.transcript import normalize_stream_events
    return normalize_stream_events(events)

KNOWN_MODELS = ["opus", "sonnet", "haiku"]

_ENV_SCRUB_PREFIXES = ("CLAUDE_CODE_",)
_ENV_SCRUB_EXACT = {"CLAUDECODE", "CLAUDE_CONFIG_DIR"}

import re as _re

_QUOTA_RX = _re.compile(r"(hit your session limit|usage limit reached|session limit .* resets)", _re.IGNORECASE)


def is_quota_exhausted(final_text: str, cost_usd: float, num_turns: int) -> bool:
    """Plan-limit notice masquerading as a normal result: limit text, ~zero cost."""
    return bool(_QUOTA_RX.search(final_text)) and cost_usd < 0.02 and num_turns <= 1


def _claude_bin() -> str:
    path = shutil.which("claude")
    if not path:
        raise RuntimeError("claude CLI not found on PATH")
    return path


def _child_env() -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in _ENV_SCRUB_EXACT and not any(k.startswith(p) for p in _ENV_SCRUB_PREFIXES)
    }
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def list_models() -> dict:
    return {
        "models": KNOWN_MODELS,
        "note": "aliases resolve to concrete snapshots at run time (recorded per cell as resolved_model); ladder order in config.yaml is a human decision",
    }


def invoke(
    *,
    prompt: str,
    cwd: Path,
    model: str,
    allowed_tools: list[str],
    timeout_s: int,
    budget_usd: float,
    resume_session: str | None = None,
) -> Invocation:
    cmd = [
        _claude_bin(), "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--max-budget-usd", f"{budget_usd:.2f}",
        # Explicitly allowlist the workspace for write ops: the sandbox blocked
        # mkdir in the temp CWD without it (observed on win32, run-1). The OS
        # temp root is included because tools like commit_tool.py hand the SUT
        # payload files there (plan_path/temp_dir) that it must edit.
        "--add-dir", str(cwd), tempfile.gettempdir(),
    ]
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    if resume_session:
        cmd += ["--resume", resume_session]
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=_child_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return Invocation(ok=False, error=f"timeout after {timeout_s}s", error_kind="over_budget")
    except OSError as exc:
        return Invocation(ok=False, error=f"failed to launch claude: {exc}", error_kind="infra")

    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    result = next((e for e in events if e.get("type") == "result"), None)
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    if result is None:
        stderr_tail = proc.stderr.strip()[-500:]
        return Invocation(
            ok=False,
            events=events,
            error=f"no result event (exit {proc.returncode}); stderr tail: {stderr_tail}",
            error_kind="infra",
        )

    inv = Invocation(
        ok=not result.get("is_error", False),
        events=events,
        session_id=result.get("session_id"),
        resolved_model=(init or {}).get("model"),
        final_text=result.get("result") or "",
        cost_usd=float(result.get("total_cost_usd") or 0.0),
        usage=result.get("usage") or {},
        num_turns=int(result.get("num_turns") or 0),
        duration_ms=int(result.get("duration_ms") or 0),
    )
    # Plan-quota exhaustion arrives as a NORMAL result whose text is the limit
    # notice (near-zero cost, no error flag) — detect it here so the runner can
    # stop launching cells instead of burning attempts (observed live).
    if is_quota_exhausted(inv.final_text, inv.cost_usd, inv.num_turns):
        inv.ok = False
        inv.error = f"plan quota exhausted: {inv.final_text.strip()[:160]}"
        inv.error_kind = "quota"
        return inv
    if result.get("is_error"):
        subtype = result.get("subtype", "unknown_error")
        inv.error = f"{subtype}: {str(result.get('result'))[:300]}"
        inv.error_kind = "over_budget" if ("budget" in subtype or "max_turns" in subtype) else "infra"
    return inv


def materialize(*, skill_src: Path, ref: str | None, workspace: Path) -> Path:
    return materialize_into(
        skill_src=skill_src, ref=ref,
        dest=workspace / ".claude" / "skills" / skill_src.name,
    )


def materialize_into(*, skill_src: Path, ref: str | None, dest: Path) -> Path:
    """Place the skill-under-test inside the hermetic workspace.

    ref=None → copy of the working tree; otherwise extracted from git at `ref`.
    tests/ (and caches) never travel: the SUT must not see its own test assets.
    Adapters with a different native skills dir (cursor) pass their own dest.
    """
    if ref:
        _extract_from_git(skill_src, ref, dest)
    else:
        shutil.copytree(
            skill_src, dest,
            ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc", ".pytest_cache"),
        )
    if not (dest / "SKILL.md").exists():
        raise RuntimeError(f"materialized skill has no SKILL.md at {dest}")
    return dest


def _extract_from_git(skill_src: Path, ref: str, dest: Path) -> None:
    import io
    import tarfile

    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=skill_src,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()
    if not repo_root:
        raise RuntimeError(f"{skill_src} is not inside a git repo; --skill-ref needs git")
    rel = skill_src.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    proc = subprocess.run(
        ["git", "archive", "--format=tar", ref, "--", rel],
        cwd=repo_root, capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git archive {ref} failed: {proc.stderr.decode(errors='replace')[:300]}")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        for member in tar.getmembers():
            inner = Path(member.name)
            try:
                inner_rel = inner.relative_to(rel)
            except ValueError:
                continue
            parts = inner_rel.parts
            if not parts or parts[0] in ("tests", "__pycache__"):
                continue
            if member.isfile():
                target = dest / inner_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())


def judge_invoke(*, prompt: str, model: str, schema: dict, cwd: Path, timeout_s: int = 600) -> dict:
    """Structured judge call: no tools, JSON schema enforced by the CLI."""
    cmd = [
        _claude_bin(), "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--strict-mcp-config",
        "--setting-sources", "project",
        "--allowedTools", "StructuredOutput",  # required by --json-schema; everything else denied
        "--max-budget-usd", "0.50",
    ]
    proc = subprocess.run(
        cmd, cwd=cwd, env=_child_env(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout_s,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"judge produced no JSON (exit {proc.returncode}): {proc.stdout[:300]}")
    if payload.get("is_error"):
        raise RuntimeError(f"judge errored: {str(payload.get('result'))[:300]}")
    structured = payload.get("structured_output")
    if structured is None:
        raw = payload.get("result") or ""
        structured = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    return {
        "output": structured,
        "cost_usd": float(payload.get("total_cost_usd") or 0.0),
        "resolved_model": payload.get("modelUsage") and next(iter(payload["modelUsage"])) or model,
    }

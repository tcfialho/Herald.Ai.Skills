"""agy (Antigravity / Gemini) headless adapter — calls the `agy` binary
directly; NO dependency on the delegate-to-agy skill.

Empirical constraints (probed 2026-07-05, agy 1.0.16):
- AGENTS.md in the workspace is NOT loaded in print mode → the skill is
  packaged IN-BAND: preamble with SKILL.md text + the workspace absolute path
  (without the explicit path, file operations land elsewhere).
- `agy -p` hangs on tool-using tasks unless stdin is detached (DEVNULL).
- No JSON/usage output → usage is ESTIMATED (chars/4), cost unknown (0.0),
  flagged via usage_quality. No tool-event stream → events/activation are NOT
  observable; the checks engine excludes those checks instead of passing them.
- Resume is `--continue` (most recent conversation, globally) → not parallel
  safe; the runner clamps jobs to 1 for this adapter.
- No granular permissions: runs with --dangerously-skip-permissions inside the
  throwaway workspace — a documented fidelity divergence (R8).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import Caps, Invocation

name = "agy"
capabilities = Caps(
    usage_quality="estimated",
    activation_observable=False,
    events_observable=False,
    parallel_safe=False,
)

_PREAMBLE_REL = ".claude/bench-agy-preamble.txt"  # under .claude/: invisible to state capture


def _agy_bin() -> str:
    for candidate in ("agy", "agy.cmd", "agy.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("agy CLI not found on PATH")


def _estimate(text: str) -> int:
    return max(0, round(len(text) / 4))


def list_models() -> dict:
    try:
        proc = subprocess.run(
            [_agy_bin(), "models"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        models = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"models": [], "error": str(exc)}
    return {
        "models": models,
        "note": "pass the display name verbatim to --model; ladder order in config.yaml is a human decision",
    }


def materialize(*, skill_src: Path, ref: str | None, workspace: Path) -> Path:
    """Same on-disk layout as claude_code (scripts must be runnable) plus the
    in-band preamble that stands in for native skill loading."""
    from . import claude_code

    dest = claude_code.materialize(skill_src=skill_src, ref=ref, workspace=workspace)
    skill_md = (dest / "SKILL.md").read_text(encoding="utf-8")
    preamble = (
        "You have the following agent skill INSTALLED. When the user's request matches it, "
        "follow it EXACTLY — its rules override your defaults.\n"
        f"Your workspace directory is: {workspace}\n"
        "All relative paths are relative to that workspace directory. The skill's own files "
        f"(scripts/, references/) live at: {dest}\n"
        "TERMINAL RULES: run the skill's scripts as ONE complete non-interactive command, "
        'e.g. python "<absolute path to script>" <subcommand> --flag value. Never start '
        "python/node/any REPL without arguments; never run a command that waits for input.\n\n"
        f"--- SKILL: {skill_src.name} ---\n{skill_md}\n--- END SKILL ---\n\n"
        "User request: "
    )
    (workspace / _PREAMBLE_REL).parent.mkdir(parents=True, exist_ok=True)
    (workspace / _PREAMBLE_REL).write_text(preamble, encoding="utf-8")
    return dest


def invoke(
    *,
    prompt: str,
    cwd: Path,
    model: str,
    allowed_tools: list[str],  # accepted for interface parity; agy has no allowlist
    timeout_s: int,
    budget_usd: float,        # agy exposes no budget control; enforced only via timeout
    resume_session: str | None = None,
) -> Invocation:
    preamble_path = cwd / _PREAMBLE_REL
    if resume_session is None and preamble_path.exists():
        full_prompt = preamble_path.read_text(encoding="utf-8") + prompt
    else:
        full_prompt = prompt

    cmd = [
        _agy_bin(), "-p", full_prompt,
        "--model", model,
        "--add-dir", str(cwd),
        "--print-timeout", f"{timeout_s}s",
        "--dangerously-skip-permissions",
    ]
    if resume_session is not None:
        cmd.append("--continue")

    fd, out_path = tempfile.mkstemp(prefix="agy-out-", suffix=".txt")
    os.close(fd)  # win32: an open mkstemp fd locks the file against unlink
    out_file = Path(out_path)
    try:
        with out_file.open("w", encoding="utf-8", errors="replace") as fh:
            proc = subprocess.run(
                cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", timeout=timeout_s + 30,
            )
        final_text = out_file.read_text(encoding="utf-8", errors="replace").strip()
    except subprocess.TimeoutExpired:
        return Invocation(ok=False, error=f"timeout after {timeout_s}s", error_kind="over_budget")
    except OSError as exc:
        return Invocation(ok=False, error=f"failed to launch agy: {exc}", error_kind="infra")
    finally:
        out_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        return Invocation(
            ok=False, final_text=final_text,
            error=f"agy exit {proc.returncode}: {(proc.stderr or '')[-400:]}",
            error_kind="infra",
        )
    if not final_text:
        return Invocation(ok=False, error="agy produced no output", error_kind="infra")

    return Invocation(
        ok=True,
        events=[{"type": "agy_final", "text": final_text}],
        session_id="agy-continue",  # sentinel: resume uses --continue, not an id
        resolved_model=model,
        final_text=final_text,
        cost_usd=0.0,  # unknown — usage_quality: estimated
        usage={
            "input_tokens": _estimate(full_prompt),
            "output_tokens": _estimate(final_text),
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        num_turns=1,
        duration_ms=0,
    )


def judge_invoke(*, prompt: str, model: str, schema: dict, cwd: Path, timeout_s: int = 600) -> dict:
    """Prompt-JSON judge (no schema enforcement in agy; parsed leniently)."""
    from .base import judge_via_text

    def run_once(full_prompt: str) -> str:
        inv = invoke(prompt=full_prompt, cwd=cwd, model=model, allowed_tools=[],
                     timeout_s=timeout_s, budget_usd=0.0)
        if not inv.ok:
            raise RuntimeError(f"agy judge failed: {inv.error}")
        return inv.final_text

    return judge_via_text(run_once, prompt=prompt, schema=schema, model=model)


def normalize_events(events: list[dict]) -> list[dict]:
    """agy has no structured stream: one assistant turn per invocation."""
    return [
        {"idx": i, "role": "assistant", "text": e["text"], "tool_calls": []}
        for i, e in enumerate(e for e in events if e.get("type") == "agy_final")
    ]

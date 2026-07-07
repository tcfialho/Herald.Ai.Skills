"""Deterministic checks engine (P8: state > event > judge).

State probes are executed against the live workspace and their outputs stored in
snapshots; check evaluation then runs on the snapshots only, so teardown never
destroys evidence and cells can be re-evaluated later.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def state_probe_cmds(items: list[dict]) -> list[str]:
    cmds = []
    for item in items:
        for check in item.get("checks", []):
            if check.get("type") == "state" and check.get("cmd"):
                cmds.append(check["cmd"])
    return sorted(set(cmds))


def capture_state(workspace: Path, probe_cmds: list[str]) -> dict:
    """Run every state probe in the workspace; capture stdout/exit code."""
    probes = {}
    for cmd in probe_cmds:
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=workspace, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )
            probes[cmd] = {"exit": proc.returncode, "stdout": proc.stdout.strip()}
        except subprocess.TimeoutExpired:
            probes[cmd] = {"exit": -1, "stdout": "", "error": "probe timeout"}
    files = sorted(
        p.relative_to(workspace).as_posix()
        for p in workspace.rglob("*")
        if p.is_file() and not {".git", ".claude", ".cursor"} & set(p.parts)
    )
    return {"probes": probes, "files": files}


def evaluate(
    items: list[dict],
    *,
    initial_state: dict,
    final_state: dict,
    turns: list[dict],
    events_observable: bool = True,
) -> dict:
    """Evaluate all deterministic checks. Returns per-item results + compliance.

    events_observable=False (adapter without a tool-call stream, e.g. agy):
    event checks become errors ("not observable") and leave the compliance
    denominator — a forbidden_event must never pass just because we're blind.
    """
    results = []
    for item in items:
        if item["kind"] != "deterministic":
            continue
        item_checks = []
        for check in item["checks"]:
            if check["type"] in ("required_event", "forbidden_event") and not events_observable:
                status, detail = "error", "tool events not observable on this adapter"
            else:
                status, detail = _eval_check(check, initial_state, final_state, turns)
            item_checks.append({"type": check["type"], "status": status, "detail": detail})
        overall = "pass" if all(c["status"] == "pass" for c in item_checks) else (
            "error" if any(c["status"] == "error" for c in item_checks) else "fail"
        )
        results.append(
            {"id": item["id"], "severity": item["severity"], "status": overall, "checks": item_checks}
        )
    evaluated = [r for r in results if r["status"] != "error"]
    passed = [r for r in evaluated if r["status"] == "pass"]
    critical_failed = [r["id"] for r in results if r["status"] == "fail" and r["severity"] == "critical"]
    return {
        "items": results,
        "compliance_pct": round(100 * len(passed) / len(evaluated), 1) if evaluated else 100.0,
        "critical_failed": critical_failed,
        "errors": [r["id"] for r in results if r["status"] == "error"],
    }


def _eval_check(check: dict, initial: dict, final: dict, turns: list[dict]):
    ctype = check["type"]
    if ctype == "state":
        return _eval_state(check, initial, final)
    if ctype in ("file_exists", "file_absent"):
        files = final.get("files", [])
        pattern = check.get("path", "")
        rx = _glob_to_re(pattern)
        hit = any(rx.fullmatch(f) for f in files)
        if ctype == "file_exists":
            return ("pass", f"matched {pattern}") if hit else ("fail", f"no file matching {pattern}")
        return ("fail", f"file matching {pattern} present") if hit else ("pass", f"absent: {pattern}")
    if ctype in ("required_event", "forbidden_event"):
        found = _find_event(check, turns)
        if ctype == "required_event":
            return ("pass", found) if found else ("fail", f"no event matched {check.get('pattern')!r}")
        return ("fail", f"forbidden event: {found}") if found else ("pass", "no forbidden event")
    return ("error", f"unknown check type {ctype!r}")


def _eval_state(check: dict, initial: dict, final: dict):
    cmd = check.get("cmd")
    if not cmd:
        return ("error", "state check without cmd")
    probe = final.get("probes", {}).get(cmd)
    if probe is None:
        return ("error", f"probe not captured: {cmd}")
    out = probe.get("stdout", "")
    if check.get("expect") == "unchanged_from_setup":
        before = initial.get("probes", {}).get(cmd, {}).get("stdout", "")
        return ("pass", "unchanged") if out == before else ("fail", f"changed: {before!r} -> {out!r}")
    if "expect_equals" in check:
        want = str(check["expect_equals"]).strip()
        return ("pass", out) if out.strip() == want else ("fail", f"want {want!r}, got {out!r}")
    if "expect_regex" in check:
        ok = re.search(check["expect_regex"], out, re.MULTILINE) is not None
        return ("pass", out[:200]) if ok else ("fail", f"regex {check['expect_regex']!r} not in {out[:200]!r}")
    if "expect_regex_per_line" in check:
        lines = [ln for ln in out.splitlines() if ln.strip()]
        if not lines:
            return ("fail", "probe produced no lines")
        bad = [ln for ln in lines if not re.fullmatch(check["expect_regex_per_line"], ln)]
        return ("pass", f"{len(lines)} lines ok") if not bad else ("fail", f"lines failing regex: {bad[:3]!r}")
    return ("error", f"state check has no expectation: {json.dumps(check)}")


def _find_event(check: dict, turns: list[dict]) -> str | None:
    tool = check.get("tool")
    rx = re.compile(check.get("pattern", ""), re.IGNORECASE) if check.get("pattern") else None
    for turn in turns:
        for call in turn.get("tool_calls", []):
            if tool and call["name"] != tool:
                continue
            haystack = call["name"] + " " + json.dumps(call.get("input", {}), ensure_ascii=False)
            if rx is None or rx.search(haystack):
                return f"turn {turn['idx']}: {haystack[:160]}"
    return None


def _glob_to_re(pattern: str) -> re.Pattern:
    parts = []
    i = 0
    while i < len(pattern):
        if pattern[i : i + 2] == "**":
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts))

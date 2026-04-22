#!/usr/bin/env python3
"""git-commit-tool: agent-native semantic commit orchestrator.

Subcommands:
  preflight    Check repo validity, ongoing ops, empty repo, clean tree.
  collect      Stage everything, create a per-invocation OS temp dir, and
               return its path alongside staged files + truncated diffs.
  validate     Validate <temp-dir>/commit-plan.json against staged files.
  execute      Commit groups atomically with synchronized timestamps.
  cleanup      Remove a temp dir returned by `collect`. Idempotent.

Contract:
  `collect` creates a fresh temp dir via tempfile.mkdtemp() in the OS
  temp area (never inside the user's repo) and returns its path in the
  stdout JSON as `temp_dir`. The agent writes the plan into
  <temp_dir>/commit-plan.json and passes `--temp-dir <path>` to
  `validate` and `execute`. On `execute --confirm` (success OR failure)
  the tool wipes the temp dir before writing the final stdout payload.
  Dry runs preserve the temp dir so the caller can retry with --confirm.
  If the flow is abandoned before `execute --confirm` (user cancelled,
  validation exhausted), the agent should call `cleanup --temp-dir <path>`
  to remove the orphaned dir.

Output channels:
  stdout  JSON payload (final response; single line).
  stderr  JSONL progress events (not persisted to disk).

Exit codes:
  0   Success.
  2   Invalid CLI arguments (argparse default).
  10  Not a git repository.
  11  Merge/rebase/cherry-pick/revert in progress.
  12  Working tree clean (informational, not a hard error).
  20  Plan validation failed.
  30  Commit failed during execute; rollback performed.
  31  Rollback failed; manual intervention required.
  40  Hook blocked the commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEMP_DIR_PREFIX = "git-commit-"
PLAN_FILENAME = "commit-plan.json"
DIFFS_SUBDIR = "diffs"

ALLOWED_TYPES_DEFAULT: tuple[str, ...] = (
    "feat", "fix", "docs", "style", "refactor", "perf",
    "test", "build", "ci", "chore", "revert",
)
MAX_MESSAGE_LENGTH_DEFAULT = 72
MAX_FILES_DEFAULT = 50
MAX_DIFF_LINES_PER_FILE_DEFAULT = 80
SUMMARY_ONLY_THRESHOLD = 100

EXIT_OK = 0
EXIT_NOT_A_REPO = 10
EXIT_OP_IN_PROGRESS = 11
EXIT_WORKING_TREE_CLEAN = 12
EXIT_PLAN_INVALID = 20
EXIT_COMMIT_FAILED = 30
EXIT_ROLLBACK_FAILED = 31
EXIT_HOOK_BLOCKED = 40


# ---------------------------------------------------------------------------
# Output helpers (strict separation: stdout = result, stderr = diagnostics)
# ---------------------------------------------------------------------------

def emit_result(payload: dict) -> None:
    """Write the final structured response to stdout as a single JSON line."""
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()


def emit_event(level: str, event: str, **fields: Any) -> None:
    """Write a JSONL progress event to stderr (no disk persistence)."""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": level,
        "event": event,
    }
    record.update(fields)
    sys.stderr.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Temp-dir helpers
# ---------------------------------------------------------------------------

def _plan_path(temp_dir: Path) -> Path:
    return temp_dir / PLAN_FILENAME


def _diffs_dir(temp_dir: Path) -> Path:
    return temp_dir / DIFFS_SUBDIR


def _cleanup_temp_dir(temp_dir: Path) -> bool:
    """Best-effort removal of a temp dir. Returns True if fully cleaned."""
    if not temp_dir.exists():
        return True
    shutil.rmtree(temp_dir, ignore_errors=True)
    if temp_dir.exists():
        emit_event("warn", "cleanup.partial", path=str(temp_dir).replace("\\", "/"))
        return False
    return True


def _as_posix(path: Path) -> str:
    return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Git subprocess wrapper (always argv list, never shell-interpolated)
# ---------------------------------------------------------------------------

def run_git(
    args: Sequence[str],
    *,
    env: Optional[dict[str, str]] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a git command. Captures stdout/stderr as text. Never uses shell."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    emit_event("debug", "git.run", argv=["git", *args])
    result = subprocess.run(
        ["git", *args],
        env=full_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        emit_event(
            "error",
            "git.failed",
            argv=["git", *args],
            exit_code=result.returncode,
            stderr=(result.stderr or "").strip(),
        )
        raise subprocess.CalledProcessError(
            result.returncode, ["git", *args],
            output=result.stdout, stderr=result.stderr,
        )
    return result


# ---------------------------------------------------------------------------
# Regex factory for commit messages
# ---------------------------------------------------------------------------

def build_commit_regex(
    allowed_types: Sequence[str],
    max_length: int,
) -> re.Pattern[str]:
    """Build Conventional Commits regex: <type>[(<scope>)][!]: <desc>."""
    types_alt = "|".join(re.escape(t) for t in allowed_types)
    pattern = (
        rf"^(?:{types_alt})"
        r"(?:\([a-z0-9][a-z0-9\-]*\))?"
        r"!?"
        rf": .{{1,{max_length}}}$"
    )
    return re.compile(pattern)


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

def cmd_preflight(_args: argparse.Namespace) -> int:
    emit_event("info", "preflight.start")

    rev = run_git(["rev-parse", "--git-dir"], check=False)
    if rev.returncode != 0:
        emit_result({
            "status": "error",
            "code": "NOT_A_REPO",
            "message": "Current directory is not a git repository.",
        })
        return EXIT_NOT_A_REPO

    git_dir = Path(rev.stdout.strip())
    markers = {
        "merge": git_dir / "MERGE_HEAD",
        "rebase": git_dir / "REBASE_HEAD",
        "cherry_pick": git_dir / "CHERRY_PICK_HEAD",
        "revert": git_dir / "REVERT_HEAD",
    }
    for op_name, marker_path in markers.items():
        if marker_path.exists():
            emit_result({
                "status": "error",
                "code": "OP_IN_PROGRESS",
                "operation": op_name,
                "message": f"{op_name} in progress; finish or abort it first.",
            })
            return EXIT_OP_IN_PROGRESS

    head_result = run_git(["rev-parse", "HEAD"], check=False)
    is_empty = head_result.returncode != 0
    head_sha = head_result.stdout.strip() if not is_empty else None

    branch_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    branch = (
        branch_result.stdout.strip()
        if branch_result.returncode == 0 and branch_result.stdout.strip() != "HEAD"
        else None
    )

    status = run_git(["status", "--porcelain"])
    if not status.stdout.strip():
        emit_result({
            "status": "clean",
            "code": "WORKING_TREE_CLEAN",
            "message": "Working tree clean. Nothing to commit.",
            "branch": branch,
            "head": head_sha,
            "is_empty": is_empty,
        })
        emit_event("info", "preflight.clean")
        return EXIT_WORKING_TREE_CLEAN

    emit_result({
        "status": "ok",
        "branch": branch,
        "head": head_sha,
        "is_empty": is_empty,
    })
    emit_event("info", "preflight.done", branch=branch, head=head_sha, is_empty=is_empty)
    return EXIT_OK


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------

def _short_hash(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def _parse_name_status(raw: str) -> list[dict[str, str]]:
    """Parse `git diff --cached --name-status --find-renames=N` output.

    Dedups renames by new path to avoid R+M duplicates.
    """
    seen_paths: set[str] = set()
    entries: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status_raw = parts[0]
        status = status_raw[0]
        if status == "R" and len(parts) >= 3:
            old_path, new_path = parts[1], parts[2]
            if new_path in seen_paths:
                continue
            seen_paths.add(new_path)
            entries.append({"status": "R", "path": new_path, "old_path": old_path})
        elif status in {"A", "M", "D", "T", "C"} and len(parts) >= 2:
            path = parts[1]
            if path in seen_paths:
                continue
            seen_paths.add(path)
            entries.append({"status": status, "path": path})
    return entries


def _collect_diff(path: str, unified_lines: int) -> tuple[str, int]:
    """Return (diff_text, line_count) truncated to `unified_lines` context."""
    result = run_git(
        ["diff", "--cached", f"--unified={unified_lines}", "--", path],
        check=False,
    )
    diff_text = result.stdout or ""
    return diff_text, len(diff_text.splitlines())


def cmd_collect(args: argparse.Namespace) -> int:
    emit_event("info", "collect.start")

    run_git(["add", "-A"])
    emit_event("info", "collect.staged_all")

    name_status = run_git(
        ["diff", "--cached", "--name-status", "--find-renames=50"],
    )
    entries = _parse_name_status(name_status.stdout)

    if not entries:
        emit_result({
            "status": "clean",
            "code": "WORKING_TREE_CLEAN",
            "message": "Nothing is staged after `git add -A`.",
        })
        return EXIT_WORKING_TREE_CLEAN

    temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    diffs_dir = _diffs_dir(temp_dir)
    diffs_dir.mkdir(parents=True, exist_ok=True)
    emit_event("info", "collect.temp_dir", path=_as_posix(temp_dir))

    numstat = run_git(["diff", "--cached", "--numstat"])
    added_total = 0
    removed_total = 0
    for line in numstat.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] != "-" and parts[1] != "-":
            try:
                added_total += int(parts[0])
                removed_total += int(parts[1])
            except ValueError:
                continue

    summary_only = len(entries) > SUMMARY_ONLY_THRESHOLD
    truncated = False

    for entry in entries:
        if entry["status"] == "D" or summary_only:
            entry["diff_file"] = None
            entry["diff_lines"] = 0
            continue
        diff_text, line_count = _collect_diff(entry["path"], args.max_diff_lines_per_file)
        entry["diff_lines"] = line_count
        if line_count > args.max_diff_lines_per_file * 4:
            truncated = True
        diff_path = diffs_dir / f"{_short_hash(entry['path'])}.diff"
        try:
            diff_path.write_text(diff_text, encoding="utf-8")
            entry["diff_file"] = _as_posix(diff_path)
        except OSError as exc:
            emit_event("warn", "collect.diff_write_failed", path=entry["path"], error=str(exc))
            entry["diff_file"] = None

    limited = entries
    if len(entries) > args.max_files:
        limited = entries[: args.max_files]
        truncated = True

    emit_result({
        "status": "ok",
        "temp_dir": _as_posix(temp_dir),
        "plan_path": _as_posix(_plan_path(temp_dir)),
        "diffs_dir": _as_posix(diffs_dir),
        "staged_files": limited,
        "total_staged": len(entries),
        "diff_summary": {
            "total_files": len(entries),
            "total_added": added_total,
            "total_removed": removed_total,
        },
        "summary_only": summary_only,
        "truncated": truncated,
    })
    emit_event(
        "info", "collect.done",
        files=len(entries), added=added_total, removed=removed_total,
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def _load_plan(plan_path: Path) -> tuple[Optional[dict], Optional[dict]]:
    """Load a plan JSON file. Returns (plan, error_payload)."""
    if not plan_path.exists():
        return None, {
            "code": "PLAN_FILE_MISSING",
            "path": _as_posix(plan_path),
            "hint": f"Write the commit plan to {_as_posix(plan_path)} before validating.",
        }
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, {
            "code": "PLAN_FILE_INVALID_JSON",
            "path": _as_posix(plan_path),
            "error": str(exc),
            "hint": "Fix the JSON syntax before retrying.",
        }
    if not isinstance(data, dict) or "groups" not in data or not isinstance(data["groups"], list):
        return None, {
            "code": "PLAN_SCHEMA_ROOT",
            "hint": "Plan must be an object with a top-level `groups` array.",
        }
    return data, None


def _current_staged_paths() -> set[str]:
    result = run_git(
        ["diff", "--cached", "--name-only", "--find-renames=50"],
    )
    return {line for line in result.stdout.splitlines() if line}


def cmd_validate(args: argparse.Namespace) -> int:
    temp_dir = Path(args.temp_dir)
    plan_path = _plan_path(temp_dir)
    emit_event("info", "validate.start", plan=_as_posix(plan_path))

    plan, err = _load_plan(plan_path)
    if err is not None:
        emit_result({"status": "invalid", "errors": [err]})
        return EXIT_PLAN_INVALID

    assert plan is not None
    allowed_types = tuple(t.strip() for t in args.allowed_types.split(",") if t.strip())
    regex = build_commit_regex(allowed_types, args.max_length)

    errors: list[dict[str, Any]] = []
    plan_paths: list[str] = []
    path_to_groups: dict[str, list[int]] = {}

    for idx, group in enumerate(plan["groups"], start=1):
        gid = group.get("id", idx)
        message = group.get("message", "")
        files = group.get("files", [])

        if not isinstance(message, str) or not regex.match(message):
            errors.append({
                "code": "INVALID_MESSAGE_FORMAT",
                "group_id": gid,
                "message": message,
                "hint": (
                    "Expected `<type>[(<scope>)][!]: <description>` in a single line "
                    f"up to {args.max_length} chars. Allowed types: "
                    f"{', '.join(allowed_types)}."
                ),
            })

        if not isinstance(files, list) or not files:
            errors.append({
                "code": "EMPTY_FILE_LIST",
                "group_id": gid,
                "hint": "Every group must contain at least one file.",
            })
            continue

        for path in files:
            if not isinstance(path, str) or not path:
                errors.append({
                    "code": "INVALID_FILE_ENTRY",
                    "group_id": gid,
                    "value": path,
                    "hint": "Files must be non-empty strings.",
                })
                continue
            plan_paths.append(path)
            path_to_groups.setdefault(path, []).append(gid)

    duplicates = {p: gs for p, gs in path_to_groups.items() if len(gs) > 1}
    for path, groups in duplicates.items():
        errors.append({
            "code": "DUPLICATE_FILE_ACROSS_GROUPS",
            "path": path,
            "groups": groups,
            "hint": "Each file must appear in exactly one group.",
        })

    if not args.skip_staging_check:
        staged = _current_staged_paths()
        plan_set = set(plan_paths)

        for path in plan_set:
            if path not in staged:
                errors.append({
                    "code": "FILE_NOT_STAGED",
                    "path": path,
                    "hint": (
                        "File is listed in the plan but not currently staged. "
                        "Run `collect` again to refresh the staging area."
                    ),
                })

        missing_from_plan = staged - plan_set
        if missing_from_plan:
            errors.append({
                "code": "STAGED_BUT_UNASSIGNED",
                "paths": sorted(missing_from_plan),
                "hint": "Every staged file must belong to exactly one group.",
            })

    if errors:
        emit_result({"status": "invalid", "errors": errors})
        emit_event("warn", "validate.failed", error_count=len(errors))
        return EXIT_PLAN_INVALID

    emit_result({
        "status": "ok",
        "groups": len(plan["groups"]),
        "files": len(plan_paths),
    })
    emit_event("info", "validate.done", groups=len(plan["groups"]), files=len(plan_paths))
    return EXIT_OK


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def _format_git_timestamp(moment: datetime) -> str:
    """Return a git-compatible date string like `2026-04-22T14:30:15+00:00`."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _perform_rollback(state: dict) -> tuple[bool, Optional[str]]:
    """Roll back the commits in `state`. Returns (success, error_message)."""
    n = len(state.get("commits_done", []))
    if n == 0:
        return True, None
    try:
        if state.get("head_was_empty"):
            run_git(["update-ref", "-d", "HEAD"])
        else:
            run_git(["reset", "--soft", f"HEAD~{n}"])
        return True, None
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or "").strip() or str(exc)


def cmd_execute(args: argparse.Namespace) -> int:
    temp_dir = Path(args.temp_dir)
    plan_path = _plan_path(temp_dir)
    emit_event("info", "execute.start", plan=_as_posix(plan_path), dry_run=not args.confirm)

    plan, err = _load_plan(plan_path)
    if err is not None:
        emit_result({"status": "error", "code": err["code"], "detail": err})
        return EXIT_PLAN_INVALID
    assert plan is not None

    head_result = run_git(["rev-parse", "HEAD"], check=False)
    head_was_empty = head_result.returncode != 0
    head_before = head_result.stdout.strip() if not head_was_empty else None

    use_sync_timestamp = not args.natural_timestamps
    batch_ts_iso: Optional[str] = None
    env_for_commits: dict[str, str] = {}
    if use_sync_timestamp:
        now = datetime.now(timezone.utc)
        batch_ts_iso = _format_git_timestamp(now)
        env_for_commits = {
            "GIT_AUTHOR_DATE": batch_ts_iso,
            "GIT_COMMITTER_DATE": batch_ts_iso,
        }

    if not args.confirm:
        # Dry run: preserve temp dir so caller can retry with --confirm.
        emit_result({
            "status": "dry_run",
            "message": "Dry run; pass --confirm to actually commit.",
            "head_before": head_before,
            "head_was_empty": head_was_empty,
            "synchronized_timestamp": batch_ts_iso,
            "temp_dir": _as_posix(temp_dir),
            "groups": [
                {
                    "id": g.get("id", i + 1),
                    "message": g.get("message"),
                    "files": g.get("files", []),
                }
                for i, g in enumerate(plan["groups"])
            ],
        })
        emit_event("info", "execute.dry_run")
        return EXIT_OK

    # In-memory state: survives only until cleanup at the end of this call.
    rollback_state: dict[str, Any] = {
        "head_was_empty": head_was_empty,
        "commits_done": [],
    }

    created: list[dict[str, str]] = []
    total = len(plan["groups"])

    for idx, group in enumerate(plan["groups"], start=1):
        gid = group.get("id", idx)
        message = group["message"]
        files = group["files"]
        emit_event("info", "execute.commit.start", group=gid, index=idx, total=total)

        try:
            run_git(
                ["commit", "-m", message, "--", *files],
                env=env_for_commits,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            is_hook = "hook" in stderr.lower() or "pre-commit" in stderr.lower()
            emit_event(
                "error", "execute.commit.failed",
                group=gid, index=idx, total=total, stderr=stderr,
            )

            rollback_ok, rollback_err = _perform_rollback(rollback_state)

            payload: dict[str, Any] = {
                "status": "failed",
                "code": "HOOK_BLOCKED" if is_hook else "COMMIT_FAILED",
                "failed_group": {
                    "id": gid, "index": idx, "total": total,
                    "message": message, "files": files,
                },
                "git_stderr": stderr,
                "commits_done": created,
                "rollback": {
                    "ok": rollback_ok,
                    "reverted_count": len(created),
                    "head_restored_to": head_before,
                    "head_was_empty": head_was_empty,
                    "error": rollback_err,
                },
            }

            # Option A: --confirm always cleans the temp dir, success OR failure.
            cleaned = _cleanup_temp_dir(temp_dir)
            payload["temp_cleaned"] = cleaned

            emit_result(payload)
            if not rollback_ok:
                return EXIT_ROLLBACK_FAILED
            return EXIT_HOOK_BLOCKED if is_hook else EXIT_COMMIT_FAILED

        sha = run_git(["rev-parse", "HEAD"]).stdout.strip()
        commit_info = {"index": idx, "group_id": gid, "sha": sha, "message": message}
        created.append(commit_info)
        rollback_state["commits_done"].append(commit_info)
        emit_event("info", "execute.commit.done", group=gid, index=idx, total=total, sha=sha)

    emit_event("info", "execute.done", count=len(created))

    cleaned = _cleanup_temp_dir(temp_dir)

    emit_result({
        "status": "ok",
        "commits": created,
        "count": len(created),
        "synchronized_timestamp": batch_ts_iso,
        "head_before": head_before,
        "temp_cleaned": cleaned,
    })
    return EXIT_OK


# ---------------------------------------------------------------------------
# cleanup (manual, idempotent)
# ---------------------------------------------------------------------------

def cmd_cleanup(args: argparse.Namespace) -> int:
    temp_dir = Path(args.temp_dir)
    emit_event("info", "cleanup.start", path=_as_posix(temp_dir))

    if not temp_dir.exists():
        emit_result({
            "status": "noop",
            "message": "Temp dir does not exist; nothing to clean.",
            "path": _as_posix(temp_dir),
        })
        return EXIT_OK

    cleaned = _cleanup_temp_dir(temp_dir)
    emit_result({
        "status": "ok" if cleaned else "partial",
        "path": _as_posix(temp_dir),
        "temp_cleaned": cleaned,
    })
    emit_event("info", "cleanup.done", cleaned=cleaned)
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="commit_tool",
        description=(
            "Agent-native semantic commit orchestrator. "
            "The agent writes a plan into the temp dir returned by `collect`; "
            "this tool validates and commits atomically with synchronized "
            "timestamps, then wipes the temp dir."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0   success\n"
            "  2   invalid CLI arguments\n"
            "  10  not a git repository\n"
            "  11  merge/rebase/cherry-pick/revert in progress\n"
            "  12  working tree clean (informational)\n"
            "  20  plan validation failed\n"
            "  30  commit failed; rollback performed\n"
            "  31  rollback failed; manual intervention required\n"
            "  40  hook blocked the commit\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="subcommand")

    sp_pre = sub.add_parser(
        "preflight",
        help="Check repo validity, ongoing ops, empty repo, clean tree.",
    )
    sp_pre.set_defaults(func=cmd_preflight)

    sp_col = sub.add_parser(
        "collect",
        help=(
            "Stage everything, create a per-invocation OS temp dir, and "
            "enumerate staged files with truncated diffs."
        ),
    )
    sp_col.add_argument(
        "--max-files", type=int, default=MAX_FILES_DEFAULT,
        help=f"Cap the number of files in the response (default: {MAX_FILES_DEFAULT}).",
    )
    sp_col.add_argument(
        "--max-diff-lines-per-file", type=int,
        default=MAX_DIFF_LINES_PER_FILE_DEFAULT,
        help=f"Unified-diff context lines per file (default: {MAX_DIFF_LINES_PER_FILE_DEFAULT}).",
    )
    sp_col.set_defaults(func=cmd_collect)

    sp_val = sub.add_parser(
        "validate",
        help="Validate <temp-dir>/commit-plan.json against staged files.",
    )
    sp_val.add_argument(
        "--temp-dir", required=True, type=str,
        help="Path returned by `collect` in the `temp_dir` field.",
    )
    sp_val.add_argument(
        "--allowed-types", type=str, default=",".join(ALLOWED_TYPES_DEFAULT),
        help="Comma-separated allowed commit types.",
    )
    sp_val.add_argument(
        "--max-length", type=int, default=MAX_MESSAGE_LENGTH_DEFAULT,
        help=f"Max total commit message length (default: {MAX_MESSAGE_LENGTH_DEFAULT}).",
    )
    sp_val.add_argument(
        "--skip-staging-check", action="store_true",
        help="Skip cross-checking plan files against the current staging area.",
    )
    sp_val.set_defaults(func=cmd_validate)

    sp_exe = sub.add_parser(
        "execute",
        help=(
            "Commit groups atomically with synchronized timestamps. "
            "With --confirm, the temp dir is wiped on success or failure."
        ),
    )
    sp_exe.add_argument(
        "--temp-dir", required=True, type=str,
        help="Path returned by `collect` in the `temp_dir` field.",
    )
    sp_exe.add_argument(
        "--confirm", action="store_true",
        help="Actually perform commits. Without this flag, runs as a dry run.",
    )
    sp_exe.add_argument(
        "--natural-timestamps", action="store_true",
        help="Let git assign a fresh timestamp per commit (default: synchronized).",
    )
    sp_exe.set_defaults(func=cmd_execute)

    sp_cln = sub.add_parser(
        "cleanup",
        help="Remove a temp dir returned by `collect`. Idempotent.",
    )
    sp_cln.add_argument(
        "--temp-dir", required=True, type=str,
        help="Path to remove (must be the one returned by `collect`).",
    )
    sp_cln.set_defaults(func=cmd_cleanup)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        emit_event("error", "unhandled.git_not_found", error=str(exc))
        emit_result({
            "status": "error",
            "code": "GIT_NOT_INSTALLED",
            "message": "git executable not found in PATH.",
        })
        return 1
    except subprocess.CalledProcessError as exc:
        emit_event(
            "error", "unhandled.git_error",
            argv=exc.cmd, exit_code=exc.returncode,
            stderr=(exc.stderr or "").strip() if isinstance(exc.stderr, str) else None,
        )
        emit_result({
            "status": "error",
            "code": "GIT_COMMAND_FAILED",
            "argv": exc.cmd,
            "exit_code": exc.returncode,
            "stderr": (exc.stderr or "").strip() if isinstance(exc.stderr, str) else None,
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())

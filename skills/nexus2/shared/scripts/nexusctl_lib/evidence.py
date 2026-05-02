import fnmatch
import subprocess
from datetime import datetime
from pathlib import Path

from .errors import NexusError
from .markdown import evidence_section, replace_section
from .models import Story, Task
from .paths import normalize_path, runtime_dir, write_text
from .tasks import parse_tasks
from .timeutil import iso_now


def append_evidence(
    story: Story,
    task: Task,
    verify_cmd: str,
    exit_code: int,
    files: list[str],
    coverage_ids: list[str],
    note: str,
) -> None:
    section = evidence_section(story.body)
    if not section or section == "None yet.":
        section = ""
    lines = []
    if section.strip():
        lines.extend([section.rstrip(), ""])
    lines.extend(
        [
            f"- {task.task_id}:",
            f"  - timestamp: {iso_now()}",
            f"  - verify_cmd: `{verify_cmd}`",
            f"  - exit_code: {exit_code}",
        ]
    )
    if files:
        lines.append("  - files_checked:")
        lines.extend(f"    - `{file_path}`" for file_path in files)
    if coverage_ids:
        lines.append("  - covers:")
        lines.extend(f"    - {coverage_id}" for coverage_id in coverage_ids)
    if note:
        lines.append(f"  - note: {note}")
    story.body = replace_section(story.body, "Execution Evidence", "\n".join(lines))


def append_bug_evidence(story: Story, bug_id: str, verify_cmd: str, exit_code: int, note: str) -> None:
    section = evidence_section(story.body)
    if not section or section == "None yet.":
        section = ""
    lines = []
    if section.strip():
        lines.extend([section.rstrip(), ""])
    lines.extend(
        [
            f"- {bug_id}:",
            f"  - timestamp: {iso_now()}",
            f"  - verify_cmd: `{verify_cmd}`",
            f"  - exit_code: {exit_code}",
        ]
    )
    if note:
        lines.append(f"  - note: {note}")
    story.body = replace_section(story.body, "Execution Evidence", "\n".join(lines))


def run_verify_cmd(command: str, root: Path, timeout: int) -> tuple[int, str]:
    if not command or command == "TBD":
        raise NexusError("task has no valid verify_cmd")
    completed = subprocess.run(
        command,
        cwd=str(root),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout or ""


def write_cache_log(root: Path, story: Story, task_id: str, output: str) -> Path:
    cache = runtime_dir(root) / "cache" / story.story_id
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
    write_text(path, output)
    return path


def files_within_write_scope(story: Story, files: list[str]) -> list[str]:
    scopes = story.meta.get("write_scope") or []
    if not isinstance(scopes, list) or not scopes:
        return files
    normalized_scopes = [normalize_path(scope) for scope in scopes if scope and str(scope) != "TBD"]
    if not normalized_scopes:
        return files
    violations = []
    for file_path in files:
        normalized_file = normalize_path(file_path)
        if not any(fnmatch.fnmatch(normalized_file, pattern) for pattern in normalized_scopes):
            violations.append(file_path)
    return violations


def missing_files(root: Path, files: list[str]) -> list[str]:
    return [file_path for file_path in files if not (root / file_path).exists()]


def run_story_verify_commands(root: Path, story: Story, timeout: int = 600) -> list[str]:
    failures: list[str] = []
    commands = [task.verify_cmd for task in parse_tasks(story.body) if task.verify_cmd and task.verify_cmd != "TBD"]
    for command in dict.fromkeys(commands):
        try:
            exit_code, output = run_verify_cmd(command, root, timeout)
        except subprocess.TimeoutExpired as exc:
            log = write_cache_log(root, story, "qa-timeout", exc.stdout or "")
            failures.append(f"verify timeout: {command} (log: {log})")
            continue
        log = write_cache_log(root, story, "qa-verify", output)
        if exit_code != 0:
            failures.append(f"verify failed ({exit_code}): {command} (log: {log})")
    return failures

import re

from .constants import REVERSE_TASK_MARKERS, TASK_MARKERS
from .errors import NexusError
from .models import Story, Task


def strip_backticks(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        return value[1:-1]
    return value


def parse_tasks(body: str) -> list[Task]:
    lines = body.splitlines()
    starts: list[tuple[int, re.Match[str]]] = []
    pattern = re.compile(r"^-\s+\[([ x>!])\]\s+(TASK-\d+):\s*(.*)$")
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            starts.append((idx, match))

    tasks: list[Task] = []
    for pos, (idx, match) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        marker, task_id, title = match.groups()
        verify_cmd = ""
        files: list[str] = []
        covers: list[str] = []
        mode: str | None = None
        for block_line in lines[idx + 1 : end]:
            stripped = block_line.strip()
            if stripped.startswith("- verify_cmd:"):
                verify_cmd = strip_backticks(stripped.split(":", 1)[1].strip())
                mode = None
            elif stripped.startswith("- files:"):
                mode = "files"
            elif stripped.startswith("- covers:"):
                mode = "covers"
            elif mode == "files" and stripped.startswith("- "):
                files.append(strip_backticks(stripped[2:].strip()))
            elif mode == "covers" and stripped.startswith("- "):
                covers.append(strip_backticks(stripped[2:].strip()))
        tasks.append(
            Task(
                task_id=task_id,
                title=title.strip(),
                status=TASK_MARKERS.get(marker, "pending"),
                marker=marker,
                verify_cmd=verify_cmd,
                files=[item for item in files if item and item != "TBD"],
                covers=[item for item in covers if item and item != "TBD"],
            )
        )
    return tasks


def update_task_marker(body: str, task_id: str, status: str) -> str:
    marker = REVERSE_TASK_MARKERS[status]
    lines = body.splitlines()
    pattern = re.compile(rf"^-\s+\[[ x>!]\]\s+({re.escape(task_id)}:\s*.*)$")
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            lines[idx] = f"- [{marker}] {match.group(1)}"
            return "\n".join(lines)
    raise NexusError(f"task not found in story body: {task_id}")


def task_by_id(story: Story, task_id: str) -> Task:
    for task in parse_tasks(story.body):
        if task.task_id == task_id:
            return task
    raise NexusError(f"task not found: {task_id}")


def earlier_incomplete_task(story: Story, task_id: str) -> Task | None:
    for task in parse_tasks(story.body):
        if task.task_id == task_id:
            return None
        if task.status != "completed":
            return task
    raise NexusError(f"task not found: {task_id}")

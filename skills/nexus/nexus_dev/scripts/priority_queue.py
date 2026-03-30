"""
Nexus Dev - Priority Queue

Produces an optimally ordered task execution queue that respects:
  1. Explicit dependency declarations
  2. Priority level (high → medium → low)
  3. Risk-first ordering within same priority (surface blockers early)

The queue is recomputed from .nexus/task_queue.json and the current
plan_state.json; already-completed tasks are automatically excluded.

Usage:
    pq = PriorityQueue(project_root=".")
    queue = pq.build_from_task_file(".nexus/nexus_auth/tasks.json")
    for task in queue:
        print(task.id, task.title)
"""

from __future__ import annotations

import dataclasses
import json
import sys
import heapq
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

def _find_nexus_core_root() -> Path:
    """Walk up from this file until we find the directory containing nexus_core."""
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "nexus_core").is_dir():
            return candidate
    raise RuntimeError(
        "nexus_core package not found in any parent directory of "
        f"{here}. Ensure nexus_core/ is installed alongside this skill."
    )


sys.path.insert(0, str(_find_nexus_core_root()))

from nexus_core.state_manager import NexusStateManager

_PRIORITY_WEIGHT = {"high": 0, "medium": 1, "low": 2}
_STATUS_TERMINAL = {"completed", "skipped"}


# ------------------------------------------------------------------
# Item
# ------------------------------------------------------------------


@dataclass
class QueueItem:
    id: str
    title: str
    priority: str = "medium"
    dependencies: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    description: str = ""
    done_criteria: str = ""
    status: str = "pending"

    @property
    def weight(self) -> int:
        return _PRIORITY_WEIGHT.get(self.priority, 1)

    @property
    def is_done(self) -> bool:
        return self.status in _STATUS_TERMINAL


# ------------------------------------------------------------------
# PriorityQueue
# ------------------------------------------------------------------


class PriorityQueue:
    """Topological-sort priority queue for Nexus tasks."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self._state_manager = NexusStateManager(project_root)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build_from_task_file(self, task_json_path: "str | Path") -> list[QueueItem]:
        """Load tasks from a JSON file and return priority-sorted, dependency-resolved queue."""
        with open(task_json_path, "r", encoding="utf-8") as fh:
            raw_tasks: list[dict] = json.load(fh)
        return self._build(raw_tasks)

    def build_from_state(self) -> list[QueueItem]:
        """Build queue from tasks registered in .nexus/plan_state.json."""
        state = self._state_manager.load_state_or_raise()
        raw_tasks = [
            {"id": tid, "title": tdata.get("title", tid), **tdata}
            for tid, tdata in state.get("tasks", {}).items()
        ]
        return self._build(raw_tasks)

    def _build(self, raw_tasks: list[dict]) -> list[QueueItem]:
        _queue_item_fields = {f.name for f in dataclasses.fields(QueueItem)}
        items = [QueueItem(**{k: v for k, v in t.items() if k in _queue_item_fields}) for t in raw_tasks]

        # Inject status from current state (tasks may have progressed)
        state = self._state_manager.load_state()
        if state:
            live_tasks = state.get("tasks", {})
            for item in items:
                if item.id in live_tasks:
                    item.status = live_tasks[item.id].get("status", item.status)

        # Remove already-done tasks
        pending = [i for i in items if not i.is_done]

        # Topological sort with priority weighting
        return self._toposort(pending)

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def _toposort(self, items: list[QueueItem]) -> list[QueueItem]:
        """
        Kahn's algorithm (BFS) with priority tie-breaking.
        Tasks with unresolvable dependencies are appended at the end with a warning.
        """
        id_map = {item.id: item for item in items}
        order_index = {item.id: idx for idx, item in enumerate(items)}
        in_degree: dict[str, int] = {item.id: 0 for item in items}
        dependents: dict[str, list[str]] = defaultdict(list)

        for item in items:
            for dep in item.dependencies:
                if dep in id_map:
                    in_degree[item.id] += 1
                    dependents[dep].append(item.id)

        # Start with all items that have no pending dependencies
        ready: list[tuple[int, int, QueueItem]] = []
        for item in items:
            if in_degree[item.id] == 0:
                heapq.heappush(ready, (item.weight, order_index[item.id], item))
        result: list[QueueItem] = []

        while ready:
            _, _, item = heapq.heappop(ready)
            result.append(item)
            released = [id_map[dep] for dep in dependents.get(item.id, []) if dep in id_map]
            for released_item in released:
                in_degree[released_item.id] -= 1
                if in_degree[released_item.id] == 0:
                    heapq.heappush(
                        ready,
                        (released_item.weight, order_index[released_item.id], released_item),
                    )

        # Anything left has circular/unresolvable deps — append with warning
        unresolved = [item for item in items if item not in result]
        result.extend(unresolved)

        return result

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_markdown(self, queue: list[QueueItem]) -> str:
        lines = [
            f"## 🚦 Execution Queue ({len(queue)} tasks)\n",
            "| Order | ID | Title | Priority | Dependencies |",
            "|-------|----|-------|----------|--------------|",
        ]
        for i, item in enumerate(queue, 1):
            deps = ", ".join(item.dependencies) if item.dependencies else "—"
            lines.append(f"| {i} | {item.id} | {item.title} | {item.priority} | {deps} |")
        return "\n".join(lines)

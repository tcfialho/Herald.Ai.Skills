"""
Nexus Core - State Manager

Manages persistent state for plan execution stored in .nexus/plan_state.json.
All mutations produce a new immutable snapshot — old entries are never overwritten,
only appended or superseded via the tasks dict.

Usage:
    sm = NexusStateManager(project_root=".")
    state = sm.create_plan_state("nexus_auth", "auth-system")
    sm.update_task_status("task-001", "in_progress", files=["src/models.py"])
    sm.update_task_status("task-001", "completed", files=["src/models.py", "tests/test_models.py"])
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

NEXUS_DIR = ".nexus"
STATE_FILE = "plan_state.json"
TASK_QUEUE_FILE = "task_queue.json"
EXECUTION_LOG_FILE = "execution_log.json"

VALID_TASK_STATUSES = {"pending", "in_progress", "completed", "skipped", "failed"}
TERMINAL_STATUSES = {"completed", "skipped"}


class NexusStateManager:
    """Thread-unsafe single-process state manager for Nexus plan execution."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.nexus_dir = self.project_root / NEXUS_DIR
        self.state_path = self.nexus_dir / STATE_FILE
        self.task_queue_path = self.nexus_dir / TASK_QUEUE_FILE
        self.execution_log_path = self.nexus_dir / EXECUTION_LOG_FILE
        self._ensure_nexus_dir()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create_plan_state(self, plan_id: str, plan_name: str) -> dict:
        """Initialise a fresh plan state. Fails if a state already exists."""
        if self.state_path.exists():
            raise FileExistsError(
                f"Plan state already exists at {self.state_path}. "
                "Load it with load_state() or delete .nexus/ to restart."
            )
        state = {
            "plan_id": plan_id,
            "plan_name": plan_name,
            "execution_mandate": "COMPLETE_ALL_TASKS_NO_EXCEPTIONS",
            "anti_mock_blocked": True,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
            "status": "active",
            "tasks": {},
            "feature_branch": f"feature/{plan_name}",
            "specs_path": f".nexus/{plan_name}/spec.md",
            "certificate_path": f".nexus/{plan_name}/review.md",
        }
        self._write_state(state)
        return state

    def load_state(self) -> Optional[dict]:
        """Return current state or None if no state file exists."""
        if not self.state_path.exists():
            return None
        with open(self.state_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def load_state_or_raise(self) -> dict:
        """Return current state or raise if nothing is initialised."""
        state = self.load_state()
        if state is None:
            raise FileNotFoundError(
                "No active plan state found. Run /plan first to initialise .nexus/plan_state.json."
            )
        return state

    def mark_plan_complete(self) -> None:
        state = self.load_state_or_raise()
        state["status"] = "completed"
        state["completed_at"] = _utcnow()
        self._write_state(state)

    # ------------------------------------------------------------------
    # Task mutations
    # ------------------------------------------------------------------

    def register_tasks(self, task_definitions: list[dict]) -> None:
        """Bulk-register tasks from task_breaker output into state."""
        state = self.load_state_or_raise()
        for task in task_definitions:
            task_id = task["id"]
            if task_id not in state["tasks"]:
                state["tasks"][task_id] = {
                    "status": "pending",
                    "title": task.get("title", ""),
                    "files": task.get("files", []),
                    "registered_at": _utcnow(),
                }
        self._write_state(state)

    def update_task_status(
        self,
        task_id: str,
        status: str,
        files: Optional[list[str]] = None,
        error: Optional[str] = None,
    ) -> dict:
        """Update a single task's status and return the new full state."""
        if status not in VALID_TASK_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_TASK_STATUSES}.")
        state = self.load_state_or_raise()
        if task_id not in state["tasks"]:
            state["tasks"][task_id] = {}
        entry = state["tasks"][task_id]
        entry["status"] = status
        entry["updated_at"] = _utcnow()
        if files:
            entry["files"] = files
        if error:
            entry["error"] = error
        else:
            entry.pop("error", None)
        if status == "completed":
            entry["completed_at"] = _utcnow()
        elif status == "in_progress":
            entry["started_at"] = _utcnow()
        self._write_state(state)
        self._append_execution_log(task_id, status, error)
        return state

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_pending_tasks(self) -> list[str]:
        """Return IDs of all tasks not in TERMINAL_STATUSES.

        ``failed`` tasks are intentionally included — they are not terminal
        and will re-enter the execution queue for retry on the next /dev pass.
        Only ``completed`` and ``skipped`` tasks are excluded.
        """
        state = self.load_state()
        if state is None:
            return []
        return [
            tid
            for tid, tdata in state["tasks"].items()
            if tdata.get("status") not in TERMINAL_STATUSES
        ]

    def get_completed_tasks(self) -> list[str]:
        state = self.load_state()
        if state is None:
            return []
        return [
            tid
            for tid, tdata in state["tasks"].items()
            if tdata.get("status") == "completed"
        ]

    def is_plan_complete(self) -> bool:
        state = self.load_state()
        if state is None:
            return False
        tasks = state.get("tasks", {})
        if not tasks:
            return False
        return all(t.get("status") in TERMINAL_STATUSES for t in tasks.values())

    def completion_percentage(self) -> float:
        state = self.load_state()
        if state is None:
            return 0.0
        tasks = state.get("tasks", {})
        if not tasks:
            return 0.0
        done = sum(1 for t in tasks.values() if t.get("status") in TERMINAL_STATUSES)
        return round(done / len(tasks) * 100, 2)

    # ------------------------------------------------------------------
    # Task queue (serialised priority list)
    # ------------------------------------------------------------------

    def save_task_queue(self, tasks: list[dict]) -> None:
        with open(self.task_queue_path, "w", encoding="utf-8") as fh:
            json.dump(tasks, fh, indent=2, ensure_ascii=False)

    def load_task_queue(self) -> list[dict]:
        if not self.task_queue_path.exists():
            return []
        with open(self.task_queue_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_nexus_dir(self) -> None:
        self.nexus_dir.mkdir(parents=True, exist_ok=True)

    def _write_state(self, state: dict) -> None:
        state["updated_at"] = _utcnow()
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)

    def _append_execution_log(
        self, task_id: str, status: str, error: Optional[str] = None
    ) -> None:
        log: list[dict] = []
        if self.execution_log_path.exists():
            with open(self.execution_log_path, "r", encoding="utf-8") as fh:
                log = json.load(fh)
        entry: dict = {"timestamp": _utcnow(), "task_id": task_id, "status": status}
        if error:
            entry["error"] = error
        log.append(entry)
        with open(self.execution_log_path, "w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


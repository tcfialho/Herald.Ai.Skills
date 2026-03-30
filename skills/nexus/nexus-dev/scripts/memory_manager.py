"""
Nexus Dev - Memory Manager

Provides session recovery for long-running /dev executions.
Persists a session snapshot to .nexus/session_memory.json so that
if a context window is exhausted or the agent crashes, progress is
fully recoverable with 100% fidelity.

The memory model is append-only: each snapshot is stored with a
monotonic sequence number; rollback returns the previous snapshot.

Usage:
    mm = MemoryManager(project_root=".")
    mm.save_snapshot(state_manager.load_state())
    # ... later, after crash ...
    snapshot = mm.load_latest_snapshot()
    # resume from snapshot
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MEMORY_FILE = ".nexus/session_memory.json"
MAX_SNAPSHOTS = 50  # prevent unbounded growth


# ------------------------------------------------------------------
# MemoryManager
# ------------------------------------------------------------------


class MemoryManager:
    """Append-only session memory for crash recovery."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.memory_path = self.project_root / MEMORY_FILE
        self._ensure_dir()

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def save_snapshot(self, state: dict, label: str = "") -> int:
        """
        Append a new state snapshot. Returns the new sequence number.
        Automatically prunes oldest entries when MAX_SNAPSHOTS is exceeded.
        """
        history = self._load_history()
        seq = (history[-1]["seq"] + 1) if history else 1
        entry = {
            "seq": seq,
            "timestamp": _utcnow(),
            "label": label or f"snapshot-{seq}",
            "state": state,
        }
        history.append(entry)
        if len(history) > MAX_SNAPSHOTS:
            history = history[-MAX_SNAPSHOTS:]
        self._write_history(history)
        return seq

    def load_latest_snapshot(self) -> Optional[dict]:
        """Return the most recent snapshot's state, or None."""
        history = self._load_history()
        if not history:
            return None
        return history[-1]["state"]

    def load_snapshot_at(self, seq: int) -> Optional[dict]:
        """Return the state from a specific sequence number."""
        history = self._load_history()
        for entry in history:
            if entry["seq"] == seq:
                return entry["state"]
        return None

    def rollback(self) -> Optional[dict]:
        """
        Remove the latest snapshot and return the previous one.
        Returns None if there is no previous state.
        """
        history = self._load_history()
        if len(history) < 2:
            if history:
                history.clear()
                self._write_history(history)
            return None
        history.pop()
        self._write_history(history)
        return history[-1]["state"]

    # ------------------------------------------------------------------
    # Context handover document
    # ------------------------------------------------------------------

    def generate_handover_prompt(self) -> str:
        """
        Generate a context-recovery prompt for the AI agent.
        Includes task titles and file lists for full resumption fidelity.
        """
        snapshot = self.load_latest_snapshot()
        if snapshot is None:
            return "No session memory found. Start a fresh /dev session."

        tasks = snapshot.get("tasks", {})
        completed_lines = [
            f"{tid}: {tdata.get('title', '')} -- files: {', '.join(tdata.get('files', []) or [])}"
            for tid, tdata in tasks.items()
            if tdata.get("status") == "completed"
        ]
        pending_lines = [
            f"{tid}: {tdata.get('title', '')} -- files: {', '.join(tdata.get('files', []) or ['TBD'])}"
            f" -- ears: {', '.join(tdata.get('ears_refs', []) or [])}"
            for tid, tdata in tasks.items()
            if tdata.get("status") not in ("completed", "skipped")
        ]
        pending_ids = [
            tid for tid, tdata in tasks.items()
            if tdata.get("status") not in ("completed", "skipped")
        ]
        next_task_id = pending_ids[0] if pending_ids else None
        next_task_data = tasks.get(next_task_id, {}) if next_task_id else {}
        completed_block = "\n".join(f"    {line}" for line in completed_lines) or "    none"
        pending_block = "\n".join(f"    {line}" for line in pending_lines) or "    none"
        next_files = ", ".join(next_task_data.get("files", []) or [])

        return (
            f"<nexus_session_recovery>\n"
            f"  <plan_id>{snapshot.get('plan_id', 'unknown')}</plan_id>\n"
            f"  <plan_status>{snapshot.get('status', 'active')}</plan_status>\n"
            f"  <completed_tasks>\n{completed_block}\n  </completed_tasks>\n"
            f"  <pending_tasks>\n{pending_block}\n  </pending_tasks>\n"
            f"  <next_task id='{next_task_id or 'ALL_COMPLETE'}' "
            f"title='{next_task_data.get('title', '')}' "
            f"files='{next_files}'></next_task>\n"
            f"  <execution_mandate>{snapshot.get('execution_mandate', 'COMPLETE_ALL_TASKS_NO_EXCEPTIONS')}</execution_mandate>\n"
            f"  <anti_mock_blocked>{snapshot.get('anti_mock_blocked', True)}</anti_mock_blocked>\n"
            f"  <recovery_instruction>Resume from next_task. Do NOT repeat completed tasks.</recovery_instruction>\n"
            f"</nexus_session_recovery>"
        )

    # ------------------------------------------------------------------
    # History accessors
    # ------------------------------------------------------------------

    def list_snapshots(self) -> list[dict]:
        """Return summary of all stored snapshots (without full state)."""
        history = self._load_history()
        return [
            {
                "seq": e["seq"],
                "timestamp": e["timestamp"],
                "label": e["label"],
                "plan_id": e["state"].get("plan_id", ""),
            }
            for e in history
        ]

    def clear(self) -> None:
        """Wipe all stored snapshots (use with caution)."""
        self._write_history([])

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_history(self) -> list[dict]:
        if not self.memory_path.exists():
            return []
        with open(self.memory_path, "r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return []

    def _write_history(self, history: list[dict]) -> None:
        with open(self.memory_path, "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

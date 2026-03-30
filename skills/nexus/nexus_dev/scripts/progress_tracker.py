"""
Nexus Dev - Progress Tracker

Computes and displays real-time execution progress during /dev.
Reads directly from .nexus/plan_state.json so it can be called
at any point — even from a shell script — to visualise status.

Usage:
    tracker = ProgressTracker(project_root=".")
    tracker.print_report()        # ASCII progress bar + table
    md = tracker.to_markdown()    # for embedding in a log file
"""

from __future__ import annotations

import sys
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


# ------------------------------------------------------------------
# Progress Tracker
# ------------------------------------------------------------------


class ProgressTracker:
    def __init__(self, project_root: str = ".") -> None:
        self.state_manager = NexusStateManager(project_root)

    # ------------------------------------------------------------------
    # Core metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        state = self.state_manager.load_state()
        if state is None:
            return {
                "plan_id": "none",
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
                "failed": 0,
                "skipped": 0,
                "pct_complete": 0.0,
                "status": "uninitialised",
            }
        tasks = state.get("tasks", {})
        counts: dict[str, int] = {}
        for tdata in tasks.values():
            s = tdata.get("status", "pending")
            counts[s] = counts.get(s, 0) + 1

        total = len(tasks)
        completed = counts.get("completed", 0) + counts.get("skipped", 0)
        pct = round(completed / total * 100, 1) if total else 0.0

        return {
            "plan_id": state.get("plan_id", ""),
            "plan_name": state.get("plan_name", ""),
            "total": total,
            "completed": counts.get("completed", 0),
            "in_progress": counts.get("in_progress", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0),
            "pct_complete": pct,
            "status": state.get("status", "active"),
        }

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def ascii_bar(self, pct: float, width: int = 20) -> str:
        filled = int(width * pct / 100)
        bar = "=" * filled + "." * (width - filled)
        return f"({bar}) {pct:.0f}%"

    # Status icon map
    _STATUS_ICON: dict[str, str] = {
        "completed": "✅",
        "in_progress": "🔄",
        "pending": "⏳",
        "failed": "❌",
        "skipped": "⏭",
    }

    def print_report(self, as_code_block: bool = False) -> None:
        """Print progress panel to stdout.

        Args:
            as_code_block: When True, wraps output in a ```text fence so it
                renders as a formatted panel inside AI chat interfaces
                (Cursor, Windsurf, Copilot).  Set to True in all /dev loop
                calls so the panel is visible in the chat, not just in tool
                output.
        """
        m = self.get_metrics()
        state = self.state_manager.load_state()
        plan_label = m.get("plan_name") or m["plan_id"] or "(no plan)"

        bar = self.ascii_bar(m["pct_complete"])
        header = f"📊 PROGRESSO: {plan_label} — {m['completed']}/{m['total']} tasks {bar}"

        lines: list[str] = [header, ""]

        if state and state.get("tasks"):
            for tid, tdata in state["tasks"].items():
                icon = self._STATUS_ICON.get(tdata.get("status", "pending"), "❓")
                title = tdata.get("title", "")
                title_str = f" {title}" if title else ""
                active_marker = "  ← EXECUTANDO AGORA" if tdata.get("status") == "in_progress" else ""
                # IDs rendered as uppercase to match SKILL.md template
                lines.append(f"   {icon} [{tid.upper()}]{title_str}{active_marker}")

        report = "\n".join(lines)
        if as_code_block:
            print(f"```text\n{report}\n```")
        else:
            print(report)

    def to_markdown(self) -> str:
        m = self.get_metrics()
        state = self.state_manager.load_state()
        lines = [
            f"## 📊 Progress — {m.get('plan_name', m['plan_id'])}\n",
            f"**{m['pct_complete']}%** complete "
            f"({m['completed']}/{m['total']} tasks)\n",
            "| Status | Count |",
            "|--------|-------|",
            f"| ✅ Completed | {m['completed']} |",
            f"| 🔄 In Progress | {m['in_progress']} |",
            f"| ⏳ Pending | {m['pending']} |",
            f"| ❌ Failed | {m['failed']} |",
            f"| ⏭ Skipped | {m['skipped']} |",
            "",
        ]

        if state and state.get("tasks"):
            lines += ["### Task Details\n", "| ID | Status | Files |", "|----|--------|-------|"]
            for tid, tdata in state["tasks"].items():
                status_icon = {
                    "completed": "✅",
                    "in_progress": "🔄",
                    "pending": "⏳",
                    "failed": "❌",
                    "skipped": "⏭",
                }.get(tdata.get("status", "pending"), "❓")
                files = ", ".join(f"`{f}`" for f in tdata.get("files", []))
                lines.append(f"| {tid} | {status_icon} {tdata.get('status')} | {files or '_TBD_'} |")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Checkpoint check (called every N files by execution engine)
    # ------------------------------------------------------------------

    def should_checkpoint(self, files_created_since_last_checkpoint: int, interval: int = 3) -> bool:
        return files_created_since_last_checkpoint >= interval

    def log_checkpoint(self, task_id: str, files_created: list[str]) -> str:
        """Return a structured checkpoint log entry."""
        m = self.get_metrics()
        return (
            f"[NEXUS CHECKPOINT] task={task_id} "
            f"files={files_created} "
            f"progress={m['pct_complete']}% "
            f"({m['completed']}/{m['total']})"
        )


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    ProgressTracker(project_root=root).print_report()

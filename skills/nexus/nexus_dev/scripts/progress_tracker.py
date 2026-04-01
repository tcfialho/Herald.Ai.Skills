"""
Nexus Dev - Progress Tracker (Hierarchical View)

Renders real-time execution progress during /dev with full
UC → Story → Task hierarchy and inline verification status.

Reads:
  - .nexus/plan_state.json   (task statuses)
  - .nexus/{plan}/stories.json (UC → Story mapping)
  - .nexus/{plan}/tasks.json   (Story → Task mapping + verify results)
  - .nexus/{plan}/submit_failures.json (circuit breaker state)

Falls back gracefully to flat task list when hierarchy files are absent.

Usage:
    tracker = ProgressTracker(project_root=".")
    tracker.print_report(as_code_block=True)
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

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
# Icons & Formatting
# ------------------------------------------------------------------

_STATUS_ICON: dict[str, str] = {
    "completed": "✅",
    "in_progress": "🔄",
    "pending": "⏳",
    "failed": "❌",
    "skipped": "⏭",
}

_VERIFY_ICON: dict[str, str] = {
    "passed": "🟢",
    "failed": "🔴",
    "not_run": "⚪",
}


def _ascii_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {pct:.0f}%"


def _story_status(task_statuses: list[str]) -> str:
    """Derive story status from its child tasks."""
    if not task_statuses:
        return "pending"
    if all(s in ("completed", "skipped") for s in task_statuses):
        return "completed"
    if any(s == "failed" for s in task_statuses):
        return "failed"
    if any(s == "in_progress" for s in task_statuses):
        return "in_progress"
    if any(s in ("completed", "skipped") for s in task_statuses):
        return "in_progress"  # Partially done
    return "pending"


def _uc_status(story_statuses: list[str]) -> str:
    """Derive UC status from its child stories."""
    return _story_status(story_statuses)


# ------------------------------------------------------------------
# Progress Tracker
# ------------------------------------------------------------------


class ProgressTracker:
    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.state_manager = NexusStateManager(project_root)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _detect_plan_name(self) -> str:
        """Extract plan_name from active state."""
        state = self.state_manager.load_state()
        if state:
            return state.get("plan_name", "")
        return ""

    def _load_json(self, path: Path) -> list | dict | None:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _load_stories(self, plan_name: str) -> list[dict]:
        data = self._load_json(self.project_root / ".nexus" / plan_name / "stories.json")
        return data if isinstance(data, list) else []

    def _load_tasks(self, plan_name: str) -> list[dict]:
        data = self._load_json(self.project_root / ".nexus" / plan_name / "tasks.json")
        return data if isinstance(data, list) else []

    def _load_submit_failures(self, plan_name: str) -> dict:
        data = self._load_json(self.project_root / ".nexus" / plan_name / "submit_failures.json")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Hierarchy builder
    # ------------------------------------------------------------------

    def _build_hierarchy(
        self, stories: list[dict], tasks: list[dict], state_tasks: dict, failures: dict
    ) -> OrderedDict:
        """Build UC → Story → Task tree.

        Returns:
            OrderedDict[uc_id] = {
                "name": str,
                "status": str,
                "stories": OrderedDict[story_id] = {
                    "desc": str,
                    "fluxo_id": str,
                    "status": str,
                    "tasks": [{task_id, title, tipo, status, verify_status, failures}]
                }
            }
        """
        # Index tasks by historia_ref
        tasks_by_story: dict[str, list[dict]] = {}
        for task in tasks:
            story_ref = task.get("historia_ref", "")
            tasks_by_story.setdefault(story_ref, []).append(task)

        # Build UC → Story → Task
        tree: OrderedDict = OrderedDict()
        for story in stories:
            uc_ref = story.get("uc_ref", "UC-??")
            story_id = story.get("id", "")

            if uc_ref not in tree:
                tree[uc_ref] = {
                    "name": uc_ref,
                    "stories": OrderedDict(),
                }

            story_tasks = tasks_by_story.get(story_id, [])
            enriched_tasks = []
            for task in story_tasks:
                task_id = task.get("id", "")
                state_entry = state_tasks.get(task_id, {})
                task_status = state_entry.get("status", "pending")
                fail_data = failures.get(task_id, {})
                consecutive_fails = fail_data.get("consecutive_failures", 0)

                # Determine verification status
                if task_status == "completed":
                    verify_status = "passed"
                elif consecutive_fails > 0:
                    verify_status = "failed"
                else:
                    verify_status = "not_run"

                enriched_tasks.append({
                    "id": task_id,
                    "title": task.get("title", ""),
                    "tipo": task.get("tipo", ""),
                    "status": task_status,
                    "verify_status": verify_status,
                    "consecutive_failures": consecutive_fails,
                    "verify_cmd": task.get("verify_cmd", ""),
                })

            task_statuses = [t["status"] for t in enriched_tasks]

            tree[uc_ref]["stories"][story_id] = {
                "desc": story.get("descricao_breve", ""),
                "fluxo_id": story.get("fluxo_id", ""),
                "status": _story_status(task_statuses),
                "tasks": enriched_tasks,
            }

        # Compute UC statuses
        for uc_data in tree.values():
            story_statuses = [s["status"] for s in uc_data["stories"].values()]
            uc_data["status"] = _uc_status(story_statuses)

        # Collect orphan tasks (tasks without a matching story)
        all_story_ids = {s.get("id", "") for s in stories}
        orphan_tasks = []
        for task in tasks:
            if task.get("historia_ref", "") not in all_story_ids:
                task_id = task.get("id", "")
                state_entry = state_tasks.get(task_id, {})
                task_status = state_entry.get("status", "pending")
                fail_data = failures.get(task_id, {})
                consecutive_fails = fail_data.get("consecutive_failures", 0)
                verify_status = "passed" if task_status == "completed" else (
                    "failed" if consecutive_fails > 0 else "not_run"
                )
                orphan_tasks.append({
                    "id": task_id,
                    "title": task.get("title", ""),
                    "tipo": task.get("tipo", ""),
                    "status": task_status,
                    "verify_status": verify_status,
                    "consecutive_failures": consecutive_fails,
                    "verify_cmd": task.get("verify_cmd", ""),
                })

        if orphan_tasks:
            tree["_ORPHAN"] = {
                "name": "Tasks Avulsas",
                "status": _story_status([t["status"] for t in orphan_tasks]),
                "stories": OrderedDict({
                    "_direct": {
                        "desc": "Tasks sem história vinculada",
                        "fluxo_id": "",
                        "status": _story_status([t["status"] for t in orphan_tasks]),
                        "tasks": orphan_tasks,
                    }
                }),
            }

        return tree

    # ------------------------------------------------------------------
    # Core metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        state = self.state_manager.load_state()
        if state is None:
            return {
                "plan_id": "none",
                "plan_name": "",
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
    # Hierarchical report
    # ------------------------------------------------------------------

    def _render_hierarchical(self, tree: OrderedDict, metrics: dict) -> list[str]:
        """Render the Story-focused view grouped into Kanban Lanes."""
        plan_label = metrics.get("plan_name") or metrics.get("plan_id", "(no plan)")
        pct = metrics["pct_complete"]

        lines: list[str] = [
            f"📊 PROGRESSO: {plan_label}  [ {pct:.0f}% ]",
            ""
        ]

        # Categorize stories into lanes
        feito: list[dict] = []
        em_progresso: list[dict] = []
        backlog: list[dict] = []

        # Flatten stories from tree to maintain topological order
        for uc_id, uc_data in tree.items():
            for story_id, story_data in uc_data.get("stories", {}).items():
                if story_id == "_direct":
                    # Handle orphan tasks by creating a virtual story
                    if not story_data["tasks"]:
                        continue
                    virtual_story = {
                        "id": "Tarefas Avulsas",
                        "desc": "",
                        "status": story_data["status"],
                        "tasks": story_data["tasks"]
                    }
                    if virtual_story["status"] == "completed":
                        feito.append(virtual_story)
                    elif virtual_story["status"] in ("in_progress", "failed"):
                        em_progresso.append(virtual_story)
                    else:
                        backlog.append(virtual_story)
                    continue

                story_entry = {
                    "id": story_id,
                    "desc": story_data["desc"],
                    "status": story_data["status"],
                    "tasks": story_data["tasks"]
                }

                if story_entry["status"] == "completed":
                    feito.append(story_entry)
                elif story_entry["status"] in ("in_progress", "failed"):
                    em_progresso.append(story_entry)
                else:
                    backlog.append(story_entry)

        # Helper to render a specific story
        def render_story(s_data: dict, collapsed: bool) -> list[str]:
            s_lines = []
            s_id = s_data["id"]
            desc = s_data["desc"]
            desc_str = f" {desc}" if desc else ""
            tasks = s_data["tasks"]
            total_s_tasks = len(tasks)
            done_s_tasks = sum(1 for t in tasks if t["status"] in ("completed", "skipped"))
            
            if collapsed:
                prefix = f"✅ [{s_id}]" if s_id != "Tarefas Avulsas" else "✅ Tarefas Avulsas"
                s_lines.append(f"{prefix}{desc_str} ({done_s_tasks}/{total_s_tasks})")
            else:
                prefix = f"📖 [{s_id}]" if s_id != "Tarefas Avulsas" else "📖 Tarefas Avulsas"
                s_lines.append(f"{prefix}{desc_str}")
                for task in tasks:
                    t_icon = _STATUS_ICON.get(task["status"], "❓")
                    v_icon = _VERIFY_ICON.get(task["verify_status"], "⚪")
                    tipo = f" [{task['tipo']}]" if task.get("tipo") else ""
                    active = " ← EXECUTANDO" if task["status"] == "in_progress" else ""
                    
                    fail_warn = ""
                    if task["consecutive_failures"] > 0:
                        fail_warn = f" (⚠️ {task['consecutive_failures']}x falha)"
                    if task["consecutive_failures"] >= 3:
                        fail_warn = " (🚨 CIRCUIT BREAKER)"

                    s_lines.append(
                        f"  {t_icon} {v_icon} [{task['id']}] {task['title']}{tipo}{active}{fail_warn}"
                    )
            return s_lines

        # Append lanes to output
        if feito:
            for s in feito:
                lines.extend(render_story(s, collapsed=True))
            lines.append("")

        if em_progresso:
            for s in em_progresso:
                lines.extend(render_story(s, collapsed=False))
                lines.append("")

        if backlog:
            for s in backlog:
                lines.extend(render_story(s, collapsed=False))
                lines.append("")

        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()

        return lines

    # ------------------------------------------------------------------
    # Flat report fallback
    # ------------------------------------------------------------------

    def _render_flat(self, state: dict, metrics: dict) -> list[str]:
        """Render flat task list (fallback when stories/tasks files are absent)."""
        plan_label = metrics.get("plan_name") or metrics.get("plan_id", "(no plan)")
        bar = _ascii_bar(metrics["pct_complete"])
        done = metrics["completed"] + metrics.get("skipped", 0)

        lines: list[str] = [
            f"📊 PROGRESSO: {plan_label}",
            f"   {bar}  ({done}/{metrics['total']} tasks)",
            "",
        ]

        if state and state.get("tasks"):
            for tid, tdata in state["tasks"].items():
                icon = _STATUS_ICON.get(tdata.get("status", "pending"), "❓")
                title = tdata.get("title", "")
                title_str = f" {title}" if title else ""
                active = "  ← EXECUTANDO AGORA" if tdata.get("status") == "in_progress" else ""
                lines.append(f"   {icon} [{tid.upper()}]{title_str}{active}")

        return lines

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def print_report(self, as_code_block: bool = False) -> None:
        """Print progress panel to stdout.

        Renders hierarchical UC → Story → Task view when stories.json and
        tasks.json exist. Falls back to flat task list otherwise.
        """
        metrics = self.get_metrics()
        state = self.state_manager.load_state()
        plan_name = self._detect_plan_name()
        state_tasks = state.get("tasks", {}) if state else {}

        stories = self._load_stories(plan_name) if plan_name else []
        tasks = self._load_tasks(plan_name) if plan_name else []
        failures = self._load_submit_failures(plan_name) if plan_name else {}

        has_hierarchy = bool(stories and tasks)

        if has_hierarchy:
            tree = self._build_hierarchy(stories, tasks, state_tasks, failures)
            lines = self._render_hierarchical(tree, metrics)
        else:
            lines = self._render_flat(state, metrics)

        report = "\n".join(lines)
        if as_code_block:
            print(f"```text\n{report}\n```")
        else:
            print(report)

    def to_markdown(self) -> str:
        """Return a Markdown report (table-based) for embedding in logs."""
        metrics = self.get_metrics()
        state = self.state_manager.load_state()
        plan_name = self._detect_plan_name()
        state_tasks = state.get("tasks", {}) if state else {}

        stories = self._load_stories(plan_name) if plan_name else []
        tasks = self._load_tasks(plan_name) if plan_name else []
        failures = self._load_submit_failures(plan_name) if plan_name else {}

        lines = [
            f"## 📊 Progress — {metrics.get('plan_name', metrics['plan_id'])}\n",
            f"**{metrics['pct_complete']}%** complete "
            f"({metrics['completed']}/{metrics['total']} tasks)\n",
            "| Status | Count |",
            "|--------|-------|",
            f"| ✅ Completed | {metrics['completed']} |",
            f"| 🔄 In Progress | {metrics['in_progress']} |",
            f"| ⏳ Pending | {metrics['pending']} |",
            f"| ❌ Failed | {metrics['failed']} |",
            f"| ⏭ Skipped | {metrics['skipped']} |",
            "",
        ]

        if stories and tasks:
            tree = self._build_hierarchy(stories, tasks, state_tasks, failures)
            lines.append("### Hierarchical View\n")
            for uc_id, uc_data in tree.items():
                uc_icon = _STATUS_ICON.get(uc_data["status"], "❓")
                lines.append(f"#### {uc_icon} {uc_id}\n")
                for story_id, story_data in uc_data["stories"].items():
                    s_icon = _STATUS_ICON.get(story_data["status"], "❓")
                    lines.append(f"**{s_icon} {story_id}** — {story_data['desc']}\n")
                    lines.append("| Task | Status | Verify | Type | Title |")
                    lines.append("|------|--------|--------|------|-------|")
                    for task in story_data["tasks"]:
                        t_icon = _STATUS_ICON.get(task["status"], "❓")
                        v_icon = _VERIFY_ICON.get(task["verify_status"], "⚪")
                        lines.append(
                            f"| {task['id']} | {t_icon} | {v_icon} "
                            f"| {task['tipo']} | {task['title']} |"
                        )
                    lines.append("")
        elif state and state.get("tasks"):
            lines += ["### Task Details\n", "| ID | Status | Files |", "|----|--------|-------|"]
            for tid, tdata in state_tasks.items():
                icon = _STATUS_ICON.get(tdata.get("status", "pending"), "❓")
                files = ", ".join(f"`{f}`" for f in tdata.get("files", []))
                lines.append(f"| {tid} | {icon} {tdata.get('status')} | {files or '_TBD_'} |")

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

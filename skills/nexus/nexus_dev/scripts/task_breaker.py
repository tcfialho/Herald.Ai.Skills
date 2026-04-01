"""
Nexus Dev - Task Breaker

Parses a spec.md document and decomposes it into an ordered list of
atomic tasks (1-3 files each), ready to feed into the execution engine.

Enforcement of the Atomic Task Rule:
  - Each task MAY touch at most 3 files
  - Tasks that would touch more are automatically split
  - Each task must have a clear "done" criterion derived from its EARS req

Decision Propagation:
  If decision_manifest.json exists alongside spec.md, each task receives
  a `decision_context` list of planning decisions. This ensures that the
  LLM agent executing the task has access to key architectural decisions
  even without reading the full spec.md.

Usage:
    breaker = TaskBreaker(plan_path=".nexus/nexus_auth-system/spec.md")
    tasks = breaker.break_tasks()
    breaker.save(".nexus/nexus_auth-system/tasks.json")
    print(breaker.to_markdown())
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
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

from nexus_core.file_utils import read_text, write_text, ensure_dir
from nexus_core.proto_loader import load_proto_index
from nexus_core.validation import validate_task_definition, ValidationResult

MAX_FILES_PER_TASK = 3

_TASK_SECTION_RE = re.compile(r"^###\s+(task-\d+):\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_FILE_LINE_RE = re.compile(r"\*\*Files:\*\*\s+(.+)", re.IGNORECASE)
_DESC_LINE_RE = re.compile(r"\*\*Description:\*\*\s+(.+)", re.IGNORECASE)
_PRIORITY_LINE_RE = re.compile(r"\*\*Priority:\*\*\s+(high|medium|low)", re.IGNORECASE)
_DEPENDS_LINE_RE = re.compile(r"\*\*Depends on:\*\*\s+(.+)", re.IGNORECASE)
_EARS_LINE_RE = re.compile(r"\*\*EARS:\*\*\s+(.+)", re.IGNORECASE)
_CRITERIA_BLOCK_RE = re.compile(r"\*\*Acceptance criteria:\*\*\s*\n((?:\s*-\s+.+\n?)+)", re.IGNORECASE)


# ------------------------------------------------------------------
# Task model
# ------------------------------------------------------------------


@dataclass
class AtomicTask:
    id: str
    title: str
    objetivo: str = ""                                            # Direct instruction: what to code
    tipo: str = "Dados"                                           # Dados | UI | API | Integração
    nivel: int = 0                                                # Dependency level: 0 | 1 | 2
    historia_ref: str = ""                                        # Parent story ID (child → parent)
    pre_condicao: list[str] = field(default_factory=list)         # Structural deps (real code from prior tasks)
    pos_condicao: list[str] = field(default_factory=list)         # Exit contract (technical, verifiable, binary)
    diretiva_de_teste: str = ""                                   # Integração | Unitário | Componente | E2E
    verify_cmd: str = ""                                          # Shell command to verify task completion (used by SubmitGate)
    files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    ears_refs: list[str] = field(default_factory=list)
    status: str = "pending"
    # Legacy fields — backward compatibility
    description: str = ""
    priority: str = "medium"
    acceptance_criteria: list[str] = field(default_factory=list)
    done_criteria: str = ""
    decision_context: list[dict] = field(default_factory=list)  # Planning decisions (from /plan)
    proto_refs: list[dict] = field(default_factory=list)         # Visual design decisions (from /proto)

    def validate(self) -> ValidationResult:
        return validate_task_definition(asdict(self))


# ------------------------------------------------------------------
# Breaker
# ------------------------------------------------------------------


class TaskBreaker:
    """Parses a Nexus spec.md and exposes atomic tasks."""

    def __init__(self, plan_path: "str | Path") -> None:
        self.plan_path = Path(plan_path)
        self._tasks: list[AtomicTask] = []
        self._parsed = False

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def break_tasks(self) -> list[AtomicTask]:
        """Parse the plan file and return the list of atomic tasks."""
        if not self.plan_path.exists():
            raise FileNotFoundError(f"Plan file not found: {self.plan_path}")
        content = read_text(self.plan_path)
        self._decision_manifest = self._load_decision_manifest()
        self._proto_index = load_proto_index(self.plan_path.parent)
        self._tasks = self._parse(content)
        self._parsed = True
        return self._tasks

    def _load_decision_manifest(self) -> list[dict]:
        """Load decision_manifest.json if it exists alongside spec.md."""
        manifest_path = self.plan_path.parent / "decision_manifest.json"
        if not manifest_path.exists():
            return []
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("decisions", [])

    def _parse(self, content: str) -> list[AtomicTask]:
        tasks: list[AtomicTask] = []
        sections = _TASK_SECTION_RE.split(content)

        # sections alternates: [preamble, id1, title1, body1, id2, title2, body2, ...]
        i = 1
        while i < len(sections) - 1:
            task_id = sections[i].strip()
            title = sections[i + 1].strip()
            body = sections[i + 2] if i + 2 < len(sections) else ""

            files = self._extract_files(body)
            description = self._extract_description(body)
            priority = self._extract_priority(body)
            dependencies = self._extract_dependencies(body)
            ears_refs = self._extract_ears_refs(body)
            acceptance_criteria = self._extract_acceptance_criteria(body)

            raw_tasks = self._enforce_atomic_rule(
                task_id, title, description, files, priority, dependencies,
                ears_refs, acceptance_criteria,
            )
            tasks.extend(raw_tasks)
            i += 3

        # If no explicit tasks found, synthesise from EARS requirements
        if not tasks:
            tasks = self._synthesise_from_ears(content)

        return tasks

    def _extract_files(self, body: str) -> list[str]:
        match = _FILE_LINE_RE.search(body)
        if not match:
            return []
        raw = match.group(1)
        files = [f.strip().strip("`") for f in raw.split(",") if f.strip() and f.strip() != "_TBD_"]
        return files

    def _extract_description(self, body: str) -> str:
        match = _DESC_LINE_RE.search(body)
        return match.group(1).strip() if match else ""

    def _extract_priority(self, body: str) -> str:
        match = _PRIORITY_LINE_RE.search(body)
        return match.group(1).lower() if match else "medium"

    def _extract_dependencies(self, body: str) -> list[str]:
        match = _DEPENDS_LINE_RE.search(body)
        if not match:
            return []
        return [d.strip() for d in match.group(1).split(",") if d.strip()]

    def _extract_ears_refs(self, body: str) -> list[str]:
        match = _EARS_LINE_RE.search(body)
        if not match:
            return []
        return [r.strip() for r in match.group(1).split(",") if r.strip()]

    def _extract_acceptance_criteria(self, body: str) -> list[str]:
        match = _CRITERIA_BLOCK_RE.search(body)
        if not match:
            return []
        raw_block = match.group(1)
        return [line.lstrip(" -").strip() for line in raw_block.splitlines() if line.strip()]

    # ------------------------------------------------------------------
    # Atomic Rule enforcement
    # ------------------------------------------------------------------

    def _enforce_atomic_rule(
        self,
        task_id: str,
        title: str,
        description: str,
        files: list[str],
        priority: str,
        dependencies: list[str],
        ears_refs: list[str] = (),
        acceptance_criteria: list[str] = (),
    ) -> list[AtomicTask]:
        """Split tasks that exceed MAX_FILES_PER_TASK into smaller ones."""
        if len(files) <= MAX_FILES_PER_TASK:
            return [
                AtomicTask(
                    id=task_id,
                    title=title,
                    description=description,
                    files=files,
                    priority=priority,
                    dependencies=dependencies,
                    ears_refs=list(ears_refs),
                    acceptance_criteria=list(acceptance_criteria),
                    done_criteria="All files compile, pass linter, and unit tests pass.",
                    decision_context=list(self._decision_manifest),
                )
            ]

        # Split into chunks of MAX_FILES_PER_TASK
        result: list[AtomicTask] = []
        chunks = [files[i : i + MAX_FILES_PER_TASK] for i in range(0, len(files), MAX_FILES_PER_TASK)]
        for part, chunk in enumerate(chunks, 1):
            split_id = f"{task_id}-p{part}"
            result.append(
                AtomicTask(
                    id=split_id,
                    title=f"{title} (part {part}/{len(chunks)})",
                    description=description,
                    files=chunk,
                    priority=priority,
                    dependencies=dependencies if part == 1 else [f"{task_id}-p{part - 1}"],
                    ears_refs=list(ears_refs),
                    acceptance_criteria=list(acceptance_criteria),
                    done_criteria=f"Part {part} files compile and unit tests pass.",
                    decision_context=list(self._decision_manifest),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Fallback: synthesise from EARS
    # ------------------------------------------------------------------

    def _synthesise_from_ears(self, content: str) -> list[AtomicTask]:
        """Create generic tasks from EARS requirements if no explicit tasks exist."""
        ears_re = re.compile(
            r"^-?\s*`?(?:WHEN|WHILE|IF|WHERE)\s+.+`?$", re.IGNORECASE | re.MULTILINE
        )
        matches = list(ears_re.finditer(content))
        if not matches:
            return []
        tasks = []
        for i, match in enumerate(matches, 1):
            requirement_text = match.group(0).strip().lstrip("-").strip().strip("`")
            title_text = (requirement_text[:60] + "...") if len(requirement_text) > 60 else requirement_text
            tasks.append(
                AtomicTask(
                    id=f"task-{i:03d}",
                    title=f"Implement: {title_text}",
                    description=f"Derived from EARS requirement: {requirement_text}",
                    ears_refs=[requirement_text],
                    priority="medium",
                    done_criteria="EARS requirement has a passing integration test.",
                )
            )
        return tasks

    # ------------------------------------------------------------------
    # Priority ordering
    # ------------------------------------------------------------------

    def get_ordered_queue(self) -> list[AtomicTask]:
        """PROIBIDO para execução em produção.

        Este método ordena por prioridade sem respeitar dependências declaradas,
        podendo executar uma task antes de suas dependências estarem completas.
        Use PriorityQueue.build_from_task_file() para ordenação topológica correta.
        Ver SKILL.md Passo 3.
        """
        raise RuntimeError(
            "get_ordered_queue() é PROIBIDO para execução — use "
            "PriorityQueue.build_from_task_file() para ordenação "
            "topológica que respeita dependências. Ver SKILL.md Passo 3."
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: "str | Path") -> Path:
        if not self._parsed:
            self.break_tasks()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(t) for t in self._tasks]
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return p

    @classmethod
    def load_from_json(cls, path: "str | Path") -> list[AtomicTask]:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        loaded = []
        for t in raw:
            t.setdefault("decision_context", [])
            t.setdefault("proto_refs", [])
            loaded.append(AtomicTask(**t))
        return loaded

    @staticmethod
    def enrich_from_stories(
        tasks: list[AtomicTask], stories_path: "str | Path"
    ) -> None:
        """Post-hoc enrichment: propagate proto_refs from parent stories to tasks.

        Call this after the agent sets historia_ref on each task.
        Tasks whose historia_ref matches a story will inherit that story's proto_refs,
        ensuring the full reference chain: UC → Story (with proto_refs) → Task.
        """
        stories_file = Path(stories_path)
        if not stories_file.exists():
            return
        with open(stories_file, "r", encoding="utf-8") as fh:
            raw_stories = json.load(fh)

        story_index = {s["id"]: s for s in raw_stories}
        for task in tasks:
            if not task.historia_ref:
                continue
            parent_story = story_index.get(task.historia_ref)
            if parent_story and not task.proto_refs:
                task.proto_refs = parent_story.get("proto_refs", [])

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        if not self._tasks:
            return "_No tasks parsed. Call break_tasks() first._"
        lines = [
            f"## 🗂 Task Queue ({len(self._tasks)} tasks)\n",
            "| ID | Title | Files | Priority | Status |",
            "|----|-------|-------|----------|--------|",
        ]
        for t in self._tasks:
            files_str = ", ".join(f"`{f}`" for f in t.files) if t.files else "_TBD_"
            lines.append(f"| {t.id} | {t.title} | {files_str} | {t.priority} | {t.status} |")
        return "\n".join(lines)


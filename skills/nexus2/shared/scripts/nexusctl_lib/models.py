from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Task:
    task_id: str
    title: str
    status: str
    marker: str
    verify_cmd: str
    files: list[str]
    covers: list[str]


@dataclass
class Story:
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def story_id(self) -> str:
        return str(self.meta.get("id") or self.path.stem.split("_", 1)[0])

    @property
    def status(self) -> str:
        return str(self.meta.get("status") or "READY")

    @property
    def owner(self) -> str:
        return str(self.meta.get("owner") or "")

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.story_id)

    @property
    def priority(self) -> int:
        try:
            return int(self.meta.get("priority", 0))
        except (TypeError, ValueError):
            return 0

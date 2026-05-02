import os
import re
import shutil
import socket
from pathlib import Path

from .errors import NexusError


def default_agent_id() -> str:
    return os.environ.get("NEXUS_AGENT_ID") or f"codex-{socket.gethostname().lower()}"


def script_root() -> Path:
    return Path(__file__).resolve().parents[2]


def templates_dir() -> Path:
    return script_root() / "templates"


def normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def slugify(value: object) -> str:
    text = str(value or "story").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "story"


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for path in [current, *current.parents]:
        if (path / "nexus").exists():
            return path
    return current


def nexus_dir(root: Path) -> Path:
    return root / "nexus"


def runtime_dir(root: Path) -> Path:
    return root / ".temp" / "nexus"


def backlog_dir(root: Path) -> Path:
    return nexus_dir(root) / "backlog"


def ensure_initialized(root: Path) -> None:
    if not nexus_dir(root).exists():
        raise NexusError("nexus/ not found. Run 'nexusctl init' first.")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def copy_template(template_name: str, target: Path, force: bool = False) -> None:
    if target.exists() and not force:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(templates_dir() / template_name, target)

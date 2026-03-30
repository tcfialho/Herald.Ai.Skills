"""
Nexus Core - File Utilities

Common file operations used by all Nexus skills.
All path arguments accept str or Path; returned paths are always Path objects.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------
# Directory helpers
# ------------------------------------------------------------------


def ensure_dir(path: "str | Path") -> Path:
    """Create directory and all parents if they do not exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------
# Text I/O
# ------------------------------------------------------------------


def read_text(path: "str | Path", encoding: str = "utf-8") -> str:
    """Read a file's full contents as text."""
    with open(path, "r", encoding=encoding) as fh:
        return fh.read()


def write_text(path: "str | Path", content: str, encoding: str = "utf-8") -> Path:
    """Write text to a file, creating parent directories as needed."""
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "w", encoding=encoding) as fh:
        fh.write(content)
    return p


def append_text(path: "str | Path", content: str, encoding: str = "utf-8") -> Path:
    """Append text to an existing file (or create it)."""
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "a", encoding=encoding) as fh:
        fh.write(content)
    return p


# ------------------------------------------------------------------
# Hashing
# ------------------------------------------------------------------


def sha256_file(path: "str | Path") -> str:
    """Return hex SHA-256 digest of a file's binary contents."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(content: str) -> str:
    """Return hex SHA-256 digest of a UTF-8 encoded string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------
# Directory listing
# ------------------------------------------------------------------


def list_markdown_files(directory: "str | Path") -> list[Path]:
    """Recursively list all .md files sorted by path."""
    return sorted(Path(directory).rglob("*.md"))


def list_python_files(directory: "str | Path") -> list[Path]:
    """Recursively list all .py files sorted by path."""
    return sorted(Path(directory).rglob("*.py"))


def find_specs_dir(plan_name: str, root: "str | Path" = ".") -> Optional[Path]:
    """Return the .nexus plan directory for a given plan name, or None if missing."""
    candidate = Path(root) / ".nexus" / plan_name
    return candidate if candidate.exists() else None


# ------------------------------------------------------------------
# Template rendering
# ------------------------------------------------------------------


def copy_template(
    template_path: "str | Path",
    dest_path: "str | Path",
    replacements: Optional[dict[str, str]] = None,
) -> Path:
    """
    Copy a Mustache-style template file to dest_path, substituting
    {{KEY}} tokens with values from the replacements dict.
    """
    content = read_text(template_path)
    if replacements:
        for key, value in replacements.items():
            content = content.replace("{{" + key + "}}", value)
    return write_text(dest_path, content)


def render_template(template_content: str, replacements: dict[str, str]) -> str:
    """Substitute {{KEY}} tokens in a template string and return rendered output."""
    for key, value in replacements.items():
        template_content = template_content.replace("{{" + key + "}}", value)
    return template_content


# ------------------------------------------------------------------
# Safe deletion
# ------------------------------------------------------------------


def safe_delete(path: "str | Path") -> bool:
    """
    Delete a file or directory tree.  Returns True if something was removed,
    False if the path did not exist.  Raises on permission errors.
    """
    p = Path(path)
    if not p.exists():
        return False
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return True

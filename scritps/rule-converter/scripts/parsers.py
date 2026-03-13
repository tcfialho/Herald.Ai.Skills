"""
Parsers for each supported AI IDE rule format.

Each parser reads a source file and returns a normalized RuleDocument —
the canonical intermediate representation consumed by all serializers.

Supported source IDEs:
  cursor      .cursor/rules/*.mdc  or  .cursorrules (legacy)
  windsurf    .windsurf/rules/*.md  or  .windsurfrules (legacy)
  cline       .clinerules/*.md  or  .clinerules (single file)
  claude      CLAUDE.md  or  ~/.claude/CLAUDE.md
  copilot     .github/copilot-instructions.md
              .github/instructions/*.instructions.md
  kiro        .kiro/steering/<name>/<name>.md
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Canonical intermediate representation
# ---------------------------------------------------------------------------

@dataclass
class RuleDocument:
    """Normalized, IDE-agnostic representation of an AI coding rule."""

    content: str                                              # Markdown body
    description: str = ""                                    # Short one-liner
    globs: list[str] = field(default_factory=list)           # File-glob patterns
    always_apply: bool = False                               # Fires on every prompt
    source_ide: str = ""                                     # Which IDE produced this
    source_file: str = ""                                    # Original file path
    activation_mode: str = "always"                          # always | manual | model_decision | glob
    rule_name: str = ""                                      # Human-readable name (stem)
    extra: dict[str, Any] = field(default_factory=dict)     # IDE-specific preserved fields


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?", re.DOTALL)
_KEY_RE = re.compile(r"^(?P<key>[a-zA-Z_][a-zA-Z0-9_]*):\s*(?P<value>.*)$")


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    """
    Minimal YAML parser covering only the scalar/list subset used by IDE frontmatters.
    Avoids a hard dependency on PyYAML.
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    list_items: list[str] = []
    in_list = False

    for raw_line in raw.splitlines():
        line = raw_line.rstrip()

        if line.startswith("  - ") or line.startswith("- "):
            item = line.lstrip("- ").strip().strip('"').strip("'")
            if current_key:
                list_items.append(item)
                in_list = True
            continue

        m = _KEY_RE.match(line)
        if m:
            if in_list and current_key:
                result[current_key] = list_items[:]
                list_items = []
                in_list = False

            current_key = m.group("key")
            raw_value = m.group("value").strip().strip('"').strip("'")

            if raw_value in ("", "|", ">"):
                result[current_key] = ""
            elif raw_value.lower() in ("true", "yes"):
                result[current_key] = True
            elif raw_value.lower() in ("false", "no"):
                result[current_key] = False
            elif raw_value.startswith("["):
                items = [v.strip().strip('"').strip("'") for v in raw_value.strip("[]").split(",") if v.strip()]
                result[current_key] = items
            else:
                result[current_key] = raw_value

    if in_list and current_key:
        result[current_key] = list_items

    return result


def _strip_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    return _parse_simple_yaml(m.group("yaml")), text[m.end():]


def _globs_from_meta(meta: dict[str, Any]) -> list[str]:
    raw = meta.get("globs", [])
    if isinstance(raw, str):
        return [g.strip() for g in raw.split(",") if g.strip()]
    return [str(g) for g in raw] if raw else []


def _stem(path: str | Path) -> str:
    return Path(path).stem


# ---------------------------------------------------------------------------
# IDE parsers
# ---------------------------------------------------------------------------

def parse_cursor(source: Path) -> RuleDocument:
    """
    Cursor .mdc files  →  .cursor/rules/*.mdc  or legacy .cursorrules

    Frontmatter:
      description: <string>
      globs: <comma-list or YAML list>
      alwaysApply: <bool>
    """
    text = source.read_text(encoding="utf-8")
    meta, body = _strip_frontmatter(text)
    is_legacy = source.suffix == "" or source.name == ".cursorrules"
    always = meta.get("alwaysApply", True) if not is_legacy else True

    return RuleDocument(
        content=body.strip(),
        description=meta.get("description", ""),
        globs=_globs_from_meta(meta),
        always_apply=bool(always),
        source_ide="cursor",
        source_file=str(source),
        activation_mode="always" if always else "glob",
        rule_name=_stem(source),
        extra={k: v for k, v in meta.items() if k not in ("description", "globs", "alwaysApply")},
    )


def parse_windsurf(source: Path) -> RuleDocument:
    """
    Windsurf .md files  →  .windsurf/rules/*.md  or legacy .windsurfrules

    Frontmatter (Wave 8+):
      trigger: always_on | manual | model_decision | glob
      globs: <list>
      description: <string>
    """
    text = source.read_text(encoding="utf-8")
    meta, body = _strip_frontmatter(text)
    trigger = meta.get("trigger", "always_on")
    activation_map = {
        "always_on":      "always",
        "always":         "always",
        "manual":         "manual",
        "model_decision": "model_decision",
        "glob":           "glob",
    }
    activation = activation_map.get(str(trigger).lower(), "always")

    return RuleDocument(
        content=body.strip(),
        description=meta.get("description", ""),
        globs=_globs_from_meta(meta),
        always_apply=(activation == "always"),
        source_ide="windsurf",
        source_file=str(source),
        activation_mode=activation,
        rule_name=_stem(source),
        extra={k: v for k, v in meta.items() if k not in ("description", "globs", "trigger")},
    )


def parse_cline(source: Path) -> RuleDocument:
    """
    Cline .md files  →  .clinerules/*.md  or  .clinerules (single file)

    Pure Markdown, always-on. Cline concatenates all files under .clinerules/.
    """
    text = source.read_text(encoding="utf-8")
    meta, body = _strip_frontmatter(text)

    return RuleDocument(
        content=(body.strip() if meta else text.strip()),
        description=meta.get("description", ""),
        globs=_globs_from_meta(meta),
        always_apply=True,
        source_ide="cline",
        source_file=str(source),
        activation_mode="always",
        rule_name=_stem(source),
    )


def parse_claude(source: Path) -> RuleDocument:
    """
    Claude Code  →  CLAUDE.md  or  ~/.claude/CLAUDE.md

    Pure Markdown, always-on.
    """
    text = source.read_text(encoding="utf-8")
    meta, body = _strip_frontmatter(text)
    is_global = "global" in str(source).lower() or str(source).startswith(str(Path.home()))

    return RuleDocument(
        content=(body.strip() if meta else text.strip()),
        description=meta.get("description", f"Claude Code {'global' if is_global else 'project'} rules"),
        globs=[],
        always_apply=True,
        source_ide="claude",
        source_file=str(source),
        activation_mode="always",
        rule_name="CLAUDE",
        extra={"is_global": is_global},
    )


def parse_copilot(source: Path) -> RuleDocument:
    """
    GitHub Copilot  →  .github/copilot-instructions.md
                       .github/instructions/*.instructions.md (path-specific)

    Path-specific files use `applyTo` glob in frontmatter.
    """
    text = source.read_text(encoding="utf-8")
    meta, body = _strip_frontmatter(text)
    apply_to = meta.get("applyTo", "**")
    globs = [apply_to] if isinstance(apply_to, str) else list(apply_to)
    is_path_specific = source.name.endswith(".instructions.md")

    return RuleDocument(
        content=(body.strip() if meta else text.strip()),
        description=meta.get("description", "GitHub Copilot custom instructions"),
        globs=globs,
        always_apply=not is_path_specific,
        source_ide="copilot",
        source_file=str(source),
        activation_mode="glob" if is_path_specific else "always",
        rule_name=_stem(source),
        extra={"applyTo": apply_to},
    )


def parse_kiro(source: Path) -> RuleDocument:
    """
    Kiro AI IDE  →  .kiro/steering/<name>/<name>.md

    Frontmatter:
      inclusion: always | fileMatch | manual
      fileMatchPattern: <glob>   (only when inclusion: fileMatch)
    """
    text = source.read_text(encoding="utf-8")
    meta, body = _strip_frontmatter(text)

    inclusion       = meta.get("inclusion", "always")
    file_match_glob = meta.get("fileMatchPattern", "")
    globs           = [file_match_glob] if file_match_glob else []
    activation      = "glob" if inclusion == "fileMatch" and globs else (
                      "manual" if inclusion == "manual" else "always")

    return RuleDocument(
        content=body.strip() if meta else text.strip(),
        description=meta.get("description", ""),
        globs=globs,
        always_apply=(activation == "always"),
        source_ide="kiro",
        source_file=str(source),
        activation_mode=activation,
        rule_name=_stem(source),
        extra={"inclusion": inclusion, "fileMatchPattern": file_match_glob},
    )


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

PARSERS: dict[str, Any] = {
    "cursor":   parse_cursor,
    "windsurf": parse_windsurf,
    "cline":    parse_cline,
    "claude":   parse_claude,
    "copilot":  parse_copilot,
    "kiro":     parse_kiro,
}


def detect_source_ide(source: Path) -> str | None:
    """
    Best-effort auto-detection of source IDE from path, name and content.
    Returns a key from PARSERS or None.
    """
    name  = source.name.lower()
    parts = [p.lower() for p in source.parts]

    if name.endswith(".mdc") or ".cursor" in parts or name == ".cursorrules":
        return "cursor"
    if ".windsurf" in parts or name == ".windsurfrules":
        return "windsurf"
    if ".clinerules" in parts or name == ".clinerules":
        return "cline"
    if name == "claude.md" or ".claude" in parts:
        return "claude"
    if ".github" in parts and ("copilot" in name or "instructions" in name):
        return "copilot"
    if ".kiro" in parts or "steering" in parts:
        return "kiro"

    # Content fingerprinting
    try:
        head = source.read_text(encoding="utf-8", errors="ignore")[:512]
    except OSError:
        return None

    if "alwaysApply" in head:
        return "cursor"
    if "trigger:" in head and ("always_on" in head or "model_decision" in head):
        return "windsurf"
    if "applyTo:" in head:
        return "copilot"
    if "inclusion:" in head and ("always" in head or "fileMatch" in head):
        return "kiro"

    return None

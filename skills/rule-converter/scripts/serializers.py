"""
Serializers for each supported AI IDE rule format.

Two output modes — the caller (converter.py) picks the right serializer
and resolves output_dir before calling here:

  repo   (default)
    output_dir = <base>/rules/<ide>/
    Produces:  <base>/rules/cursor/<name>.mdc
               <base>/rules/windsurf/<name>.md
               ...

  deploy
    output_dir = <base>  (project root)
    Produces:  <base>/.cursor/rules/<name>.mdc
               <base>/.windsurf/rules/<name>.md
               ...

Supported target IDEs: cursor, windsurf, cline, claude, copilot
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from parsers import RuleDocument


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            elif len(value) == 1:
                lines.append(f"{key}: {value[0]}")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        else:
            escaped = str(value).replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
    lines.append("---")
    return "\n".join(lines)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _filename(doc: RuleDocument, extension: str) -> str:
    name = doc.rule_name.replace(" ", "_").replace("/", "_") or "rule"
    return f"{name}{extension}"


# ---------------------------------------------------------------------------
# Shared meta builders
# ---------------------------------------------------------------------------

def _cursor_meta(doc: RuleDocument) -> dict:
    meta: dict = {"description": doc.description or "AI coding rules"}
    meta["globs"] = doc.globs if doc.globs else "*"
    meta["alwaysApply"] = doc.always_apply
    return meta


def _windsurf_meta(doc: RuleDocument) -> dict:
    trigger_map = {
        "always":         "always_on",
        "manual":         "manual",
        "model_decision": "model_decision",
        "glob":           "glob",
    }
    trigger = trigger_map.get(doc.activation_mode, "always_on")
    meta: dict = {"trigger": trigger}
    if doc.description:
        meta["description"] = doc.description
    if doc.globs and trigger == "glob":
        meta["globs"] = doc.globs
    return meta


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------

def serialize_cursor(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """repo → output_dir/<name>.mdc"""
    text = _frontmatter(_cursor_meta(doc)) + "\n\n" + doc.content + "\n"
    return [_write(output_dir / _filename(doc, ".mdc"), text)]


def serialize_cursor_deploy(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """deploy → output_dir/.cursor/rules/<name>.mdc"""
    text = _frontmatter(_cursor_meta(doc)) + "\n\n" + doc.content + "\n"
    return [_write(output_dir / ".cursor" / "rules" / _filename(doc, ".mdc"), text)]


# ---------------------------------------------------------------------------
# Windsurf
# ---------------------------------------------------------------------------

def serialize_windsurf(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """repo → output_dir/<name>.md"""
    text = _frontmatter(_windsurf_meta(doc)) + "\n\n" + doc.content + "\n"
    return [_write(output_dir / _filename(doc, ".md"), text)]


def serialize_windsurf_deploy(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """deploy → output_dir/.windsurf/rules/<name>.md"""
    text = _frontmatter(_windsurf_meta(doc)) + "\n\n" + doc.content + "\n"
    return [_write(output_dir / ".windsurf" / "rules" / _filename(doc, ".md"), text)]


# ---------------------------------------------------------------------------
# Cline
# ---------------------------------------------------------------------------

def _cline_text(doc: RuleDocument) -> str:
    prefix = f"<!-- {doc.description} -->\n\n" if doc.description else ""
    return prefix + doc.content + "\n"


def serialize_cline(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """repo → output_dir/<name>.md"""
    return [_write(output_dir / _filename(doc, ".md"), _cline_text(doc))]


def serialize_cline_deploy(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """deploy → output_dir/.clinerules/<name>.md"""
    return [_write(output_dir / ".clinerules" / _filename(doc, ".md"), _cline_text(doc))]


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

def _claude_text(doc: RuleDocument) -> str:
    header = f"<!-- {doc.description} -->\n\n" if doc.description else ""
    return header + doc.content + "\n"


def serialize_claude(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """repo/deploy → output_dir/CLAUDE.md  (same content, caller controls dir)"""
    return [_write(output_dir / "CLAUDE.md", _claude_text(doc))]


serialize_claude_deploy = serialize_claude


# ---------------------------------------------------------------------------
# GitHub Copilot
# ---------------------------------------------------------------------------

def _copilot_glob_text(doc: RuleDocument) -> str:
    apply_to = doc.globs[0] if doc.globs else "**"
    meta = {"applyTo": apply_to}
    extra = (
        f"\n<!-- Additional globs: {', '.join(doc.globs[1:])} -->"
        if len(doc.globs) > 1 else ""
    )
    return _frontmatter(meta) + extra + "\n\n" + doc.content + "\n"


def serialize_copilot(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """
    repo (output_dir = instructions/):
      Generates BOTH:
      1. instructions/global/<name>/copilot-instructions.md
      2. instructions/workspace/<name>/<name>.instructions.md
    """
    name = (doc.rule_name or "rule").replace(" ", "_")
    
    # 1. Global
    dest_g = output_dir / "global" / name / "copilot-instructions.md"
    path_g = _write(dest_g, doc.content + "\n")
    
    # 2. Workspace
    dest_w = output_dir / "workspace" / name / f"{name}.instructions.md"
    path_w = _write(dest_w, _copilot_glob_text(doc))
    
    return [path_g, path_w]


def serialize_copilot_deploy(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """
    deploy → output_dir/.github/copilot-instructions.md  (no globs)
             output_dir/.github/instructions/<name>.instructions.md  (globs)
    """
    if doc.globs:
        filename = f"{doc.rule_name or 'rule'}.instructions.md"
        path = output_dir / ".github" / "instructions" / filename
        return [_write(path, _copilot_glob_text(doc))]
    path = output_dir / ".github" / "copilot-instructions.md"
    return [_write(path, doc.content + "\n")]


# ---------------------------------------------------------------------------
# Kiro AI
# ---------------------------------------------------------------------------

def _kiro_meta(doc: RuleDocument) -> dict:
    """Build Kiro frontmatter from a RuleDocument."""
    meta: dict = {}
    if doc.globs and doc.activation_mode == "glob":
        meta["inclusion"] = "fileMatch"
        meta["fileMatchPattern"] = doc.globs[0]
    elif doc.activation_mode == "manual":
        meta["inclusion"] = "manual"
    else:
        meta["inclusion"] = "always"
    return meta


def serialize_kiro(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """
    repo  →  output_dir/<name>/<name>.md
    Mirrors the steering/<name>/<name>.md structure used in this repo.
    """
    name      = (doc.rule_name or "rule").replace(" ", "_")
    rule_dir  = output_dir / name
    filename  = f"{name}.md"
    text      = _frontmatter(_kiro_meta(doc)) + "\n" + doc.content + "\n"
    return [_write(rule_dir / filename, text)]


def serialize_kiro_deploy(doc: RuleDocument, output_dir: Path) -> list[Path]:
    """
    deploy  →  output_dir/.kiro/steering/<name>/<name>.md
    """
    name      = (doc.rule_name or "rule").replace(" ", "_")
    rule_dir  = output_dir / ".kiro" / "steering" / name
    filename  = f"{name}.md"
    text      = _frontmatter(_kiro_meta(doc)) + "\n" + doc.content + "\n"
    return [_write(rule_dir / filename, text)]





# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, tuple[Callable, Callable]] = {
    "cursor":   (serialize_cursor,   serialize_cursor_deploy),
    "windsurf": (serialize_windsurf, serialize_windsurf_deploy),
    "cline":    (serialize_cline,    serialize_cline_deploy),
    "claude":   (serialize_claude,   serialize_claude_deploy),
    "copilot":  (serialize_copilot,  serialize_copilot_deploy),
    "kiro":     (serialize_kiro,     serialize_kiro_deploy),
}

SERIALIZERS:        dict[str, Callable] = {k: v[0] for k, v in _REGISTRY.items()}
DEPLOY_SERIALIZERS: dict[str, Callable] = {k: v[1] for k, v in _REGISTRY.items()}
ALL_TARGETS: list[str] = list(_REGISTRY.keys())

REPO_SUBFOLDER: dict[str, str] = {
    "cursor":   "cursor",
    "windsurf": "windsurf",
    "cline":    "cline",
    "claude":   "claude",
    "copilot":  "copilot",
    "kiro":     "kiro",
}

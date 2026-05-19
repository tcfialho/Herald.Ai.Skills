import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import SpecError
from .markdown import extract_section, expected_file_artifacts
from .models import Story
from .paths import normalize_path, read_text, spec_dir
from .tasks import parse_tasks


def story_context_refs(story: Story) -> dict[str, Any]:
    refs = story.meta.get("context_refs") or {}
    return refs if isinstance(refs, dict) else {}


def is_spike_story(story: Story) -> bool:
    return story.story_id.startswith("SP-") or str(story.meta.get("type", "")).upper() == "SPIKE"


def validate_story_context_refs(root: Path, story: Story) -> list[str]:
    if story.status in ("QA", "DONE"):
        return []

    refs = story_context_refs(story)
    if not refs:
        if not is_spike_story(story):
            return [f"{story.story_id}: missing context_refs"]
        return []

    errors: list[str] = []
    product_refs = _list_value(refs.get("product"))
    architecture_refs = _list_value(refs.get("architecture"))
    design_mode = str(refs.get("design") or "none").strip().lower()

    if not product_refs and not is_spike_story(story):
        errors.append(f"{story.story_id}: context_refs.product is empty")
    if not architecture_refs and not is_spike_story(story):
        errors.append(f"{story.story_id}: context_refs.architecture is empty")
    if design_mode not in ("full", "none"):
        errors.append(f"{story.story_id}: context_refs.design must be 'full' or 'none'")

    ndir = spec_dir(root)
    spec_path = ndir / "spec.md"
    arch_path = ndir / "architecture.md"
    design_path = ndir / "design.md"
    if product_refs:
        errors.extend(_missing_refs(story.story_id, spec_path, product_refs, "product"))
    if architecture_refs:
        errors.extend(_missing_refs(story.story_id, arch_path, architecture_refs, "architecture"))
    if design_mode == "full" and not design_path.exists():
        errors.append(f"{story.story_id}: context_refs.design is full but .spec/design.md is missing")

    errors.extend(validate_implementation_targets(root, story))
    return errors


def resolved_story_context(root: Path, story: Story) -> str:
    refs = story_context_refs(story)
    if not refs:
        return ""

    errors = validate_story_context_refs(root, story)
    if errors:
        raise SpecError("context refs invalid: " + "; ".join(errors))

    ndir = spec_dir(root)
    spec_text = read_text(ndir / "spec.md")
    arch_text = read_text(ndir / "architecture.md")

    lines = [
        "# Resolved DotSpec Context",
        "",
        f"Story: {story.story_id}",
        "",
    ]

    product_refs = _list_value(refs.get("product"))
    if product_refs:
        lines.extend(["## Product", ""])
        for ref in product_refs:
            lines.extend(_render_ref_block(ref, spec_text, ".spec/spec.md"))

    architecture_refs = _list_value(refs.get("architecture"))
    if architecture_refs:
        lines.extend(["## Architecture", ""])
        for ref in architecture_refs:
            lines.extend(_render_ref_block(ref, arch_text, ".spec/architecture.md"))

    design_mode = str(refs.get("design") or "none").strip().lower()
    if design_mode == "full":
        design_path = ndir / "design.md"
        lines.extend(["## Design", "", f"[source: .spec/design.md]", "", read_text(design_path).strip(), ""])
    elif design_mode == "none":
        lines.extend(["## Design", "", "No design impact.", ""])

    return "\n".join(lines).rstrip() + "\n"


def validate_implementation_targets(root: Path, story: Story) -> list[str]:
    if is_spike_story(story):
        return []

    affected_files = expected_file_artifacts(story.body)
    if not affected_files:
        return []

    errors: list[str] = []
    architecture_context_refs = set(_list_value(story_context_refs(story).get("architecture")))
    architecture_file_refs, symbol_index = _load_architecture_indices(root)
    architecture_referenced_files = [
        file_path for file_path in affected_files if architecture_file_refs.get(normalize_path(file_path))
    ]
    targets = implementation_targets(story.body)
    if not targets:
        if architecture_referenced_files:
            return [
                f"{story.story_id}: missing Implementation Targets for architecture-referenced files: {', '.join(architecture_referenced_files)}"
            ]
        return []

    targets_by_file = {normalize_path(target["file"]): target for target in targets}

    for affected_file in affected_files:
        normalized_file = normalize_path(affected_file)
        required_refs = architecture_file_refs.get(normalized_file, set())
        if not required_refs:
            continue
        target = targets_by_file.get(normalized_file)
        if not target:
            errors.append(
                f"{story.story_id}: architecture-referenced file missing Implementation Target: {affected_file}"
            )
            continue
        target_refs = set(target["architecture_refs"])
        if not target_refs:
            errors.append(
                f"{story.story_id}: Implementation Target {affected_file} needs Architecture Ref because the file is referenced in architecture.md"
            )
        elif not required_refs.intersection(target_refs):
            errors.append(
                f"{story.story_id}: Implementation Target {affected_file} must reference one of {sorted(required_refs)} from architecture.md"
            )

    for target in targets:
        for architecture_ref in target["architecture_refs"]:
            if architecture_context_refs and architecture_ref not in architecture_context_refs:
                errors.append(
                    f"{story.story_id}: Implementation Target {target['file']} uses {architecture_ref} not listed in context_refs.architecture"
                )
            expected_symbols = target["expected_symbols"]
            known_symbol = symbol_index.get(architecture_ref)
            if known_symbol and "test coverage" not in {item.lower() for item in expected_symbols}:
                if not expected_symbols:
                    errors.append(
                        f"{story.story_id}: Implementation Target {target['file']} maps {architecture_ref} but is missing Expected Symbol {known_symbol}"
                    )
                elif known_symbol not in expected_symbols:
                    errors.append(
                        f"{story.story_id}: {target['file']} maps {architecture_ref} to expected symbol {expected_symbols}, but architecture defines {known_symbol}"
                    )

    task_refs = task_architecture_refs(story.body)
    task_files = {task.task_id: task.files for task in parse_tasks(story.body)}
    for task_id, files in task_files.items():
        task_required_refs: set[str] = set()
        for file_path in files:
            task_required_refs.update(architecture_file_refs.get(normalize_path(file_path), set()))
        if not task_required_refs:
            continue
        refs = set(task_refs.get(task_id, []))
        if not refs:
            errors.append(
                f"{story.story_id}/{task_id}: task needs architecture_refs because it touches architecture-referenced file(s)"
            )
        elif not task_required_refs.intersection(refs):
            errors.append(
                f"{story.story_id}/{task_id}: architecture_refs must include one of {sorted(task_required_refs)} from architecture.md"
            )

    for task_id, refs in task_refs.items():
        for architecture_ref in refs:
            if architecture_context_refs and architecture_ref not in architecture_context_refs:
                errors.append(f"{story.story_id}/{task_id}: architecture_ref {architecture_ref} not listed in context_refs.architecture")

    return errors


def implementation_targets(body: str) -> list[dict[str, Any]]:
    rows = _table_rows(extract_section(body, "Implementation Targets"))
    targets = []
    for row in rows:
        file_path = _clean_cell(row.get("file", ""))
        if not file_path:
            continue
        targets.append(
            {
                "file": file_path,
                "architecture_refs": _split_cell_values(row.get("architecture ref", "")),
                "expected_symbols": _split_cell_values(row.get("expected symbol", "")),
            }
        )
    return targets


def task_architecture_refs(body: str) -> dict[str, list[str]]:
    lines = body.splitlines()
    starts: list[tuple[int, str]] = []
    pattern = re.compile(r"^-\s+\[[ x>!]\]\s+(TASK-\d+):")
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            starts.append((idx, match.group(1)))

    refs_by_task: dict[str, list[str]] = {}
    for pos, (idx, task_id) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        mode = None
        refs: list[str] = []
        for block_line in lines[idx + 1 : end]:
            stripped = block_line.strip()
            if stripped.startswith("- architecture_refs:"):
                mode = "architecture_refs"
                continue
            if stripped.startswith("- ") and not block_line.startswith("    - "):
                mode = None
            if mode == "architecture_refs" and stripped.startswith("- "):
                refs.append(_clean_cell(stripped[2:]))
        if refs:
            refs_by_task[task_id] = refs
    return refs_by_task


@lru_cache(maxsize=None)
def _build_architecture_indices(arch_path_str: str, mtime_ns: int) -> tuple[dict[str, set[str]], dict[str, str]]:
    file_index: dict[str, set[str]] = {}
    symbol_index: dict[str, str] = {}
    for row in _table_rows(read_text(Path(arch_path_str))):
        ref_id = _clean_cell(row.get("id", ""))
        if not ref_id:
            continue
        for value in row.values():
            for file_path in _file_paths_from_cell(value):
                file_index.setdefault(normalize_path(file_path), set()).add(ref_id)
        symbol = _clean_cell(
            row.get("symbol")
            or row.get("class")
            or row.get("class / interface")
            or row.get("name")
            or ""
        )
        if symbol:
            symbol_index[ref_id] = symbol
    return file_index, symbol_index


def _load_architecture_indices(root: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    # validate_implementation_targets runs once per story; without this cache a
    # full-backlog audit re-reads and re-parses architecture.md for every story.
    # Keyed by mtime so edits invalidate it. Returned dicts/sets are shared from
    # the cache and must be treated as read-only by callers.
    arch_path = spec_dir(root) / "architecture.md"
    if not arch_path.exists():
        return {}, {}
    return _build_architecture_indices(str(arch_path), arch_path.stat().st_mtime_ns)


def _missing_refs(story_id: str, path: Path, refs: list[str], label: str) -> list[str]:
    if not path.exists():
        return [f"{story_id}: missing source document for {label}: {path}"]
    text = read_text(path)
    return [f"{story_id}: unresolved {label} ref {ref} in {path.name}" for ref in refs if not _resolve_ref(text, ref)]


def _render_ref_block(ref: str, text: str, source: str) -> list[str]:
    content = _resolve_ref(text, ref)
    if not content:
        content = f"[missing ref: {ref}]"
    return [f"### {ref}", "", f"[source: {source}]", "", content.strip(), ""]


def _resolve_ref(text: str, ref: str) -> str:
    return (
        _heading_block(text, ref)
        or _flow_block(text, ref)
        or _list_item_block(text, ref)
        or _table_row_block(text, ref)
    )


def _heading_block(text: str, ref: str) -> str:
    pattern = re.compile(rf"^(?P<marks>##+)\s+{re.escape(ref)}\b.*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    level = len(match.group("marks"))
    start = match.start()
    next_heading = re.search(rf"^#{{2,{level}}}\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _flow_block(text: str, ref: str) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if ref not in line:
            continue
        if not ("Flow" in line or ".FP" in ref or ".FA" in ref):
            continue
        block = [line]
        for next_line in lines[idx + 1 :]:
            stripped = next_line.strip()
            if not stripped:
                block.append(next_line)
                continue
            if stripped.startswith("**") or stripped.startswith("- **UC-") or stripped.startswith("### ") or stripped.startswith("## "):
                break
            block.append(next_line)
        return "\n".join(block).strip()
    return ""


def _list_item_block(text: str, ref: str) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not re.match(rf"^\s*-\s+(?:\[[ xX]\]\s+)?{re.escape(ref)}\b", line):
            continue
        block = [line]
        for next_line in lines[idx + 1 :]:
            if next_line.startswith("  ") or next_line.startswith("    "):
                block.append(next_line)
                continue
            break
        return "\n".join(block).strip()
    return ""


def _table_row_block(text: str, ref: str) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = _split_table_line(line)
        if not cells or _clean_cell(cells[0]) != ref:
            continue
        header_idx = _find_table_header(lines, idx)
        if header_idx is None:
            return line.strip()
        return "\n".join([lines[header_idx], lines[header_idx + 1], line]).strip()
    return ""


def _find_table_header(lines: list[str], row_idx: int) -> int | None:
    for idx in range(row_idx - 1, -1, -1):
        if not lines[idx].lstrip().startswith("|"):
            return None
        if _is_separator_row(lines[idx]):
            return idx - 1 if idx > 0 and lines[idx - 1].lstrip().startswith("|") else None
    return None


def _table_rows(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    rows: list[dict[str, str]] = []
    idx = 0
    while idx + 1 < len(lines):
        if not lines[idx].lstrip().startswith("|") or not _is_separator_row(lines[idx + 1]):
            idx += 1
            continue
        headers = [_normalize_header(cell) for cell in _split_table_line(lines[idx])]
        idx += 2
        while idx < len(lines) and lines[idx].lstrip().startswith("|"):
            if _is_separator_row(lines[idx]):
                idx += 1
                continue
            cells = _split_table_line(lines[idx])
            rows.append({headers[pos]: cells[pos].strip() for pos in range(min(len(headers), len(cells)))})
            idx += 1
    return rows


def _split_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", line))


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", _clean_cell(value).lower())


def _clean_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def _split_cell_values(value: str) -> list[str]:
    cleaned = _clean_cell(value)
    if not cleaned:
        return []
    return [_clean_cell(item) for item in re.split(r"\s*,\s*", cleaned) if _clean_cell(item)]


def _file_paths_from_cell(value: str) -> list[str]:
    candidates = re.findall(r"`([^`]+)`", value)
    if not candidates:
        candidates = re.split(r"\s*,\s*", _clean_cell(value))
    return [item for item in (_clean_cell(candidate) for candidate in candidates) if _looks_like_file_path(item)]


def _looks_like_file_path(value: str) -> bool:
    if not value or value.endswith(("/", "\\")) or "*" in value:
        return False
    if "/" not in value and "\\" not in value:
        return False
    last_segment = re.split(r"[\\/]", value)[-1]
    return "." in last_segment


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []

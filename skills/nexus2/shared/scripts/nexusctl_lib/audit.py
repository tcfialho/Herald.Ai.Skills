import os
import re
from pathlib import Path

from .constants import AUDIT_SKIP_DIRS, DEFAULT_BANNED_FOLDERS
from .evidence import files_within_write_scope, missing_files
from .markdown import (
    acceptance_criteria_ids,
    evidence_section,
    extract_section,
    expected_file_artifacts,
    parse_frontmatter,
)
from .paths import nexus_dir, normalize_path, read_text
from .stories import parse_story_filename, story_has_open_bugs
from .models import Story
from .tasks import parse_tasks


def validate_docs(root: Path) -> list[str]:
    errors: list[str] = []
    ndir = nexus_dir(root)
    spec = ndir / "spec.md"
    design = ndir / "design.md"
    arch = ndir / "architecture.md"

    if not spec.exists():
        errors.append("missing nexus/spec.md")
    else:
        spec_text = read_text(spec)
        for heading in ("Objective", "Use Cases", "Use Case Details", "Business Rules"):
            if f"## {heading}" not in spec_text:
                errors.append(f"spec.md missing section: {heading}")

    if design.exists():
        design_text = read_text(design)
        meta, _body = parse_frontmatter(design_text)
        if not meta:
            errors.append("design.md missing YAML front matter")
        headings = re.findall(r"^##\s+(.+)$", design_text, flags=re.MULTILINE)
        for heading in sorted({heading for heading in headings if headings.count(heading) > 1}):
            errors.append(f"design.md duplicate section: {heading}")

    if not arch.exists():
        errors.append("missing nexus/architecture.md")
    else:
        arch_text = read_text(arch)
        for needle in ("Herald Architecture", "## NFRs", "## Quality Gates"):
            if needle not in arch_text:
                errors.append(f"architecture.md missing required content: {needle}")
    return errors


def audit_story(root: Path, story: Story) -> list[str]:
    errors: list[str] = []
    parsed = parse_story_filename(story.path)
    if parsed["status"] != story.status:
        errors.append(f"{story.path.name}: filename status differs from front matter")
    if not story.meta.get("write_scope") or story.meta.get("write_scope") == ["TBD"]:
        errors.append(f"{story.story_id}: missing write_scope")

    ac_ids = acceptance_criteria_ids(story.body)
    tasks = parse_tasks(story.body)
    is_spike = story.story_id.startswith("SP-") or str(story.meta.get("type", "")).upper() == "SPIKE"
    if is_spike:
        if not extract_section(story.body, "Research Question"):
            errors.append(f"{story.story_id}: missing research question")
        if not spike_deliverables(story):
            errors.append(f"{story.story_id}: missing deliverables")
    elif not ac_ids:
        errors.append(f"{story.story_id}: missing acceptance criteria")
    if not tasks:
        errors.append(f"{story.story_id}: missing tasks")
    if not expected_file_artifacts(story.body):
        errors.append(f"{story.story_id}: missing expected artifacts")

    for task in tasks:
        if not task.verify_cmd or task.verify_cmd == "TBD":
            errors.append(f"{story.story_id}/{task.task_id}: missing verify_cmd")
        if not task.files:
            errors.append(f"{story.story_id}/{task.task_id}: missing files")
        out_of_scope = files_within_write_scope(story, task.files)
        if out_of_scope:
            errors.append(f"{story.story_id}/{task.task_id}: files outside write_scope: {', '.join(out_of_scope)}")
        if story.status in ("QA", "DONE"):
            missing = missing_files(root, task.files)
            if missing:
                errors.append(f"{story.story_id}/{task.task_id}: declared files missing: {', '.join(missing)}")

    if story.status in ("QA", "DONE"):
        missing_expected = missing_files(root, expected_file_artifacts(story.body))
        if missing_expected:
            errors.append(f"{story.story_id}: missing expected artifacts: {', '.join(missing_expected)}")
        evidence = evidence_section(story.body)
        if is_spike:
            missing_deliverables = [
                item for item in spike_deliverables(story) if item not in evidence
            ]
            if missing_deliverables:
                errors.append(f"{story.story_id}: deliverables without evidence: {', '.join(missing_deliverables)}")
        else:
            missing_ac = [ac_id for ac_id in ac_ids if ac_id not in evidence]
            if missing_ac:
                errors.append(f"{story.story_id}: acceptance criteria without evidence: {', '.join(missing_ac)}")
        if story_has_open_bugs(story):
            errors.append(f"{story.story_id}: open QA bugs remain")
    return errors


def spike_deliverables(story: Story) -> list[str]:
    section = extract_section(story.body, "Deliverables")
    return sorted(set(re.findall(r"\bDEL-\d+\b", section)))


def audit_project_structure(root: Path) -> list[str]:
    errors: list[str] = []
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in AUDIT_SKIP_DIRS]
        if current_path != root and current_path.name in DEFAULT_BANNED_FOLDERS:
            errors.append(f"banned folder present: {normalize_path(current_path.relative_to(root))}")
    return errors

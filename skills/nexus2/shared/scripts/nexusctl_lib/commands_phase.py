import argparse
import re
from pathlib import Path

from .audit import audit_story, validate_docs
from .commands_base import resolve_root
from .errors import NexusError
from .markdown import parse_frontmatter
from .paths import copy_template, ensure_initialized, nexus_dir, read_text
from .status import print_status
from .stories import list_stories


PHASES = ("spec", "design", "arch", "spike", "backlog", "dev", "qa")

PHASE_TEMPLATES = {
    "spec": ("spec_template.md", "spec.md"),
    "design": ("design_template.md", "design.md"),
    "arch": ("architecture_template.md", "architecture.md"),
}

NEXT_PHASE = {
    "spec": "Nexus 2.0 /design",
    "design": "Nexus 2.0 /arch",
    "arch": "Nexus 2.0 /spike if research is needed, otherwise Nexus 2.0 /backlog",
    "spike": "Nexus 2.0 /backlog",
    "backlog": "Nexus 2.0 /dev",
    "dev": "Nexus 2.0 /qa",
    "qa": "none",
}


def cmd_phase_check(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    errors = phase_start_errors(root, args.phase)
    if errors:
        print(f"PHASE_BLOCKED: {args.phase}")
        for error in errors:
            print(f"- {error}")
        raise NexusError(f"phase {args.phase} cannot start")
    materialize_phase_template(root, args.phase)
    print(f"PHASE_OK: {args.phase}")
    print_status(root)


def materialize_phase_template(root: Path, phase: str) -> None:
    entry = PHASE_TEMPLATES.get(phase)
    if not entry:
        return
    template_name, target_name = entry
    target = nexus_dir(root) / target_name
    if target.exists():
        return
    copy_template(template_name, target)


def cmd_phase_done(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    errors = phase_done_errors(root, args.phase)
    if errors:
        print(f"PHASE_INCOMPLETE: {args.phase}")
        for error in errors:
            print(f"- {error}")
        raise NexusError(f"phase {args.phase} is incomplete")
    print(f"PHASE_DONE: {args.phase}")
    next_phase = NEXT_PHASE[args.phase]
    if next_phase == "none":
        print("NEXT: Nexus 2.0 flow complete.")
    else:
        print(f"NEXT: Ask the user to call {next_phase}.")
    print_status(root)


def phase_start_errors(root: Path, phase: str) -> list[str]:
    if phase == "spec":
        return []
    if phase == "design":
        return require_ready(root, "spec")
    if phase == "arch":
        return require_ready(root, "spec") + require_ready(root, "design")
    if phase == "backlog":
        return require_ready(root, "spec") + require_ready(root, "design") + require_ready(root, "arch")
    if phase == "spike":
        return require_ready(root, "spec") + require_ready(root, "design") + require_ready(root, "arch")
    if phase == "dev":
        return require_ready(root, "backlog")
    if phase == "qa":
        return require_qa_story(root)
    return [f"unknown phase: {phase}"]


def phase_done_errors(root: Path, phase: str) -> list[str]:
    if phase in ("spec", "design", "arch", "spike", "backlog"):
        return unique_errors(phase_start_errors(root, phase) + require_ready(root, phase))
    if phase == "dev":
        stories = list_stories(root)
        if not stories:
            return ["no backlog stories found"]
        if any(story.status not in ("QA", "DONE") for story in stories):
            return ["all started DEV stories must be QA or DONE before ending /dev"]
        return []
    if phase == "qa":
        stories = list_stories(root)
        if not stories:
            return ["no backlog stories found"]
        if any(story.status != "DONE" for story in stories):
            return ["all stories must be DONE before ending /qa"]
        return []
    return [f"unknown phase: {phase}"]


def unique_errors(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def require_ready(root: Path, phase: str) -> list[str]:
    if phase == "spec":
        return artifact_errors(nexus_dir(root) / "spec.md", ("Objective", "Use Cases", "Use Case Details"))
    if phase == "design":
        return design_errors(nexus_dir(root) / "design.md")
    if phase == "arch":
        return artifact_errors(nexus_dir(root) / "architecture.md", ("Architectural Style", "NFRs", "Quality Gates"))
    if phase == "spike":
        return spike_errors(root)
    if phase == "backlog":
        return backlog_errors(root)
    return [f"unknown ready artifact: {phase}"]


def artifact_errors(path: Path, headings: tuple[str, ...]) -> list[str]:
    if not path.exists():
        return [f"missing {path}"]
    text = read_text(path)
    errors = [f"{path.name} still contains TBD placeholders"] if re.search(r"\bTBD\b", text) else []
    for heading in headings:
        if f"## {heading}" not in text:
            errors.append(f"{path.name} missing section: {heading}")
    return errors


def design_errors(path: Path) -> list[str]:
    errors = artifact_errors(path, ("Overview", "Colors", "Typography", "Components"))
    if path.exists():
        text = read_text(path)
        meta, _body = parse_frontmatter(text)
        if not meta:
            errors.append("design.md missing YAML front matter")
        prototype_dir = path.parent / "prototype"
        has_prototype = prototype_dir.exists() and any(item.is_file() for item in prototype_dir.iterdir())
        declares_no_ui = bool(re.search(r"\b(no ui|sem ui|no user interface|sem interface)\b", text, re.IGNORECASE))
        if not has_prototype and not declares_no_ui:
            errors.append("design phase requires at least one static prototype file or an explicit no-UI note")
    return errors


def backlog_errors(root: Path) -> list[str]:
    stories = list_stories(root)
    if not stories:
        return ["no backlog stories found"]
    errors = require_ready(root, "spec") + require_ready(root, "design") + require_ready(root, "arch")
    errors.extend(validate_docs(root))
    for story in stories:
        errors.extend(audit_story(root, story))
    return errors


def spike_errors(root: Path) -> list[str]:
    spec_path = nexus_dir(root) / "spec.md"
    if not spec_path.exists():
        return [f"missing {spec_path}"]
    text = read_text(spec_path)
    if "## Spikes" not in text:
        return ["spec.md missing ## Spikes section"]
    if "SP-" not in text:
        return ["spec.md has ## Spikes but no SP-* item"]
    if "Research Question" not in text and "Pergunta de Pesquisa" not in text:
        return ["spike spec missing research question"]
    if "Deliverables" not in text and "Entregáveis" not in text and "Entregaveis" not in text:
        return ["spike spec missing deliverables"]
    return []


def require_qa_story(root: Path) -> list[str]:
    stories = list_stories(root)
    if not stories:
        return ["no backlog stories found"]
    if all(story.status == "DONE" for story in stories):
        return []
    if not any(story.status == "QA" for story in stories):
        return ["no story is in QA status; run /dev first"]
    return []

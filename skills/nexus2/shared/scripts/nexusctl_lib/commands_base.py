import argparse
from pathlib import Path

from .audit import audit_project_structure, audit_story, validate_docs
from .errors import NexusError
from .paths import ensure_initialized, find_project_root, nexus_dir, runtime_dir
from .status import print_status
from .stories import list_stories, story_by_id


def resolve_root(args: argparse.Namespace) -> Path:
    return find_project_root(Path(args.root).resolve() if getattr(args, "root", "") else None)


def cmd_init(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
    ndir = nexus_dir(root)
    rdir = runtime_dir(root)
    (ndir / "backlog").mkdir(parents=True, exist_ok=True)
    (ndir / "prototype").mkdir(parents=True, exist_ok=True)
    (rdir / "locks").mkdir(parents=True, exist_ok=True)
    (rdir / "cache").mkdir(parents=True, exist_ok=True)
    print(f"OK initialized Nexus 2.0 at {root}")
    print_status(root)


def cmd_docs_validate(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    errors = validate_docs(root)
    if errors:
        print("DOCS INVALID")
        for error in errors:
            print(f"- {error}")
        raise NexusError("docs validation failed")
    print("DOCS VALID")
    print_status(root)


def cmd_status(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    print_status(root)


def cmd_audit(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    errors = validate_docs(root)
    errors.extend(audit_project_structure(root))
    stories = [story_by_id(root, args.story_id)] if args.story_id else list_stories(root)
    for story in stories:
        errors.extend(audit_story(root, story))
    if errors:
        print("AUDIT FAILED")
        for error in errors:
            print(f"- {error}")
        raise NexusError("audit failed")
    print("AUDIT PASSED")
    print_status(root)

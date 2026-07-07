#!/usr/bin/env python3
"""Build an installable copy of the skill-test skill, stripped of everything
that only matters inside THIS dev repo: its own dogfood test suite, docs meant
for humans reading the repo, and build/cache junk.

New files are included by default — there is no per-file allowlist. Only the
exclude rules below remove things; add a rule here if a new dev-only
file/folder pattern shows up (e.g. a new cache dir), not a per-file entry.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]  # skills/skill-test/

# Excluded only at the skill root (same name one level deeper IS shipped —
# e.g. this does not touch tests/fixtures/*/tests/ inside a target skill,
# because that lives outside SKILL_DIR entirely).
EXCLUDE_TOP_LEVEL_DIRS = {
    "release",  # this script's own output — never ship a release inside a release
    "tests",    # skill-test's OWN dogfood suite (contract/scenarios/fixtures/baselines
                # for testing skill-test itself) — irrelevant to an installed copy
}
EXCLUDE_TOP_LEVEL_FILES = {
    "README.md",       # repo documentation for humans, not needed at runtime
    "release.sh", "release.ps1", "release.bat",  # this build tooling itself
}

# Excluded at any depth, by name
EXCLUDE_ANY_DEPTH_DIRS = {"__pycache__", ".pytest_cache", ".git", ".ruff_cache", ".mypy_cache"}
EXCLUDE_ANY_DEPTH_FILE_SUFFIXES = (".pyc", ".pyo")
EXCLUDE_ANY_DEPTH_FILE_NAMES = {".DS_Store", "Thumbs.db"}

# Explicit nested exclusions, relative to SKILL_DIR (not top-level, so the
# top-level rule above doesn't cover them)
EXCLUDE_RELATIVE_PATHS = {
    "scripts/tests",             # skill-test's own unit tests (test_offline.py) — dev-only
    "scripts/build_release.py",  # this build tooling itself — not needed at runtime
}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(SKILL_DIR)
    parts = rel.parts
    if not parts:
        return False
    if path.is_dir() and parts[0] in EXCLUDE_TOP_LEVEL_DIRS and len(parts) == 1:
        return True
    if path.is_file() and len(parts) == 1 and parts[0] in EXCLUDE_TOP_LEVEL_FILES:
        return True
    if path.is_dir() and path.name in EXCLUDE_ANY_DEPTH_DIRS:
        return True
    if path.is_file():
        if path.name in EXCLUDE_ANY_DEPTH_FILE_NAMES:
            return True
        if path.suffix in EXCLUDE_ANY_DEPTH_FILE_SUFFIXES:
            return True
    rel_posix = rel.as_posix()
    for ex in EXCLUDE_RELATIVE_PATHS:
        if rel_posix == ex or rel_posix.startswith(ex + "/"):
            return True
    return False


def build(output_dir: Path) -> dict:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    included: list[str] = []
    excluded: list[str] = []

    def walk(src: Path, dst: Path) -> None:
        for entry in sorted(src.iterdir()):
            if should_skip(entry):
                excluded.append(str(entry.relative_to(SKILL_DIR).as_posix()))
                continue
            target = dst / entry.name
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                walk(entry, target)
            else:
                shutil.copy2(entry, target)
                included.append(str(entry.relative_to(SKILL_DIR).as_posix()))

    walk(SKILL_DIR, output_dir)
    return {"included": included, "excluded": excluded}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(SKILL_DIR / "release" / "skill-test"),
                        help="output directory for the installable copy")
    parser.add_argument("--zip", action="store_true", help="also produce a .zip next to the folder")
    args = parser.parse_args()

    output_dir = Path(args.out).resolve()
    result = build(output_dir)

    if not (output_dir / "SKILL.md").exists():
        print("ERROR: SKILL.md missing from release output — aborting", file=sys.stderr)
        sys.exit(1)

    zip_path = None
    if args.zip:
        zip_path = shutil.make_archive(
            str(output_dir), "zip", root_dir=output_dir.parent, base_dir=output_dir.name
        )

    print(f"Release built at: {output_dir}")
    print(f"Files included: {len(result['included'])}")
    print(f"Excluded (dev-only, {len(result['excluded'])}):")
    for ex in result["excluded"]:
        print(f"  - {ex}")
    if zip_path:
        print(f"Zipped: {zip_path}")


if __name__ == "__main__":
    main()

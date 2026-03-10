#!/usr/bin/env python3
"""
rule-converter — Convert AI coding rules between IDE formats.

Supported IDEs: cursor, windsurf, cline, claude, copilot, kiro

OUTPUT MODES
  repo (default)  → <base>/rules/<ide>/<name>.<ext>
                    mirrors the Herald.Ai.Skills repository structure
  deploy          → native IDE paths (.cursor/rules/, .windsurf/rules/, etc.)
                    use when dropping rules directly into a project

DEFAULT BASE DIR  = directory of the source file (no --output needed)

USAGE
  # Auto-detect IDE, convert to all other formats, output next to source file
  python converter.py my-rule.mdc

  # Explicit source IDE, specific targets
  python converter.py my-rule.mdc --from cursor --to windsurf,claude

  # Custom output base dir
  python converter.py my-rule.mdc --output /path/to/repo

  # Deploy mode (native IDE paths)
  python converter.py my-rule.mdc --mode deploy --output ./my-project

  # Preview without writing
  python converter.py my-rule.mdc --dry-run

  # List supported IDE keys
  python converter.py --list-ides
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from parsers import PARSERS, RuleDocument, detect_source_ide
from serializers import SERIALIZERS, DEPLOY_SERIALIZERS, REPO_SUBFOLDER, ALL_TARGETS


# ---------------------------------------------------------------------------
# Human-readable labels
# ---------------------------------------------------------------------------

_IDE_LABELS: dict[str, str] = {
    "cursor":   "Cursor (.mdc)",
    "windsurf": "Windsurf (.md)",
    "cline":    "Cline (.md)",
    "claude":   "Claude Code (CLAUDE.md)",
    "copilot":  "GitHub Copilot",
    "kiro":     "Kiro (steering)",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="converter",
        description="Convert AI coding rules between IDE formats.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("source", metavar="SOURCE_FILE", nargs="?",
                   help="Path to the source rule file.")
    p.add_argument("--from", dest="source_ide", metavar="IDE",
                   choices=list(PARSERS), default=None,
                   help=f"Source IDE. Auto-detected when omitted. Choices: {', '.join(PARSERS)}.")
    p.add_argument("--to", dest="targets", metavar="IDE[,IDE,...]", default=None,
                   help=f"Comma-separated targets. Default: all except source. Available: {', '.join(ALL_TARGETS)}.")
    p.add_argument("--output", metavar="DIR", default=None,
                   help="Base output directory. Default: directory of source file.")
    p.add_argument("--mode", choices=["repo", "deploy"], default="repo",
                   help="'repo' (default): rules/<ide>/ structure. 'deploy': native IDE paths.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview files that would be created without writing.")
    p.add_argument("--list-ides", action="store_true",
                   help="List supported IDE keys and exit.")
    p.add_argument("--verbose", action="store_true",
                   help="Print parsed rule metadata.")
    return p


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _resolve_targets(raw: str | None, source_ide: str) -> list[str]:
    if raw is None:
        return [t for t in ALL_TARGETS if t != source_ide]
    requested = [t.strip() for t in raw.split(",") if t.strip()]
    unknown = [t for t in requested if t not in SERIALIZERS]
    if unknown:
        print(f"[ERROR] Unknown target(s): {', '.join(unknown)}. Valid: {', '.join(ALL_TARGETS)}", file=sys.stderr)
        sys.exit(1)
    return requested


def _resolve_source_ide(source: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    detected = detect_source_ide(source)
    if detected:
        return detected
    print(f"[ERROR] Cannot detect IDE for: {source}\n        Use --from. Valid: {', '.join(PARSERS)}", file=sys.stderr)
    sys.exit(1)


def _resolve_base(output_arg: str | None, source: Path) -> Path:
    """
    Resolve the base directory for output.

    Priority:
      1. Explicit --output flag → use as-is
      2. Source is inside a  …/rules/<ide>/…  tree → return the root above 'rules/'
      3. Fallback → directory of the source file

    Rule:
      In repo mode, outputs go to <base>/rules/<ide>/
      So if source = …/rules/cursor/my-rule.mdc, we want base = …/ (not …/rules/cursor/)
    """
    if output_arg is not None:
        return Path(output_arg).expanduser().resolve()

    resolved = source.parent.resolve()
    parts = resolved.parts

    # Walk up until we find a 'rules' directory in the path
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "rules":
            # parent of the 'rules' dir is the repo root
            return Path(*parts[:i])

    return resolved


def _target_dir(base: Path, ide: str, mode: str) -> Path:
    if mode == "repo":
        # These IDEs use top-level folders, not rules/
        if ide == "kiro":
            return base / "steering"
        if ide == "copilot":
            return base / "instructions"
        return base / "rules" / REPO_SUBFOLDER[ide]
    return base


# ---------------------------------------------------------------------------
# Dry-run simulation
# ---------------------------------------------------------------------------

def _simulate(doc: RuleDocument, ide: str, t_dir: Path, mode: str) -> list[Path]:
    name = (doc.rule_name or "rule").replace(" ", "_")
    if mode == "repo":
        if ide == "kiro":
            return [t_dir / name / f"{name}.md"]
        if ide == "copilot":
            return [
                t_dir / "global" / name / "copilot-instructions.md",
                t_dir / "workspace" / name / f"{name}.instructions.md",
            ]
        fixed = {"claude": "CLAUDE.md"}
        ext   = ".mdc" if ide == "cursor" else ".md"
        fname = fixed.get(ide, f"{name}{ext}")
        return [t_dir / fname]
    deploy_map: dict[str, list[Path]] = {
        "cursor":   [t_dir / ".cursor" / "rules" / f"{name}.mdc"],
        "windsurf": [t_dir / ".windsurf" / "rules" / f"{name}.md"],
        "cline":    [t_dir / ".clinerules" / f"{name}.md"],
        "claude":   [t_dir / "CLAUDE.md"],
        "copilot":  [
            t_dir / ".github" / "instructions" / f"{name}.instructions.md"
            if doc.globs else t_dir / ".github" / "copilot-instructions.md"
        ],
        "kiro":     [t_dir / ".kiro" / "steering" / name / f"{name}.md"],
    }
    return deploy_map.get(ide, [t_dir / f"{name}.md"])


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def convert(
    source: Path,
    source_ide: str,
    targets: list[str],
    base_dir: Path,
    mode: str = "repo",
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, list[Path]]:
    doc: RuleDocument = PARSERS[source_ide](source)

    if verbose:
        print(f"  parsed  → ide={source_ide}  activation={doc.activation_mode}")
        print(f"  name    → {doc.rule_name}")
        print(f"  desc    → {doc.description or '(none)'}")
        print(f"  globs   → {doc.globs or '(none)'}")
        print(f"  content → {len(doc.content)} chars")
        print()

    registry = SERIALIZERS if mode == "repo" else DEPLOY_SERIALIZERS
    results: dict[str, list[Path]] = {}

    for ide in targets:
        t_dir = _target_dir(base_dir, ide, mode)
        results[ide] = _simulate(doc, ide, t_dir, mode) if dry_run else registry[ide](doc, t_dir)

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_results(results: dict[str, list[Path]], dry_run: bool) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    total  = sum(len(v) for v in results.values())
    print(f"\n{prefix}Results — {total} file(s) across {len(results)} target(s):\n")
    for ide, files in results.items():
        print(f"  ▸ {_IDE_LABELS.get(ide, ide)}")
        for f in files:
            print(f"    {'→' if dry_run else '✓'} {f}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.list_ides:
        print("Supported IDE keys:\n")
        for k, label in _IDE_LABELS.items():
            print(f"  {k:<14} {label}")
        sys.exit(0)

    if not args.source:
        parser.print_help()
        sys.exit(0)

    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        print(f"[ERROR] File not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    source_ide = _resolve_source_ide(source_path, args.source_ide)
    targets    = _resolve_targets(args.targets, source_ide)
    base_dir   = _resolve_base(args.output, source_path)
    mode       = args.mode

    if not targets:
        print("[WARN] No targets selected.", file=sys.stderr)
        sys.exit(0)

    print("rule-converter")
    print(f"  Source  : {source_path}")
    print(f"  IDE     : {_IDE_LABELS.get(source_ide, source_ide)}")
    print(f"  Mode    : {mode}  ({'rules/<ide>/' if mode == 'repo' else 'native IDE paths'})")
    print(f"  Base    : {base_dir}")
    print(f"  Targets : {', '.join(_IDE_LABELS.get(t, t) for t in targets)}")
    if args.dry_run:
        print("  [DRY RUN — nothing will be written]")
    print()

    try:
        results = convert(source_path, source_ide, targets, base_dir, mode, args.dry_run, args.verbose)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    _print_results(results, args.dry_run)
    print("Done.")


if __name__ == "__main__":
    main()

---
name: rule-converter
description: Converts AI coding rules between IDE formats (Cursor, Windsurf, Cline, Claude Code, GitHub Copilot, AGENTS.md). Use when the user wants to port a rule from one IDE to another, convert a skill's instructions to a specific IDE format, or generate all IDE variants of a rule from a single source file.
metadata:
  author: Herald.Ai.Skills
  version: "1.0"
---

# rule-converter

Converts AI coding rules between IDE formats. Given any source rule file, it
produces equivalent files for the other supported IDEs — preserving metadata,
activation mode, glob patterns, and all Markdown content.

## Supported IDEs

| Key         | IDE / Tool                    | Output file                              |
|-------------|-------------------------------|------------------------------------------|
| `cursor`    | Cursor                        | `rules/cursor/<name>.mdc`                |
| `windsurf`  | Windsurf (Codeium)            | `rules/windsurf/<name>.md`               |
| `cline`     | Cline (VSCode)                | `rules/cline/<name>.md`                  |
| `claude`    | Claude Code (Anthropic CLI)   | `rules/claude/CLAUDE.md`                 |
| `copilot`   | GitHub Copilot                | `rules/copilot/copilot-instructions.md`  |
| `agents_md` | AGENTS.md (open standard)     | `rules/agents_md/AGENTS.md`              |

## Output modes

- **`repo` (default):** Files go into `rules/<ide>/` — mirrors the Herald.Ai.Skills repo structure.
  The base directory defaults to the directory of the source file, so no `--output` flag is needed for in-repo conversions.

- **`deploy`:** Files are written to native IDE paths (`.cursor/rules/`, `.windsurf/rules/`, etc.).
  Use when dropping rules directly into a project.

## Instructions

### Workflow 1 — Convert a file by path

1. The user provides a file path (absolute or relative).
2. Run:
   ```
   python skills/rule-converter/scripts/converter.py "<path>" [--from <ide>] [--to <ide,...>] [--output <dir>] [--mode repo|deploy]
   ```
3. If `--from` is omitted, the script auto-detects the source IDE from path and content.
4. If `--to` is omitted, the script converts to **all other** supported IDEs.
5. Report the list of files created to the user.

### Workflow 2 — Convert another skill's SKILL.md

1. The user references a skill (by name or path, e.g. `fix-my-code` or `skills/fix-my-code/SKILL.md`).
2. Locate the `SKILL.md` at `skills/<skill-name>/SKILL.md`.
3. Run:
   ```
   python skills/rule-converter/scripts/converter.py "skills/<skill-name>/SKILL.md" --from agents_md [--to <ide,...>]
   ```
   Skill `SKILL.md` files are treated as `agents_md` format (pure Markdown, always-on).
4. Report the list of files created to the user.

### Workflow 3 — Dry-run preview

Use `--dry-run` to show which files would be created without writing anything.

```
python skills/rule-converter/scripts/converter.py "<path>" --dry-run
```

## Edge cases

- **Source IDE not detected:** Pass `--from <ide>` explicitly.
- **Convert to a single IDE:** Pass `--to <ide>`.
- **Output to a specific project:** Pass `--output /path/to/project --mode deploy`.
- **Multiple targets:** Pass `--to cursor,windsurf,claude`.
- **Source is already in rules/ folder:** The script still works; it reads the file and writes the conversions.

## Examples

```bash
# Convert a Cursor rule to all other IDEs (output next to source file)
python skills/rule-converter/scripts/converter.py rules/cursor/ultimate-agent-rules.mdc

# Convert the fix-my-code skill to Cursor + Windsurf format
python skills/rule-converter/scripts/converter.py skills/fix-my-code/SKILL.md --from agents_md --to cursor,windsurf

# Convert to all IDEs and place output in /tmp/converted/
python skills/rule-converter/scripts/converter.py rules/cursor/ultimate-agent-rules.mdc --output /tmp/converted

# Deploy a rule directly into a project
python skills/rule-converter/scripts/converter.py rules/cursor/ultimate-agent-rules.mdc --mode deploy --output ~/Projects/my-app

# Preview without writing
python skills/rule-converter/scripts/converter.py rules/cursor/ultimate-agent-rules.mdc --dry-run
```

## Script reference

All scripts live in `scripts/` relative to this skill:

- **`scripts/converter.py`** — CLI entry point; orchestrates parse + serialize
- **`scripts/parsers.py`** — One parser per source IDE → canonical `RuleDocument`
- **`scripts/serializers.py`** — One serializer per target IDE → output files

No external dependencies — stdlib Python 3.8+ only.

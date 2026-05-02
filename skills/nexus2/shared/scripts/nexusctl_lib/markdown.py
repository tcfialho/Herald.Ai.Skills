import re
from typing import Any

from .constants import FRONTMATTER_ORDER


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value in ("null", "None", "~"):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def scalar_to_yaml(value: Any) -> str:
    if value is None or value == "":
        return "null"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_\-./:]+", text):
        return text
    return '"' + text.replace('"', '\\"') + '"'


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_index = next((idx for idx in range(1, len(lines)) if lines[idx].strip() == "---"), None)
    if end_index is None:
        return {}, text

    meta: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:end_index]:
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            current = meta.setdefault(current_key, [])
            if isinstance(current, list):
                current.append(parse_scalar(line[4:]))
            continue
        match = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        if raw_value == "":
            meta[key] = []
            current_key = key
        else:
            meta[key] = parse_scalar(raw_value)
            current_key = key
    return meta, "\n".join(lines[end_index + 1 :]).lstrip("\n")


def render_frontmatter(meta: dict[str, Any], body: str) -> str:
    keys = [key for key in FRONTMATTER_ORDER if key in meta]
    keys.extend(sorted(key for key in meta if key not in keys))
    lines = ["---"]
    for key in keys:
        value = meta.get(key)
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {scalar_to_yaml(item)}" for item in value)
        else:
            lines.append(f"{key}: {scalar_to_yaml(value)}")
    lines.extend(["---", "", body.rstrip(), ""])
    return "\n".join(lines)


def extract_section(body: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", body, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", body[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(body)
    return body[start:end].strip()


def replace_section(body: str, heading: str, content: str) -> str:
    heading_line = f"## {heading}"
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", body, flags=re.MULTILINE)
    replacement = f"{heading_line}\n\n{content.strip()}\n"
    if not match:
        return body.rstrip() + "\n\n" + replacement
    start = match.start()
    after_heading = match.end()
    next_match = re.search(r"^##\s+", body[after_heading:], flags=re.MULTILINE)
    end = after_heading + next_match.start() if next_match else len(body)
    return body[:start] + replacement + body[end:].lstrip("\n")


def acceptance_criteria_ids(body: str) -> list[str]:
    return sorted(set(re.findall(r"\bAC-\d+\b", extract_section(body, "Acceptance Criteria"))))


def evidence_section(body: str) -> str:
    return extract_section(body, "Execution Evidence")


def expected_file_artifacts(body: str) -> list[str]:
    section = extract_section(body, "Expected Artifacts")
    return [
        value
        for value in (match.group(1).strip() for match in re.finditer(r"file:\s*`([^`]+)`", section))
        if value and value != "TBD"
    ]

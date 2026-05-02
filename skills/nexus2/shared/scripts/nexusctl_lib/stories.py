import re
from pathlib import Path
from typing import Any

from .constants import STATUSES
from .errors import NexusError
from .markdown import parse_frontmatter, render_frontmatter
from .models import Story
from .paths import backlog_dir, read_text, slugify, write_text
from .tasks import parse_tasks
from .timeutil import lease_until_iso, parse_iso


def parse_story_filename(path: Path) -> dict[str, str]:
    parts = path.stem.split("_", 2)
    story_id = parts[0] if parts else "US-000"
    status = parts[1] if len(parts) > 1 and parts[1] in STATUSES else "READY"
    slug = parts[2] if len(parts) > 2 else ""
    owner = ""
    if "__" in slug:
        slug, owner = slug.rsplit("__", 1)
    return {"id": story_id, "status": status, "slug": slug, "owner": owner}


def title_from_filename(path: Path) -> str:
    slug = parse_story_filename(path)["slug"].replace("_", " ").replace("-", " ").strip()
    return slug.title() if slug else parse_story_filename(path)["id"]


def story_filename(current_path: Path, meta: dict[str, Any], agent: str | None = None) -> Path:
    parsed = parse_story_filename(current_path)
    story_id = str(meta.get("id") or parsed["id"])
    status = str(meta.get("status") or "READY")
    slug = parsed["slug"] or slugify(meta.get("title") or story_id)
    name = f"{story_id}_{status}_{slug}"
    if status == "ACTIVE":
        owner = agent or str(meta.get("owner") or parsed.get("owner") or "")
        if owner:
            name += f"__{slugify(owner)}"
    return current_path.parent / f"{name}.md"


def load_story(path: Path) -> Story:
    meta, body = parse_frontmatter(read_text(path))
    parsed = parse_story_filename(path)
    meta.setdefault("id", parsed["id"])
    meta.setdefault("status", parsed["status"])
    meta.setdefault("title", title_from_filename(path))
    return Story(path=path, meta=meta, body=body)


def save_story(story: Story, root: Path, new_status: str | None = None, agent: str | None = None) -> Story:
    if new_status:
        story.meta["status"] = new_status
    write_text(story.path, render_frontmatter(story.meta, story.body))
    expected = story_filename(story.path, story.meta, agent=agent)
    if expected != story.path:
        if expected.exists():
            raise NexusError(f"target story filename already exists: {expected}")
        story.path.rename(expected)
        story = load_story(expected)
    return story


def list_stories(root: Path) -> list[Story]:
    bdir = backlog_dir(root)
    if not bdir.exists():
        return []
    paths = sorted([*bdir.glob("US-*.md"), *bdir.glob("SP-*.md")])
    stories = [load_story(path) for path in paths]
    return sorted(
        stories,
        key=lambda story: (
            0 if story.story_id.startswith("SP-") else 1,
            story.priority,
            story.story_id,
        ),
    )


def story_by_id(root: Path, story_id: str) -> Story:
    matches = [story for story in list_stories(root) if story.story_id == story_id]
    if not matches:
        raise NexusError(f"story not found: {story_id}")
    if len(matches) > 1:
        raise NexusError(f"multiple files found for story {story_id}")
    return matches[0]


def active_story_for_agent(root: Path, agent: str) -> Story | None:
    agent_slug = slugify(agent)
    for story in list_stories(root):
        owner = slugify(story.owner)
        parsed_owner = parse_story_filename(story.path).get("owner", "")
        if story.status == "ACTIVE" and (owner == agent_slug or parsed_owner == agent_slug):
            return story
    return None


def lease_is_valid(story: Story) -> bool:
    lease_until = parse_iso(story.meta.get("lease_until"))
    from .timeutil import now_utc

    return bool(lease_until and lease_until > now_utc())


def renew_lease(story: Story) -> None:
    from .timeutil import iso_now

    story.meta["heartbeat_at"] = iso_now()
    story.meta["lease_until"] = lease_until_iso()


def first_unfinished_story(stories: list[Story]) -> Story | None:
    return next((story for story in stories if story.status != "DONE"), None)


def earlier_unfinished_story(root: Path, story: Story) -> Story | None:
    for candidate in list_stories(root):
        if candidate.story_id == story.story_id:
            return None
        if candidate.status != "DONE":
            return candidate
    return None


def describe_blocking_story(story: Story) -> str:
    if story.status == "ACTIVE":
        state = "valid" if lease_is_valid(story) else "expired"
        return f"{story.story_id} is ACTIVE for {story.owner or 'unknown'} (lease {state}, until {story.meta.get('lease_until') or '-'})"
    return f"{story.story_id} is {story.status}"


def story_has_open_bugs(story: Story) -> bool:
    from .markdown import extract_section

    return bool(re.search(r"^\s*-\s*\[\s*\]\s+BUG-\d+:", extract_section(story.body, "QA Bugs"), re.MULTILINE))


def story_open_bug_count(story: Story) -> int:
    from .markdown import extract_section

    return len(re.findall(r"^\s*-\s*\[\s*\]\s+BUG-\d+:", extract_section(story.body, "QA Bugs"), re.MULTILINE))


def bug_exists(story: Story, bug_id: str) -> bool:
    return bool(re.search(rf"^\s*-\s*\[[ x]\]\s+{re.escape(bug_id)}:", story.body, re.MULTILINE))


def update_bug_marker(body: str, bug_id: str, completed: bool) -> str:
    marker = "x" if completed else " "
    lines = body.splitlines()
    pattern = re.compile(rf"^(\s*-\s*)\[[ x]\](\s+{re.escape(bug_id)}:\s*.*)$")
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            lines[idx] = f"{match.group(1)}[{marker}]{match.group(2)}"
            return "\n".join(lines)
    raise NexusError(f"bug not found: {bug_id}")


def claim_story(root: Path, story: Story, agent: str, reclaim: bool = False) -> Story:
    if story.status == "ACTIVE":
        if slugify(story.owner) == slugify(agent):
            renew_lease(story)
            return save_story(story, root, agent=agent)
        if lease_is_valid(story):
            raise NexusError(f"{story.story_id} is ACTIVE for {story.owner} until {story.meta.get('lease_until')}")
        if not reclaim:
            raise NexusError(f"{story.story_id} is ACTIVE. Use --reclaim if the lease expired.")
    if story.status not in ("READY", "ACTIVE", "BLOCKED"):
        raise NexusError(f"{story.story_id} is {story.status}; cannot claim")
    blocker = earlier_unfinished_story(root, story)
    if blocker:
        raise NexusError(f"cannot claim {story.story_id} before earlier story is DONE: {describe_blocking_story(blocker)}")
    story.meta["status"] = "ACTIVE"
    story.meta["owner"] = agent
    from .timeutil import iso_now

    story.meta["claimed_at"] = story.meta.get("claimed_at") or iso_now()
    renew_lease(story)
    current = next((task.task_id for task in parse_tasks(story.body) if task.status != "completed"), None)
    story.meta["current_task"] = current
    return save_story(story, root, new_status="ACTIVE", agent=agent)

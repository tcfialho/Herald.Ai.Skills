import argparse

from .commands_base import resolve_root
from .errors import NexusError
from .paths import default_agent_id, ensure_initialized, slugify
from .status import print_status
from .stories import active_story_for_agent, renew_lease, save_story, story_by_id


def cmd_heartbeat(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    agent = args.agent or default_agent_id()
    story = story_by_id(root, args.story_id) if args.story_id else active_story_for_agent(root, agent)
    if story is None:
        raise NexusError("no active story for this agent")
    if slugify(story.owner) != slugify(agent):
        raise NexusError(f"{story.story_id} is owned by {story.owner}, not {agent}")
    renew_lease(story)
    story = save_story(story, root, agent=agent)
    print("HEARTBEAT_OK")
    print_status(root, active=story)

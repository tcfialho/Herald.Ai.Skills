import argparse

from .commands_base import resolve_root
from .context_refs import is_spike_story, resolved_story_context, validate_story_context_refs
from .errors import SpecError
from .evidence import missing_files
from .audit import spike_deliverables
from .markdown import acceptance_criteria_ids, evidence_section, expected_file_artifacts
from .paths import default_agent_id, ensure_initialized, read_text, slugify
from .status import print_status
from .stories import (
    active_story_for_agent,
    claim_story,
    describe_blocking_story,
    first_unfinished_story,
    lease_is_valid,
    list_stories,
    save_story,
    story_by_id,
    story_has_open_bugs,
)
from .tasks import parse_tasks
from .timeutil import iso_now


def cmd_story_next(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    agent = args.agent or default_agent_id()
    active = active_story_for_agent(root, agent)
    if active:
        print(f"ACTIVE_STORY: {active.path}")
        print_status(root, active=active)
        return

    first = first_unfinished_story(list_stories(root))
    if not first:
        print("NO_READY_STORY")
        print_status(root)
        return
    if first.status != "READY":
        print(f"ORDER_BLOCKED: {describe_blocking_story(first)}")
        if first.status == "ACTIVE" and not lease_is_valid(first):
            print(f"To reclaim: spec story claim {first.story_id} --agent {agent} --reclaim")
        print_status(root)
        raise SpecError(f"next story is blocked by {first.story_id}")
    if args.no_claim:
        print(f"NEXT_STORY: {first.path}")
        print_status(root, next_story=first)
        return
    story = claim_story(root, first, agent)
    print(f"CLAIMED_STORY: {story.path}")
    print_status(root, active=story)


def cmd_story_claim(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    agent = args.agent or default_agent_id()
    existing = active_story_for_agent(root, agent)
    if existing and existing.story_id != args.story_id:
        raise SpecError(f"agent already has active story {existing.story_id}; submit/release it before claiming another")
    story = claim_story(root, story_by_id(root, args.story_id), agent, reclaim=args.reclaim)
    print(f"CLAIMED_STORY: {story.path}")
    print_status(root, active=story)


def cmd_story_context(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    story = story_by_id(root, args.story_id) if args.story_id else None
    if story is None:
        story = active_story_for_agent(root, args.agent or default_agent_id())
    if story is None:
        raise SpecError("no story selected and no active story for this agent")
    print(read_text(story.path))
    resolved_context = resolved_story_context(root, story)
    if resolved_context:
        print("\n---\n")
        print(resolved_context)


def cmd_story_submit_qa(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    agent = args.agent or default_agent_id()
    story = story_by_id(root, args.story_id) if args.story_id else active_story_for_agent(root, agent)
    if story is None:
        raise SpecError("no active story for this agent")
    if story.status != "ACTIVE":
        raise SpecError(f"{story.story_id} is {story.status}; only ACTIVE stories can be submitted")
    if slugify(story.owner) != slugify(agent):
        raise SpecError(f"{story.story_id} is owned by {story.owner}, not {agent}")
    incomplete = [task.task_id for task in parse_tasks(story.body) if task.status != "completed"]
    if incomplete:
        raise SpecError(f"incomplete tasks: {', '.join(incomplete)}")
    if story_has_open_bugs(story):
        raise SpecError("story has open QA bugs")
    context_errors = validate_story_context_refs(root, story)
    if context_errors:
        raise SpecError("context refs invalid: " + "; ".join(context_errors))
    missing_expected = missing_files(root, expected_file_artifacts(story.body))
    if missing_expected:
        raise SpecError(f"missing affected files: {', '.join(missing_expected)}")
    evidence = evidence_section(story.body)
    is_spike = is_spike_story(story)
    if is_spike:
        missing_deliverables = [item for item in spike_deliverables(story) if item not in evidence]
        if missing_deliverables:
            raise SpecError(f"deliverables without evidence: {', '.join(missing_deliverables)}")
    else:
        missing_ac = [ac_id for ac_id in acceptance_criteria_ids(story.body) if ac_id not in evidence]
        if missing_ac:
            raise SpecError(f"acceptance criteria without evidence: {', '.join(missing_ac)}")
    story.meta.update({"owner": None, "lease_until": None, "heartbeat_at": iso_now(), "current_task": None})
    if is_spike:
        story = save_story(story, root, new_status="DONE")
        print(f"COMPLETED_SPIKE: {story.path}")
    else:
        story = save_story(story, root, new_status="QA")
        print(f"SUBMITTED_QA: {story.path}")
    print_status(root)


def cmd_story_release(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    agent = args.agent or default_agent_id()
    story = story_by_id(root, args.story_id) if args.story_id else active_story_for_agent(root, agent)
    if story is None:
        raise SpecError("no active story for this agent")
    if slugify(story.owner) != slugify(agent) and not args.force:
        raise SpecError(f"{story.story_id} is owned by {story.owner}; use --force to release")
    story.meta.update({"owner": None, "lease_until": None, "heartbeat_at": iso_now()})
    story = save_story(story, root, new_status="READY")
    print(f"RELEASED_STORY: {story.path}")
    print_status(root)

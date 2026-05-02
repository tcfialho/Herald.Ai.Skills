import argparse
import subprocess

from .commands_base import resolve_root
from .errors import NexusError
from .evidence import (
    append_bug_evidence,
    append_evidence,
    files_within_write_scope,
    missing_files,
    run_verify_cmd,
    write_cache_log,
)
from .paths import default_agent_id, ensure_initialized, slugify
from .status import print_status
from .stories import (
    active_story_for_agent,
    bug_exists,
    renew_lease,
    save_story,
    story_by_id,
    story_open_bug_count,
    update_bug_marker,
)
from .tasks import earlier_incomplete_task, parse_tasks, task_by_id, update_task_marker


def _active_story(args: argparse.Namespace):
    root = resolve_root(args)
    ensure_initialized(root)
    agent = args.agent or default_agent_id()
    story = story_by_id(root, args.story_id) if args.story_id else active_story_for_agent(root, agent)
    if story is None:
        raise NexusError("no active story for this agent")
    if story.status != "ACTIVE":
        raise NexusError(f"{story.story_id} is not ACTIVE")
    if slugify(story.owner) != slugify(agent):
        raise NexusError(f"{story.story_id} is owned by {story.owner}, not {agent}")
    return root, agent, story


def cmd_task_start(args: argparse.Namespace) -> None:
    root, agent, story = _active_story(args)
    task = task_by_id(story, args.task_id)
    previous = earlier_incomplete_task(story, args.task_id)
    if previous:
        raise NexusError(f"cannot start {args.task_id} before {previous.task_id} is completed")
    if task.status == "completed":
        raise NexusError(f"{args.task_id} is already completed")
    story.body = update_task_marker(story.body, args.task_id, "in_progress")
    story.meta["current_task"] = args.task_id
    renew_lease(story)
    story = save_story(story, root, agent=agent)
    print(f"TASK_STARTED: {args.task_id}")
    print_status(root, active=story)


def cmd_task_complete(args: argparse.Namespace) -> None:
    root, agent, story = _active_story(args)
    task = task_by_id(story, args.task_id)
    previous = earlier_incomplete_task(story, args.task_id)
    if previous:
        raise NexusError(f"cannot complete {args.task_id} before {previous.task_id} is completed")
    if task.status != "in_progress":
        raise NexusError(f"{args.task_id} must be started before completion")
    verify_cmd = args.verify_cmd or task.verify_cmd
    if not verify_cmd or verify_cmd == "TBD":
        raise NexusError(f"{task.task_id} has no verify_cmd")
    if not task.files:
        raise NexusError(f"{task.task_id} has no declared files")
    out_of_scope = files_within_write_scope(story, task.files)
    if out_of_scope:
        raise NexusError(f"task files outside write_scope: {', '.join(out_of_scope)}")
    missing = missing_files(root, task.files)
    if missing:
        raise NexusError(f"declared task files do not exist: {', '.join(missing)}")

    try:
        exit_code, output = run_verify_cmd(verify_cmd, root, args.verify_timeout)
    except subprocess.TimeoutExpired as exc:
        log = write_cache_log(root, story, task.task_id, exc.stdout or "")
        raise NexusError(f"verify command timed out; log: {log}")
    log = write_cache_log(root, story, task.task_id, output)
    if exit_code != 0:
        story.body = update_task_marker(story.body, args.task_id, "failed")
        story.meta["current_task"] = args.task_id
        renew_lease(story)
        save_story(story, root, agent=agent)
        raise NexusError(f"verify command failed with exit code {exit_code}; log: {log}")

    story.body = update_task_marker(story.body, args.task_id, "completed")
    append_evidence(story, task, verify_cmd, exit_code, task.files, args.covers or task.covers, args.note or f"log: {log}")
    remaining = [item for item in parse_tasks(story.body) if item.status != "completed"]
    story.meta["current_task"] = remaining[0].task_id if remaining else None
    renew_lease(story)
    story = save_story(story, root, agent=agent)
    print(f"TASK_COMPLETED: {args.task_id}")
    print_status(root, active=story)


def cmd_task_fail(args: argparse.Namespace) -> None:
    root, agent, story = _active_story(args)
    task = task_by_id(story, args.task_id)
    story.body = update_task_marker(story.body, args.task_id, "failed")
    story.meta["current_task"] = args.task_id
    renew_lease(story)
    append_evidence(story, task, "not executed", 1, [], [], args.error)
    story = save_story(story, root, agent=agent)
    print(f"TASK_FAILED: {args.task_id}")
    print_status(root, active=story)


def cmd_bug_resolve(args: argparse.Namespace) -> None:
    root, agent, story = _active_story(args)
    if not bug_exists(story, args.bug_id):
        raise NexusError(f"bug not found in story: {args.bug_id}")
    verify_cmd = args.verify_cmd
    if not verify_cmd:
        commands = [task.verify_cmd for task in parse_tasks(story.body) if task.verify_cmd and task.verify_cmd != "TBD"]
        if not commands:
            raise NexusError("bug resolution requires --verify-cmd because no task verify_cmd is available")
        verify_cmd = " && ".join(dict.fromkeys(commands))
    try:
        exit_code, output = run_verify_cmd(verify_cmd, root, args.verify_timeout)
    except subprocess.TimeoutExpired as exc:
        log = write_cache_log(root, story, args.bug_id, exc.stdout or "")
        raise NexusError(f"bug verify command timed out; log: {log}")
    log = write_cache_log(root, story, args.bug_id, output)
    if exit_code != 0:
        raise NexusError(f"bug verify command failed with exit code {exit_code}; log: {log}")
    story.body = update_bug_marker(story.body, args.bug_id, completed=True)
    append_bug_evidence(story, args.bug_id, verify_cmd, exit_code, args.note or f"log: {log}")
    story.meta["current_task"] = None if story_open_bug_count(story) == 0 else story.meta.get("current_task")
    renew_lease(story)
    story = save_story(story, root, agent=agent)
    print(f"BUG_RESOLVED: {args.bug_id}")
    print_status(root, active=story)

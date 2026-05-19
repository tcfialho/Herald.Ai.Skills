import argparse
import json
import re

from .commands_base import resolve_root
from .context_refs import is_spike_story
from .errors import SpecError
from .audit import spike_deliverables
from .evidence import files_within_write_scope, missing_files, run_story_verify_commands
from .markdown import (
    acceptance_criteria_ids,
    evidence_section,
    expected_file_artifacts,
    extract_section,
    replace_section,
    sync_coverage_checklists,
    sync_definition_of_done,
)
from .paths import ensure_initialized, runtime_dir
from .status import print_status
from .stories import list_stories, save_story, story_by_id, story_has_open_bugs
from .tasks import parse_tasks
from .timeutil import iso_now


QA_ROUND_CAP = 5


def cmd_qa_start(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    candidates = [story for story in list_stories(root) if story.status == "QA"]
    if args.story_id:
        story = story_by_id(root, args.story_id)
        if story.status != "QA":
            raise SpecError(f"{story.story_id} is {story.status}; expected QA")
    elif candidates:
        story = candidates[0]
    else:
        print("NO_QA_STORY")
        print_status(root)
        return
    print(f"QA_STORY: {story.path}")
    print_status(root, next_story=story)


def next_bug_id(body: str) -> str:
    ids = [int(value) for value in re.findall(r"\bBUG-(\d+)\b", body)]
    return f"BUG-{max(ids, default=0) + 1:03d}"


def _record_qa_bug(root, story, bug_text: str):
    bug_id = next_bug_id(story.body)
    section = extract_section(story.body, "QA Bugs")
    if not section or section == "None.":
        section = ""
    lines = [section.rstrip()] if section.strip() else []
    lines.append(f"- [ ] {bug_id}: {bug_text}")
    story.body = replace_section(story.body, "QA Bugs", "\n".join(lines))
    story.meta.update({"current_task": bug_id, "owner": None, "lease_until": None, "heartbeat_at": iso_now()})
    return save_story(story, root, new_status="READY"), bug_id


def _validate_qa_story(root, story, verify_timeout: int) -> list[str]:
    failures: list[str] = []
    has_open_bugs = story_has_open_bugs(story)
    if has_open_bugs:
        failures.append("story has open QA bugs")
    tasks = parse_tasks(story.body)
    incomplete_tasks = [task.task_id for task in tasks if task.status != "completed"]
    if incomplete_tasks:
        failures.append(f"incomplete tasks: {', '.join(incomplete_tasks)}")
    architecture_failures = []
    for task in tasks:
        out_of_scope = files_within_write_scope(story, task.files)
        if out_of_scope:
            architecture_failures.append(f"{task.task_id} files outside write_scope: {', '.join(out_of_scope)}")
    if architecture_failures:
        failures.extend(architecture_failures)
    missing_expected = missing_files(root, expected_file_artifacts(story.body))
    if missing_expected:
        failures.append(f"missing affected files: {', '.join(missing_expected)}")
    evidence = evidence_section(story.body)
    missing_coverage = []
    if is_spike_story(story):
        missing_deliverables = [item for item in spike_deliverables(story) if item not in evidence]
        if missing_deliverables:
            failures.append(f"deliverables without evidence: {', '.join(missing_deliverables)}")
            missing_coverage.extend(missing_deliverables)
    else:
        missing_ac = [ac_id for ac_id in acceptance_criteria_ids(story.body) if ac_id not in evidence]
        if missing_ac:
            failures.append(f"acceptance criteria without evidence: {', '.join(missing_ac)}")
            missing_coverage.extend(missing_ac)
    verify_failures = run_story_verify_commands(root, story, timeout=verify_timeout)
    if verify_failures:
        failures.append("verify failed: " + "; ".join(verify_failures[:3]))
    story.body = sync_coverage_checklists(story.body)
    story.body = sync_definition_of_done(
        story.body,
        {
            "All acceptance criteria are covered": not missing_coverage,
            "All tasks are complete": bool(tasks) and not incomplete_tasks,
            "Every verify command passed": not verify_failures,
            "Affected files exist": not missing_expected,
            "Architecture gates pass": not architecture_failures,
            "No open QA bugs remain": not has_open_bugs,
        },
    )
    return failures


def _approve_qa_story(root, story):
    story.meta.update({"owner": None, "lease_until": None, "current_task": None, "heartbeat_at": iso_now()})
    return save_story(story, root, new_status="DONE")


def cmd_qa_fail(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    story = story_by_id(root, args.story_id)
    if story.status not in ("QA", "DONE"):
        raise SpecError(f"{story.story_id} is {story.status}; QA can fail only QA/DONE stories")
    story, bug_id = _record_qa_bug(root, story, args.bug)
    print(f"QA_FAILED: {story.path}")
    print(f"BUG_ADDED: {bug_id}")
    print_status(root)


def cmd_qa_approve(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    story = story_by_id(root, args.story_id)
    if story.status != "QA":
        raise SpecError(f"{story.story_id} is {story.status}; expected QA")
    failures = _validate_qa_story(root, story, args.verify_timeout)
    if failures:
        raise SpecError("; ".join(failures))
    story = _approve_qa_story(root, story)
    print(f"QA_APPROVED: {story.path}")
    print_status(root)


def _round_state_path(root):
    return runtime_dir(root) / "cache" / "qa_rounds.json"


def _read_round_state(root) -> dict:
    path = _round_state_path(root)
    if not path.exists():
        return {"round": 0, "started_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"round": 0, "started_at": None}


def _write_round_state(root, state: dict) -> None:
    path = _round_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8", newline="\n")


def _reset_round_state(root) -> None:
    path = _round_state_path(root)
    if path.exists():
        path.unlink()


def cmd_qa_run(args: argparse.Namespace) -> None:
    root = resolve_root(args)
    ensure_initialized(root)
    qa_stories = [story for story in list_stories(root) if story.status == "QA"]
    if not qa_stories:
        print("NO_QA_STORIES")
        print_status(root)
        return
    state = _read_round_state(root)
    current_round = int(state.get("round", 0)) + 1
    if current_round > QA_ROUND_CAP and not args.force:
        print(f"QA_ROUND_CAP_REACHED: {QA_ROUND_CAP} rounds completed without convergence")
        print("ESCALATION_REQUIRED: ask the user to inspect failing stories before continuing")
        print_status(root)
        raise SpecError(
            f"QA round cap reached ({QA_ROUND_CAP}); escalate to the user. Use --force to override."
        )
    state.update({
        "round": current_round,
        "started_at": state.get("started_at") or iso_now(),
        "last_run_at": iso_now(),
    })
    _write_round_state(root, state)
    approved: list[str] = []
    failed: list[tuple[str, str, str]] = []
    for story in qa_stories:
        failures = _validate_qa_story(root, story, args.verify_timeout)
        if failures:
            reason = "; ".join(failures)
            updated, bug_id = _record_qa_bug(root, story, reason)
            failed.append((updated.story_id, bug_id, reason))
        else:
            updated = _approve_qa_story(root, story)
            approved.append(updated.story_id)
    print(f"QA_RUN_SUMMARY: round={current_round}/{QA_ROUND_CAP} approved={len(approved)} failed={len(failed)}")
    for story_id in approved:
        print(f"  APPROVED {story_id}")
    for story_id, bug_id, reason in failed:
        print(f"  FAILED {story_id} ({bug_id}): {reason}")
    print_status(root)
    if failed:
        if current_round >= QA_ROUND_CAP:
            print(f"QA_ROUND_CAP_REACHED: {QA_ROUND_CAP} rounds without convergence")
            print("ESCALATION_REQUIRED: stop the dev↔qa auto-loop and surface the failing stories to the user")
        raise SpecError("qa run completed with failures; fix bugs and resubmit")
    _reset_round_state(root)

import argparse

from .commands_base import cmd_audit, cmd_docs_validate, cmd_init, cmd_status
from .commands_misc import cmd_heartbeat
from .commands_phase import PHASES, cmd_phase_check, cmd_phase_done
from .commands_qa import cmd_qa_approve, cmd_qa_fail, cmd_qa_run, cmd_qa_start
from .commands_story import (
    cmd_story_claim,
    cmd_story_context,
    cmd_story_next,
    cmd_story_release,
    cmd_story_submit_qa,
)
from .commands_task import cmd_bug_resolve, cmd_task_complete, cmd_task_fail, cmd_task_start
from .errors import NexusError


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default="", help="Project root. Defaults to current project.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexusctl", description="Nexus 2.0 control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create nexus/ and .temp/nexus/ structure")
    init_p.add_argument("--root", default="", help="Target project root")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing base docs")
    init_p.set_defaults(func=cmd_init)

    status_p = sub.add_parser("status", help="Show Nexus status")
    add_common(status_p)
    status_p.set_defaults(func=cmd_status)

    docs_p = sub.add_parser("docs", help="Documentation commands")
    docs_sub = docs_p.add_subparsers(dest="docs_command", required=True)
    validate_p = docs_sub.add_parser("validate", help="Validate nexus docs")
    add_common(validate_p)
    validate_p.set_defaults(func=cmd_docs_validate)

    _add_phase(sub)
    _add_story(sub)
    _add_task(sub)
    _add_bug(sub)
    _add_qa(sub)

    heartbeat_p = sub.add_parser("heartbeat", help="Extend active story lease")
    add_common(heartbeat_p)
    heartbeat_p.add_argument("story_id", nargs="?")
    heartbeat_p.add_argument("--agent", default="", help="Agent id")
    heartbeat_p.set_defaults(func=cmd_heartbeat)

    audit_p = sub.add_parser("audit", help="Run docs and backlog audit")
    add_common(audit_p)
    audit_p.add_argument("--story", dest="story_id", default="")
    audit_p.set_defaults(func=cmd_audit)
    return parser


def _add_phase(sub) -> None:
    phase_p = sub.add_parser("phase", help="Phase dependency guardrails")
    phase_sub = phase_p.add_subparsers(dest="phase_command", required=True)
    check_p = phase_sub.add_parser("check", help="Check whether a phase can start")
    add_common(check_p)
    check_p.add_argument("phase", choices=PHASES)
    check_p.set_defaults(func=cmd_phase_check)
    done_p = phase_sub.add_parser("done", help="Validate phase output and print the next skill")
    add_common(done_p)
    done_p.add_argument("phase", choices=PHASES)
    done_p.set_defaults(func=cmd_phase_done)


def _add_story(sub) -> None:
    story_p = sub.add_parser("story", help="Story commands")
    story_sub = story_p.add_subparsers(dest="story_command", required=True)
    next_p = story_sub.add_parser("next", help="Get and claim the next READY story")
    add_common(next_p)
    next_p.add_argument("--agent", default="", help="Agent id")
    next_p.add_argument("--no-claim", action="store_true", help="Preview without claiming")
    next_p.set_defaults(func=cmd_story_next)
    claim_p = story_sub.add_parser("claim", help="Claim a story")
    add_common(claim_p)
    claim_p.add_argument("story_id")
    claim_p.add_argument("--agent", default="", help="Agent id")
    claim_p.add_argument("--reclaim", action="store_true", help="Reclaim an expired ACTIVE story")
    claim_p.set_defaults(func=cmd_story_claim)
    context_p = story_sub.add_parser("context", help="Print story context")
    add_common(context_p)
    context_p.add_argument("story_id", nargs="?")
    context_p.add_argument("--agent", default="", help="Agent id")
    context_p.set_defaults(func=cmd_story_context)
    submit_p = story_sub.add_parser("submit-qa", help="Submit active story to QA")
    add_common(submit_p)
    submit_p.add_argument("story_id", nargs="?")
    submit_p.add_argument("--agent", default="", help="Agent id")
    submit_p.set_defaults(func=cmd_story_submit_qa)
    release_p = story_sub.add_parser("release", help="Release active story back to READY")
    add_common(release_p)
    release_p.add_argument("story_id", nargs="?")
    release_p.add_argument("--agent", default="", help="Agent id")
    release_p.add_argument("--force", action="store_true")
    release_p.set_defaults(func=cmd_story_release)


def _add_task(sub) -> None:
    task_p = sub.add_parser("task", help="Task commands")
    task_sub = task_p.add_subparsers(dest="task_command", required=True)
    start_p = task_sub.add_parser("start", help="Start a task")
    add_common(start_p)
    start_p.add_argument("task_id")
    start_p.add_argument("--story", dest="story_id", default="")
    start_p.add_argument("--agent", default="", help="Agent id")
    start_p.set_defaults(func=cmd_task_start)
    complete_p = task_sub.add_parser("complete", help="Complete a task after running verify_cmd")
    add_common(complete_p)
    complete_p.add_argument("task_id")
    complete_p.add_argument("--story", dest="story_id", default="")
    complete_p.add_argument("--agent", default="", help="Agent id")
    complete_p.add_argument("--verify-cmd", default="", help="Override story verify_cmd")
    complete_p.add_argument("--verify-timeout", type=int, default=600)
    complete_p.add_argument("--covers", "--ac", nargs="*", default=[], help="AC/DEL IDs covered")
    complete_p.add_argument("--note", default="")
    complete_p.set_defaults(func=cmd_task_complete)
    fail_p = task_sub.add_parser("fail", help="Mark task failed")
    add_common(fail_p)
    fail_p.add_argument("task_id")
    fail_p.add_argument("--story", dest="story_id", default="")
    fail_p.add_argument("--agent", default="", help="Agent id")
    fail_p.add_argument("--error", required=True)
    fail_p.set_defaults(func=cmd_task_fail)


def _add_bug(sub) -> None:
    bug_p = sub.add_parser("bug", help="QA bug commands for DEV fixes")
    bug_sub = bug_p.add_subparsers(dest="bug_command", required=True)
    resolve_p = bug_sub.add_parser("resolve", help="Resolve a QA bug in the active story")
    add_common(resolve_p)
    resolve_p.add_argument("bug_id")
    resolve_p.add_argument("--story", dest="story_id", default="")
    resolve_p.add_argument("--agent", default="", help="Agent id")
    resolve_p.add_argument("--verify-cmd", default="", help="Command proving the bug fix")
    resolve_p.add_argument("--verify-timeout", type=int, default=600)
    resolve_p.add_argument("--note", default="")
    resolve_p.set_defaults(func=cmd_bug_resolve)


def _add_qa(sub) -> None:
    qa_p = sub.add_parser("qa", help="QA commands")
    qa_sub = qa_p.add_subparsers(dest="qa_command", required=True)
    qa_start_p = qa_sub.add_parser("start", help="Select QA story")
    add_common(qa_start_p)
    qa_start_p.add_argument("story_id", nargs="?")
    qa_start_p.add_argument("--agent", default="", help="Agent id")
    qa_start_p.set_defaults(func=cmd_qa_start)
    qa_fail_p = qa_sub.add_parser("fail", help="Return story with a QA bug")
    add_common(qa_fail_p)
    qa_fail_p.add_argument("story_id")
    qa_fail_p.add_argument("--bug", required=True)
    qa_fail_p.set_defaults(func=cmd_qa_fail)
    qa_approve_p = qa_sub.add_parser("approve", help="Approve a single QA story")
    add_common(qa_approve_p)
    qa_approve_p.add_argument("story_id")
    qa_approve_p.add_argument("--agent", default="", help="Agent id")
    qa_approve_p.add_argument("--verify-timeout", type=int, default=600)
    qa_approve_p.set_defaults(func=cmd_qa_approve)
    qa_run_p = qa_sub.add_parser("run", help="Audit and resolve every QA-pending story in one batch")
    add_common(qa_run_p)
    qa_run_p.add_argument("--agent", default="", help="Agent id")
    qa_run_p.add_argument("--verify-timeout", type=int, default=600)
    qa_run_p.add_argument("--force", action="store_true", help="Override the QA round cap after user escalation")
    qa_run_p.set_defaults(func=cmd_qa_run)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except NexusError as exc:
        import sys

        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

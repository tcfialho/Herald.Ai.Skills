"""Deterministic user simulator: mechanical anchor matching, no LLM in the loop.

Contract (rev.2 §9): an anchor that does not match is a `desync`, never a guessed
reply. `respond_label` resolves the option number by scanning the menu text in
the assistant's last message, so scripts survive menu renumbering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SimReply:
    status: str  # "reply" | "done" | "desync"
    text: str = ""
    detail: str = ""
    next_index: int = 0  # script position after this reply is consumed


_MENU_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(\d+)(?:\*\*)?\s*[.):\-]\s*(.+?)\s*$")


def _anchor_matches(anchor: str, text: str) -> bool:
    """Case-insensitive substring; falls back to regex when the anchor contains
    regex metacharacters that a plain substring would miss."""
    if anchor.lower() in text.lower():
        return True
    try:
        return re.search(anchor, text, re.IGNORECASE) is not None
    except re.error:
        return False


def resolve_label(label: str, text: str) -> str | None:
    """Find a numbered menu line containing `label`; return the number."""
    for line in text.splitlines():
        m = _MENU_LINE.match(line)
        if m and label.lower() in m.group(2).lower():
            return m.group(1)
    return None


def next_reply(user_script: list[dict], step_index: int, last_assistant_text: str) -> SimReply:
    """Decide what the simulated user says after the SUT ends a turn.

    step_index: how many script steps were already consumed. A step marked
    `optional: true` that does not match is skipped and the next step is tried
    (real SUTs sometimes legitimately shortcut a menu); a non-matching
    REQUIRED step is still a desync — the simulator never guesses.
    """
    i = step_index
    while i < len(user_script):
        step = user_script[i]
        anchors = step["expect_any"]
        if any(_anchor_matches(a, last_assistant_text) for a in anchors):
            return _respond(step, last_assistant_text, next_index=i + 1)
        if step.get("optional"):
            i += 1
            continue
        return SimReply(
            "desync",
            detail=f"step {i}: none of {anchors!r} matched the last assistant message",
            next_index=i,
        )
    return SimReply("done", next_index=i)


def _respond(step: dict, last_assistant_text: str, *, next_index: int) -> SimReply:
    if step.get("respond_label"):
        number = resolve_label(step["respond_label"], last_assistant_text)
        if number is not None:
            return SimReply("reply", number, next_index=next_index)
        # No numbered menu found: answer with the label text itself (fallback menus
        # sometimes render as prose); still deterministic.
        return SimReply("reply", step["respond_label"], next_index=next_index)
    return SimReply("reply", str(step["respond"]), next_index=next_index)

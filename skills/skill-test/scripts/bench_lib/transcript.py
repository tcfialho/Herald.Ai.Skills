"""Normalize adapter raw events into the bench transcript schema (§4.3)."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def normalize_stream_events(raw_events: list[dict]) -> list[dict]:
    """Claude Code stream-json → normalized turns.

    One normalized turn per assistant message (text + tool calls merged) and one
    per tool_result / simulated user reply.
    """
    turns: list[dict] = []
    for ev in raw_events:
        etype = ev.get("type")
        if etype == "assistant":
            texts, calls = [], []
            for block in ev.get("message", {}).get("content", []) or []:
                if block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
                elif block.get("type") == "tool_use":
                    calls.append(
                        {
                            "name": block.get("name", ""),
                            "input": block.get("input") or {},
                            "input_digest": _digest(block.get("input") or {}),
                        }
                    )
            if texts or calls:
                turns.append(
                    {
                        "idx": len(turns),
                        "role": "assistant",
                        "text": "\n".join(texts),
                        "tool_calls": calls,
                    }
                )
        elif etype == "user":
            content = ev.get("message", {}).get("content")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        turns.append(
                            {
                                "idx": len(turns),
                                "role": "tool_result",
                                "text": _tool_result_text(block),
                                "tool_calls": [],
                            }
                        )
            elif isinstance(content, str):
                turns.append({"idx": len(turns), "role": "user_sim", "text": content, "tool_calls": []})
    return turns


def _tool_result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return json.dumps(content, ensure_ascii=False) if content is not None else ""


def append_user_turn(turns: list[dict], text: str) -> None:
    turns.append({"idx": len(turns), "role": "user_sim", "text": text, "tool_calls": []})


def last_assistant_text(turns: list[dict]) -> str:
    """Concatenate every assistant text block since the last user turn, in order.

    A SUT often writes the substantive screen (plan + menu) in one assistant
    turn, then a short trailing nudge ("Reply with a number...") in another
    before yielding — tool calls in between don't end the "conversational
    turn" from the user's point of view. Matching only the very last block
    caused false desyncs when the real anchor was one block up (observed live
    on git-commit's create-branch scenario).
    """
    tail: list[str] = []
    for turn in reversed(turns):
        if turn["role"] in ("user_sim",):
            break
        if turn["role"] == "assistant" and turn["text"].strip():
            tail.append(turn["text"])
    return "\n\n".join(reversed(tail))


def detect_activation(turns: list[dict], skill_name: str, workspace: str | None = None) -> bool:
    """Did the SUT actually load the skill? Skill tool call or SKILL.md read.

    A Read only counts when the path sits inside the hermetic workspace —
    run-3 showed haiku Read-ing a hallucinated ~/.claude/... path (the call
    fails, but the tool_use event exists) and being miscounted as activated.
    """
    needle = f"skills/{skill_name}/SKILL.md".lower()
    ws = workspace.replace("\\", "/").lower().rstrip("/") if workspace else None
    for turn in turns:
        for call in turn["tool_calls"]:
            if call["name"] == "Skill" and call["input"].get("skill") == skill_name:
                return True
            if call["name"] == "Read":
                path = str(call["input"].get("file_path", "")).replace("\\", "/").lower()
                if needle in path and (ws is None or path.startswith(ws + "/")):
                    return True
    return False

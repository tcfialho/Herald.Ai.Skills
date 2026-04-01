"""
Nexus Core - Proto Loader

Shared utility for loading proto.json screen decisions and building
UC → compact screen index. Used by StoryGenerator and TaskBreaker
to inject proto_refs into stories/tasks.
"""

from __future__ import annotations

import json
from pathlib import Path


def normalize_uc_id(uc_raw: str) -> str:
    """Normalize UC IDs: 'UC01' → 'UC-01', 'UC-01' stays."""
    cleaned = uc_raw.strip().upper()
    if cleaned.startswith("UC-"):
        return cleaned
    if cleaned.startswith("UC"):
        num = cleaned[2:]
        return f"UC-{num}"
    return cleaned


def _compact_screen(screen: dict) -> dict:
    """Extract compact representation of a decided screen."""
    chosen = screen.get("chosen", "")
    if chosen == "A":
        chosen_intent = screen.get("variant_a_intent", "")
    elif chosen == "B":
        chosen_intent = screen.get("variant_b_intent", "")
    else:
        chosen_intent = ""

    return {
        "screen_id": screen["screen_id"],
        "screen_name": screen["screen_name"],
        "dimension": screen["dimension"],
        "chosen": chosen,
        "chosen_intent": chosen_intent,
        "change_requests": [
            cr["description"] for cr in screen.get("change_requests", [])
        ],
    }


def load_proto_index(plan_dir: "str | Path") -> dict[str, list[dict]]:
    """Load proto.json from plan_dir and build UC → compact screen decisions index.

    Args:
        plan_dir: Directory containing proto.json (same as spec.md location).

    Returns:
        Dict mapping normalized UC IDs to lists of compact screen decisions.
        Empty dict if proto.json doesn't exist.
    """
    proto_path = Path(plan_dir) / "proto.json"
    if not proto_path.exists():
        return {}

    with open(proto_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    uc_index: dict[str, list[dict]] = {}
    for screen in data.get("screens", []):
        if screen.get("status") != "decided":
            continue
        compact = _compact_screen(screen)
        for uc in screen.get("source_ucs", []):
            uc_normalized = normalize_uc_id(uc)
            uc_index.setdefault(uc_normalized, []).append(compact)
    return uc_index

"""Adapter interface. A new CLI = a new module implementing these hooks."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Invocation:
    """One headless CLI call (opening prompt or a resume)."""
    ok: bool
    events: list[dict] = field(default_factory=list)
    session_id: str | None = None
    resolved_model: str | None = None
    final_text: str = ""
    cost_usd: float = 0.0
    usage: dict = field(default_factory=dict)
    num_turns: int = 0
    duration_ms: int = 0
    error: str = ""
    error_kind: str = ""  # "infra" | "over_budget" | ""


@dataclass
class Caps:
    usage_quality: str = "exact"        # exact | estimated
    activation_observable: bool = True  # can we SEE whether the skill was loaded?
    events_observable: bool = True      # is there a tool-call stream for event checks?
    parallel_safe: bool = True          # can cells of this adapter run concurrently?


def get_adapter(name: str):
    if name == "claude_code":
        from . import claude_code
        return claude_code
    if name == "agy":
        from . import agy
        return agy
    raise ValueError(f"unknown adapter: {name} (available: claude_code, agy)")


def sum_usage(invocations: list[Invocation]) -> dict:
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_creation": 0}
    cost = 0.0
    turns = 0
    for inv in invocations:
        u = inv.usage or {}
        totals["input_tokens"] += u.get("input_tokens", 0)
        totals["output_tokens"] += u.get("output_tokens", 0)
        totals["cache_read"] += u.get("cache_read_input_tokens", 0)
        totals["cache_creation"] += u.get("cache_creation_input_tokens", 0)
        cost += inv.cost_usd
        turns += inv.num_turns
    totals["fresh_input"] = totals["input_tokens"] + totals["cache_creation"]
    totals["cost_usd"] = round(cost, 6)
    totals["api_turns"] = turns
    return totals

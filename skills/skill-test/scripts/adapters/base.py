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
    if name == "cursor":
        from . import cursor
        return cursor
    if name == "copilot":
        from . import copilot
        return copilot
    raise ValueError(f"unknown adapter: {name} (available: claude_code, agy, cursor, copilot)")


# adapter name -> executable that must exist for it to run
ADAPTER_BINARIES = {
    "claude_code": ("claude",),
    "agy": ("agy",),
    "cursor": ("agent", "cursor-agent"),
    "copilot": ("copilot",),
}


def resolve_adapter(name: str | None, cfg: dict):
    """Resolve which adapter to use: explicit --adapter > config.yaml
    default_adapter > host detection (env fingerprint, then process tree) >
    the only CLI installed. Ambiguity errors with guidance — never a silent
    guess. Returns (adapter_module, provenance_string)."""
    import shutil

    from bench_lib.config import BenchError

    if name and name != "auto":
        return get_adapter(name), f"explicit --adapter {name}"
    cfg_default = (cfg or {}).get("default_adapter")
    if cfg_default:
        return get_adapter(cfg_default), f"config.yaml default_adapter: {cfg_default}"

    from .detect import detect_host
    det = detect_host()
    if det["adapter"]:
        return get_adapter(det["adapter"]), f"host detected ({det['method']})"
    if det["method"] == "ambiguous":
        raise BenchError(
            f"nested host sessions detected ({', '.join(det['candidates'])}) and the "
            "process tree could not tell which is innermost",
            next_step="pass --adapter <name> or set default_adapter in skill-test config.yaml",
        )

    installed = [
        a for a, exes in ADAPTER_BINARIES.items()
        if any(shutil.which(exe) for exe in exes)
    ]
    if len(installed) == 1:
        return get_adapter(installed[0]), f"only CLI installed ({installed[0]})"
    if not installed:
        raise BenchError(
            "no supported agent CLI found on PATH (claude, agent, copilot, agy)",
            next_step="install at least one, or run `test_tool.py doctor` for details",
        )
    raise BenchError(
        f"no host session detected and several CLIs are installed ({', '.join(installed)})",
        next_step="pass --adapter <name> or set default_adapter in skill-test config.yaml",
    )


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

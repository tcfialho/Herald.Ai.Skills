"""Paired blind A/B comparison between two runs (P3: paired > absolute).

For each cell present in both runs, the judge sees the two transcripts in a
random order, twice (both orders); verdicts that disagree between orders
collapse to "tie" — position bias cannot survive that. Deterministic metric
deltas (cost, tokens, turns) ride along, computed by script, not judged.
"""
from __future__ import annotations

import random
from pathlib import Path

from .assets import contract_items_for_scenario
from .config import BenchError
from .runner import load_progress, run_dir
from .util import dump_json, emit_event, now_iso, read_json

COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": ["contract", "clarity", "overall"]},
                    "winner": {"type": "string", "enum": ["1", "2", "tie"]},
                    "reason": {"type": "string"},
                },
                "required": ["dimension", "winner", "reason"],
            },
        }
    },
    "required": ["verdicts"],
}

DIMENSIONS = ("contract", "clarity", "overall")


def compare_runs(
    *, cfg: dict, skill_dir: Path, run_a: str, run_b: str, contract: dict,
    scenarios_by_name: dict[str, dict], judge_model: str | None,
) -> dict:
    from adapters.base import resolve_judge

    adapter, default_model, _ = resolve_judge(cfg)
    model = judge_model or default_model

    rdir_a, rdir_b = run_dir(skill_dir, run_a), run_dir(skill_dir, run_b)
    prog_a, prog_b = load_progress(rdir_a), load_progress(rdir_b)
    common = sorted(
        k for k in prog_a
        if k in prog_b
        and prog_a[k]["status"] in ("pass", "fail")
        and prog_b[k]["status"] in ("pass", "fail")
    )
    if not common:
        raise BenchError(
            f"no comparable cells between {run_a} and {run_b}",
            next_step="both runs need verdict cells (pass/fail) for the same scenario/model/rep",
        )

    import tempfile
    from .util import safe_rmtree
    neutral = Path(tempfile.mkdtemp(prefix="bench-compare-"))
    cells_out, total_cost = [], 0.0
    rng = random.Random(f"{run_a}:{run_b}")  # reproducible order shuffling
    try:
        for cell_key in common:
            scenario_name = cell_key.split("/")[0]
            scenario = scenarios_by_name.get(scenario_name)
            items = contract_items_for_scenario(contract, scenario) if scenario else []
            tr_a = _cell_transcript(rdir_a, cell_key)
            tr_b = _cell_transcript(rdir_b, cell_key)

            verdict_rounds = []
            for a_first in _both_orders(rng):
                first, second = (tr_a, tr_b) if a_first else (tr_b, tr_a)
                prompt = _build_prompt(items, first, second)
                result = adapter.judge_invoke(prompt=prompt, model=model,
                                              schema=COMPARE_SCHEMA, cwd=neutral)
                total_cost += result["cost_usd"]
                mapped = {}
                for v in result["output"].get("verdicts", []):
                    if v["dimension"] not in DIMENSIONS:
                        continue
                    winner = v["winner"]
                    if winner in ("1", "2"):
                        shown_first_is_a = a_first
                        winner = ("A" if (winner == "1") == shown_first_is_a else "B")
                    mapped[v["dimension"]] = {"winner": winner, "reason": v["reason"][:200]}
                verdict_rounds.append(mapped)

            merged = {}
            for dim in DIMENSIONS:
                w1 = verdict_rounds[0].get(dim, {}).get("winner")
                w2 = verdict_rounds[1].get(dim, {}).get("winner")
                merged[dim] = {
                    "winner": w1 if w1 == w2 and w1 in ("A", "B") else "tie",
                    "rounds": [verdict_rounds[0].get(dim), verdict_rounds[1].get(dim)],
                }
            deltas = _metric_deltas(tr_a, tr_b)
            cells_out.append({"cell": cell_key, "verdicts": merged, "metric_deltas": deltas})
            emit_event("cell_compared", cell=cell_key,
                       overall=merged["overall"]["winner"])
    finally:
        safe_rmtree(neutral)

    summary = {dim: {"A": 0, "B": 0, "tie": 0} for dim in DIMENSIONS}
    for c in cells_out:
        for dim in DIMENSIONS:
            summary[dim][c["verdicts"][dim]["winner"]] += 1
    payload = {
        "skill": skill_dir.name, "run_a": run_a, "run_b": run_b,
        "judge_model": model, "compared_at": now_iso(), "cost_usd": round(total_cost, 4),
        "cells": cells_out, "summary": summary,
        "note": "A = --run-id, B = --baseline; per-dimension winner needs BOTH blind orders to agree, else tie",
    }
    dump_json(rdir_a / f"compare-vs-{run_b}.json", payload)
    return payload


def _both_orders(rng: random.Random):
    first = rng.random() < 0.5
    return [first, not first]


def _cell_transcript(rdir: Path, cell_key: str) -> dict:
    scenario, model, rep = cell_key.split("/")
    return read_json(rdir / "cells" / scenario / model / f"rep-{rep}" / "transcript.json")


def _metric_deltas(tr_a: dict, tr_b: dict) -> dict:
    ua, ub = tr_a.get("usage", {}), tr_b.get("usage", {})
    return {
        key: {"a": ua.get(key), "b": ub.get(key)}
        for key in ("cost_usd", "fresh_input", "output_tokens", "api_turns")
    }


def _render(tr: dict, label: str) -> list[str]:
    lines = [f"### Transcript {label}"]
    for t in tr.get("turns", []):
        text = t["text"][:1200] if t["role"] == "assistant" else t["text"][:300]
        calls = "".join(f" [tool:{c['name']}]" for c in t.get("tool_calls", []))
        lines.append(f"[{t['idx']}] {t['role']}:{calls} {text}")
    return lines


def _build_prompt(items: list[dict], first: dict, second: dict) -> str:
    lines = [
        "Two AI agents executed the same task under the same skill contract. "
        "Compare the two transcripts BLINDLY (you don't know which version is newer).",
        "",
        "Dimensions:",
        '- "contract": which transcript better obeys the contract items below',
        '- "clarity": which communicates better to the user (structure, no noise)',
        '- "overall": all things considered',
        'For each dimension answer winner "1", "2" or "tie" with a short reason. '
        "Prefer \"tie\" unless the difference is clear.",
        "",
        "## Contract items",
    ]
    lines += [f"- {it['id']} ({it['severity']}): {it['rule']}" for it in items]
    lines.append("")
    lines += _render(first, "1")
    lines.append("")
    lines += _render(second, "2")
    lines.append("")
    lines.append('Return JSON: {"verdicts": [{"dimension", "winner", "reason"}]}')
    return "\n".join(lines)

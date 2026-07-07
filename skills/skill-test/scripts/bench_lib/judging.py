"""LLM judge over judge-kind contract items.

Anti-hallucination guard (rev.2 §6/§8): a "fail" verdict must cite a verbatim
quote from the cited turn; the quote is verified mechanically here, in script —
an unverifiable fail is discarded (one retry, then judge_error). Judged via the
bench-level judge model from config.yaml, never by the session agent.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .assets import SEVERITY_WEIGHT, contract_items_for_scenario
from .config import BenchError
from .runner import load_progress, run_dir
from .util import dump_json, emit_event, normalize_ws, now_iso, read_json, safe_rmtree

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["pass", "fail"]},
                    "evidence": {
                        "type": "object",
                        "properties": {"turn": {"type": "integer"}, "quote": {"type": "string"}},
                    },
                    "confidence": {"type": "integer"},
                },
                "required": ["item", "verdict", "confidence"],
            },
        }
    },
    "required": ["verdicts"],
}

JUDGEABLE_STATUSES = {"pass", "fail"}


def judge_run(
    *, cfg: dict, skill_dir: Path, run_id: str, contract: dict,
    scenarios_by_name: dict[str, dict], judge_model: str | None, votes: int,
) -> dict:
    from adapters.base import resolve_judge

    adapter, default_model, _ = resolve_judge(cfg)
    model = judge_model or default_model
    rdir = run_dir(skill_dir, run_id)
    progress = load_progress(rdir)
    if not progress:
        raise BenchError(f"{run_id} has no finished cells to judge",
                         next_step="run `test_tool.py run` first (or `run --resume` to finish an interrupted matrix)")

    neutral_cwd = Path(tempfile.mkdtemp(prefix="bench-judge-"))
    cells_out, total_cost = [], 0.0
    try:
        for cell_key, rec in sorted(progress.items()):
            scenario_name, cell_model, rep = cell_key.split("/")
            scenario = scenarios_by_name.get(scenario_name)
            if scenario is None or rec["status"] not in JUDGEABLE_STATUSES:
                continue
            items = [
                it for it in contract_items_for_scenario(contract, scenario) if it["kind"] == "judge"
            ]
            if not items:
                continue
            cell_dir = rdir / "cells" / scenario_name / cell_model / f"rep-{rep}"
            tr = read_json(cell_dir / "transcript.json")
            state = read_json(cell_dir / "state.json")
            det = read_json(cell_dir / "checks.json")
            prompt = _build_prompt(items, tr["turns"], state["final"], det)

            try:
                verdicts, cost = _judge_with_votes(
                    adapter, prompt=prompt, model=model, votes=votes,
                    items=items, turns=tr["turns"], cwd=neutral_cwd,
                )
            except Exception as exc:  # one broken cell must not sink the whole judge run
                if "session limit" in str(exc).lower():
                    raise  # quota: stop burning attempts; re-run judge after reset
                emit_event("warning", msg=f"judge failed on {cell_key}: {str(exc)[:200]}")
                cells_out.append({
                    "cell": cell_key, "contract_pct": None,
                    "verdicts": [], "excluded_items": [it["id"] for it in items],
                    "judge_error": str(exc)[:300],
                })
                continue
            total_cost += cost
            score = _contract_score(items, verdicts)
            cells_out.append({
                "cell": cell_key, "contract_pct": score["pct"],
                "verdicts": verdicts, "excluded_items": score["excluded"],
            })
            emit_event("cell_judged", cell=cell_key, contract_pct=score["pct"])
    finally:
        safe_rmtree(neutral_cwd)

    payload = {
        "run_id": run_id, "judge_adapter": adapter.name, "judge_model": model, "votes": votes,
        "judged_at": now_iso(), "cost_usd": round(total_cost, 4), "cells": cells_out,
    }
    dump_json(rdir / "judge.json", payload)
    return payload


def _judge_with_votes(adapter, *, prompt, model, votes, items, turns, cwd):
    rounds, cost = [], 0.0
    for _ in range(max(1, votes)):
        result = adapter.judge_invoke(prompt=prompt, model=model, schema=JUDGE_SCHEMA, cwd=cwd)
        cost += result["cost_usd"]
        rounds.append(_verify_round(result["output"].get("verdicts", []), items, turns))
    merged = []
    for item in items:
        per_round = [r.get(item["id"]) for r in rounds if r.get(item["id"])]
        if not per_round:
            merged.append({"item": item["id"], "verdict": "judge_error",
                           "detail": "no usable verdict in any vote"})
            continue
        fails = [v for v in per_round if v["verdict"] == "fail"]
        winner = fails[0] if len(fails) * 2 > len(per_round) else \
            next(v for v in per_round if v["verdict"] == "pass") if any(
                v["verdict"] == "pass" for v in per_round) else fails[0]
        winner = dict(winner)
        winner["votes"] = f"{len(fails)}f/{len(per_round) - len(fails)}p"
        merged.append(winner)
    return merged, cost


import re as _re

_ITEM_ID_RX = _re.compile(r"[A-Za-z]+-\d+")


def _normalize_item_id(raw, known: set[str]) -> str | None:
    """Judges without schema enforcement decorate ids ("B-01 (major)") —
    recover the bare id when it unambiguously maps to a known item."""
    if raw in known:
        return raw
    m = _ITEM_ID_RX.search(str(raw or ""))
    return m.group(0) if m and m.group(0) in known else None


def _verify_round(raw_verdicts: list[dict], items: list[dict], turns: list[dict]) -> dict:
    """Keep only verdicts whose evidence survives mechanical verification."""
    by_id = {}
    known = {it["id"] for it in items}
    for v in raw_verdicts:
        iid = _normalize_item_id(v.get("item"), known)
        if iid is None or iid in by_id:
            continue
        if v["verdict"] == "fail":
            ev = v.get("evidence") or {}
            quote, turn_idx = ev.get("quote", ""), ev.get("turn", -1)
            if not quote or not _quote_in_turn(quote, turn_idx, turns):
                emit_event("warning", msg=f"judge evidence for {iid} failed verification; verdict discarded")
                continue
        by_id[iid] = {"item": iid, "verdict": v["verdict"],
                      "evidence": v.get("evidence"), "confidence": v.get("confidence")}
    return by_id


def _quote_in_turn(quote: str, turn_idx: int, turns: list[dict]) -> bool:
    q = normalize_ws(quote)
    if not q:
        return False
    if 0 <= turn_idx < len(turns) and q in normalize_ws(turns[turn_idx]["text"]):
        return True
    # tolerate off-by-one turn citations, but the quote must exist verbatim somewhere
    return any(q in normalize_ws(t["text"]) for t in turns)


def _contract_score(items: list[dict], verdicts: list[dict]) -> dict:
    v_by_id = {v["item"]: v for v in verdicts}
    num = den = 0
    excluded = []
    for it in items:
        v = v_by_id.get(it["id"])
        if not v or v["verdict"] == "judge_error":
            excluded.append(it["id"])
            continue
        w = SEVERITY_WEIGHT[it["severity"]]
        den += w
        if v["verdict"] == "pass":
            num += w
    return {"pct": round(100 * num / den, 1) if den else None, "excluded": excluded}


def _build_prompt(items: list[dict], turns: list[dict], final_state: dict, det: dict) -> str:
    lines = [
        "You are a strict QA judge for an AI agent skill. Evaluate ONLY the contract items below "
        "against the transcript of the agent under test (SUT).",
        "",
        "Rules:",
        '- A "fail" verdict REQUIRES evidence: the turn index and a quote of up to 200 characters '
        "copied VERBATIM from that turn. Unverifiable quotes void the verdict.",
        '- If you cannot cite verbatim evidence of a violation, the verdict must be "pass".',
        "- Judge only what each item states. Do not invent extra requirements.",
        "- confidence: 0-100.",
        "",
        "## Contract items",
    ]
    for it in items:
        lines.append(f"- {it['id']} ({it['severity']}): {it['rule']}")
    lines.append("")
    lines.append("## Transcript")
    for t in turns:
        text = t["text"][:2000] if t["role"] == "assistant" else t["text"][:500]
        calls = "".join(f" [tool:{c['name']}]" for c in t.get("tool_calls", []))
        lines.append(f"[{t['idx']}] {t['role']}:{calls} {text}")
    lines.append("")
    lines.append("## Final environment state (probe outputs)")
    for cmd, probe in (final_state.get("probes") or {}).items():
        lines.append(f"$ {cmd}\n{probe.get('stdout', '')[:400]}")
    lines.append(f"files: {', '.join(final_state.get('files', [])[:50])}")
    lines.append("")
    lines.append("## Deterministic check results (context only — do not re-judge these)")
    for r in det.get("items", []):
        lines.append(f"- {r['id']}: {r['status']}")
    lines.append("")
    lines.append('Return JSON: {"verdicts": [{"item", "verdict", "evidence": {"turn", "quote"}, "confidence"}]}')
    lines.append('"item" must be EXACTLY the item id (e.g. "B-01") — no severity, no extra text.')
    return "\n".join(lines)

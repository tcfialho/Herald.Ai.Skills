"""Mutation testing (P5): plant known defects in a COPY of the skill and check
the suite catches them. Two products per mutation:

- detected/undetected → is the suite trustworthy? (target: catch criticals)
- "decorative rule": a mutation that removes a rule and NOTHING fails means the
  rule has no behavioral effect — a token-cut candidate (or a rule the models
  ignore either way; both readings demand action).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import judging, runner
from .config import BenchError
from .util import dump_json, emit_event, load_structured, now_iso, safe_rmtree


def load_mutations(skill_dir: Path, mutations_file: str | None) -> list[dict]:
    path = Path(mutations_file) if mutations_file else skill_dir / "tests" / "mutations.yaml"
    if not path.exists():
        raise BenchError(
            f"no mutations file at {path}",
            next_step="author tests/mutations.yaml: a list of {id, description, "
                      "expect_detected_by: [item ids], edits: [{old_string, new_string}]}",
        )
    mutations = load_structured(path)
    if not isinstance(mutations, list) or not mutations:
        raise BenchError(f"{path.name} must be a non-empty list of mutations")
    for m in mutations:
        if not m.get("id") or not m.get("edits"):
            raise BenchError(f"mutation missing id/edits: {m}")
    return mutations


def mutate(
    *, cfg: dict, skill_dir: Path, adapter, contract: dict, scenarios: list[dict],
    mutations: list[dict], model: str, votes: int,
) -> dict:
    scenarios_by_name = {s["name"]: s for s in scenarios}
    results = []
    for m in mutations:
        work = Path(tempfile.mkdtemp(prefix="mutate-")) / skill_dir.name
        shutil.copytree(skill_dir, work, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        try:
            applied, err = _apply(work / "SKILL.md", m["edits"])
            if not applied:
                results.append({"id": m["id"], "status": "apply_error", "error": err})
                emit_event("warning", msg=f"mutation {m['id']} not applicable: {err}")
                continue
            meta = runner.run_matrix(
                cfg=cfg, skill_dir=skill_dir, adapter=adapter, models=[model],
                scenarios=scenarios, contract=contract, repeat=1, skill_ref=None,
                jobs=1, max_cost_usd=None, fail_fast=False, resume_run_id=None,
                label=f"mutate:{m['id']}", materialize_src=work,
            )
            judging.judge_run(
                cfg=cfg, skill_dir=skill_dir, run_id=meta["run_id"], contract=contract,
                scenarios_by_name=scenarios_by_name, judge_model=None, votes=votes,
            )
            from .adapting import _collect_failing
            failing = _collect_failing(runner.run_dir(skill_dir, meta["run_id"]), None)
            expected = set(m.get("expect_detected_by") or [])
            detected = bool(failing)
            results.append({
                "id": m["id"], "description": m.get("description", ""),
                "run_id": meta["run_id"], "status": "detected" if detected else "undetected",
                "failing_items": failing,
                "expected_hit": bool(expected & set(failing)) if expected else None,
                "decorative_rule_candidate": not detected,
            })
            emit_event("mutation_done", id=m["id"], detected=detected, failing=failing)
        finally:
            safe_rmtree(work.parent)

    evaluated = [r for r in results if r["status"] in ("detected", "undetected")]
    detected_n = sum(1 for r in evaluated if r["status"] == "detected")
    report = {
        "skill": skill_dir.name, "model": model, "votes": votes, "ts": now_iso(),
        "mutations_run": len(evaluated),
        "detected": detected_n,
        "detection_rate": round(detected_n / len(evaluated), 2) if evaluated else None,
        "decorative_candidates": [r["id"] for r in evaluated if r["decorative_rule_candidate"]],
        "results": results,
        "note": "target ≥0.9 on critical mutations before trusting the suite (P5); "
                "decorative candidates are token-cut / rewrite candidates",
    }
    dump_json(runner.baselines_dir(skill_dir) / "mutate-latest.json", report)
    return report


def _apply(skill_md: Path, edits: list[dict]) -> tuple[bool, str]:
    text = skill_md.read_text(encoding="utf-8")
    for e in edits:
        old = e["old_string"]
        if text.count(old) != 1:
            return False, f"old_string not unique/present: {old[:80]!r}"
        text = text.replace(old, e.get("new_string", ""))
    skill_md.write_text(text, encoding="utf-8")
    return True, ""

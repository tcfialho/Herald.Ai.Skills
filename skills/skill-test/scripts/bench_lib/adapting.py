"""Adaptation loop (fase 2): patch → re-run → gate, until the target model
meets the contract or the iteration budget runs out.

Safety model: the loop NEVER touches the real skill. It works on a temp copy;
the winning SKILL.md is saved next to the adapt report and the agent shows the
diff to the user for approval before applying anything.

P4 gate: a patch that fixes the weak model must not break the strong one —
each accepted iteration is re-validated on the gate model (ladder top).
"""
from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path

from . import judging, runner
from .assets import contract_items_for_scenario
from .config import BenchError
from .util import dump_json, emit_event, estimate_tokens, now_iso, read_json, safe_rmtree

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["old_string", "new_string"],
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["edits", "rationale"],
}


def adapt(
    *, cfg: dict, skill_dir: Path, adapter, contract: dict, scenarios: list[dict],
    target_model: str, target_items: list[str] | None, max_iters: int,
    votes: int, patcher_model: str | None,
) -> dict:
    from adapters.base import resolve_judge

    judge_adapter, default_model, _ = resolve_judge(cfg)
    patcher = patcher_model or default_model
    ladder = (cfg["adapters"].get(adapter.name) or {}).get("ladder") or [target_model]
    gate_model = ladder[0] if ladder[0] != target_model else None
    scenarios_by_name = {s["name"]: s for s in scenarios}
    threshold = cfg["defaults"]["floor_threshold"]

    base = runner.runs_dir(skill_dir)
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name.split("-")[1]) for p in base.glob("adapt-*") if p.name.split("-")[1].isdigit()]
    adir = base / f"adapt-{max(nums, default=0) + 1}"
    adir.mkdir()

    work = Path(tempfile.mkdtemp(prefix="adapt-")) / skill_dir.name
    shutil.copytree(skill_dir, work, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    original_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    iterations = []
    converged = False
    gate_baseline_failing: list[str] | None = None  # measured lazily, on the ORIGINAL skill
    try:
        for it in range(max_iters + 1):  # iteration 0 = baseline measurement
            outcome = _measure(
                cfg=cfg, skill_dir=skill_dir, adapter=adapter, contract=contract,
                scenarios=scenarios, scenarios_by_name=scenarios_by_name,
                model=target_model, votes=votes, work=work,
                label=f"adapt{adir.name.split('-')[1]}:iter{it}",
            )
            failing = _collect_failing(
                runner.run_dir(skill_dir, outcome["run_id"]), target_items
            )
            record = {"iter": it, "run_id": outcome["run_id"], "failing_items": failing,
                      "cells_pass": outcome["cells_pass"], "cells_run": outcome["cells_run"]}
            emit_event("adapt_iter", **record)

            appended = False
            if not failing and outcome["cells_run"] == outcome["cells_pass"]:
                gate = {"skipped": gate_model is None}
                if gate_model and it > 0:  # only patched versions need the gate
                    if gate_baseline_failing is None:
                        # P4 is about REGRESSION: the strong model must not get
                        # worse than it already was on the ORIGINAL skill.
                        baseline = _gate(
                            cfg=cfg, skill_dir=skill_dir, adapter=adapter, contract=contract,
                            scenarios=scenarios, scenarios_by_name=scenarios_by_name,
                            model=gate_model, work=skill_dir,
                            label=f"adapt{adir.name.split('-')[1]}:gate-baseline",
                        )
                        gate_baseline_failing = baseline["failing"]
                    patched = _gate(
                        cfg=cfg, skill_dir=skill_dir, adapter=adapter, contract=contract,
                        scenarios=scenarios, scenarios_by_name=scenarios_by_name,
                        model=gate_model, work=work,
                        label=f"adapt{adir.name.split('-')[1]}:gate{it}",
                    )
                    new_failures = sorted(set(patched["failing"]) - set(gate_baseline_failing))
                    gate = {
                        "ok": not new_failures, "run_id": patched["run_id"],
                        "baseline_failing": gate_baseline_failing,
                        "patched_failing": patched["failing"],
                        "new_failures": new_failures,
                    }
                record["gate"] = gate
                iterations.append(record)
                appended = True
                if gate.get("skipped") or gate.get("ok"):
                    converged = True
                    break
                failing = [f"GATE:{gate_model} new failures: {gate['new_failures']}"]

            if it == max_iters:
                if not appended:
                    iterations.append(record)
                break

            patch = _propose_patch(
                judge_adapter=judge_adapter, patcher=patcher, work=work,
                failing=failing, outcome=outcome, history=iterations,
            )
            record["patch"] = {"applied": patch["applied"], "rationale": patch["rationale"],
                               "edits": len(patch["edits"]), "error": patch.get("error")}
            if not appended:
                iterations.append(record)
            if not patch["applied"]:
                emit_event("warning", msg=f"iter {it}: patch not applicable — {patch.get('error')}")

        adapted_md = (work / "SKILL.md").read_text(encoding="utf-8")
        diff = "".join(difflib.unified_diff(
            original_md.splitlines(keepends=True), adapted_md.splitlines(keepends=True),
            fromfile="SKILL.md (original)", tofile="SKILL.md (adapted)",
        ))
        (adir / "SKILL.adapted.md").write_text(adapted_md, encoding="utf-8")
        (adir / "final.diff").write_text(diff, encoding="utf-8")
        report = {
            "adapt_id": adir.name, "skill": skill_dir.name, "target_model": target_model,
            "gate_model": gate_model, "target_items": target_items,
            "converged": converged, "iterations": iterations,
            "prompt_tax": {
                "skill_md_delta_tokens_est": estimate_tokens(adapted_md) - estimate_tokens(original_md),
                "iterations_used": max(0, len([r for r in iterations if "patch" in r])),
            },
            "final_diff_lines": len(diff.splitlines()),
            "apply_hint": ("show final.diff to the user; apply to the real SKILL.md ONLY after "
                           "explicit approval, then run a smoke to refresh the seal"),
            "ts": now_iso(),
        }
        dump_json(adir / "adapt.json", report)
        return report
    finally:
        safe_rmtree(work.parent)


def _measure(*, cfg, skill_dir, adapter, contract, scenarios, scenarios_by_name,
             model, votes, work, label):
    meta = runner.run_matrix(
        cfg=cfg, skill_dir=skill_dir, adapter=adapter, models=[model],
        scenarios=scenarios, contract=contract, repeat=1, skill_ref=None,
        jobs=1, max_cost_usd=None, fail_fast=False, resume_run_id=None,
        label=label, materialize_src=work,
    )
    if meta["cells_run"]:
        judging.judge_run(
            cfg=cfg, skill_dir=skill_dir, run_id=meta["run_id"], contract=contract,
            scenarios_by_name=scenarios_by_name, judge_model=None, votes=votes,
        )
    return meta


def _collect_failing(rdir: Path, target_items: list[str] | None) -> list[str]:
    """Failing contract item ids in a judged run (restricted to target_items when given).
    Non-verdict cell statuses surface as STATUS: markers so the loop never
    mistakes a desync/quota for 'nothing left to fix'."""
    failing = set()
    progress = runner.load_progress(rdir)
    for cell_key, rec in progress.items():
        scenario, model, rep = cell_key.split("/")
        cdir = rdir / "cells" / scenario / model / f"rep-{rep}"
        if (cdir / "checks.json").exists():
            det = read_json(cdir / "checks.json")
            failing.update(i["id"] for i in det["items"] if i["status"] == "fail")
        if rec["status"] not in ("pass", "fail"):
            failing.add(f"STATUS:{cell_key}:{rec['status']}")
    jfile = rdir / "judge.json"
    if jfile.exists():
        for cell in read_json(jfile)["cells"]:
            failing.update(v["item"] for v in cell["verdicts"] if v["verdict"] == "fail")
    items = sorted(failing)
    if target_items:
        items = [i for i in items if i in target_items or i.startswith("STATUS:")]
    return items


def _gate(*, cfg, skill_dir, adapter, contract, scenarios, scenarios_by_name,
          model, work, label):
    meta = _measure(cfg=cfg, skill_dir=skill_dir, adapter=adapter, contract=contract,
                    scenarios=scenarios, scenarios_by_name=scenarios_by_name,
                    model=model, votes=1, work=work, label=label)
    failing = _collect_failing(runner.run_dir(skill_dir, meta["run_id"]), None)
    ok = meta["cells_run"] == meta["cells_pass"] and not failing
    return {"ok": ok, "run_id": meta["run_id"], "failing": failing}


def _propose_patch(*, judge_adapter, patcher, work, failing, outcome, history):
    skill_md = (work / "SKILL.md").read_text(encoding="utf-8")
    past = [
        f"- iter {r['iter']}: patched ({r['patch']['rationale'][:120]}) → still failing: {r.get('failing_items')}"
        for r in history if r.get("patch")
    ]
    prompt = (
        "You are adapting an AI-agent skill prompt so a weaker model obeys its contract.\n"
        "Propose the MINIMAL edit set to the SKILL.md below that fixes the failing contract "
        "items without changing any other behavior. Prefer moving/rephrasing rules for "
        "salience over adding text; every added token is a permanent cost.\n\n"
        f"## Failing contract items\n" + "\n".join(f"- {f}" for f in failing) + "\n\n"
        + ("## Previous attempts (did NOT fully work — try a different lever)\n" + "\n".join(past) + "\n\n" if past else "")
        + "## Current SKILL.md\n```markdown\n" + skill_md + "\n```\n\n"
        "Return JSON: {edits: [{old_string, new_string}], rationale}. Each old_string must "
        "appear EXACTLY ONCE in the file, copied verbatim."
    )
    try:
        result = judge_adapter.judge_invoke(
            prompt=prompt, model=patcher, schema=PATCH_SCHEMA, cwd=work, timeout_s=300,
        )
    except (RuntimeError, Exception) as exc:  # noqa: BLE001 - patcher failure is an iteration outcome
        return {"applied": False, "edits": [], "rationale": "", "error": f"patcher call failed: {exc}"}
    edits = result["output"].get("edits", [])
    rationale = result["output"].get("rationale", "")
    text = skill_md
    for edit in edits:
        old = edit["old_string"]
        if text.count(old) != 1:
            return {"applied": False, "edits": edits, "rationale": rationale,
                    "error": f"old_string not unique/present: {old[:80]!r}"}
        text = text.replace(old, edit["new_string"])
    if text == skill_md:
        return {"applied": False, "edits": edits, "rationale": rationale, "error": "empty patch"}
    (work / "SKILL.md").write_text(text, encoding="utf-8")
    return {"applied": True, "edits": edits, "rationale": rationale}

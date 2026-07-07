"""Consolidation: init scaffolding, status, report, promote, floor, profile."""
from __future__ import annotations

from pathlib import Path

from .config import BenchError
from .runner import baselines_dir, load_progress, run_dir
from .util import dump_json, estimate_tokens, now_iso, read_json, skill_behavior_hash

# ---------------------------------------------------------------- init

GITIGNORE = "run-*/cells/\nrun-*/judge-raw/\n"

EXAMPLE_SCENARIO = """\
# Example scenario — copy, rename, edit. See skill-test references/authoring.md.
version: 1
name: example
goal: "One user journey through the skill, phrased as the user would."
fixture: example              # tests/fixtures/example/setup.py (delete key if no fixture needed)
invocation: auto              # auto = natural prompt (measures activation) | explicit
opening_prompt: "do the thing"
allowed_tools: ["Read", "Write"]
user_script:
  - expect_any: ["How do you want to proceed"]
    respond_label: "Approve"
on_desync: fail
contract_focus: []            # scope:always items are evaluated automatically
budget: {max_turns: 12, max_cost_usd: 0.40, timeout_s: 300}
"""

EXAMPLE_SETUP = '''\
"""Fixture setup: build the world inside the workspace dir (argv[1]).

Must be idempotent and self-contained; print nothing on success, exit non-zero
on failure. The workspace becomes the SUT's CWD.
"""
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
(workspace / "README.md").write_text("fixture world\\n", encoding="utf-8")
'''

CONTRACT_SKELETON = """\
# Contract for this skill — the testable spec, SEPARATE from SKILL.md on purpose
# (editing the skill must not silently edit the test). Authored by the agent
# from SKILL.md rules; see skill-test references/authoring.md for check types.
version: 1
skill: {skill}
items: []
#  - id: C-01
#    kind: judge                  # judge | deterministic
#    severity: major              # critical | major | minor
#    scope: always                # always (every scenario) | focused (via contract_focus)
#    rule: "Every chat message starts with the skill banner."
#  - id: C-02
#    kind: deterministic
#    severity: critical
#    scope: focused
#    rule: "The expected file is produced."
#    checks:
#      - {{type: file_exists, path: "out/*.txt"}}
#      - {{type: state, cmd: "git log --format=%s", expect_regex_per_line: "^(feat|fix): .+"}}
"""


def cmd_init(skill_dir: Path) -> dict:
    tests = skill_dir / "tests"
    created = []
    for sub in ("scenarios", "fixtures/example", "baselines"):
        d = tests / sub
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d))
    targets = {
        tests / "contract.yaml": CONTRACT_SKELETON.format(skill=skill_dir.name),
        tests / "scenarios" / "example.yaml.disabled": EXAMPLE_SCENARIO,
        tests / "fixtures" / "example" / "setup.py": EXAMPLE_SETUP,
        tests / "baselines" / ".gitignore": GITIGNORE,
    }
    for path, content in targets.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(str(path))
    return {
        "status": "ok", "skill": skill_dir.name, "created": created,
        "next": "author contract.yaml items and at least one scenario (agent judgment, "
                "guided by skill-test references/authoring.md), then `bench run`",
    }


# ---------------------------------------------------------------- status / report

def cmd_status(skill_dir: Path, run_id: str) -> dict:
    rdir = run_dir(skill_dir, run_id)
    meta = read_json(rdir / "run.json")
    progress = load_progress(rdir)
    by_status: dict[str, int] = {}
    for rec in progress.values():
        by_status[rec["status"]] = by_status.get(rec["status"], 0) + 1
    return {
        "run_id": run_id, "run_status": meta.get("status"),
        "cells_total": meta.get("cells_total"), "cells_done": len(progress),
        "by_status": by_status,
        "cost_usd": round(sum(r.get("cost_usd", 0) for r in progress.values()), 4),
    }


def cmd_report(skill_dir: Path, run_id: str, vs_baseline: bool, cell: str | None) -> dict:
    rdir = run_dir(skill_dir, run_id)
    meta = read_json(rdir / "run.json")
    if cell:
        return _cell_report(rdir, cell)
    progress = load_progress(rdir)
    judge = read_json(rdir / "judge.json") if (rdir / "judge.json").exists() else None
    judge_by_cell = {c["cell"]: c for c in (judge or {}).get("cells", [])}

    matrix: dict[str, dict] = {}
    failures = []
    for cell_key, rec in sorted(progress.items()):
        scenario, model, rep = cell_key.split("/")
        cdir = rdir / "cells" / scenario / model / f"rep-{rep}"
        det = read_json(cdir / "checks.json") if (cdir / "checks.json").exists() else {}
        tr = read_json(cdir / "transcript.json") if (cdir / "transcript.json").exists() else {}
        jc = judge_by_cell.get(cell_key)
        entry = matrix.setdefault(scenario, {}).setdefault(model, {"reps": []})
        entry["reps"].append({
            "rep": int(rep), "status": rec["status"],
            "compliance_pct": det.get("compliance_pct"),
            "contract_pct": jc["contract_pct"] if jc else None,
            "critical_failed": det.get("critical_failed", []),
            "activated": tr.get("meta", {}).get("activated"),
            "cost_usd": rec.get("cost_usd"), "wall_s": rec.get("wall_s"),
            "tokens_out": tr.get("usage", {}).get("output_tokens"),
        })
        if rec["status"] != "pass" or (jc and (jc["contract_pct"] or 100) < 100):
            failures.append(_failure_detail(cell_key, rec, det, jc))

    report = {
        "run": meta, "matrix": matrix,
        "ladder": _derive_ladder(meta.get("models", []), matrix),
        "failures": failures,
        "judge": {"model": judge.get("judge_model"), "cost_usd": judge.get("cost_usd")} if judge else None,
        "drill_down_hint": "test_tool.py report --run-id <id> --cell <scenario>,<model>,<rep>",
    }
    # Single-rep cells are a sample, not a verdict: the same skill text has
    # been observed swinging 100→0 between identical runs (SUT non-determinism).
    if int(meta.get("repeat", 1)) < 3:
        report["verdict_quality"] = (
            f"reps={meta.get('repeat', 1)}: NOT a verdict — pass/fail near the threshold is "
            "within known run-to-run variance; decisions (promote, prompt changes) need --repeat 3"
        )
    baseline_path = baselines_dir(skill_dir) / "baseline.json"
    if vs_baseline and baseline_path.exists():
        report["baseline"] = read_json(baseline_path)
    return report


def _failure_detail(cell_key, rec, det, jc):
    detail = {"cell": cell_key, "status": rec["status"], "failed_items": []}
    for item in det.get("items", []):
        if item["status"] == "fail":
            detail["failed_items"].append({
                "id": item["id"], "severity": item["severity"],
                "detail": "; ".join(c["detail"] for c in item["checks"] if c["status"] == "fail")[:300],
            })
    for v in (jc or {}).get("verdicts", []):
        if v["verdict"] == "fail":
            detail["failed_items"].append({
                "id": v["item"], "kind": "judge", "evidence": v.get("evidence"),
                "confidence": v.get("confidence"), "votes": v.get("votes"),
            })
    return detail


def _derive_ladder(models: list[str], matrix: dict) -> dict:
    """Highest→lowest: last model (in given strong→weak order) where every rep passes."""
    stable_until = None
    breaks_at = None
    for model in models:
        all_pass = all(
            rep["status"] == "pass"
            for scenario in matrix.values()
            for rep in scenario.get(model, {}).get("reps", [])
        ) and any(model in scenario for scenario in matrix.values())
        if all_pass:
            stable_until = model
        else:
            breaks_at = model
            break
    return {"stable_until": stable_until, "breaks_at": breaks_at}


def _cell_report(rdir: Path, cell: str) -> dict:
    try:
        scenario, model, rep = cell.split(",")
    except ValueError:
        raise BenchError("--cell expects <scenario>,<model>,<rep>",
                         next_step="example: --cell happy-path,sonnet,1")
    cdir = rdir / "cells" / scenario / model / f"rep-{rep}"
    if not cdir.exists():
        raise BenchError(f"cell dir not found: {cdir}",
                         next_step="list cells with `test_tool.py status --run-id <id>`")
    out = {"cell": f"{scenario}/{model}/{rep}"}
    for name in ("transcript", "checks", "state"):
        path = cdir / f"{name}.json"
        if path.exists():
            out[name] = read_json(path)
    judge_path = rdir / "judge.json"
    if judge_path.exists():
        out["judge"] = next(
            (c for c in read_json(judge_path)["cells"] if c["cell"] == out["cell"]), None
        )
    return out


# ---------------------------------------------------------------- promote

def cmd_promote(skill_dir: Path, run_id: str) -> dict:
    rdir = run_dir(skill_dir, run_id)
    meta = read_json(rdir / "run.json")
    if not (rdir / "judge.json").exists():
        raise BenchError(
            "refusing to promote an unjudged run",
            next_step=f"run `test_tool.py judge --skill {skill_dir.name} --run-id {run_id} --votes 3` first",
        )
    judge = read_json(rdir / "judge.json")
    if int(judge.get("votes", 1)) < 3:
        # 1-vote judges flip verdicts between runs (seen live: G-14); a baseline
        # promoted on a noisy judge poisons every future comparison.
        raise BenchError(
            f"refusing to promote: run was judged with {judge.get('votes', 1)} vote(s); baselines require 3",
            next_step=f"re-judge with `test_tool.py judge --skill {skill_dir.name} --run-id {run_id} --votes 3`, then promote",
        )
    report = cmd_report(skill_dir, run_id, vs_baseline=False, cell=None)
    baseline = {
        "run_id": run_id, "promoted_at": now_iso(),
        "skill_hash": meta["skill_hash"], "contract_hash": meta["contract_hash"],
        "matrix": report["matrix"], "ladder": report["ladder"],
    }
    dump_json(baselines_dir(skill_dir) / "baseline.json", baseline)
    return {"status": "ok", "baseline": run_id}


# ---------------------------------------------------------------- floor

def classify_rung(report: dict, threshold: dict) -> dict:
    """Native/floor classification for one ladder rung from its consolidated report."""
    reps = [
        rep
        for scenario in report["matrix"].values()
        for model_entry in scenario.values()
        for rep in model_entry["reps"]
    ]
    critical_ok = all(not rep["critical_failed"] and rep["status"] == "pass" for rep in reps)
    contract_scores = [rep["contract_pct"] for rep in reps if rep["contract_pct"] is not None]
    contract_ok = (
        min(contract_scores) >= threshold.get("contract", 90) if contract_scores else True
    )
    return {
        "meets_threshold": bool(reps) and critical_ok and contract_ok,
        "critical_ok": critical_ok,
        "min_contract_pct": min(contract_scores) if contract_scores else None,
    }


# ---------------------------------------------------------------- profile

def profile_decomposition(skill_dir: Path, run_id: str) -> dict:
    """Exact usage totals + ESTIMATED token split (skill text / payloads / chat)."""
    rdir = run_dir(skill_dir, run_id)
    progress = load_progress(rdir)
    skill_name = skill_dir.name
    skill_md_tokens = estimate_tokens((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    cells = []
    for cell_key in sorted(progress):
        scenario, model, rep = cell_key.split("/")
        cdir = rdir / "cells" / scenario / model / f"rep-{rep}"
        tpath = cdir / "transcript.json"
        if not tpath.exists():
            continue
        tr = read_json(tpath)
        # prefer the size recorded at run time (the materialized version under
        # test), falling back to the worktree only for pre-fix runs
        cell_skill_tokens = (
            round(tr["meta"]["skill_text_chars"] / 4)
            if tr.get("meta", {}).get("skill_text_chars")
            else skill_md_tokens
        )
        conv = payload = skill_ref_tokens = 0
        skill_marker = f"skills/{skill_name}/".lower()
        pending_skill_read = False
        for turn in tr["turns"]:
            if turn["role"] == "assistant":
                conv += estimate_tokens(turn["text"])
                pending_skill_read = any(
                    c["name"] == "Read"
                    and skill_marker in str(c["input"].get("file_path", "")).replace("\\", "/").lower()
                    for c in turn["tool_calls"]
                )
            elif turn["role"] == "tool_result":
                t = estimate_tokens(turn["text"])
                if pending_skill_read:
                    skill_ref_tokens += t
                    pending_skill_read = False
                else:
                    payload += t
        cells.append({
            "cell": cell_key,
            "usage_exact": tr["usage"],
            "estimated_split": {
                "skill_text": cell_skill_tokens + skill_ref_tokens,
                "tool_payloads": payload,
                "conversation": conv,
            },
        })
    return {
        "run_id": run_id, "note": "totals are exact (API usage); split is a chars/4 estimate",
        "skill_md_tokens_est": skill_md_tokens, "cells": cells,
    }


def cmd_overview(skills_root: Path) -> dict:
    """Dashboard data: every skill under the root, bench state of each."""
    skills = []
    for skill_dir in sorted(p for p in skills_root.iterdir() if (p / "SKILL.md").exists()):
        entry = {"skill": skill_dir.name, "has_tests": (skill_dir / "tests" / "contract.yaml").exists()}
        if entry["has_tests"]:
            try:
                from .assets import load_scenarios
                entry["scenarios"] = [s["name"] for s in load_scenarios(skill_dir, "all")]
            except Exception:
                entry["scenarios"] = []
            entry.update(seal_info(skill_dir))
            runs = sorted(
                (skill_dir / "tests" / "baselines").glob("run-*"),
                key=lambda p: int(p.name.split("-")[1]),
            )
            if runs and (runs[-1] / "run.json").exists():
                meta = read_json(runs[-1] / "run.json")
                entry["last_run"] = {
                    "run_id": meta["run_id"], "label": meta.get("label"),
                    "models": meta.get("models"), "status": meta.get("status"),
                    "pass": f"{meta.get('cells_pass', 0)}/{meta.get('cells_run', 0)}",
                    "judged": (runs[-1] / "judge.json").exists(),
                    "finished_at": meta.get("finished_at"),
                }
            baseline = skill_dir / "tests" / "baselines" / "baseline.json"
            entry["baseline"] = read_json(baseline)["run_id"] if baseline.exists() else None
        skills.append(entry)
    return {"skills_root": str(skills_root), "skills": skills}


def seal_info(skill_dir: Path) -> dict:
    path = baselines_dir(skill_dir) / "last-smoke.json"
    if not path.exists():
        return {"seal": None}
    seal = read_json(path)
    seal["hash_current"] = skill_behavior_hash(skill_dir)
    seal["stale"] = seal["hash_current"] != seal.get("skill_hash")
    return {"seal": seal}

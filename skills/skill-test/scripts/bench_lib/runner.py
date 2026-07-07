"""Cell orchestration: fixture → materialize → drive SUT → capture → checks.

The cell is the unit of checkpointing: every finished cell appends one line to
progress.jsonl, and `run --resume` re-runs only what is missing (infra errors
are retried; verdict statuses are kept).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import checks as checks_mod
from . import simulator, transcript
from .assets import contract_items_for_scenario
from .config import BenchError
from .util import (
    BENCH_VERSION, dump_json, emit_event, monotonic, now_iso, read_json,
    safe_rmtree, skill_behavior_hash,
)

TERMINAL_STATUSES = {"pass", "fail", "not_activated", "desync", "over_budget"}


# ---------------------------------------------------------------- run store

def baselines_dir(skill_dir: Path) -> Path:
    return skill_dir / "tests" / "baselines"


def new_run_id(skill_dir: Path) -> str:
    base = baselines_dir(skill_dir)
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name.split("-")[1]) for p in base.glob("run-*") if p.name.split("-")[1].isdigit()]
    return f"run-{max(nums, default=0) + 1}"


def run_dir(skill_dir: Path, run_id: str) -> Path:
    d = baselines_dir(skill_dir) / run_id
    if not d.exists():
        raise BenchError(f"run not found: {d}",
                         next_step="existing runs live in <skill>/tests/baselines/run-*; check `overview`")
    return d


def load_progress(rdir: Path) -> dict[str, dict]:
    done = {}
    progress = rdir / "progress.jsonl"
    if progress.exists():
        import json
        for line in progress.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["cell"]] = rec
    return done


class _Progress:
    def __init__(self, rdir: Path):
        self.path = rdir / "progress.jsonl"
        self.lock = threading.Lock()
        self.total_cost = 0.0

    def record(self, cell_key: str, status: str, cost: float, wall_s: float) -> None:
        import json
        with self.lock:
            self.total_cost += cost
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "cell": cell_key, "status": status, "cost_usd": round(cost, 6),
                    "wall_s": round(wall_s, 1), "ts": now_iso(),
                }) + "\n")
        emit_event("cell_done", cell=cell_key, status=status, cost_usd=round(cost, 6))


# ---------------------------------------------------------------- matrix run

def run_matrix(
    *,
    cfg: dict,
    skill_dir: Path,
    adapter,
    models: list[str],
    scenarios: list[dict],
    contract: dict,
    repeat: int,
    skill_ref: str | None,
    jobs: int,
    max_cost_usd: float | None,
    fail_fast: bool,
    resume_run_id: str | None,
    label: str,
    materialize_src: Path | None = None,  # adapt loop: test a patched COPY of the skill
) -> dict:
    defaults = cfg["defaults"]
    if resume_run_id:
        rdir = run_dir(skill_dir, resume_run_id)
        run_meta = read_json(rdir / "run.json")
        run_id = resume_run_id
    else:
        run_id = new_run_id(skill_dir)
        rdir = baselines_dir(skill_dir) / run_id
        (rdir / "cells").mkdir(parents=True)
        run_meta = {
            "run_id": run_id,
            "skill": skill_dir.name,
            "skill_ref": skill_ref or ("adapted-copy" if materialize_src else "worktree"),
            "skill_hash": skill_behavior_hash(materialize_src or skill_dir),
            "adapter": adapter.name,
            "usage_quality": adapter.capabilities.usage_quality,
            "models": models,
            "scenarios": [s["name"] for s in scenarios],
            "repeat": repeat,
            "label": label,
            "bench_version": BENCH_VERSION,
            "contract_hash": contract["_hash"],
            "started_at": now_iso(),
            "status": "running",
        }
        dump_json(rdir / "run.json", run_meta)

    done = load_progress(rdir)
    progress = _Progress(rdir)
    progress.total_cost = sum(rec.get("cost_usd", 0) for rec in done.values())
    budget = max_cost_usd if max_cost_usd is not None else defaults["run_budget_usd"]

    aborted = None
    for model in models:
        cells = [
            (scenario, model, rep)
            for scenario in scenarios
            for rep in range(1, repeat + 1)
            if not _already_done(done, scenario["name"], model, rep)
        ]
        if cells:
            if progress.total_cost >= budget:
                aborted = f"run budget ${budget:.2f} reached before model {model}"
                break
            if not adapter.capabilities.parallel_safe:
                jobs = 1  # e.g. agy: --continue resumes the GLOBAL latest conversation
            with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
                list(pool.map(
                    lambda c: _run_cell_safe(
                        c[0], c[1], c[2],
                        cfg=cfg, skill_dir=skill_dir, adapter=adapter, contract=contract,
                        skill_ref=skill_ref, rdir=rdir, progress=progress,
                        materialize_src=materialize_src,
                    ),
                    cells,
                ))
        done = load_progress(rdir)
        model_statuses = [
            rec["status"] for key, rec in done.items() if key.split("/")[1] == model
        ]
        if any(s == "quota" for s in model_statuses):
            aborted = ("plan quota exhausted — no more cells launched; "
                       f"resume after the limit resets with: run --resume {run_id}")
            break
        if fail_fast and any(s != "pass" for s in model_statuses):
            aborted = f"fail-fast: model {model} did not fully pass; weaker models skipped"
            break

    done = load_progress(rdir)
    statuses = [rec["status"] for rec in done.values()]
    run_meta.update({
        "finished_at": now_iso(),
        "status": "aborted" if aborted else "complete",
        "abort_reason": aborted,
        "total_cost_usd": round(progress.total_cost, 4),
        "cells_total": len(models) * len(scenarios) * repeat,
        "cells_run": len(statuses),
        "cells_pass": statuses.count("pass"),
        "cells_fail": statuses.count("fail"),
        "cells_other": len(statuses) - statuses.count("pass") - statuses.count("fail"),
    })
    dump_json(rdir / "run.json", run_meta)
    if not skill_ref and materialize_src is None:
        # a seal only vouches for the working tree actually tested — never for
        # a git ref or an adapt-loop copy
        _write_seal(skill_dir, run_meta)
    return run_meta


def _already_done(done: dict, scenario: str, model: str, rep: int) -> bool:
    rec = done.get(f"{scenario}/{model}/{rep}")
    return bool(rec and rec["status"] in TERMINAL_STATUSES)


def _run_cell_safe(scenario, model, rep, **kw) -> None:
    key = f"{scenario['name']}/{model}/{rep}"
    started = monotonic()
    try:
        status, cost = _run_cell(scenario, model, rep, **kw)
    except Exception as exc:  # harness bug or env failure: never poisons the matrix
        emit_event("error", cell=key, error=str(exc))
        cell_dir = kw["rdir"] / "cells" / scenario["name"] / model / f"rep-{rep}"
        dump_json(cell_dir / "error.json", {"error": str(exc)})
        status, cost = "infra_error", 0.0
    kw["progress"].record(key, status, cost, monotonic() - started)


def _run_cell(
    scenario: dict, model: str, rep: int, *,
    cfg: dict, skill_dir: Path, adapter, contract: dict,
    skill_ref: str | None, rdir: Path, progress: _Progress,
    materialize_src: Path | None = None,
) -> tuple[str, float]:
    defaults = cfg["defaults"]
    budget = dict(scenario.get("budget") or {})
    max_turns = int(budget.get("max_turns", defaults["max_turns"]))
    cell_budget = float(budget.get("max_cost_usd", defaults["cell_budget_usd"]))
    timeout_s = int(budget.get("timeout_s", defaults["timeout_s"]))
    cell_dir = rdir / "cells" / scenario["name"] / model / f"rep-{rep}"
    cell_dir.mkdir(parents=True, exist_ok=True)

    items = contract_items_for_scenario(contract, scenario)
    probe_cmds = checks_mod.state_probe_cmds(items)

    workspace = Path(tempfile.mkdtemp(prefix="bench-"))
    invocations = []
    turns: list[dict] = []
    raw_events: list[dict] = []
    status = "pass"
    try:
        _setup_fixture(scenario, skill_dir, workspace)
        materialized = adapter.materialize(
            skill_src=materialize_src or skill_dir, ref=skill_ref, workspace=workspace
        )
        # size of the version ACTUALLY under test (profile attribution must not
        # read the worktree when the run used --skill-ref)
        skill_files = [materialized / "SKILL.md"]
        if (materialized / "references").is_dir():
            skill_files += sorted((materialized / "references").rglob("*.md"))
        skill_text_chars = sum(
            len(p.read_text(encoding="utf-8", errors="replace")) for p in skill_files if p.exists()
        )
        initial_state = checks_mod.capture_state(workspace, probe_cmds)

        session_id = None
        prompt = scenario["opening_prompt"]
        step = 0
        seen_uuids: set[str] = set()
        while True:
            if len(invocations) >= max_turns:
                status = "over_budget"
                break
            inv = adapter.invoke(
                prompt=prompt, cwd=workspace, model=model,
                allowed_tools=scenario.get("allowed_tools") or [],
                timeout_s=timeout_s, budget_usd=cell_budget,
                resume_session=session_id,
            )
            invocations.append(inv)
            fresh = [e for e in inv.events if e.get("uuid") not in seen_uuids or not e.get("uuid")]
            seen_uuids.update(e["uuid"] for e in inv.events if e.get("uuid"))
            raw_events.extend(fresh)
            new_turns = adapter.normalize_events(fresh)
            turns.extend(new_turns)
            for i, t in enumerate(turns):
                t["idx"] = i
            if not inv.ok:
                if inv.error_kind == "quota":
                    status = "quota"
                elif inv.error_kind == "over_budget":
                    status = "over_budget"
                else:
                    status = "infra_error"
                break
            session_id = inv.session_id or session_id
            total_cost = sum(i.cost_usd for i in invocations)
            if total_cost > cell_budget:
                status = "over_budget"
                break
            reply = simulator.next_reply(
                scenario["user_script"], step, transcript.last_assistant_text(turns)
            )
            if reply.status == "done":
                break
            if reply.status == "desync":
                status = "desync"
                dump_json(cell_dir / "desync.json", {"detail": reply.detail})
                break
            step = reply.next_index
            transcript.append_user_turn(turns, reply.text)
            prompt = reply.text

        final_state = checks_mod.capture_state(workspace, probe_cmds)
    finally:
        safe_rmtree(workspace)

    from adapters.base import sum_usage
    usage = sum_usage(invocations)
    caps = adapter.capabilities
    activated = (
        transcript.detect_activation(turns, skill_dir.name, workspace=str(workspace))
        if caps.activation_observable else None
    )
    det = checks_mod.evaluate(
        items, initial_state=initial_state, final_state=final_state, turns=turns,
        events_observable=caps.events_observable,
    )

    # Precedence: harness conditions stay; then non-activation explains any
    # desync (a script written for the skill's flow can't match a SUT that
    # never entered the skill); only then contract verdicts. Adapters that
    # can't observe activation (agy) never yield not_activated.
    if (status in ("pass", "desync") and activated is False
            and scenario.get("invocation", "auto") == "auto"):
        status = "not_activated"
    elif status == "pass" and any(r["status"] == "fail" for r in det["items"]):
        status = "fail"

    resolved = next((i.resolved_model for i in invocations if i.resolved_model), model)
    meta = {
        "skill": skill_dir.name, "skill_ref": skill_ref or "worktree",
        "scenario": scenario["name"], "model": model, "resolved_model": resolved,
        "adapter": adapter.name, "rep": rep, "status": status,
        "activated": activated, "invocation_mode": scenario.get("invocation", "auto"),
        "skill_text_chars": skill_text_chars,
        "invocations": len(invocations),
        "wall_ms": sum(i.duration_ms for i in invocations),
        "error": next((i.error for i in invocations if i.error), ""),
    }
    dump_json(cell_dir / "transcript.json", {"meta": meta, "turns": turns, "usage": usage})
    dump_json(cell_dir / "state.json", {"initial": initial_state, "final": final_state})
    dump_json(cell_dir / "checks.json", det)
    import json as _json
    (cell_dir / "raw.jsonl").write_text(
        "\n".join(_json.dumps(e, ensure_ascii=False) for e in raw_events), encoding="utf-8"
    )
    return status, usage["cost_usd"]


def run_activation_probe(
    *, cfg: dict, skill_dir: Path, adapter, scenario: dict, model: str, repeat: int,
) -> dict:
    """Measure the activation lottery cheaply: fixture + ONE invocation per rep,
    no simulator, no checks — just 'did the model load the skill?'. ~1/3 of a
    full cell. Only meaningful on invocation:auto scenarios and adapters where
    activation is observable."""
    if scenario.get("invocation", "auto") != "auto":
        raise BenchError(
            f"scenario {scenario['name']} is invocation:explicit — activation is forced there",
            next_step="probe an invocation:auto scenario, or add one",
        )
    if not adapter.capabilities.activation_observable:
        raise BenchError(
            f"adapter {adapter.name} cannot observe activation",
            next_step="use the claude_code adapter for activation probes",
        )
    defaults = cfg["defaults"]
    budget = dict(scenario.get("budget") or {})
    base = baselines_dir(skill_dir)
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name.split("-")[1]) for p in base.glob("probe-*") if p.name.split("-")[1].isdigit()]
    pdir = base / f"probe-{max(nums, default=0) + 1}"
    pdir.mkdir()

    reps = []
    for rep in range(1, repeat + 1):
        workspace = Path(tempfile.mkdtemp(prefix="bench-probe-"))
        try:
            _setup_fixture(scenario, skill_dir, workspace)
            adapter.materialize(skill_src=skill_dir, ref=None, workspace=workspace)
            inv = adapter.invoke(
                prompt=scenario["opening_prompt"], cwd=workspace, model=model,
                allowed_tools=scenario.get("allowed_tools") or [],
                timeout_s=int(budget.get("timeout_s", defaults["timeout_s"])),
                budget_usd=float(budget.get("max_cost_usd", defaults["cell_budget_usd"])),
            )
            if not inv.ok:
                reps.append({"rep": rep, "status": inv.error_kind or "infra_error", "error": inv.error[:200]})
                if inv.error_kind == "quota":
                    break
                continue
            turns = adapter.normalize_events(inv.events)
            activated = transcript.detect_activation(turns, skill_dir.name, workspace=str(workspace))
            reps.append({"rep": rep, "status": "activated" if activated else "not_activated",
                         "cost_usd": inv.cost_usd})
            emit_event("probe_rep", rep=rep, activated=activated)
        finally:
            safe_rmtree(workspace)

    valid = [r for r in reps if r["status"] in ("activated", "not_activated")]
    activated_n = sum(1 for r in valid if r["status"] == "activated")
    summary = {
        "probe_id": pdir.name, "skill": skill_dir.name, "scenario": scenario["name"],
        "model": model, "reps_requested": repeat, "reps_valid": len(valid),
        "activated": activated_n,
        "activation_rate": round(activated_n / len(valid), 2) if valid else None,
        "cost_usd": round(sum(r.get("cost_usd", 0) for r in reps), 4),
        "reps": reps, "ts": now_iso(),
    }
    dump_json(pdir / "probe.json", summary)
    return summary


def _setup_fixture(scenario: dict, skill_dir: Path, workspace: Path) -> None:
    fixture = scenario.get("fixture")
    if not fixture:
        return
    setup = skill_dir / "tests" / "fixtures" / fixture / "setup.py"
    proc = subprocess.run(
        [sys.executable, str(setup), str(workspace)],
        cwd=setup.parent, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"fixture {fixture} setup failed: {proc.stderr[:400]}")


def _write_seal(skill_dir: Path, run_meta: dict) -> None:
    all_pass = run_meta.get("cells_run", 0) > 0 and run_meta.get("cells_run") == run_meta.get("cells_pass")
    dump_json(baselines_dir(skill_dir) / "last-smoke.json", {
        "skill": skill_dir.name,
        "skill_hash": run_meta["skill_hash"],
        "run_id": run_meta["run_id"],
        "label": run_meta.get("label", ""),
        "all_pass": all_pass,
        "ts": now_iso(),
    })

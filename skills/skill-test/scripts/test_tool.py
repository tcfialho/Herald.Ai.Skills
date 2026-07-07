#!/usr/bin/env python3
"""skill-test CLI — the agent orchestrates, this script executes and measures.

House contract: single JSON result on stdout; JSONL progress events on stderr
only with SKILL_TEST_VERBOSE=1 (warnings/errors always); stable exit codes.

Exit codes: 0 ok/all-pass · 1 some cell failed · 2 config/infra error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_lib import judging, reporting, runner  # noqa: E402
from bench_lib.assets import load_contract, load_scenarios  # noqa: E402
from bench_lib.config import BenchError, load_bench_config, resolve_skill_dir  # noqa: E402
from bench_lib.util import emit_result, force_utf8_stdio  # noqa: E402
from adapters.base import get_adapter  # noqa: E402


def _models_arg(value: str | None, cfg: dict, adapter_name: str) -> list[str]:
    if value:
        return [m.strip() for m in value.split(",") if m.strip()]
    ladder = (cfg["adapters"].get(adapter_name) or {}).get("ladder")
    if not ladder:
        raise BenchError(f"no --models given and no ladder for {adapter_name} in config.yaml",
                         next_step="pass --models a,b or add a ladder under adapters.<name> in skill-test config.yaml")
    return ladder


def cmd_init(args, cfg):
    emit_result(reporting.cmd_init(resolve_skill_dir(args.skill)))


def _do_run(args, cfg, *, skill_ref=None, label=None, models=None, run_kwargs=None):
    skill_dir = resolve_skill_dir(args.skill)
    adapter = get_adapter(args.adapter)
    contract = load_contract(skill_dir)
    scenarios = load_scenarios(skill_dir, args.scenarios)
    models = models or _models_arg(getattr(args, "models", None), cfg, args.adapter)
    meta = runner.run_matrix(
        cfg=cfg, skill_dir=skill_dir, adapter=adapter, models=models,
        scenarios=scenarios, contract=contract,
        repeat=getattr(args, "repeat", 1) or cfg["defaults"]["repeat"],
        skill_ref=skill_ref if skill_ref is not None else getattr(args, "skill_ref", None),
        jobs=getattr(args, "jobs", 1),
        max_cost_usd=getattr(args, "max_cost_usd", None),
        fail_fast=getattr(args, "fail_fast", False),
        resume_run_id=getattr(args, "resume", None),
        label=label or getattr(args, "label", "") or "",
        **(run_kwargs or {}),
    )
    return skill_dir, contract, scenarios, meta


def cmd_run(args, cfg):
    _, _, _, meta = _do_run(args, cfg)
    exit_code = 2 if meta["status"] == "aborted" and meta["cells_run"] == 0 else (
        0 if meta["cells_run"] and meta["cells_run"] == meta["cells_pass"] else 1
    )
    emit_result(meta, exit_code)


def cmd_status(args, cfg):
    emit_result(reporting.cmd_status(resolve_skill_dir(args.skill), args.run_id))


def cmd_judge(args, cfg):
    skill_dir = resolve_skill_dir(args.skill)
    contract = load_contract(skill_dir)
    scenarios = {s["name"]: s for s in load_scenarios(skill_dir, "all")}
    payload = judging.judge_run(
        cfg=cfg, skill_dir=skill_dir, run_id=args.run_id, contract=contract,
        scenarios_by_name=scenarios, judge_model=args.judge_model, votes=args.votes,
    )
    emit_result(payload)


def cmd_report(args, cfg):
    emit_result(reporting.cmd_report(
        resolve_skill_dir(args.skill), args.run_id,
        vs_baseline=args.vs_baseline, cell=args.cell,
    ))


def cmd_promote(args, cfg):
    emit_result(reporting.cmd_promote(resolve_skill_dir(args.skill), args.run_id))


def cmd_models(args, cfg):
    adapter = get_adapter(args.adapter)
    payload = adapter.list_models()
    payload["ladder_in_bench_yaml"] = (cfg["adapters"].get(args.adapter) or {}).get("ladder")
    emit_result(payload)


def cmd_seal(args, cfg):
    emit_result(reporting.seal_info(resolve_skill_dir(args.skill)))


def cmd_activation_probe(args, cfg):
    skill_dir = resolve_skill_dir(args.skill)
    scenarios = load_scenarios(skill_dir, args.scenario)
    summary = runner.run_activation_probe(
        cfg=cfg, skill_dir=skill_dir, adapter=get_adapter(args.adapter),
        scenario=scenarios[0], model=args.model, repeat=args.repeat,
    )
    emit_result(summary)


def cmd_compare(args, cfg):
    from bench_lib import comparing
    skill_dir = resolve_skill_dir(args.skill)
    contract = load_contract(skill_dir)
    scenarios = {s["name"]: s for s in load_scenarios(skill_dir, "all")}
    emit_result(comparing.compare_runs(
        cfg=cfg, skill_dir=skill_dir, run_a=args.run_id, run_b=args.baseline,
        contract=contract, scenarios_by_name=scenarios, judge_model=args.judge_model,
    ))


def cmd_mutate(args, cfg):
    from bench_lib import mutating
    skill_dir = resolve_skill_dir(args.skill)
    contract = load_contract(skill_dir)
    scenarios = load_scenarios(skill_dir, args.scenarios)
    mutations = mutating.load_mutations(skill_dir, args.mutations)
    if args.only:
        wanted = {m.strip() for m in args.only.split(",")}
        mutations = [m for m in mutations if m["id"] in wanted]
    report = mutating.mutate(
        cfg=cfg, skill_dir=skill_dir, adapter=get_adapter(args.adapter),
        contract=contract, scenarios=scenarios, mutations=mutations,
        model=args.model, votes=args.votes,
    )
    rate = report["detection_rate"]
    emit_result(report, 0 if rate is not None and rate >= 0.9 else 1)


def cmd_adapt(args, cfg):
    from bench_lib import adapting
    skill_dir = resolve_skill_dir(args.skill)
    contract = load_contract(skill_dir)
    scenarios = load_scenarios(skill_dir, args.scenarios)
    report = adapting.adapt(
        cfg=cfg, skill_dir=skill_dir, adapter=get_adapter(args.adapter),
        contract=contract, scenarios=scenarios, target_model=args.model,
        target_items=[i.strip() for i in args.target_items.split(",")] if args.target_items else None,
        max_iters=args.max_iters or cfg["defaults"]["adaptation_max_iters"],
        votes=args.votes, patcher_model=args.patcher_model,
    )
    emit_result(report, 0 if report["converged"] else 1)


def cmd_doctor(args, cfg):
    """Environment diagnostics: answers 'why doesn't it run on my machine?'."""
    import shutil
    import subprocess
    import sys as _sys

    checks = []

    def check(name, ok, detail, next_step=None):
        entry = {"name": name, "ok": bool(ok), "detail": detail}
        if not ok and next_step:
            entry["next_step"] = next_step
        checks.append(entry)

    check("python", _sys.version_info >= (3, 10), _sys.version.split()[0],
          "install Python 3.10+")
    try:
        import yaml  # noqa: F401
        check("pyyaml", True, "importable")
    except ImportError:
        check("pyyaml", False, "missing", "pip install pyyaml")
    for cli, args_v, needed_for in (
        ("git", ["--version"], "fixtures and --skill-ref"),
        ("claude", ["--version"], "the claude_code adapter (SUT sessions + judge)"),
        ("agy", ["--version"], "the agy adapter (optional unless benching on Gemini)"),
    ):
        path = shutil.which(cli)
        if not path:
            check(cli, False, "not on PATH", f"install it — needed for {needed_for}")
            if cli == "agy":
                checks[-1]["optional"] = True
            continue
        try:
            proc = subprocess.run([path, *args_v], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=30)
            check(cli, proc.returncode == 0, proc.stdout.strip().splitlines()[0][:60] if proc.stdout else "?")
        except (OSError, subprocess.TimeoutExpired) as exc:
            check(cli, False, str(exc)[:80], f"reinstall {cli}")
    from bench_lib.config import SKILL_TEST_ROOT
    cfg_path = SKILL_TEST_ROOT / "config.yaml"
    check("config.yaml", cfg_path.exists(), str(cfg_path),
          "restore skill-test/config.yaml (ladders + judge live there)")
    required_ok = all(c["ok"] for c in checks if not c.get("optional"))
    emit_result({"status": "ok" if required_ok else "problems", "checks": checks}, 0 if required_ok else 2)


def cmd_overview(args, cfg):
    from bench_lib.config import SKILL_TEST_ROOT
    root = Path(args.root) if args.root else SKILL_TEST_ROOT.parent
    if not root.is_dir():
        raise BenchError(f"skills root not found: {root}")
    emit_result(reporting.cmd_overview(root))


def cmd_profile(args, cfg):
    skill_dir, contract, scenarios, meta = _do_run(args, cfg, label="profile")
    profile = reporting.profile_decomposition(skill_dir, meta["run_id"])
    payload = {"current": {"run": meta, "profile": profile}}
    if args.vs_ref:
        args.resume = None
        _, _, _, meta_b = _do_run(args, cfg, skill_ref=args.vs_ref, label=f"profile:{args.vs_ref}")
        payload["reference"] = {
            "ref": args.vs_ref, "run": meta_b,
            "profile": reporting.profile_decomposition(skill_dir, meta_b["run_id"]),
        }
    emit_result(payload)


def cmd_floor(args, cfg):
    skill_dir = resolve_skill_dir(args.skill)
    ladder = (cfg["adapters"].get(args.adapter) or {}).get("ladder")
    if not ladder:
        raise BenchError(f"no ladder for adapter {args.adapter} in config.yaml",
                         next_step="add adapters.<name>.ladder to skill-test config.yaml (list models with `test_tool.py models`)")
    threshold = cfg["defaults"]["floor_threshold"]
    contract = load_contract(skill_dir)
    scenarios_by_name = {s["name"]: s for s in load_scenarios(skill_dir, args.scenarios)}
    rungs = []
    floor_at = None
    for model in ladder:
        args.models = model
        args.resume = None
        _, _, _, meta = _do_run(args, cfg, label=f"floor:{model}", models=[model])
        judging.judge_run(
            cfg=cfg, skill_dir=skill_dir, run_id=meta["run_id"], contract=contract,
            scenarios_by_name=scenarios_by_name, judge_model=None, votes=1,
        )
        report = reporting.cmd_report(skill_dir, meta["run_id"], vs_baseline=False, cell=None)
        verdict = reporting.classify_rung(report, threshold)
        zone = "native" if verdict["meets_threshold"] else "floor"
        rungs.append({"model": model, "run_id": meta["run_id"], "zone": zone, **verdict})
        if zone == "floor":
            floor_at = model
            break
    emit_result({
        "skill": skill_dir.name, "adapter": args.adapter, "threshold": threshold,
        "rungs": rungs, "floor_at": floor_at,
        "note": "native mode (fase 1); --adapt / adapted zone lands in fase 2",
    }, 0 if floor_at is None else 1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="test_tool.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, **extra):
        sp = sub.add_parser(name)
        sp.add_argument("--skill", required=True)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init)

    sp = add("run", cmd_run)
    sp.add_argument("--adapter", default="claude_code")
    sp.add_argument("--models")
    sp.add_argument("--scenarios", default="all")
    sp.add_argument("--repeat", type=int, default=1)
    sp.add_argument("--skill-ref", dest="skill_ref")
    sp.add_argument("--jobs", type=int, default=1)
    sp.add_argument("--max-cost-usd", dest="max_cost_usd", type=float)
    sp.add_argument("--fail-fast", dest="fail_fast", action="store_true")
    sp.add_argument("--resume")
    sp.add_argument("--label", default="")

    sp = add("status", cmd_status)
    sp.add_argument("--run-id", dest="run_id", required=True)

    sp = add("judge", cmd_judge)
    sp.add_argument("--run-id", dest="run_id", required=True)
    sp.add_argument("--judge-model", dest="judge_model")
    sp.add_argument("--votes", type=int, default=1, choices=[1, 3])

    sp = add("report", cmd_report)
    sp.add_argument("--run-id", dest="run_id", required=True)
    sp.add_argument("--vs-baseline", dest="vs_baseline", action="store_true")
    sp.add_argument("--cell")

    sp = add("promote", cmd_promote)
    sp.add_argument("--run-id", dest="run_id", required=True)

    sp = add("models", cmd_models)
    sp.add_argument("--adapter", default="claude_code")

    add("seal", cmd_seal)

    sp = sub.add_parser("overview")
    sp.add_argument("--root", help="skills root dir (default: parent of skill-test)")
    sp.set_defaults(fn=cmd_overview)

    sp = sub.add_parser("doctor")
    sp.set_defaults(fn=cmd_doctor)

    sp = add("compare", cmd_compare)
    sp.add_argument("--run-id", dest="run_id", required=True)
    sp.add_argument("--baseline", required=True)
    sp.add_argument("--judge-model", dest="judge_model")

    sp = add("mutate", cmd_mutate)
    sp.add_argument("--model", required=True, help="model that executes the mutated skill")
    sp.add_argument("--adapter", default="claude_code")
    sp.add_argument("--scenarios", default="all")
    sp.add_argument("--mutations", help="mutations yaml (default: tests/mutations.yaml)")
    sp.add_argument("--only", help="comma-separated mutation ids to run")
    sp.add_argument("--votes", type=int, default=1, choices=[1, 3])

    sp = add("adapt", cmd_adapt)
    sp.add_argument("--model", required=True, help="target (weak) model to adapt for")
    sp.add_argument("--adapter", default="claude_code")
    sp.add_argument("--scenarios", default="all")
    sp.add_argument("--target-items", dest="target_items")
    sp.add_argument("--max-iters", dest="max_iters", type=int)
    sp.add_argument("--votes", type=int, default=1, choices=[1, 3])
    sp.add_argument("--patcher-model", dest="patcher_model")

    sp = add("activation-probe", cmd_activation_probe)
    sp.add_argument("--scenario", required=True)
    sp.add_argument("--model", required=True)
    sp.add_argument("--adapter", default="claude_code")
    sp.add_argument("--repeat", type=int, default=3)

    sp = add("profile", cmd_profile)
    sp.add_argument("--adapter", default="claude_code")
    sp.add_argument("--models")
    sp.add_argument("--scenarios", default="all")
    sp.add_argument("--repeat", type=int, default=1)
    sp.add_argument("--skill-ref", dest="skill_ref")
    sp.add_argument("--vs-ref", dest="vs_ref")
    sp.add_argument("--jobs", type=int, default=1)
    sp.add_argument("--max-cost-usd", dest="max_cost_usd", type=float)

    sp = add("floor", cmd_floor)
    sp.add_argument("--adapter", default="claude_code")
    sp.add_argument("--scenarios", default="all")
    sp.add_argument("--repeat", type=int, default=1)
    sp.add_argument("--jobs", type=int, default=1)
    sp.add_argument("--max-cost-usd", dest="max_cost_usd", type=float)

    return p


def main() -> None:
    force_utf8_stdio()
    args = build_parser().parse_args()
    cfg = load_bench_config()
    try:
        args.fn(args, cfg)
    except BenchError as exc:
        payload = {"status": "error", "error": str(exc)}
        if exc.next_step:
            payload["next_step"] = exc.next_step
        emit_result(payload, 2)
    except Exception as exc:  # harness bug: still emit machine-readable JSON
        import traceback
        emit_result({
            "status": "error", "error": f"{type(exc).__name__}: {exc}",
            "trace_tail": traceback.format_exc().splitlines()[-4:],
        }, 2)


if __name__ == "__main__":
    main()

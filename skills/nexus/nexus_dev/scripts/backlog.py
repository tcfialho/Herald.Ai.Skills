#!/usr/bin/env python3
"""
Nexus Dev — Backlog Builder & Execution Tool

Single CLI that the AI agent calls to:
  1. BUILD the backlog (stories + tasks) from a finalized spec.json
  2. EXECUTE tasks (start, complete, fail) with embedded validation
  3. READ context for the current task (the AI never reads files directly)
  4. DISPLAY progress (hierarchical, metrics, recovery prompt)

Replaces: story_generator.py, task_breaker.py, progress_tracker.py,
          priority_queue.py, memory_manager.py, state_manager.py, submit_gate.py

Subcommands:
  BUILD:
    init          Create backlog.json from a finalized spec.json
    add-story     Register a user story
    add-criterio  Add a Gherkin criterion to a story
    add-task      Register an atomic task under a story

  EXECUTE:
    start         Mark a task as in_progress
    complete      Validate + mark as completed (anti-mock + verify_cmd)
    fail          Record a task failure

  CONTEXT (READ):
    next          Get next task with full context (dependencies-aware)
    context       Get context for a specific task or story
    recovery      Generate crash recovery prompt

  DISPLAY:
    progress      Hierarchical visual progress (Story -> Task)
    show          Summary counts
    validate      Check backlog completeness

Usage:
  python backlog.py .nexus/runs/001/backlog.json init --spec .nexus/spec.json
  python backlog.py .nexus/runs/001/backlog.json add-story --id US-UC01-FP --uc-ref UC-01 ...
  python backlog.py .nexus/runs/001/backlog.json next
  python backlog.py .nexus/runs/001/backlog.json start TASK-001
  python backlog.py .nexus/runs/001/backlog.json complete TASK-001
  python backlog.py .nexus/runs/001/backlog.json progress
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_backlog(data: dict) -> dict:
    data.setdefault("nexus_version", "3.0")
    data.setdefault("plan_ref", "")
    data.setdefault("spec_path", "")
    data.setdefault("feature_branch", "")
    data.setdefault("created_at", _utcnow())
    data.setdefault("updated_at", _utcnow())
    data.setdefault("status", "building")
    data.setdefault("stories", [])
    data.setdefault("log", [])

    context = data.setdefault("context", {})
    context.setdefault("overview", "")
    context.setdefault("decisions", [])
    context.setdefault("ears_index", {})
    context.setdefault("ears_detail_index", {})
    context.setdefault("uc_ears_index", {})
    context.setdefault("entity_index", {})
    context.setdefault("invariants", [])
    context.setdefault("screens", {})
    context.setdefault("uc_origins", {})
    context.setdefault("uc_index", {})
    context.setdefault(
        "architecture", {"principles": [], "components": [], "folders": []}
    )
    context.setdefault("dependencies", {"packages": [], "services": []})

    execution = data.setdefault("execution", {})
    execution.setdefault("current_task", None)
    execution.setdefault("total_tasks", 0)
    execution.setdefault("completed_tasks", 0)
    execution.setdefault("failed_attempts", 0)

    quality = data.setdefault("quality", {})
    quality.setdefault("tests_status", "healthy")
    quality.setdefault("blocked_reason", "")
    quality.setdefault("updated_at", _utcnow())

    return data


def _load(path: Path) -> dict:
    if not path.exists():
        print(f"ERRO: backlog.json nao encontrado: {path}", file=sys.stderr)
        print("   Execute 'init' primeiro.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_backlog(json.load(f))


def _save(path: Path, data: dict) -> None:
    data = _normalize_backlog(data)
    data["updated_at"] = _utcnow()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _to_yaml_lines(value, indent: int = 0) -> list[str]:
    space = " " * indent
    if isinstance(value, dict):
        if not value:
            return [space + "{}"]
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.extend(_to_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {_yaml_scalar(item)}")
        return lines

    if isinstance(value, list):
        if not value:
            return [space + "[]"]
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.extend(_to_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{space}- {_yaml_scalar(item)}")
        return lines

    return [space + _yaml_scalar(value)]


def _to_yaml(value) -> str:
    return "\n".join(_to_yaml_lines(value))


def _find_task(data: dict, task_id: str) -> tuple[Optional[dict], Optional[dict]]:
    """Find a task and its parent story. Returns (story, task) or (None, None)."""
    for story in data.get("stories", []):
        for task in story.get("tasks", []):
            if task["id"] == task_id:
                return story, task
    return None, None


def _find_story(data: dict, story_id: str) -> Optional[dict]:
    for story in data.get("stories", []):
        if story["id"] == story_id:
            return story
    return None


def _all_tasks(data: dict) -> list[tuple[dict, dict]]:
    """Yield (story, task) pairs for all tasks."""
    result = []
    for story in data.get("stories", []):
        for task in story.get("tasks", []):
            result.append((story, task))
    return result


def _append_log(data: dict, task_id: str, action: str, detail: str = "") -> None:
    if "log" not in data:
        data["log"] = []
    entry = {"timestamp": _utcnow(), "task_id": task_id, "action": action}
    if detail:
        entry["detail"] = detail
    data["log"].append(entry)


def _update_execution_counts(data: dict) -> None:
    total = 0
    completed = 0
    failed = 0
    current = None
    for _story, task in _all_tasks(data):
        total += 1
        if task["status"] == "completed":
            completed += 1
        if task["status"] == "in_progress":
            current = task["id"]
        failed += task.get("failures", 0)
    data["execution"] = {
        "current_task": current,
        "total_tasks": total,
        "completed_tasks": completed,
        "failed_attempts": failed,
    }


def _progress_snapshot(data: dict) -> dict:
    ex = data.get("execution", {})
    total = ex.get("total_tasks", 0)
    completed = ex.get("completed_tasks", 0)
    percent = int((completed / total) * 100) if total > 0 else 0
    return {
        "completed": completed,
        "total": total,
        "percent": percent,
        "current_task": ex.get("current_task"),
        "timestamp": _utcnow(),
    }


def _quality_gate_snapshot(data: dict) -> dict:
    quality = data.get("quality", {})
    status = quality.get("tests_status", "healthy")
    blocked_reason = quality.get("blocked_reason", "")
    return {
        "tests_status": status,
        "blocked": status in ("failing", "blocked"),
        "blocked_reason": blocked_reason,
        "updated_at": quality.get("updated_at"),
    }


def _set_tests_status(data: dict, status: str, blocked_reason: str = "") -> None:
    quality = data.setdefault("quality", {})
    quality["tests_status"] = status
    quality["blocked_reason"] = blocked_reason
    quality["updated_at"] = _utcnow()


def _assert_delivery_unblocked(data: dict) -> None:
    quality_gate = _quality_gate_snapshot(data)
    if quality_gate["blocked"]:
        reason = quality_gate.get("blocked_reason", "")
        print(
            "DELIVERY_BLOCKED: TESTS_FAILED — regularize os testes com 'backlog.py complete' antes de solicitar nova task.",
            file=sys.stderr,
        )
        if reason:
            print(f"   Motivo: {reason}", file=sys.stderr)
        sys.exit(1)


def _build_story_payload(story: dict) -> dict:
    return {
        "id": story.get("id"),
        "descricao": story.get("descricao", ""),
        "uc_ref": story.get("uc_ref", ""),
        "fluxo_id": story.get("fluxo_id", ""),
        "criterios": story.get("criterios", []),
    }


def _build_task_payload(task: dict) -> dict:
    return {
        "id": task.get("id"),
        "title": task.get("title", ""),
        "tipo": task.get("tipo", ""),
        "nivel": task.get("nivel", 0),
        "status": task.get("status", "pending"),
        "objetivo": task.get("objetivo", ""),
        "pre_condicao": task.get("pre_condicao", []),
        "pos_condicao": task.get("pos_condicao", []),
        "files": task.get("files", []),
        "dependencies": task.get("dependencies", []),
        "diretiva_de_teste": task.get("diretiva_de_teste", ""),
        "verify_cmd": task.get("verify_cmd", ""),
        "ears_refs": task.get("ears_refs", []),
    }


def _build_ears_payload(data: dict, story: dict, task: dict | None) -> dict:
    context = data.get("context", {})
    detail_index = context.get("ears_detail_index", {})
    uc_ears_index = context.get("uc_ears_index", {})
    uc_ref = story.get("uc_ref", "")

    task_refs = []
    if task:
        for ear_id in task.get("ears_refs", []):
            detail = detail_index.get(ear_id)
            if detail:
                task_refs.append(detail)
            else:
                task_refs.append(
                    {"id": ear_id, "uc_ref": uc_ref, "type": "", "notation": ""}
                )

    uc_refs = uc_ears_index.get(uc_ref, [])
    return {
        "task_refs": task_refs,
        "use_case_refs": uc_refs,
    }


def _build_delivery_payload(
    data: dict,
    story: dict,
    task: dict | None,
    *,
    command: str,
    mode: str,
) -> dict:
    context = data.get("context", {})
    uc_ref = story.get("uc_ref", "")
    use_case = context.get("uc_index", {}).get(
        uc_ref,
        {
            "id": uc_ref,
            "name": "",
            "description": "",
            "origin": context.get("uc_origins", {}).get(uc_ref, "new"),
        },
    )
    payload = {
        "delivery": {
            "command": command,
            "mode": mode,
            "generated_at": _utcnow(),
        },
        "task": _build_task_payload(task) if task else None,
        "story": _build_story_payload(story),
        "use_case": {
            "id": use_case.get("id", uc_ref),
            "name": use_case.get("name", ""),
            "description": use_case.get("description", ""),
            "origin": use_case.get("origin", "new"),
            "fluxo_id": story.get("fluxo_id", ""),
        },
        "ears": _build_ears_payload(data, story, task),
        "architecture_context": context.get(
            "architecture", {"principles": [], "components": [], "folders": []}
        ),
        "dependencies_context": context.get(
            "dependencies", {"packages": [], "services": []}
        ),
        "progress": _progress_snapshot(data),
        "quality_gate": _quality_gate_snapshot(data),
    }
    return payload


# ------------------------------------------------------------------
# Anti-mock scanner (embedded from submit_gate)
# ------------------------------------------------------------------

_MOCK_PATTERNS = [
    r"#\s*TODO\b",
    r"#\s*FIXME\b",
    r"//\s*TODO\b",
    r"//\s*FIXME\b",
    r"\bpass\b\s*(#.*)?$",
    r"raise\s+NotImplementedError",
    r"return\s+\{\s*\}",
    r"return\s+\[\s*\]",
    r"return\s+None\s*(#.*)?$",
    r"\bmock_\w+",
    r"\bfake_\w+",
    r"\bdummy_\w+",
]
_MOCK_RE = re.compile("|".join(_MOCK_PATTERNS), re.MULTILINE)


def _is_inside_multiline(line: str, state: dict) -> bool:
    """Track whether the current line is inside a multi-line string or block comment.
    Mutates `state` dict with keys: in_block_comment, in_triple_quote, quote_char."""
    stripped = line.strip()

    if state.get("in_block_comment"):
        if "*/" in stripped:
            state["in_block_comment"] = False
        return True

    if state.get("in_triple_quote"):
        q = state["quote_char"]
        if q in stripped:
            count = stripped.count(q)
            if count % 2 == 1:
                state["in_triple_quote"] = False
                state["quote_char"] = ""
        return True

    if stripped.startswith("/*"):
        if "*/" not in stripped[2:]:
            state["in_block_comment"] = True
        return True

    if stripped.startswith("#") or stripped.startswith("//"):
        return False

    for q in ('"""', "'''"):
        occurrences = stripped.count(q)
        if occurrences == 1:
            state["in_triple_quote"] = True
            state["quote_char"] = q
            return True

    return False


def _scan_for_mocks(file_paths: list[str], project_root: Path) -> list[str]:
    """Scan files for mock/placeholder patterns. Returns list of violations.
    Skips shebangs, multi-line strings (triple quotes), and block comments."""
    violations = []
    for fp in file_paths:
        full = project_root / fp
        if not full.exists():
            violations.append(f"{fp}: arquivo nao encontrado")
            continue
        try:
            content = full.read_text(encoding="utf-8")
        except Exception as exc:
            violations.append(f"{fp}: erro de leitura — {exc}")
            continue
        ml_state: dict = {
            "in_block_comment": False,
            "in_triple_quote": False,
            "quote_char": "",
        }
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#!"):
                continue
            if _is_inside_multiline(line, ml_state):
                continue
            if _MOCK_RE.search(stripped):
                violations.append(f"{fp}:{i}: {stripped[:80]}")
    return violations


# ------------------------------------------------------------------
# Topological sort for task ordering (embedded from priority_queue)
# ------------------------------------------------------------------


def _toposort_tasks(data: dict) -> list[str]:
    """Return task IDs in dependency-respecting order (Kahn's algorithm).
    Only returns pending/in_progress tasks. Completed tasks are excluded.
    Detects and reports circular dependencies."""
    all_pairs = _all_tasks(data)
    completed_ids = {
        t["id"] for _, t in all_pairs if t["status"] in ("completed", "skipped")
    }

    pending = []
    for _story, task in all_pairs:
        if task["id"] not in completed_ids:
            pending.append(task)

    in_degree: dict[str, int] = {t["id"]: 0 for t in pending}
    dependents: dict[str, list[str]] = defaultdict(list)

    for task in pending:
        for dep_id in task.get("dependencies", []):
            if dep_id in completed_ids:
                continue
            if dep_id in in_degree:
                in_degree[task["id"]] += 1
                dependents[dep_id].append(task["id"])

    queue = sorted([tid for tid, deg in in_degree.items() if deg == 0])
    order = []

    while queue:
        current = queue.pop(0)
        order.append(current)
        for dep in sorted(dependents.get(current, [])):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)
        queue.sort()

    orphaned = [t["id"] for t in pending if t["id"] not in set(order)]
    if orphaned:
        print(
            f"AVISO: dependencia circular detectada — tasks travadas: {', '.join(orphaned)}",
            file=sys.stderr,
        )

    return order


# ------------------------------------------------------------------
# BUILD commands
# ------------------------------------------------------------------


def _check_pipeline_order(spec_path: Path) -> None:
    """Validate that /plan was completed before /dev can start."""
    if not spec_path.exists():
        print("ERRO: spec.json nao encontrado.", file=sys.stderr)
        print(f"   Caminho: {spec_path}", file=sys.stderr)
        print("   Execute /plan primeiro para gerar o spec.json.", file=sys.stderr)
        sys.exit(1)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    errors = []
    ears = spec.get("ears", [])
    ucs = spec.get("use_cases", [])
    drilldowns = spec.get("drilldowns", [])

    if len(ears) < 5:
        errors.append(f"EARS insuficientes ({len(ears)}, minimo 5)")
    if not ucs:
        errors.append("Nenhum caso de uso registrado")
    if not drilldowns:
        errors.append("Nenhum drill-down registrado")

    uc_ids = {uc["id"] for uc in ucs}
    dd_ids = {dd["uc_id"] for dd in drilldowns}
    missing_dd = uc_ids - dd_ids
    if missing_dd:
        errors.append(f"UCs sem drill-down: {', '.join(sorted(missing_dd))}")

    if errors:
        print("ERRO: spec.json incompleto — /plan nao foi finalizado.", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        print(
            "   Execute /plan, finalize a especificacao e rode 'spec_builder.py validate'.",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_init(bl_path: Path, args: argparse.Namespace) -> None:
    if bl_path.exists():
        print(f"ERRO: backlog.json ja existe: {bl_path}", file=sys.stderr)
        sys.exit(1)

    if args.spec:
        spec_path = Path(args.spec)
    else:
        nexus = _find_nexus_root()
        if nexus is None:
            print(
                "ERRO: --spec nao fornecido e .nexus/ nao encontrado.", file=sys.stderr
            )
            sys.exit(1)
        spec_path = nexus / "spec.json"
    _check_pipeline_order(spec_path)
    spec_path = spec_path.resolve()

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    ears_index: dict[str, str] = {}
    ears_detail_index: dict[str, dict] = {}
    uc_ears_index: dict[str, list[dict]] = defaultdict(list)
    for ear in spec.get("ears", []):
        ear_id = ear.get("id", "")
        notation = ear.get("notation", "")
        uc_ref = ear.get("uc_ref", "")
        ears_index[ear_id] = notation
        detail = {
            "id": ear_id,
            "uc_ref": uc_ref,
            "type": ear.get("type", ""),
            "notation": notation,
        }
        ears_detail_index[ear_id] = detail
        if uc_ref:
            uc_ears_index[uc_ref].append(detail)

    entity_index = {}
    for ent in spec.get("entities", []):
        entity_index[ent["name"]] = ent["definition"]

    uc_origins = {}
    uc_index = {}
    for uc in spec.get("use_cases", []):
        uc_origins[uc["id"]] = uc.get("origin", "new")
        uc_index[uc["id"]] = {
            "id": uc.get("id", ""),
            "name": uc.get("name", ""),
            "description": uc.get("description", ""),
            "origin": uc.get("origin", "new"),
        }

    screens_index: dict[str, list[dict]] = {}
    visual_path = spec_path.parent / "visual.json"
    if visual_path.exists():
        with open(visual_path, "r", encoding="utf-8") as f:
            visual = json.load(f)
        for screen in visual.get("screens", []):
            compact = {
                "id": screen["id"],
                "name": screen["name"],
                "layout": screen.get("layout_decision", ""),
                "components": {
                    c["name"]: c["spec"] for c in screen.get("components", [])
                },
            }
            for uc_ref in screen.get("uc_refs", []):
                screens_index.setdefault(uc_ref, []).append(compact)

    data = {
        "nexus_version": "3.0",
        "plan_ref": spec.get("plan_name", ""),
        "spec_path": str(spec_path),
        "feature_branch": "",
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "status": "building",
        "context": {
            "overview": spec.get("overview", ""),
            "decisions": spec.get("decisions", []),
            "ears_index": ears_index,
            "ears_detail_index": ears_detail_index,
            "uc_ears_index": dict(uc_ears_index),
            "entity_index": entity_index,
            "invariants": spec.get("invariants", []),
            "screens": screens_index,
            "uc_origins": uc_origins,
            "uc_index": uc_index,
            "architecture": spec.get(
                "architecture", {"principles": [], "components": [], "folders": []}
            ),
            "dependencies": spec.get("dependencies", {"packages": [], "services": []}),
        },
        "stories": [],
        "execution": {
            "current_task": None,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_attempts": 0,
        },
        "quality": {
            "tests_status": "healthy",
            "blocked_reason": "",
            "updated_at": _utcnow(),
        },
        "log": [],
    }
    _save(bl_path, data)
    plan = spec.get("plan_name", "?")
    ears = len(ears_index)
    decs = len(data["context"]["decisions"])
    ents = len(entity_index)
    scr = sum(len(v) for v in screens_index.values())
    new_ucs = sum(1 for v in uc_origins.values() if v == "new")
    inferred_ucs = sum(1 for v in uc_origins.values() if v == "inferred")
    print(f"OK backlog.json criado: {bl_path}")
    print(
        f"   Plano: {plan} | Contexto: {decs} decisoes, {ears} EARS, {ents} entidades"
    )
    if inferred_ucs > 0:
        print(
            f"   UCs: {new_ucs} new (gerarao stories), {inferred_ucs} inferred (somente contexto)"
        )
    else:
        print(f"   UCs: {new_ucs} new")
    if screens_index:
        ucs_with_screens = len(screens_index)
        print(f"   Visual: {scr} screen-refs em {ucs_with_screens} UCs")


def cmd_add_story(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    uc_origins = data.get("context", {}).get("uc_origins", {})
    uc_origin = uc_origins.get(args.uc_ref, "new")
    if uc_origin == "inferred":
        print(
            f"AVISO: UC '{args.uc_ref}' tem origin=inferred (codigo ja existente). "
            f"Stories devem ser geradas apenas para UCs com origin=new.",
            file=sys.stderr,
        )
    existing = _find_story(data, args.id)
    if existing:
        existing["uc_ref"] = args.uc_ref
        existing["fluxo_id"] = args.fluxo_id
        existing["descricao"] = args.descricao
        action = "atualizada"
    else:
        story = {
            "id": args.id,
            "uc_ref": args.uc_ref,
            "fluxo_id": args.fluxo_id,
            "descricao": args.descricao,
            "criterios": [],
            "tasks": [],
        }
        data["stories"].append(story)
        action = "adicionada"
    _save(bl_path, data)
    print(f"OK Historia '{args.id}' {action} — total: {len(data['stories'])}")


def cmd_add_criterio(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    story = _find_story(data, args.story)
    if story is None:
        print(f"ERRO: Historia '{args.story}' nao encontrada.", file=sys.stderr)
        sys.exit(1)
    criterio = {"dado": args.dado, "quando": args.quando, "entao": args.entao}
    for existing in story["criterios"]:
        if (
            existing["dado"] == criterio["dado"]
            and existing["quando"] == criterio["quando"]
            and existing["entao"] == criterio["entao"]
        ):
            print(f"Criterio ja existe em '{args.story}' — ignorado")
            return
    story["criterios"].append(criterio)
    _save(bl_path, data)
    total = len(story["criterios"])
    print(f"OK Criterio adicionado a '{args.story}' — total: {total}")


def cmd_add_task(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    story = _find_story(data, args.story_ref)
    if story is None:
        print(f"ERRO: Historia '{args.story_ref}' nao encontrada.", file=sys.stderr)
        sys.exit(1)

    task = {
        "id": args.id,
        "title": args.title,
        "tipo": args.tipo,
        "nivel": args.nivel,
        "objetivo": args.objetivo,
        "pre_condicao": args.pre_condicao or [],
        "pos_condicao": args.pos_condicao or [],
        "diretiva_de_teste": args.diretiva or "",
        "verify_cmd": args.verify_cmd or "",
        "files": args.files or [],
        "dependencies": args.dependencies or [],
        "ears_refs": args.ears_refs or [],
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "failures": 0,
        "last_error": None,
    }

    existing_idx = None
    for i, t in enumerate(story["tasks"]):
        if t["id"] == args.id:
            existing_idx = i
            break

    if existing_idx is not None:
        task["status"] = story["tasks"][existing_idx].get("status", "pending")
        task["failures"] = story["tasks"][existing_idx].get("failures", 0)
        story["tasks"][existing_idx] = task
        action = "atualizada"
    else:
        story["tasks"].append(task)
        action = "adicionada"

    _update_execution_counts(data)
    _save(bl_path, data)
    total = data["execution"]["total_tasks"]
    print(f"OK Task '{args.id}' {action} em '{args.story_ref}' — total global: {total}")


# ------------------------------------------------------------------
# EXECUTE commands
# ------------------------------------------------------------------


def cmd_start(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    story, task = _find_task(data, args.task_id)
    if task is None:
        print(f"ERRO: Task '{args.task_id}' nao encontrada.", file=sys.stderr)
        sys.exit(1)
    if task["status"] == "completed":
        print(f"ERRO: Task '{args.task_id}' ja esta completed.", file=sys.stderr)
        sys.exit(1)
    if task["status"] == "in_progress":
        print(
            f"AVISO: Task '{args.task_id}' ja esta in_progress — reiniciando.",
            file=sys.stderr,
        )

    task["status"] = "in_progress"
    task["started_at"] = _utcnow()
    data["status"] = "executing"
    _append_log(data, args.task_id, "started")
    _update_execution_counts(data)
    _save(bl_path, data)
    print(f"OK Task '{args.task_id}' iniciada")
    pct = _pct(data)
    print(f"   Progresso: {pct}%")


def _save_evidence(bl_path: Path, task_id: str, evidence: dict) -> Path:
    """Write evidence JSON to .nexus/runs/{run}/evidence/{task_id}.json."""
    evidence_dir = bl_path.parent / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{task_id}.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    return evidence_path


def cmd_complete(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    story, task = _find_task(data, args.task_id)
    if task is None:
        print(f"ERRO: Task '{args.task_id}' nao encontrada.", file=sys.stderr)
        sys.exit(1)
    if task["status"] == "completed":
        print(f"Task '{args.task_id}' ja esta completed.")
        return

    if args.project_root:
        project_root = Path(args.project_root)
    else:
        nexus = _find_nexus_root()
        project_root = nexus.parent if nexus else bl_path.parent.parent.parent.parent
    claimed_test_files = args.test_files or []
    claimed_passed = args.test_passed
    claimed_failed = args.test_failed

    audit = {}
    gate_failures: list[tuple[str, str]] = []

    # ── GATE 1: All task.files exist on disk ──
    all_task_files = task.get("files", [])
    missing_files = [f for f in all_task_files if not (project_root / f).exists()]
    audit["files_exist"] = len(missing_files) == 0
    if missing_files:
        gate_failures.append(
            ("FILES", f"arquivos nao encontrados: {', '.join(missing_files)}")
        )

    # ── GATE 2: Anti-mock scan on implementation files only ──
    test_file_set = set(claimed_test_files)
    impl_files = [f for f in all_task_files if f not in test_file_set]
    mock_violations = _scan_for_mocks(impl_files, project_root)
    audit["no_mocks"] = len(mock_violations) == 0
    if mock_violations:
        gate_failures.append(("MOCKS", "; ".join(mock_violations[:5])))

    # ── GATE 3: Claimed test files exist on disk ──
    if claimed_test_files:
        missing_tests = [
            f for f in claimed_test_files if not (project_root / f).exists()
        ]
        audit["test_files_exist"] = len(missing_tests) == 0
        if missing_tests:
            gate_failures.append(
                ("TESTS", f"test files nao encontrados: {', '.join(missing_tests)}")
            )
    else:
        audit["test_files_exist"] = None

    # ── GATE 4: AI claims all tests passed ──
    if claimed_test_files:
        audit["tests_pass_check"] = claimed_failed == 0 and claimed_passed > 0
        if claimed_failed > 0:
            gate_failures.append(
                ("TEST_RESULT", f"IA reportou {claimed_failed} teste(s) falhando")
            )
        if claimed_passed == 0:
            gate_failures.append(
                (
                    "TEST_RESULT",
                    "IA reportou 0 testes passando (nenhum teste executado?)",
                )
            )
    else:
        audit["tests_pass_check"] = None

    # ── REJECT if any gate failed (all failures reported together) ──
    if gate_failures:
        task["failures"] = task.get("failures", 0) + 1
        failures = task["failures"]
        all_details = "; ".join(f"[{g}] {d}" for g, d in gate_failures)
        task["last_error"] = all_details
        _append_log(data, args.task_id, "rejected", all_details)

        has_test_failure = any(g == "TEST_RESULT" for g, _ in gate_failures)
        if has_test_failure:
            _set_tests_status(data, "blocked", all_details)

        _update_execution_counts(data)
        _save(bl_path, data)
        for gate, detail in gate_failures:
            print(f"REJEITADO [{gate}]: {detail}", file=sys.stderr)
        print(f"TENTATIVA: {failures}/3", file=sys.stderr)
        if 2 <= failures < 3:
            print(
                "ATENCAO: Correcao anterior nao resolveu. Releia o contexto da task e mude a abordagem.",
                file=sys.stderr,
            )
        if failures >= 3:
            print(
                f"CIRCUIT BREAKER: {args.task_id} falhou {failures}x. HALT.",
                file=sys.stderr,
            )
        sys.exit(1)

    # ── ALL GATES PASSED → generate evidence ──
    evidence = {
        "task_id": args.task_id,
        "timestamp": _utcnow(),
        "claims": {
            "test_files": claimed_test_files,
            "test_passed": claimed_passed,
            "test_failed": claimed_failed,
        },
        "audit": audit,
        "result": "ACCEPTED",
    }
    evidence_path = _save_evidence(bl_path, args.task_id, evidence)

    task["status"] = "completed"
    task["completed_at"] = _utcnow()
    task["verification"] = {
        "evidence_file": str(evidence_path.relative_to(bl_path.parent)),
        "gates_passed": sum(1 for v in audit.values() if v is True),
        "gates_total": sum(1 for v in audit.values() if v is not None),
        "test_count": claimed_passed,
    }
    _append_log(data, args.task_id, "completed", f"evidence: {evidence_path.name}")

    _set_tests_status(data, "healthy", "")

    _update_execution_counts(data)

    ex = data["execution"]
    if ex["completed_tasks"] == ex["total_tasks"] and ex["total_tasks"] > 0:
        data["status"] = "completed"

    _save(bl_path, data)
    pct = _pct(data)
    gates = task["verification"]
    print(
        f"OK Task '{args.task_id}' completed ({gates['gates_passed']}/{gates['gates_total']} gates)"
    )
    print(f"   Evidencia: {evidence_path}")
    print(f"   Progresso: {pct}%")
    if data["status"] == "completed":
        print("   PLANO COMPLETO!")


def cmd_fail(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    story, task = _find_task(data, args.task_id)
    if task is None:
        print(f"ERRO: Task '{args.task_id}' nao encontrada.", file=sys.stderr)
        sys.exit(1)
    task["failures"] = task.get("failures", 0) + 1
    task["last_error"] = args.error or "unspecified"
    _append_log(data, args.task_id, "failed", args.error or "")
    _update_execution_counts(data)
    _save(bl_path, data)
    print(f"OK Falha registrada em '{args.task_id}' (tentativa {task['failures']})")
    if task["failures"] >= 3:
        print(f"   CIRCUIT BREAKER: {task['failures']} falhas consecutivas.")


# ------------------------------------------------------------------
# CONTEXT (READ) commands
# ------------------------------------------------------------------


def _format_task_context(data: dict, story: dict, task: dict) -> str:
    """Compose the full context the AI needs to execute a task."""
    lines = []
    lines.append(f"TASK: {task['id']} — {task['title']}")
    lines.append(
        f"TIPO: {task['tipo']} | NIVEL: {task['nivel']} | STATUS: {task['status']}"
    )
    lines.append(f"HISTORIA: {story['id']} ({story['descricao']})")
    lines.append(f"UC: {story['uc_ref']} | FLUXO: {story['fluxo_id']}")
    lines.append("")

    lines.append("OBJETIVO:")
    lines.append(f"  {task['objetivo']}")
    lines.append("")

    if task.get("pre_condicao"):
        lines.append("PRE-CONDICOES:")
        for pc in task["pre_condicao"]:
            lines.append(f"  - {pc}")
        lines.append("")

    if task.get("pos_condicao"):
        lines.append("POS-CONDICOES:")
        for pc in task["pos_condicao"]:
            lines.append(f"  - {pc}")
        lines.append("")

    if task.get("files"):
        lines.append("ARQUIVOS:")
        for f in task["files"]:
            lines.append(f"  - {f}")
        lines.append("")

    if task.get("dependencies"):
        lines.append("DEPENDENCIAS:")
        for dep in task["dependencies"]:
            dep_story, dep_task = _find_task(data, dep)
            status = dep_task["status"] if dep_task else "?"
            title = dep_task["title"] if dep_task else dep
            lines.append(f"  - [{dep}] {title} ({status})")
        lines.append("")

    if task.get("diretiva_de_teste"):
        lines.append(f"DIRETIVA DE TESTE: {task['diretiva_de_teste']}")
    if task.get("verify_cmd"):
        lines.append(f"VERIFY CMD: {task['verify_cmd']}")
    lines.append("")

    ears_index = data.get("context", {}).get("ears_index", {})
    uc_ears_index = data.get("context", {}).get("uc_ears_index", {})
    uc_ref = story.get("uc_ref", "")
    uc_ears = uc_ears_index.get(uc_ref, [])

    if task.get("ears_refs") or uc_ears:
        lines.append(f"EARS (TASK + UC↔EARS {uc_ref}):")
        uc_ears_by_id = {item.get("id", ""): item for item in uc_ears if item.get("id")}
        printed_ids = set()

        for ref in task.get("ears_refs", []):
            if ref in printed_ids:
                continue
            uc_item = uc_ears_by_id.get(ref)
            notation = (
                uc_item.get("notation", "") if uc_item else ears_index.get(ref, "?")
            )
            origin = "task+uc" if uc_item else "task"
            lines.append(f"  - [{ref}] ({origin}) {notation}")
            printed_ids.add(ref)

        for item in uc_ears:
            ear_id = item.get("id", "?")
            if ear_id in printed_ids:
                continue
            notation = item.get("notation", "")
            lines.append(f"  - [{ear_id}] (uc) {notation}")
            printed_ids.add(ear_id)

        lines.append("")

    screens_index = data.get("context", {}).get("screens", {})
    uc_screens = screens_index.get(uc_ref, [])
    if uc_screens:
        lines.append(f"LAYOUT (telas do {uc_ref}):")
        for scr in uc_screens:
            lines.append(f"  {scr['id']} — {scr['name']}:")
            if scr.get("layout"):
                lines.append(f"    {scr['layout']}")
            components = scr.get("components", {})
            if components:
                lines.append("    Componentes:")
                for comp_name, comp_spec in components.items():
                    lines.append(f"      {comp_name}: {comp_spec}")
        lines.append("")

    if story.get("criterios"):
        lines.append("CRITERIOS DE ACEITACAO (Gherkin):")
        for i, c in enumerate(story["criterios"], 1):
            lines.append(f"  {i}. DADO {c['dado']}")
            lines.append(f"     QUANDO {c['quando']}")
            lines.append(f"     ENTAO {c['entao']}")
        lines.append("")

    decisions = data.get("context", {}).get("decisions", [])
    if decisions:
        lines.append("DECISOES DO PROJETO:")
        for d in decisions:
            lines.append(f"  - {d['label']}: {d['chosen']} ({d['rationale']})")
        lines.append("")

    architecture = data.get("context", {}).get("architecture", {})
    if architecture:
        lines.append("ARQUITETURA:")
        for principle in architecture.get("principles", []):
            lines.append(f"  - Principio: {principle}")
        for component in architecture.get("components", []):
            lines.append(f"  - Componente: {component}")
        for folder in architecture.get("folders", []):
            lines.append(
                f"  - Pasta {folder.get('path', '')}: {folder.get('purpose', '')}"
            )
        lines.append("")

    dependencies = data.get("context", {}).get("dependencies", {})
    packages = dependencies.get("packages", [])
    services = dependencies.get("services", [])
    if packages or services:
        lines.append("DEPENDENCIAS (SPEC):")
        for pkg in packages:
            envs = ", ".join(pkg.get("environments", []))
            lines.append(
                f"  - Package {pkg.get('name', '')}@{pkg.get('version', '')} [{envs}]"
            )
        for svc in services:
            envs = ", ".join(svc.get("environments", []))
            lines.append(f"  - Service {svc.get('name', '')} [{envs}]")
        lines.append("")

    entity_index = data.get("context", {}).get("entity_index", {})
    if entity_index:
        lines.append("ENTIDADES:")
        for name, defn in entity_index.items():
            lines.append(f"  - {name}: {defn}")
        lines.append("")

    quality_gate = _quality_gate_snapshot(data)
    lines.append(
        f"QUALITY GATE: tests_status={quality_gate['tests_status']} blocked={quality_gate['blocked']}"
    )
    if quality_gate.get("blocked_reason"):
        lines.append(f"  blocked_reason: {quality_gate['blocked_reason']}")
    lines.append("")

    if task.get("failures", 0) > 0:
        lines.append(f"ATENCAO: {task['failures']} falha(s) anterior(es).")
        if task.get("last_error"):
            lines.append(f"  Ultimo erro: {task['last_error']}")
        lines.append("")

    return "\n".join(lines)


def cmd_next(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    _assert_delivery_unblocked(data)

    selected_story: Optional[dict] = None
    selected_task: Optional[dict] = None
    mode = "next"

    for s, t in _all_tasks(data):
        if t["status"] == "in_progress":
            selected_story = s
            selected_task = t
            mode = "resume"
            break

    if selected_task is None:
        order = _toposort_tasks(data)
        if not order:
            ex = data["execution"]
            if ex["completed_tasks"] == ex["total_tasks"] and ex["total_tasks"] > 0:
                print("PLANO COMPLETO — nenhuma task pendente.")
            else:
                print("Nenhuma task disponivel (possivel deadlock de dependencias).")
            return

        next_id = order[0]
        selected_story, selected_task = _find_task(data, next_id)
        if selected_story is None or selected_task is None:
            print(f"ERRO: task {next_id} nao encontrada.", file=sys.stderr)
            sys.exit(1)

    if args.format == "yaml":
        payload = _build_delivery_payload(
            data,
            selected_story,
            selected_task,
            command="next",
            mode=mode,
        )
        print(_to_yaml(payload))
        return

    remaining = len(_toposort_tasks(data))
    pct = _pct(data)
    if mode == "resume":
        print(f"PROXIMA TASK ({remaining} restantes, {pct}% completo) [RETOMANDO]:")
    else:
        print(f"PROXIMA TASK ({remaining} restantes, {pct}% completo):")
    print("---")
    print(_format_task_context(data, selected_story, selected_task))


def cmd_context(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    _assert_delivery_unblocked(data)

    if args.task_id:
        story, task = _find_task(data, args.task_id)
        if task is None or story is None:
            print(f"ERRO: Task '{args.task_id}' nao encontrada.", file=sys.stderr)
            sys.exit(1)

        if args.format == "yaml":
            payload = _build_delivery_payload(
                data,
                story,
                task,
                command="context",
                mode="task",
            )
            print(_to_yaml(payload))
            return

        print(_format_task_context(data, story, task))
        return

    if args.story_id:
        story = _find_story(data, args.story_id)
        if story is None:
            print(f"ERRO: Historia '{args.story_id}' nao encontrada.", file=sys.stderr)
            sys.exit(1)

        uc_ref = story.get("uc_ref", "")
        uc_index = data.get("context", {}).get("uc_index", {})
        use_case = uc_index.get(
            uc_ref,
            {
                "id": uc_ref,
                "name": "",
                "description": "",
                "origin": data.get("context", {})
                .get("uc_origins", {})
                .get(uc_ref, "new"),
            },
        )

        if args.format == "yaml":
            payload = {
                "delivery": {
                    "command": "context",
                    "mode": "story",
                    "generated_at": _utcnow(),
                },
                "task": None,
                "story": _build_story_payload(story),
                "tasks": [_build_task_payload(t) for t in story.get("tasks", [])],
                "use_case": {
                    "id": use_case.get("id", uc_ref),
                    "name": use_case.get("name", ""),
                    "description": use_case.get("description", ""),
                    "origin": use_case.get("origin", "new"),
                    "fluxo_id": story.get("fluxo_id", ""),
                },
                "ears": {
                    "task_refs": [],
                    "use_case_refs": data.get("context", {})
                    .get("uc_ears_index", {})
                    .get(uc_ref, []),
                },
                "architecture_context": data.get("context", {}).get(
                    "architecture", {"principles": [], "components": [], "folders": []}
                ),
                "dependencies_context": data.get("context", {}).get(
                    "dependencies", {"packages": [], "services": []}
                ),
                "progress": _progress_snapshot(data),
                "quality_gate": _quality_gate_snapshot(data),
            }
            print(_to_yaml(payload))
            return

        print(f"HISTORIA: {story['id']} — {story['descricao']}")
        print(f"UC: {story['uc_ref']} | FLUXO: {story['fluxo_id']}")
        if story.get("criterios"):
            print(f"\nCRITERIOS ({len(story['criterios'])}):")
            for i, c in enumerate(story["criterios"], 1):
                print(
                    f"  {i}. DADO {c['dado']} QUANDO {c['quando']} ENTAO {c['entao']}"
                )
        print(f"\nTASKS ({len(story['tasks'])}):")
        for t in story["tasks"]:
            icon = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(
                t["status"], "[?]"
            )
            print(f"  {icon} {t['id']} — {t['title']} [{t['tipo']}]")
        return

    print("ERRO: Use --task <id> ou --story <id>", file=sys.stderr)
    sys.exit(1)


def cmd_recovery(bl_path: Path, _args: argparse.Namespace) -> None:
    data = _load(bl_path)
    lines = []
    lines.append("=== NEXUS RECOVERY PROMPT ===")
    lines.append(f"Plano: {data.get('plan_ref', '?')}")
    lines.append(f"Status: {data.get('status', '?')}")
    lines.append(f"Branch: {data.get('feature_branch', '?')}")
    lines.append("")

    ex = data.get("execution", {})
    completed = ex.get("completed_tasks", 0)
    total = ex.get("total_tasks", 0)
    current = ex.get("current_task")
    lines.append(f"Progresso: {completed}/{total}")
    if current:
        lines.append(f"Task em andamento: {current}")
    lines.append("")

    completed_tasks = []
    pending_tasks = []
    for story, task in _all_tasks(data):
        if task["status"] == "completed":
            completed_tasks.append(f"  [x] {task['id']} — {task['title']}")
        elif task["status"] == "in_progress":
            pending_tasks.insert(0, f"  [>] {task['id']} — {task['title']} (RETOMAR)")
        elif task["status"] == "pending":
            pending_tasks.append(f"  [ ] {task['id']} — {task['title']}")

    if completed_tasks:
        lines.append("COMPLETAS (nao re-executar):")
        lines.extend(completed_tasks)
        lines.append("")

    if pending_tasks:
        lines.append("PENDENTES (executar em ordem):")
        lines.extend(pending_tasks)
        lines.append("")

    order = _toposort_tasks(data)
    if order:
        next_id = order[0]
        story, task = _find_task(data, next_id)
        if story and task:
            lines.append("PROXIMA TASK A EXECUTAR:")
            lines.append(f"  {task['id']} — {task['title']}")
            lines.append(f"  Historia: {story['id']} | UC: {story['uc_ref']}")
            lines.append(f"  Objetivo: {task['objetivo']}")

    lines.append("")
    lines.append("INSTRUCAO: Retome a execucao a partir da proxima task pendente.")
    lines.append("Nao re-execute tasks ja completas.")
    lines.append("=== FIM RECOVERY ===")
    print("\n".join(lines))


# ------------------------------------------------------------------
# DISPLAY commands
# ------------------------------------------------------------------


def _pct(data: dict) -> int:
    ex = data.get("execution", {})
    total = ex.get("total_tasks", 0)
    if total == 0:
        return 0
    return int((ex.get("completed_tasks", 0) / total) * 100)


def _progress_bar(pct: int, width: int = 20) -> str:
    filled = int(width * pct / 100)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def cmd_progress(bl_path: Path, args: argparse.Namespace) -> None:
    data = _load(bl_path)
    if args.format == "yaml":
        payload = {
            "delivery": {
                "command": "progress",
                "mode": "snapshot",
                "generated_at": _utcnow(),
            },
            "progress": _progress_snapshot(data),
            "quality_gate": _quality_gate_snapshot(data),
        }
        print(_to_yaml(payload))
        return

    pct = _pct(data)
    plan_ref = data.get("plan_ref", "?")

    print(f"\U0001f4ca PROGRESSO: {plan_ref}  [ {pct}% ]")
    print("")

    for story in data.get("stories", []):
        tasks = story.get("tasks", [])
        completed_count = sum(1 for t in tasks if t["status"] == "completed")
        total = len(tasks)

        all_done = total > 0 and completed_count == total
        if all_done:
            print(
                f"\u2705 [{story['id']}] {story['descricao']} ({completed_count}/{total})"
            )
            continue

        print(f"\U0001f4d6 [{story['id']}] {story['descricao']}")

        for task in tasks:
            status = task["status"]
            failures = task.get("failures", 0)

            if status == "completed":
                icon = "\u2705 \U0001f7e2"
            elif status == "in_progress":
                icon = "\U0001f504 \U0001f534"
            else:
                icon = "\u23f3 \u26aa"

            suffix = ""
            if status == "in_progress":
                suffix = " \u2190 EXECUTANDO"
                if failures > 0:
                    suffix += f" (\u26a0\ufe0f {failures}x falha)"
            elif failures > 0:
                suffix += f" (\u26a0\ufe0f {failures}x falha)"

            print(f"  {icon} [{task['id']}] {task['title']} [{task['tipo']}]{suffix}")

        print("")

    ex = data.get("execution", {})
    total = ex.get("total_tasks", 0)
    completed_total = ex.get("completed_tasks", 0)
    failed = ex.get("failed_attempts", 0)
    quality_gate = _quality_gate_snapshot(data)
    print(f"  Total: {completed_total}/{total} tasks | Falhas acumuladas: {failed}")
    print(
        f"  QualityGate: tests_status={quality_gate['tests_status']} | blocked={quality_gate['blocked']}"
    )
    if quality_gate.get("blocked_reason"):
        print(f"  BlockedReason: {quality_gate['blocked_reason']}")


def cmd_show(bl_path: Path, _args: argparse.Namespace) -> None:
    data = _load(bl_path)
    stories = data.get("stories", [])
    all_t = _all_tasks(data)
    pct = _pct(data)

    by_status = defaultdict(int)
    by_tipo = defaultdict(int)
    for _, t in all_t:
        by_status[t["status"]] += 1
        by_tipo[t["tipo"]] += 1

    print(f"BACKLOG: {data.get('plan_ref', '?')} ({data.get('status', '?')})")
    print(f"   Historias: {len(stories)} | Tasks: {len(all_t)} | Progresso: {pct}%")
    status_parts = [f"{s}: {c}" for s, c in sorted(by_status.items())]
    print(f"   Status: {' | '.join(status_parts)}")
    tipo_parts = [f"{t}: {c}" for t, c in sorted(by_tipo.items())]
    if tipo_parts:
        print(f"   Tipos: {' | '.join(tipo_parts)}")

    ctx = data.get("context", {})
    decs = len(ctx.get("decisions", []))
    ears = len(ctx.get("ears_index", {}))
    ents = len(ctx.get("entity_index", {}))
    uc_origins = ctx.get("uc_origins", {})
    new_ucs = sum(1 for v in uc_origins.values() if v == "new")
    inferred_ucs = sum(1 for v in uc_origins.values() if v == "inferred")
    print(f"   Contexto: {decs} decisoes | {ears} EARS | {ents} entidades")
    if inferred_ucs > 0:
        print(
            f"   UCs: {new_ucs} new, {inferred_ucs} inferred (stories geradas somente para new)"
        )


def cmd_validate(bl_path: Path, _args: argparse.Namespace) -> None:
    data = _load(bl_path)
    errors = []

    stories = data.get("stories", [])
    if not stories:
        errors.append("Nenhuma historia registrada")

    all_t = _all_tasks(data)
    if not all_t:
        errors.append("Nenhuma task registrada")

    for story in stories:
        if not story.get("criterios"):
            errors.append(f"Historia '{story['id']}' sem criterios de aceitacao")
        if not story.get("tasks"):
            errors.append(f"Historia '{story['id']}' sem tasks")

    for _, task in all_t:
        if not task.get("verify_cmd"):
            errors.append(f"Task '{task['id']}' sem verify_cmd")
        if not task.get("files"):
            errors.append(f"Task '{task['id']}' sem files")
        if not task.get("objetivo"):
            errors.append(f"Task '{task['id']}' sem objetivo")

    dep_ids = {t["id"] for _, t in all_t}
    for _, task in all_t:
        for dep in task.get("dependencies", []):
            if dep not in dep_ids:
                errors.append(f"Task '{task['id']}' depende de '{dep}' que nao existe")

    if errors:
        print(f"FALHA: {len(errors)} problema(s):")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    else:
        total = len(all_t)
        print(f"OK backlog valido ({len(stories)} historias, {total} tasks)")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backlog",
        description="Nexus Dev — Backlog Builder & Execution Tool",
    )
    p.add_argument("backlog_path", help="Caminho do backlog.json")
    sub = p.add_subparsers(dest="action", required=True)

    # init
    s = sub.add_parser("init", help="Criar backlog.json a partir de spec.json")
    s.add_argument(
        "--spec",
        default="",
        help="Caminho do spec.json (auto-descobre .nexus/spec.json se omitido)",
    )

    # add-story
    s = sub.add_parser("add-story", help="Registrar historia de usuario")
    s.add_argument("--id", required=True, help="ID da historia (ex: US-UC01-FP)")
    s.add_argument("--uc-ref", required=True, help="ID do UC pai (ex: UC-01)")
    s.add_argument("--fluxo-id", required=True, help="ID do fluxo (ex: UC-01.FP)")
    s.add_argument("--descricao", required=True, help="Descricao breve")

    # add-criterio
    s = sub.add_parser("add-criterio", help="Adicionar criterio Gherkin a uma historia")
    s.add_argument("--story", required=True, help="ID da historia pai")
    s.add_argument("--dado", required=True, help="Dado (Given)")
    s.add_argument("--quando", required=True, help="Quando (When)")
    s.add_argument("--entao", required=True, help="Entao (Then)")

    # add-task
    s = sub.add_parser("add-task", help="Registrar task atomica")
    s.add_argument("--story-ref", required=True, help="ID da historia pai")
    s.add_argument("--id", required=True, help="ID da task (ex: TASK-001)")
    s.add_argument("--title", required=True, help="Titulo da task")
    s.add_argument("--tipo", required=True, help="Tipo: Dados, UI, API, Integracao")
    s.add_argument(
        "--nivel", type=int, default=0, help="Nivel de dependencia (0, 1, 2)"
    )
    s.add_argument("--objetivo", required=True, help="Objetivo da task")
    s.add_argument("--pre-condicao", nargs="+", default=[], help="Pre-condicoes")
    s.add_argument("--pos-condicao", nargs="+", default=[], help="Pos-condicoes")
    s.add_argument(
        "--diretiva", default="", help="Diretiva de teste (Integracao, Componente, E2E)"
    )
    s.add_argument("--verify-cmd", default="", help="Comando de verificacao")
    s.add_argument("--files", nargs="+", default=[], help="Arquivos da task")
    s.add_argument(
        "--dependencies", nargs="+", default=[], help="IDs de tasks dependentes"
    )
    s.add_argument(
        "--ears-refs", nargs="+", default=[], help="IDs de EARS relacionados"
    )

    # start
    s = sub.add_parser("start", help="Marcar task como in_progress")
    s.add_argument("task_id", help="ID da task")

    # complete
    s = sub.add_parser(
        "complete", help="Validar claims da IA e marcar task como completed"
    )
    s.add_argument("task_id", help="ID da task")
    s.add_argument(
        "--test-files", nargs="+", default=[], help="Arquivos de teste criados pela IA"
    )
    s.add_argument(
        "--test-passed", type=int, default=0, help="Numero de testes que passaram"
    )
    s.add_argument(
        "--test-failed", type=int, default=0, help="Numero de testes que falharam"
    )
    s.add_argument(
        "--project-root",
        default="",
        help="Raiz do projeto (default: 3 niveis acima do backlog.json)",
    )

    # fail
    s = sub.add_parser("fail", help="Registrar falha em uma task")
    s.add_argument("task_id", help="ID da task")
    s.add_argument("--error", default="", help="Descricao do erro")

    # next
    s = sub.add_parser("next", help="Obter proxima task com contexto completo")
    s.add_argument(
        "--format",
        choices=["yaml", "text"],
        default="yaml",
        help="Formato de saida (default: yaml)",
    )

    # context
    s = sub.add_parser("context", help="Obter contexto de task ou historia especifica")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--task", dest="task_id", help="ID da task")
    g.add_argument("--story", dest="story_id", help="ID da historia")
    s.add_argument(
        "--format",
        choices=["yaml", "text"],
        default="yaml",
        help="Formato de saida (default: yaml)",
    )

    # recovery
    sub.add_parser("recovery", help="Gerar prompt de recuperacao apos crash")

    # progress
    s = sub.add_parser("progress", help="Exibir progresso hierarquico")
    s.add_argument(
        "--format",
        choices=["yaml", "text"],
        default="text",
        help="Formato de saida (default: text)",
    )

    # show
    sub.add_parser("show", help="Exibir resumo do backlog")

    # validate
    sub.add_parser("validate", help="Verificar completude do backlog")

    return p


_ACTIONS = {
    "init": cmd_init,
    "add-story": cmd_add_story,
    "add-criterio": cmd_add_criterio,
    "add-task": cmd_add_task,
    "start": cmd_start,
    "complete": cmd_complete,
    "fail": cmd_fail,
    "next": cmd_next,
    "context": cmd_context,
    "recovery": cmd_recovery,
    "progress": cmd_progress,
    "show": cmd_show,
    "validate": cmd_validate,
}


def _find_nexus_root() -> "Path | None":
    """Walk up from CWD to find .nexus/ directory."""
    current = Path.cwd()
    while True:
        candidate = current / ".nexus"
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _run_is_fully_closed(run_dir: Path) -> bool:
    review_path = run_dir / "review.json"
    if not review_path.exists():
        return False
    with open(review_path, "r", encoding="utf-8") as f:
        review = json.load(f)
    return review.get("verdict") == "APPROVED"


def _resolve_active_run(nexus_root: Path) -> "Path | None":
    """Find the latest run directory that has a backlog.json."""
    runs_dir = nexus_root / "runs"
    if not runs_dir.exists():
        return None
    for d in sorted(
        (x for x in runs_dir.iterdir() if x.is_dir() and x.name.isdigit()),
        key=lambda x: int(x.name),
        reverse=True,
    ):
        if (d / "backlog.json").exists():
            return d
    return None


def _resolve_next_run(nexus_root: Path) -> Path:
    """Find the next available run directory for a new backlog.
    Exits with error if there is an active (non-closed) run."""
    runs_dir = nexus_root / "runs"
    if not runs_dir.exists():
        return runs_dir / "001"

    existing = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )
    if not existing:
        return runs_dir / "001"

    for run_dir in reversed(existing):
        bl_path = run_dir / "backlog.json"
        if not bl_path.exists():
            continue
        with open(bl_path, "r", encoding="utf-8") as f:
            backlog = json.load(f)
        status = backlog.get("status", "building")
        if status == "completed" and _run_is_fully_closed(run_dir):
            next_num = int(run_dir.name) + 1
            return runs_dir / f"{next_num:03d}"
        print(
            f"ERRO: run ativa em {run_dir.name} — complete /dev e /review antes de iniciar nova run.",
            file=sys.stderr,
        )
        sys.exit(1)

    max_num = int(existing[-1].name)
    return runs_dir / f"{max_num + 1:03d}"


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in _ACTIONS:
        nexus = _find_nexus_root()
        if nexus is None:
            print(
                "ERRO: .nexus/ nao encontrado. Execute a partir do diretorio do projeto.",
                file=sys.stderr,
            )
            sys.exit(1)
        if sys.argv[1] == "init":
            run_dir = _resolve_next_run(nexus)
        else:
            run_dir = _resolve_active_run(nexus)
            if run_dir is None:
                print(
                    "ERRO: nenhuma run com backlog encontrada em .nexus/runs/.",
                    file=sys.stderr,
                )
                sys.exit(1)
        sys.argv.insert(1, str(run_dir / "backlog.json"))

    parser = _build_parser()
    args = parser.parse_args()
    bl_path = Path(args.backlog_path)
    handler = _ACTIONS.get(args.action)
    if handler:
        handler(bl_path, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

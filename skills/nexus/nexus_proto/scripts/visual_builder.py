#!/usr/bin/env python3
"""
Nexus Proto — Visual Builder

CLI tool that the AI agent calls to register visual/layout decisions
collected during the /proto A/B wireframe exploration phase.

The AI explores layouts (via SVGs, canvas, etc.) and collects user decisions.
This script REGISTERS the final decisions — it does not generate visuals.

Subcommands:
  init           Create visual.json from an existing spec.json
  add-screen     Register a decided screen with its layout
  add-component  Register a component spec within a screen
  show           Display screen inventory
  validate       Check completeness (all screens have layout + components)

Usage:
  python visual_builder.py .nexus/plan/visual.json init --spec .nexus/plan/spec.json
  python visual_builder.py .nexus/plan/visual.json add-screen --id S01 --name "Lista de Tarefas" --uc-refs UC-01 UC-03 --layout "Filtros no topo..."
  python visual_builder.py .nexus/plan/visual.json add-component --screen S01 --name FilterBar --spec "Pills 22px horizontais..."
  python visual_builder.py .nexus/plan/visual.json show
  python visual_builder.py .nexus/plan/visual.json validate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    if not path.exists():
        print(f"ERRO: visual.json nao encontrado: {path}", file=sys.stderr)
        print("   Execute 'init' primeiro.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    data["updated_at"] = _utcnow()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _find_screen(data: dict, screen_id: str) -> dict | None:
    for screen in data.get("screens", []):
        if screen["id"] == screen_id:
            return screen
    return None


# ------------------------------------------------------------------
# BUILD commands
# ------------------------------------------------------------------


def _check_pipeline_order(spec_path: Path) -> None:
    """Validate that /plan was completed before /proto can start."""
    if not spec_path.exists():
        print("ERRO: spec.json nao encontrado.", file=sys.stderr)
        print(f"   Caminho: {spec_path}", file=sys.stderr)
        print("   Execute /plan primeiro para gerar o spec.json.", file=sys.stderr)
        sys.exit(1)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    ucs = spec.get("use_cases", [])
    if not ucs:
        print("ERRO: spec.json nao contem casos de uso.", file=sys.stderr)
        print("   O /plan precisa ser concluido antes de executar /proto.", file=sys.stderr)
        print("   Execute: python spec_builder.py {spec} uc --id UC-01 ...", file=sys.stderr)
        sys.exit(1)

    backlog_path = spec_path.parent / "backlog.json"
    if backlog_path.exists():
        with open(backlog_path, "r", encoding="utf-8") as f:
            backlog = json.load(f)
        status = backlog.get("status", "?")
        sys.stderr.flush()
        sys.stdout.flush()
        print("AVISO: backlog.json ja existe neste plano — /dev ja foi iniciado.", file=sys.stderr)
        print(f"   Status do backlog: {status}", file=sys.stderr)
        print("   O visual.json NAO sera incorporado ao backlog existente.", file=sys.stderr)
        print("   Para incluir visual no /dev: delete backlog.json e re-execute 'backlog.py init'.", file=sys.stderr)
        sys.stderr.flush()


def cmd_init(vpath: Path, args: argparse.Namespace) -> None:
    if vpath.exists():
        print(f"ERRO: visual.json ja existe: {vpath}", file=sys.stderr)
        sys.exit(1)

    spec_path = Path(args.spec)
    _check_pipeline_order(spec_path)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    data = {
        "nexus_version": "3.0",
        "plan_name": spec.get("plan_name", ""),
        "spec_ref": str(spec_path),
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "screens": [],
    }
    _save(vpath, data)
    plan = spec.get("plan_name", "?")
    ucs = len(spec.get("use_cases", []))
    print(f"OK visual.json criado: {vpath}")
    print(f"   Plano: {plan} | UCs no spec: {ucs}")


def cmd_add_screen(vpath: Path, args: argparse.Namespace) -> None:
    data = _load(vpath)
    existing = _find_screen(data, args.id)

    if existing:
        existing["name"] = args.name
        existing["uc_refs"] = args.uc_refs or existing.get("uc_refs", [])
        existing["layout_decision"] = args.layout or existing.get("layout_decision", "")
        action = "atualizada"
    else:
        screen = {
            "id": args.id,
            "name": args.name,
            "uc_refs": args.uc_refs or [],
            "layout_decision": args.layout or "",
            "components": [],
        }
        data["screens"].append(screen)
        action = "adicionada"

    _save(vpath, data)
    total = len(data["screens"])
    print(f"OK Screen '{args.id}' {action} — total: {total}")


def cmd_decide(vpath: Path, args: argparse.Namespace) -> None:
    data = _load(vpath)
    screen = _find_screen(data, args.screen)
    if screen is None:
        print(f"ERRO: Screen '{args.screen}' nao encontrada.", file=sys.stderr)
        sys.exit(1)

    screen["layout_decision"] = args.layout
    _save(vpath, data)
    print(f"OK Layout registrado para '{args.screen}'")
    preview = args.layout[:80] + ("..." if len(args.layout) > 80 else "")
    print(f"   {preview}")


def cmd_add_component(vpath: Path, args: argparse.Namespace) -> None:
    data = _load(vpath)
    screen = _find_screen(data, args.screen)
    if screen is None:
        print(f"ERRO: Screen '{args.screen}' nao encontrada.", file=sys.stderr)
        sys.exit(1)

    components = screen.get("components", [])
    existing_idx = None
    for i, comp in enumerate(components):
        if comp["name"] == args.name:
            existing_idx = i
            break

    component = {"name": args.name, "spec": args.spec}

    if existing_idx is not None:
        components[existing_idx] = component
        action = "atualizado"
    else:
        components.append(component)
        action = "adicionado"

    screen["components"] = components
    _save(vpath, data)
    total = len(components)
    print(f"OK Componente '{args.name}' {action} em '{args.screen}' — total: {total}")


# ------------------------------------------------------------------
# DISPLAY commands
# ------------------------------------------------------------------


def cmd_show(vpath: Path, _args: argparse.Namespace) -> None:
    data = _load(vpath)
    screens = data.get("screens", [])
    plan = data.get("plan_name", "?")

    print(f"VISUAL: {plan} ({len(screens)} screens)")
    print("")

    for screen in screens:
        ucs = ", ".join(screen.get("uc_refs", [])) or "—"
        components = screen.get("components", [])
        layout = screen.get("layout_decision", "")
        has_layout = bool(layout)
        has_components = len(components) > 0

        check = "[x]" if (has_layout and has_components) else "[ ]"
        print(f"  {check} {screen['id']} — {screen['name']} ({ucs})")

        if layout:
            preview = layout[:80] + ("..." if len(layout) > 80 else "")
            print(f"      Layout: {preview}")

        if components:
            for comp in components:
                spec_preview = comp['spec'][:60] + ("..." if len(comp['spec']) > 60 else "")
                print(f"      • {comp['name']}: {spec_preview}")
        else:
            print(f"      (sem componentes)")

        print("")

    complete = sum(
        1 for s in screens
        if s.get("layout_decision") and s.get("components")
    )
    print(f"  Completas: {complete}/{len(screens)}")


def cmd_validate(vpath: Path, args: argparse.Namespace) -> None:
    data = _load(vpath)
    errors = []
    screens = data.get("screens", [])

    if not screens:
        errors.append("Nenhuma screen registrada")

    for screen in screens:
        sid = screen["id"]
        if not screen.get("layout_decision"):
            errors.append(f"Screen '{sid}' sem layout_decision")
        if not screen.get("components"):
            errors.append(f"Screen '{sid}' sem componentes")
        if not screen.get("uc_refs"):
            errors.append(f"Screen '{sid}' sem uc_refs")

    if args.spec:
        spec_path = Path(args.spec)
        if spec_path.exists():
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = json.load(f)
            spec_uc_ids = {uc["id"] for uc in spec.get("use_cases", [])}
            visual_uc_ids = set()
            for screen in screens:
                visual_uc_ids.update(screen.get("uc_refs", []))
            missing = spec_uc_ids - visual_uc_ids
            if missing:
                for uc_id in sorted(missing):
                    errors.append(f"UC '{uc_id}' do spec nao tem screen associada")

    if errors:
        print(f"FALHA: {len(errors)} problema(s):")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    else:
        total = len(screens)
        comp_count = sum(len(s.get("components", [])) for s in screens)
        print(f"OK visual valido ({total} screens, {comp_count} componentes)")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="visual_builder",
        description="Nexus Proto — Visual Builder (registro de decisoes visuais)",
    )
    p.add_argument("visual_path", help="Caminho do visual.json")
    sub = p.add_subparsers(dest="action", required=True)

    s = sub.add_parser("init", help="Criar visual.json a partir de spec.json")
    s.add_argument("--spec", required=True, help="Caminho do spec.json")

    s = sub.add_parser("add-screen", help="Registrar screen decidida")
    s.add_argument("--id", required=True, help="ID da screen (ex: S01)")
    s.add_argument("--name", required=True, help="Nome da screen")
    s.add_argument("--uc-refs", nargs="+", default=[], help="IDs dos UCs relacionados")
    s.add_argument("--layout", default="", help="Descricao textual do layout decidido")

    s = sub.add_parser("decide", help="Registrar layout decidido em uma screen")
    s.add_argument("--screen", required=True, help="ID da screen")
    s.add_argument("--layout", required=True, help="Descricao textual do layout decidido")

    s = sub.add_parser("add-component", help="Registrar componente em uma screen")
    s.add_argument("--screen", required=True, help="ID da screen pai")
    s.add_argument("--name", required=True, help="Nome do componente")
    s.add_argument("--spec", required=True, help="Especificacao visual do componente")

    sub.add_parser("show", help="Exibir inventario de screens")

    s = sub.add_parser("validate", help="Verificar completude")
    s.add_argument("--spec", default="", help="Caminho do spec.json para cross-reference UCs")

    return p


_ACTIONS = {
    "init": cmd_init,
    "add-screen": cmd_add_screen,
    "decide": cmd_decide,
    "add-component": cmd_add_component,
    "show": cmd_show,
    "validate": cmd_validate,
}


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    vpath = Path(args.visual_path)
    handler = _ACTIONS.get(args.action)
    if handler:
        handler(vpath, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

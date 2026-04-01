#!/usr/bin/env python3
"""
Nexus Plan — Spec Builder

CLI tool that the AI agent calls to incrementally build spec.json.
Each subcommand adds structured data to the correct section.
The `render` subcommand converts spec.json → spec.md + decision_manifest.json.

Replaces: plan_generator.py, option_resolver.py

Subcommands:
  init        Criar novo spec.json
  decision    Adicionar decisão de projeto
  ear         Adicionar requisito EARS
  actor       Adicionar ator ao dicionário
  uc          Adicionar caso de uso à matriz
  uc-diagram  Definir diagrama Mermaid de casos de uso
  drilldown   Adicionar drill-down de caso de uso (fluxo principal)
  alt-flow    Adicionar fluxo alternativo a um drill-down existente
  entity      Adicionar entidade ao dicionário
  invariant   Adicionar invariante do sistema
  nfr         Adicionar requisito não-funcional
  show        Exibir resumo do spec.json
  validate    Verificar completude do spec.json
  render      Gerar spec.md e decision_manifest.json

Usage:
  python spec_builder.py .nexus/plan/spec.json init --plan "my-plan" --overview "..."
  python spec_builder.py .nexus/plan/spec.json ear --id REQ-01 --type WHEN --notation "WHEN ..."
  python spec_builder.py .nexus/plan/spec.json render
"""

from __future__ import annotations

import argparse
import json
import re
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
        print(f"ERRO: spec.json nao encontrado: {path}", file=sys.stderr)
        print("   Execute 'init' primeiro.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    data["updated_at"] = _utcnow()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _upsert(items: list[dict], entry: dict, key: str) -> str:
    """Insert or update by natural key. Returns 'adicionado' or 'atualizado'."""
    for i, existing in enumerate(items):
        if existing.get(key) == entry[key]:
            items[i] = entry
            return "atualizado"
    items.append(entry)
    return "adicionado"


def _dedup_append(items: list, text: str) -> str:
    if text in items:
        return "ja existe"
    items.append(text)
    return "adicionado"


def load_spec(path: "str | Path") -> dict:
    """Public API: load and return spec.json data for downstream scripts."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"spec.json not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

_VAGUE_TERMS = [
    "rapido", "rápido", "rapidamente", "lento", "lentamente",
    "eficiente", "eficientemente", "robusto", "robustamente",
    "seguro", "seguramente", "facil", "fácil", "facilmente",
    "simples", "simplesmente", "adequado", "adequadamente",
    "bom", "melhor", "escalavel", "escalável",
    "fast", "quickly", "slow", "slowly",
    "efficient", "efficiently", "robust", "robustly",
    "secure", "securely", "easy", "easily",
    "simple", "simply", "adequate", "adequately",
    "good", "better", "scalable",
]
_VAGUE_RE = re.compile(r"\b(" + "|".join(_VAGUE_TERMS) + r")\b", re.IGNORECASE)


def _validate(data: dict) -> list[str]:
    """Return list of error messages. Empty list = valid."""
    errors: list[str] = []

    if not data.get("overview"):
        errors.append("Visao geral vazia")

    if not data.get("decisions"):
        errors.append("Nenhuma decisao de projeto registrada")

    ears = data.get("ears", [])
    if len(ears) < 5:
        errors.append(f"Minimo de 5 EARS nao atingido (atual: {len(ears)})")

    for ear in ears:
        notation = ear.get("notation", "")
        if "THE SYSTEM SHALL" not in notation.upper():
            errors.append(f"{ear['id']}: notacao nao contem 'THE SYSTEM SHALL'")
        vague_match = _VAGUE_RE.search(notation)
        if vague_match:
            errors.append(
                f"{ear['id']}: linguagem vaga detectada ('{vague_match.group()}')"
                " — substitua por metrica concreta"
            )

    actors = data.get("actors", [])
    if not actors:
        errors.append("Nenhum ator no Dicionario de Atores")

    if not data.get("uc_diagram"):
        errors.append("Diagrama Mermaid de Casos de Uso nao definido")

    entities = data.get("entities", [])
    if not entities:
        errors.append("Nenhuma entidade no Dicionario de Entidades")

    ucs = data.get("use_cases", [])
    if not ucs:
        errors.append("Nenhum caso de uso registrado")

    drilldowns = data.get("drilldowns", [])
    uc_ids = {uc["id"] for uc in ucs}
    dd_ids = {dd["uc_id"] for dd in drilldowns}

    missing_dd = uc_ids - dd_ids
    if missing_dd:
        errors.append(f"UCs sem drill-down: {', '.join(sorted(missing_dd))}")

    orphan_dd = dd_ids - uc_ids
    if orphan_dd:
        errors.append(f"Drill-downs sem UC correspondente: {', '.join(sorted(orphan_dd))}")

    return errors


# ------------------------------------------------------------------
# Renderer (spec.json → spec.md)
# ------------------------------------------------------------------


def _render_md(data: dict) -> str:
    lines: list[str] = []
    title = data.get("title", data.get("plan_name", "UNKNOWN").upper())

    lines.append(f"# {title} — Especificação Técnica (NEXUS)")
    lines.append("")

    # 1. Visão Geral
    lines.append("## 1. Visão Geral")
    lines.append(data.get("overview", ""))
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Decisões do Projeto
    lines.append("## 2. Decisões do Projeto")
    lines.append("")
    for d in data.get("decisions", []):
        lines.append(f"- **{d['label']}:** {d['chosen']} — {d['rationale']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Requisitos EARS
    lines.append("## 3. Requisitos EARS")
    lines.append("")
    ears = data.get("ears", [])
    if ears:
        lines.append("| ID | Tipo | Notação EARS |")
        lines.append("|----|------|--------------|")
        for e in ears:
            lines.append(f"| **{e['id']}** | {e['type']} | {e['notation']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Especificação Funcional (UML)
    lines.append("## 4. Especificação Funcional (UML)")
    lines.append("")

    # 4.1 Diagrama
    lines.append("### 4.1 Diagrama de Casos de Uso (Mermaid)")
    lines.append("")
    uc_diagram = data.get("uc_diagram", "")
    if uc_diagram:
        lines.append("```mermaid")
        lines.append(uc_diagram)
        lines.append("```")
    lines.append("")

    # 4.2 Atores
    lines.append("### 4.2 Dicionário de Atores")
    lines.append("")
    actors = data.get("actors", [])
    if actors:
        lines.append("| Ator | Tipo | Responsabilidade |")
        lines.append("|------|------|------------------|")
        for a in actors:
            lines.append(f"| **{a['name']}** | {a['type']} | {a['responsibility']} |")
    lines.append("")

    # 4.3 Matriz de UCs
    lines.append("### 4.3 Matriz de Casos de Uso")
    lines.append("")
    ucs = data.get("use_cases", [])
    if ucs:
        lines.append("| ID | Nome | Descrição |")
        lines.append("|----|------|-----------|")
        for uc in ucs:
            lines.append(f"| **{uc['id']}** | {uc['name']} | {uc['description']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 5. Drill-down de Casos de Uso
    lines.append("## 5. Drill-down de Casos de Uso")
    lines.append("")
    for dd in data.get("drilldowns", []):
        uc_id = dd["uc_id"]
        lines.append(f"### {uc_id}: {dd['name']}")

        lines.append(f"- **Ator:** {dd['actor']}")

        pcs = dd.get("preconditions", [])
        if pcs:
            if len(pcs) == 1:
                lines.append(f"- **Pré-condições:** {pcs[0]}")
            else:
                lines.append("- **Pré-condições:**")
                for pc in pcs:
                    lines.append(f"  - {pc}")

        main_flow = dd.get("main_flow", [])
        if main_flow:
            lines.append(f"- **Fluxo Principal ({uc_id}.FP):**")
            for i, step in enumerate(main_flow, 1):
                lines.append(f"  {i}. {step}")

        alt_flows = dd.get("alt_flows", [])
        if alt_flows:
            lines.append("- **Fluxos Alternativos:**")
            for af in alt_flows:
                steps = af.get("steps", [])
                desc = af["description"]
                if len(steps) <= 1:
                    step_text = steps[0] if steps else desc
                    lines.append(f"  - **{af['id']} ({desc}):** {step_text}")
                else:
                    lines.append(f"  - **{af['id']} ({desc}):**")
                    for j, step in enumerate(steps, 1):
                        lines.append(f"    {j}. {step}")

        posts = dd.get("postconditions", [])
        if posts:
            if len(posts) == 1:
                lines.append(f"- **Pós-condições:** {posts[0]}")
            else:
                lines.append("- **Pós-condições:**")
                for pc in posts:
                    lines.append(f"  - {pc}")

        lines.append("")

    lines.append("---")
    lines.append("")

    # 6. Dicionário de Entidades
    lines.append("## 6. Dicionário de Entidades")
    lines.append("")
    entities = data.get("entities", [])
    if entities:
        lines.append("| Entidade | Tipo | Definição |")
        lines.append("|----------|------|-----------|")
        for e in entities:
            lines.append(f"| **{e['name']}** | {e['type']} | {e['definition']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 7. Invariantes do Sistema
    lines.append("## 7. Invariantes do Sistema")
    lines.append("")
    for inv in data.get("invariants", []):
        lines.append(f"- {inv}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 8. NFRs
    lines.append("## 8. NFRs (Non-Functional Requirements)")
    lines.append("")
    for nfr in data.get("nfrs", []):
        if isinstance(nfr, dict):
            if nfr.get("label"):
                lines.append(f"- **{nfr['label']}:** {nfr['text']}")
            else:
                lines.append(f"- {nfr['text']}")
        else:
            lines.append(f"- {nfr}")
    lines.append("")

    lines.append("> Plano gerado via Nexus `/plan`. Execute `/dev` para iniciar a implementação.")
    lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Action handlers
# ------------------------------------------------------------------


def cmd_init(spec_path: Path, args: argparse.Namespace) -> None:
    if spec_path.exists():
        print(f"spec.json ja existe: {spec_path}", file=sys.stderr)
        print("   Use os subcomandos para adicionar dados.", file=sys.stderr)
        sys.exit(1)
    title = args.title or args.plan.replace("-", " ").upper()
    data = {
        "nexus_version": "3.0",
        "plan_name": args.plan,
        "title": title,
        "overview": args.overview,
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
        "decisions": [],
        "ears": [],
        "uc_diagram": "",
        "actors": [],
        "use_cases": [],
        "drilldowns": [],
        "entities": [],
        "invariants": [],
        "nfrs": [],
    }
    _save(spec_path, data)
    print(f"OK spec.json criado: {spec_path}")
    print(f"   Plano: {args.plan} | Titulo: {title}")


def cmd_decision(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {
        "label": args.label,
        "chosen": args.chosen,
        "rationale": args.rationale,
        "auto_assumed": args.auto_assumed,
    }
    action = _upsert(data["decisions"], entry, "label")
    _save(spec_path, data)
    prefix = "AUTO-ASSUMED " if args.auto_assumed else ""
    print(f"OK {prefix}Decisao '{args.label}' {action} — total: {len(data['decisions'])}")


def cmd_ear(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {"id": args.id, "type": args.type, "notation": args.notation}
    action = _upsert(data["ears"], entry, "id")
    _save(spec_path, data)
    print(f"OK {args.id} ({args.type}) {action} — total: {len(data['ears'])} EARS")


def cmd_actor(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {"name": args.name, "type": args.type, "responsibility": args.responsibility}
    action = _upsert(data["actors"], entry, "name")
    _save(spec_path, data)
    print(f"OK Ator '{args.name}' {action} — total: {len(data['actors'])}")


def cmd_uc(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {"id": args.id, "name": args.name, "description": args.description}
    action = _upsert(data["use_cases"], entry, "id")
    _save(spec_path, data)
    print(f"OK {args.id} '{args.name}' {action} — total: {len(data['use_cases'])} UCs")


def cmd_uc_diagram(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"ERRO: Arquivo nao encontrado: {args.file}", file=sys.stderr)
            sys.exit(1)
        mermaid = fp.read_text(encoding="utf-8").strip()
    else:
        mermaid = args.mermaid.replace("\\n", "\n")
    data["uc_diagram"] = mermaid
    _save(spec_path, data)
    print(f"OK Diagrama de casos de uso definido ({len(mermaid)} chars)")


def cmd_drilldown(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    name = args.name or ""
    if not name:
        for uc in data["use_cases"]:
            if uc["id"] == args.uc_id:
                name = uc["name"]
                break
    if not name:
        name = args.uc_id

    existing_alt_flows: list[dict] = []
    existing_preconditions: list[str] = []
    existing_postconditions: list[str] = []
    for existing in data["drilldowns"]:
        if existing["uc_id"] == args.uc_id:
            existing_alt_flows = existing.get("alt_flows", [])
            existing_preconditions = existing.get("preconditions", [])
            existing_postconditions = existing.get("postconditions", [])
            break

    entry = {
        "uc_id": args.uc_id,
        "name": name,
        "actor": args.actor,
        "preconditions": args.preconditions or existing_preconditions,
        "main_flow": args.main_flow or [],
        "alt_flows": existing_alt_flows,
        "postconditions": args.postconditions or existing_postconditions,
    }
    action = _upsert(data["drilldowns"], entry, "uc_id")
    _save(spec_path, data)
    steps = len(entry["main_flow"])
    print(f"OK Drill-down {args.uc_id} {action} ({steps} passos no fluxo principal)")


def cmd_alt_flow(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    drilldown = None
    for dd in data["drilldowns"]:
        if dd["uc_id"] == args.uc_id:
            drilldown = dd
            break
    if drilldown is None:
        print(f"ERRO: Drill-down {args.uc_id} nao encontrado. Crie-o primeiro com 'drilldown'.", file=sys.stderr)
        sys.exit(1)

    flow_entry = {"id": args.id, "description": args.description, "steps": args.steps or []}
    if "alt_flows" not in drilldown:
        drilldown["alt_flows"] = []
    action = _upsert(drilldown["alt_flows"], flow_entry, "id")
    _save(spec_path, data)
    print(f"OK Fluxo alternativo {args.id} {action} no {args.uc_id}")


def cmd_entity(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {"name": args.name, "type": args.type, "definition": args.definition}
    action = _upsert(data["entities"], entry, "name")
    _save(spec_path, data)
    print(f"OK Entidade '{args.name}' {action} — total: {len(data['entities'])}")


def cmd_invariant(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    action = _dedup_append(data["invariants"], args.text)
    _save(spec_path, data)
    print(f"OK Invariante {action} — total: {len(data['invariants'])}")


def cmd_nfr(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {"label": args.label or "", "text": args.text}
    action = _upsert(data["nfrs"], entry, "text")
    _save(spec_path, data)
    label_str = f" ({args.label})" if args.label else ""
    print(f"OK NFR{label_str} {action} — total: {len(data['nfrs'])}")


def cmd_show(spec_path: Path, _args: argparse.Namespace) -> None:
    data = _load(spec_path)
    decisions = len(data.get("decisions", []))
    ears = len(data.get("ears", []))
    actors = len(data.get("actors", []))
    ucs = len(data.get("use_cases", []))
    dds = len(data.get("drilldowns", []))
    entities = len(data.get("entities", []))
    invariants = len(data.get("invariants", []))
    nfrs = len(data.get("nfrs", []))

    print(f"SPEC: {data['plan_name']} ({data.get('title', '')})")
    print(f"   Decisoes: {decisions} | EARS: {ears} | Atores: {actors} | UCs: {ucs}")
    print(f"   Drill-downs: {dds} | Entidades: {entities} | Invariantes: {invariants} | NFRs: {nfrs}")
    has_diagram = "sim" if data.get("uc_diagram") else "nao"
    print(f"   Diagrama UC: {has_diagram}")

    uc_ids = {uc["id"] for uc in data.get("use_cases", [])}
    dd_ids = {dd["uc_id"] for dd in data.get("drilldowns", [])}
    missing = uc_ids - dd_ids
    if missing:
        print(f"   AVISO — UCs sem drill-down: {', '.join(sorted(missing))}")
    elif ucs > 0 and dds == ucs:
        print(f"   Drill-downs: 1:1 com UCs (OK)")


def cmd_validate(spec_path: Path, _args: argparse.Namespace) -> None:
    data = _load(spec_path)
    errors = _validate(data)
    if errors:
        print(f"FALHA: {len(errors)} problema(s):")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    ears = len(data.get("ears", []))
    ucs = len(data.get("use_cases", []))
    entities = len(data.get("entities", []))
    print(f"OK spec.json valido ({ears} EARS, {ucs} UCs, {entities} entidades)")


def cmd_render(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)

    errors = _validate(data)
    if errors and not args.force:
        print(f"FALHA: Validacao falhou ({len(errors)} erro(s)):", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        print("   Use --force para renderizar mesmo com erros.", file=sys.stderr)
        sys.exit(1)

    md = _render_md(data)
    md_path = spec_path.parent / "spec.md"
    md_path.write_text(md, encoding="utf-8")

    manifest = {
        "plan_name": data.get("plan_name", "UNKNOWN"),
        "decisions": [
            {
                "id": f"D{i:02d}",
                "category": d["label"],
                "question": d["label"],
                "chosen": d["chosen"],
                "rationale": d["rationale"],
                "auto_assumed": d.get("auto_assumed", False),
                "risk": "low",
            }
            for i, d in enumerate(data.get("decisions", []), 1)
        ],
    }
    manifest_path = spec_path.parent / "decision_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    ears = len(data.get("ears", []))
    ucs = len(data.get("use_cases", []))
    entities = len(data.get("entities", []))
    print(f"OK spec.md renderizado: {md_path}")
    print(f"   {ears} EARS | {ucs} UCs | {entities} entidades")
    print(f"OK decision_manifest.json gerado: {manifest_path}")
    if errors:
        print(f"AVISO: Renderizado com {len(errors)} problema(s) (--force)")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _ear_type(value: str) -> str:
    upper = value.upper()
    if upper not in ("WHEN", "WHILE", "IF", "WHERE"):
        raise argparse.ArgumentTypeError(f"Tipo EARS invalido: {value}. Use WHEN/WHILE/IF/WHERE.")
    return upper


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spec_builder",
        description="Nexus Plan — Constroi spec.json incrementalmente e renderiza spec.md.",
    )
    p.add_argument("spec_path", help="Caminho do spec.json (ex: .nexus/meu-plano/spec.json)")
    sub = p.add_subparsers(dest="action", required=True)

    # init
    s = sub.add_parser("init", help="Criar novo spec.json")
    s.add_argument("--plan", required=True, help="Nome do plano (slug, ex: hellfire-spark)")
    s.add_argument("--title", help="Titulo de exibicao (default: plan em maiusculas)")
    s.add_argument("--overview", required=True, help="Visao geral do projeto")

    # decision
    s = sub.add_parser("decision", help="Adicionar decisao de projeto")
    s.add_argument("--label", required=True, help="Rotulo (ex: Destruicao)")
    s.add_argument("--chosen", required=True, help="Opcao escolhida (ex: Permanente (A))")
    s.add_argument("--rationale", required=True, help="Justificativa")
    s.add_argument("--auto-assumed", action="store_true", help="Marcar como decisao auto-assumida")

    # ear
    s = sub.add_parser("ear", help="Adicionar requisito EARS")
    s.add_argument("--id", required=True, help="ID do requisito (ex: REQ-01)")
    s.add_argument("--type", required=True, type=_ear_type, help="Tipo: WHEN, WHILE, IF, WHERE")
    s.add_argument("--notation", required=True, help="Notacao EARS completa")

    # actor
    s = sub.add_parser("actor", help="Adicionar ator ao dicionario")
    s.add_argument("--name", required=True, help="Nome do ator")
    s.add_argument("--type", required=True, help="Tipo (Humanos, Sistema, Externo)")
    s.add_argument("--responsibility", required=True, help="Responsabilidade")

    # uc
    s = sub.add_parser("uc", help="Adicionar caso de uso a matriz")
    s.add_argument("--id", required=True, help="ID do UC (ex: UC-01)")
    s.add_argument("--name", required=True, help="Nome do caso de uso")
    s.add_argument("--description", required=True, help="Descricao")

    # uc-diagram
    s = sub.add_parser("uc-diagram", help="Definir diagrama Mermaid de casos de uso")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--mermaid", help="Codigo Mermaid inline (\\n literal = quebra de linha; prefira --file)")
    g.add_argument("--file", help="Arquivo contendo o codigo Mermaid")

    # drilldown
    s = sub.add_parser("drilldown", help="Adicionar drill-down de caso de uso")
    s.add_argument("--uc-id", required=True, help="ID do UC (ex: UC-01)")
    s.add_argument("--name", default="", help="Nome (auto-detectado da matriz se omitido)")
    s.add_argument("--actor", required=True, help="Ator principal")
    s.add_argument("--preconditions", nargs="+", default=[], help="Pre-condicoes")
    s.add_argument("--main-flow", nargs="+", required=True, help="Passos do fluxo principal")
    s.add_argument("--postconditions", nargs="+", default=[], help="Pos-condicoes")

    # alt-flow
    s = sub.add_parser("alt-flow", help="Adicionar fluxo alternativo a um drill-down")
    s.add_argument("--uc-id", required=True, help="ID do UC pai (ex: UC-01)")
    s.add_argument("--id", required=True, help="ID do fluxo (ex: UC-01.FA1)")
    s.add_argument("--description", required=True, help="Descricao do fluxo alternativo")
    s.add_argument("--steps", nargs="+", required=True, help="Passos do fluxo")

    # entity
    s = sub.add_parser("entity", help="Adicionar entidade ao dicionario")
    s.add_argument("--name", required=True, help="Nome da entidade")
    s.add_argument("--type", required=True, help="Tipo (Domain, Actor, External, Value Object)")
    s.add_argument("--definition", required=True, help="Definicao")

    # invariant
    s = sub.add_parser("invariant", help="Adicionar invariante do sistema")
    s.add_argument("--text", required=True, help="Texto da invariante")

    # nfr
    s = sub.add_parser("nfr", help="Adicionar requisito nao-funcional")
    s.add_argument("--label", default="", help="Rotulo opcional (ex: Performance)")
    s.add_argument("--text", required=True, help="Texto do NFR")

    # show
    sub.add_parser("show", help="Exibir resumo do spec.json")

    # validate
    sub.add_parser("validate", help="Verificar completude do spec.json")

    # render
    s = sub.add_parser("render", help="Gerar spec.md e decision_manifest.json")
    s.add_argument("--force", action="store_true", help="Renderizar mesmo com erros de validacao")

    return p


_ACTIONS = {
    "init": cmd_init,
    "decision": cmd_decision,
    "ear": cmd_ear,
    "actor": cmd_actor,
    "uc": cmd_uc,
    "uc-diagram": cmd_uc_diagram,
    "drilldown": cmd_drilldown,
    "alt-flow": cmd_alt_flow,
    "entity": cmd_entity,
    "invariant": cmd_invariant,
    "nfr": cmd_nfr,
    "show": cmd_show,
    "validate": cmd_validate,
    "render": cmd_render,
}


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    spec_path = Path(args.spec_path)
    handler = _ACTIONS.get(args.action)
    if handler:
        handler(spec_path, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

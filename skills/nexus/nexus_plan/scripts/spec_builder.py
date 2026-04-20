#!/usr/bin/env python3
"""
Nexus Plan — Spec Builder

CLI tool that the AI agent calls to incrementally build spec.json.
Each subcommand adds structured data to the correct section.
The `render` subcommand converts spec.json → spec.md.

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
  render      Gerar spec.md

Usage:
  python spec_builder.py .nexus/spec.json init --plan "my-plan" --overview "..."
  python spec_builder.py .nexus/spec.json ear --id REQ-01 --type WHEN --notation "WHEN ..."
  python spec_builder.py .nexus/spec.json render
  python spec_builder.py .nexus/spec.json next-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


_VALID_DEP_ENVIRONMENTS = {"dev", "tst", "prd", "n/a", "na"}


def _normalize_dependency_envs(raw_envs: list[str] | None) -> list[str]:
    if not raw_envs:
        return []
    normalized: list[str] = []
    for env in raw_envs:
        token = (env or "").strip().lower()
        if token and token not in normalized:
            normalized.append(token)
    return normalized


def _normalize_spec(data: dict) -> dict:
    data.setdefault("nexus_version", "3.0")
    data.setdefault("plan_name", "")
    data.setdefault("title", "")
    data.setdefault("overview", "")
    data.setdefault("created_at", _utcnow())
    data.setdefault("updated_at", _utcnow())
    data.setdefault("decisions", [])
    data.setdefault("ears", [])
    data.setdefault("uc_diagram", "")
    data.setdefault("actors", [])
    data.setdefault("use_cases", [])
    data.setdefault("drilldowns", [])
    data.setdefault("entities", [])
    data.setdefault("invariants", [])
    data.setdefault("nfrs", [])

    overview_lock = data.get("overview_lock")
    if not isinstance(overview_lock, dict) or not overview_lock.get("value"):
        data["overview_lock"] = {
            "value": data.get("overview", ""),
            "created_at": data.get("created_at", _utcnow()),
            "mutability": "immutable",
        }
    else:
        overview_lock.setdefault("created_at", data.get("created_at", _utcnow()))
        overview_lock.setdefault("mutability", "immutable")

    architecture = data.get("architecture")
    if not isinstance(architecture, dict):
        architecture = {}
    architecture.setdefault("principles", [])
    architecture.setdefault("components", [])
    architecture.setdefault("folders", [])
    normalized_folders = []
    for folder in architecture.get("folders", []):
        if not isinstance(folder, dict):
            continue
        normalized_folders.append(
            {
                "path": folder.get("path", ""),
                "purpose": folder.get("purpose", ""),
                "owner": folder.get("owner", ""),
                "notes": folder.get("notes", ""),
            }
        )
    architecture["folders"] = normalized_folders
    data["architecture"] = architecture

    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict):
        dependencies = {}
    dependencies.setdefault("packages", [])
    dependencies.setdefault("services", [])

    normalized_packages = []
    for pkg in dependencies.get("packages", []):
        if not isinstance(pkg, dict):
            continue
        normalized_packages.append(
            {
                "name": pkg.get("name", ""),
                "kind": pkg.get("kind", ""),
                "version": pkg.get("version", ""),
                "install_cmd": pkg.get("install_cmd", ""),
                "environments": _normalize_dependency_envs(pkg.get("environments", [])),
            }
        )
    dependencies["packages"] = normalized_packages

    normalized_services = []
    for svc in dependencies.get("services", []):
        if not isinstance(svc, dict):
            continue
        normalized_services.append(
            {
                "name": svc.get("name", ""),
                "purpose": svc.get("purpose", ""),
                "start_cmd": svc.get("start_cmd", ""),
                "healthcheck": svc.get("healthcheck", ""),
                "environments": _normalize_dependency_envs(svc.get("environments", [])),
            }
        )
    dependencies["services"] = normalized_services
    data["dependencies"] = dependencies

    return data


def _load(path: Path) -> dict:
    if not path.exists():
        print(f"ERRO: spec.json nao encontrado: {path}", file=sys.stderr)
        print("   Execute 'init' primeiro.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_spec(json.load(f))


def _save(path: Path, data: dict) -> None:
    data = _normalize_spec(data)
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
        return _normalize_spec(json.load(f))


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

_VAGUE_TERMS = [
    "rapido",
    "rápido",
    "rapidamente",
    "lento",
    "lentamente",
    "eficiente",
    "eficientemente",
    "robusto",
    "robustamente",
    "seguro",
    "seguramente",
    "facil",
    "fácil",
    "facilmente",
    "simples",
    "simplesmente",
    "adequado",
    "adequadamente",
    "bom",
    "melhor",
    "escalavel",
    "escalável",
    "fast",
    "quickly",
    "slow",
    "slowly",
    "efficient",
    "efficiently",
    "robust",
    "robustly",
    "secure",
    "securely",
    "easy",
    "easily",
    "simple",
    "simply",
    "adequate",
    "adequately",
    "good",
    "better",
    "scalable",
]
_VAGUE_RE = re.compile(r"\b(" + "|".join(_VAGUE_TERMS) + r")\b", re.IGNORECASE)

_OVERVIEW_EXECUTION_TERMS = [
    "run atual",
    "nesta run",
    "desta run",
    "task",
    "tasks",
    "sprint",
    "execução desta entrega",
    "execucao desta entrega",
    "backlog",
]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_text.lower()


def _build_overview_execution_patterns() -> list[tuple[str, re.Pattern]]:
    patterns: list[tuple[str, re.Pattern]] = []
    for term in _OVERVIEW_EXECUTION_TERMS:
        normalized_term = _normalize_text(term)
        escaped = re.escape(normalized_term)
        compact = escaped.replace(r"\ ", r"\s+")
        regex = re.compile(rf"\b{compact}\b", re.IGNORECASE)
        patterns.append((term, regex))
    return patterns


_OVERVIEW_EXECUTION_PATTERNS = _build_overview_execution_patterns()


def _find_overview_execution_terms(overview: str) -> list[str]:
    normalized_overview = _normalize_text(overview)
    matched: list[str] = []
    for label, pattern in _OVERVIEW_EXECUTION_PATTERNS:
        if pattern.search(normalized_overview):
            matched.append(label)
    return matched


def _validate(data: dict) -> list[str]:
    """Return list of error messages. Empty list = valid."""
    errors: list[str] = []

    overview = (data.get("overview", "") or "").strip()
    if not overview:
        errors.append("Visao geral vazia")

    overview_lock = data.get("overview_lock", {})
    lock_value = (overview_lock.get("value", "") or "").strip()
    if not lock_value:
        errors.append(
            "overview_lock ausente/invalido — execute init para gerar baseline imutavel"
        )
    elif overview != lock_value:
        errors.append(
            "Visao geral e imutavel: alteracao detectada. "
            "Registre mudancas incrementais em nova run/backlog."
        )

    if overview_lock.get("mutability") != "immutable":
        errors.append("overview_lock.mutability deve ser 'immutable'")

    found_terms = _find_overview_execution_terms(overview)
    if found_terms:
        errors.append(
            "Visao geral deve ser sistemica (aplicacao como um todo), sem foco de execucao/run/task: "
            + ", ".join(found_terms)
        )

    if not data.get("decisions"):
        errors.append("Nenhuma decisao de projeto registrada")

    ucs = data.get("use_cases", [])
    if not ucs:
        errors.append("Nenhum caso de uso registrado")
    uc_ids = {uc["id"] for uc in ucs}

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

        uc_ref = (ear.get("uc_ref", "") or "").strip()
        if not uc_ref:
            errors.append(
                f"{ear.get('id', '?')}: EARS sem uc_ref (vinculo UC↔EARS obrigatorio)"
            )
        elif uc_ref not in uc_ids:
            errors.append(f"{ear['id']}: uc_ref '{uc_ref}' nao existe na matriz de UCs")

    actors = data.get("actors", [])
    if not actors:
        errors.append("Nenhum ator no Dicionario de Atores")

    if not data.get("uc_diagram"):
        errors.append("Diagrama Mermaid de Casos de Uso nao definido")

    entities = data.get("entities", [])
    if not entities:
        errors.append("Nenhuma entidade no Dicionario de Entidades")

    drilldowns = data.get("drilldowns", [])
    dd_ids = {dd["uc_id"] for dd in drilldowns}

    missing_dd = uc_ids - dd_ids
    if missing_dd:
        errors.append(f"UCs sem drill-down: {', '.join(sorted(missing_dd))}")

    orphan_dd = dd_ids - uc_ids
    if orphan_dd:
        errors.append(
            f"Drill-downs sem UC correspondente: {', '.join(sorted(orphan_dd))}"
        )

    architecture = data.get("architecture", {})
    principles = architecture.get("principles", [])
    components = architecture.get("components", [])
    folders = architecture.get("folders", [])
    if not principles and not components and not folders:
        errors.append(
            "Arquitetura vazia: informe ao menos um principio, componente ou pasta"
        )

    folder_paths: set[str] = set()
    duplicate_paths: set[str] = set()
    for folder in folders:
        path = (folder.get("path", "") or "").strip()
        if not path:
            errors.append("architecture.folders contem item sem path")
            continue
        if path in folder_paths:
            duplicate_paths.add(path)
        folder_paths.add(path)
    if duplicate_paths:
        errors.append(
            "architecture.folders.path deve ser unico. Duplicados: "
            + ", ".join(sorted(duplicate_paths))
        )

    dependencies = data.get("dependencies", {})
    packages = dependencies.get("packages", [])
    services = dependencies.get("services", [])
    if not packages and not services:
        errors.append("Dependencias vazias: registre ao menos um package ou service")

    env_coverage: set[str] = set()
    has_na_marker = False
    for kind, entries in (("package", packages), ("service", services)):
        for item in entries:
            name = (item.get("name", "") or "").strip()
            if not name:
                errors.append(f"dependencies.{kind}s contem item sem name")
            envs = _normalize_dependency_envs(item.get("environments", []))
            if not envs:
                errors.append(
                    f"dependencies.{kind}s '{name or '?'}' sem environments (dev/tst/prd ou N/A)"
                )
            for env in envs:
                if env in ("n/a", "na"):
                    has_na_marker = True
                    continue
                if env not in {"dev", "tst", "prd"}:
                    errors.append(
                        f"dependencies.{kind}s '{name or '?'}' possui environment invalido: {env}"
                    )
                    continue
                env_coverage.add(env)

    missing_envs = sorted({"dev", "tst", "prd"} - env_coverage)
    if missing_envs and not has_na_marker:
        errors.append(
            "Cobertura de ambientes incompleta nas dependencias. "
            f"Ausentes: {', '.join(missing_envs)} (use dev/tst/prd ou marcador N/A explicito)"
        )

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

    # 3. Especificação Funcional (UML)
    lines.append("## 3. Especificação Funcional (UML)")
    lines.append("")

    # 3.1 Diagrama
    lines.append("### 3.1 Diagrama de Casos de Uso (Mermaid)")
    lines.append("")
    uc_diagram = data.get("uc_diagram", "")
    if uc_diagram:
        lines.append("```mermaid")
        lines.append(uc_diagram)
        lines.append("```")
    lines.append("")

    # 3.2 Atores
    lines.append("### 3.2 Dicionário de Atores")
    lines.append("")
    actors = data.get("actors", [])
    if actors:
        lines.append("| Ator | Tipo | Responsabilidade |")
        lines.append("|------|------|------------------|")
        for a in actors:
            lines.append(f"| **{a['name']}** | {a['type']} | {a['responsibility']} |")
    lines.append("")

    # 3.3 Matriz de UCs
    lines.append("### 3.3 Matriz de Casos de Uso")
    lines.append("")
    ucs = data.get("use_cases", [])
    has_inferred = any(uc.get("origin", "new") == "inferred" for uc in ucs)
    if ucs:
        if has_inferred:
            lines.append("| ID | Nome | Descrição | Origin |")
            lines.append("|----|------|-----------|--------|")
            for uc in ucs:
                origin = uc.get("origin", "new")
                origin_label = "inferred" if origin == "inferred" else "new"
                lines.append(
                    f"| **{uc['id']}** | {uc['name']} | {uc['description']} | {origin_label} |"
                )
        else:
            lines.append("| ID | Nome | Descrição |")
            lines.append("|----|------|-----------|")
            for uc in ucs:
                lines.append(f"| **{uc['id']}** | {uc['name']} | {uc['description']} |")
    lines.append("")

    # 3.4 Requisitos EARS e associação UC↔EARS
    lines.append("### 3.4 Requisitos EARS e Associação UC↔EARS")
    lines.append("")
    ears = data.get("ears", [])
    if ears:
        lines.append("| ID | UC Ref | Tipo | Notação EARS |")
        lines.append("|----|--------|------|--------------|")
        for e in ears:
            lines.append(
                f"| **{e['id']}** | {e.get('uc_ref', '')} | {e['type']} | {e['notation']} |"
            )

        lines.append("")
        lines.append("#### Associação direta UC ↔ EARS")
        lines.append("")
        lines.append("| UC ID | UC Nome | EARS ID | Tipo | Notação |")
        lines.append("|-------|---------|---------|------|---------|")

        uc_by_id = {uc["id"]: uc for uc in ucs}

        def _ear_sort_key(item: dict) -> tuple[int, str]:
            match = re.search(r"\d+", item.get("id", ""))
            num = int(match.group()) if match else 10**9
            return (num, item.get("id", ""))

        for ear in sorted(ears, key=_ear_sort_key):
            uc_ref = ear.get("uc_ref", "")
            uc_name = uc_by_id.get(uc_ref, {}).get("name", "?")
            lines.append(
                f"| **{uc_ref}** | {uc_name} | **{ear['id']}** | {ear['type']} | {ear['notation']} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Drill-down de Casos de Uso
    lines.append("## 4. Drill-down de Casos de Uso")
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

    # 5. Arquitetura e Estrutura de Pastas
    lines.append("## 5. Arquitetura e Estrutura de Pastas")
    lines.append("")
    architecture = data.get("architecture", {})
    principles = architecture.get("principles", [])
    components = architecture.get("components", [])
    folders = architecture.get("folders", [])

    lines.append("### 5.1 Princípios Arquiteturais")
    lines.append("")
    if principles:
        for principle in principles:
            lines.append(f"- {principle}")
    else:
        lines.append("- (nenhum princípio informado)")
    lines.append("")

    lines.append("### 5.2 Componentes")
    lines.append("")
    if components:
        for component in components:
            lines.append(f"- {component}")
    else:
        lines.append("- (nenhum componente informado)")
    lines.append("")

    lines.append("### 5.3 Estrutura de Pastas")
    lines.append("")
    if folders:
        lines.append("| Path | Purpose | Owner | Notes |")
        lines.append("|------|---------|-------|-------|")
        for folder in folders:
            lines.append(
                f"| `{folder.get('path', '')}` | {folder.get('purpose', '')} | {folder.get('owner', '')} | {folder.get('notes', '')} |"
            )
    else:
        lines.append("- (nenhuma pasta estruturada informada)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 6. Dependências
    lines.append("## 6. Dependências")
    lines.append("")
    dependencies = data.get("dependencies", {})
    packages = dependencies.get("packages", [])
    services = dependencies.get("services", [])

    lines.append("### 6.1 Pacotes e Bibliotecas")
    lines.append("")
    if packages:
        lines.append("| Nome | Tipo | Versão | Install Cmd | Environments |")
        lines.append("|------|------|--------|-------------|--------------|")
        for pkg in packages:
            envs = ", ".join(pkg.get("environments", []))
            lines.append(
                f"| {pkg.get('name', '')} | {pkg.get('kind', '')} | {pkg.get('version', '')} | `{pkg.get('install_cmd', '')}` | {envs} |"
            )
    else:
        lines.append("- (nenhum pacote informado)")
    lines.append("")

    lines.append("### 6.2 Serviços e Ferramentas")
    lines.append("")
    if services:
        lines.append("| Nome | Propósito | Start Cmd | Healthcheck | Environments |")
        lines.append("|------|-----------|-----------|-------------|--------------|")
        for svc in services:
            envs = ", ".join(svc.get("environments", []))
            lines.append(
                f"| {svc.get('name', '')} | {svc.get('purpose', '')} | `{svc.get('start_cmd', '')}` | {svc.get('healthcheck', '')} | {envs} |"
            )
    else:
        lines.append("- (nenhum serviço informado)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 7. Dicionário de Entidades
    lines.append("## 7. Dicionário de Entidades")
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

    # 8. Invariantes do Sistema
    lines.append("## 8. Invariantes do Sistema")
    lines.append("")
    for inv in data.get("invariants", []):
        lines.append(f"- {inv}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 9. NFRs
    lines.append("## 9. NFRs (Non-Functional Requirements)")
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

    lines.append(
        "> Plano gerado via Nexus `/plan`. Execute `/dev` para iniciar a implementação."
    )
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
    now = _utcnow()
    data = {
        "nexus_version": "3.0",
        "plan_name": args.plan,
        "title": title,
        "overview": args.overview,
        "overview_lock": {
            "value": args.overview,
            "created_at": now,
            "mutability": "immutable",
        },
        "created_at": now,
        "updated_at": now,
        "decisions": [],
        "ears": [],
        "uc_diagram": "",
        "actors": [],
        "use_cases": [],
        "drilldowns": [],
        "architecture": {
            "principles": [],
            "components": [],
            "folders": [],
        },
        "dependencies": {
            "packages": [],
            "services": [],
        },
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
    print(
        f"OK {prefix}Decisao '{args.label}' {action} — total: {len(data['decisions'])}"
    )


def cmd_ear(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    uc_ids = {uc["id"] for uc in data.get("use_cases", [])}
    if args.uc_ref not in uc_ids:
        print(
            f"ERRO: uc_ref '{args.uc_ref}' nao encontrado na matriz de UCs.",
            file=sys.stderr,
        )
        print("   Cadastre o UC antes de vincular o EARS.", file=sys.stderr)
        sys.exit(1)

    entry = {
        "id": args.id,
        "uc_ref": args.uc_ref,
        "type": args.type,
        "notation": args.notation,
    }
    action = _upsert(data["ears"], entry, "id")
    _save(spec_path, data)
    print(
        f"OK {args.id} ({args.type}) {action} [uc_ref={args.uc_ref}] — total: {len(data['ears'])} EARS"
    )


def _upsert_architecture_folder(folders: list[dict], entry: dict) -> str:
    for i, folder in enumerate(folders):
        if folder.get("path") == entry["path"]:
            folders[i] = entry
            return "atualizada"
    folders.append(entry)
    return "adicionada"


def cmd_architecture_principle(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    architecture = data.setdefault(
        "architecture", {"principles": [], "components": [], "folders": []}
    )
    action = _dedup_append(architecture.setdefault("principles", []), args.text)
    _save(spec_path, data)
    print(
        f"OK Principio arquitetural {action} — total: {len(architecture['principles'])}"
    )


def cmd_architecture_component(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    architecture = data.setdefault(
        "architecture", {"principles": [], "components": [], "folders": []}
    )
    action = _dedup_append(architecture.setdefault("components", []), args.text)
    _save(spec_path, data)
    print(
        f"OK Componente arquitetural {action} — total: {len(architecture['components'])}"
    )


def cmd_architecture_folder(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    architecture = data.setdefault(
        "architecture", {"principles": [], "components": [], "folders": []}
    )
    folders = architecture.setdefault("folders", [])
    entry = {
        "path": args.path,
        "purpose": args.purpose,
        "owner": args.owner,
        "notes": args.notes,
    }
    action = _upsert_architecture_folder(folders, entry)
    _save(spec_path, data)
    print(f"OK Pasta arquitetural '{args.path}' {action} — total: {len(folders)}")


def _upsert_dependency(items: list[dict], entry: dict) -> str:
    for i, existing in enumerate(items):
        if existing.get("name") == entry["name"]:
            items[i] = entry
            return "atualizada"
    items.append(entry)
    return "adicionada"


def _validate_dependency_envs_or_exit(envs: list[str], field_name: str) -> list[str]:
    normalized = _normalize_dependency_envs(envs)
    invalid = [env for env in normalized if env not in _VALID_DEP_ENVIRONMENTS]
    if invalid:
        print(
            f"ERRO: {field_name} possui environments invalidos: {', '.join(invalid)}",
            file=sys.stderr,
        )
        print("   Valores aceitos: dev, tst, prd, N/A", file=sys.stderr)
        sys.exit(1)
    return normalized


def cmd_dependency_package(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    dependencies = data.setdefault("dependencies", {"packages": [], "services": []})
    envs = _validate_dependency_envs_or_exit(args.environments, "dependency-package")
    entry = {
        "name": args.name,
        "kind": args.kind,
        "version": args.version,
        "install_cmd": args.install_cmd,
        "environments": envs,
    }
    action = _upsert_dependency(dependencies.setdefault("packages", []), entry)
    _save(spec_path, data)
    print(
        f"OK Dependencia package '{args.name}' {action} — total: {len(dependencies['packages'])}"
    )


def cmd_dependency_service(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    dependencies = data.setdefault("dependencies", {"packages": [], "services": []})
    envs = _validate_dependency_envs_or_exit(args.environments, "dependency-service")
    entry = {
        "name": args.name,
        "purpose": args.purpose,
        "start_cmd": args.start_cmd,
        "healthcheck": args.healthcheck,
        "environments": envs,
    }
    action = _upsert_dependency(dependencies.setdefault("services", []), entry)
    _save(spec_path, data)
    print(
        f"OK Dependencia service '{args.name}' {action} — total: {len(dependencies['services'])}"
    )


def cmd_actor(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {
        "name": args.name,
        "type": args.type,
        "responsibility": args.responsibility,
    }
    action = _upsert(data["actors"], entry, "name")
    _save(spec_path, data)
    print(f"OK Ator '{args.name}' {action} — total: {len(data['actors'])}")


def cmd_uc(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    entry = {
        "id": args.id,
        "name": args.name,
        "description": args.description,
        "origin": args.origin,
    }
    action = _upsert(data["use_cases"], entry, "id")
    _save(spec_path, data)
    origin_tag = f" [origin={args.origin}]" if args.origin != "new" else ""
    print(
        f"OK {args.id} '{args.name}' {action}{origin_tag} — total: {len(data['use_cases'])} UCs"
    )


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
        print(
            f"ERRO: Drill-down {args.uc_id} nao encontrado. Crie-o primeiro com 'drilldown'.",
            file=sys.stderr,
        )
        sys.exit(1)

    flow_entry = {
        "id": args.id,
        "description": args.description,
        "steps": args.steps or [],
    }
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


def cmd_show(spec_path: Path, args: argparse.Namespace) -> None:
    data = _load(spec_path)
    decisions = len(data.get("decisions", []))
    ears = len(data.get("ears", []))
    actors = len(data.get("actors", []))
    ucs = len(data.get("use_cases", []))
    dds = len(data.get("drilldowns", []))
    architecture = data.get("architecture", {})
    principles = len(architecture.get("principles", []))
    components = len(architecture.get("components", []))
    folders = len(architecture.get("folders", []))
    dependencies = data.get("dependencies", {})
    packages = len(dependencies.get("packages", []))
    services = len(dependencies.get("services", []))
    entities = len(data.get("entities", []))
    invariants = len(data.get("invariants", []))
    nfrs = len(data.get("nfrs", []))

    print(f"SPEC: {data['plan_name']} ({data.get('title', '')})")
    print(f"   Decisoes: {decisions} | EARS: {ears} | Atores: {actors} | UCs: {ucs}")
    print(
        f"   Drill-downs: {dds} | Entidades: {entities} | Invariantes: {invariants} | NFRs: {nfrs}"
    )
    print(
        f"   Arquitetura: {principles} principios | {components} componentes | {folders} pastas"
    )
    print(f"   Dependencias: {packages} packages | {services} services")
    has_diagram = "sim" if data.get("uc_diagram") else "nao"
    print(f"   Diagrama UC: {has_diagram}")

    overview_lock = data.get("overview_lock", {})
    lock_state = overview_lock.get("mutability", "?")
    print(f"   Overview lock: {lock_state}")

    uc_ids = {uc["id"] for uc in data.get("use_cases", [])}
    dd_ids = {dd["uc_id"] for dd in data.get("drilldowns", [])}
    missing = uc_ids - dd_ids
    if missing:
        print(f"   AVISO — UCs sem drill-down: {', '.join(sorted(missing))}")
    elif ucs > 0 and dds == ucs:
        print("   Drill-downs: 1:1 com UCs (OK)")

    orphan_ears = [
        e["id"]
        for e in data.get("ears", [])
        if (e.get("uc_ref") or "").strip() not in uc_ids
    ]
    if orphan_ears:
        print(f"   AVISO — EARS sem UC valido: {', '.join(sorted(orphan_ears))}")

    if getattr(args, "detail", False):
        print("")
        print("DETAIL:")

        if data.get("decisions"):
            labels = [d["label"] for d in data["decisions"]]
            print(f"   Decisoes: {', '.join(labels)}")

        ear_list = data.get("ears", [])
        if ear_list:
            ids = [f"{e['id']}->{e.get('uc_ref', '?')}" for e in ear_list]
            print(f"   EARS IDs: {', '.join(ids)}")
            max_num = max(
                (
                    int(re.search(r"\d+", e["id"]).group())
                    for e in ear_list
                    if re.search(r"\d+", e["id"])
                ),
                default=0,
            )
            print(f"   Proximo EARS: REQ-{max_num + 1:02d}")

        uc_list = data.get("use_cases", [])
        if uc_list:
            new_count = sum(1 for uc in uc_list if uc.get("origin", "new") == "new")
            inferred_count = len(uc_list) - new_count
            for uc in uc_list:
                origin = uc.get("origin", "new")
                origin_tag = " [inferred]" if origin == "inferred" else ""
                print(f"   UC {uc['id']}: {uc['name']}{origin_tag}")
            max_num = max(
                (
                    int(re.search(r"\d+", uc["id"]).group())
                    for uc in uc_list
                    if re.search(r"\d+", uc["id"])
                ),
                default=0,
            )
            print(f"   Proximo UC: UC-{max_num + 1:02d}")
            if inferred_count > 0:
                print(f"   Origin: {new_count} new, {inferred_count} inferred")

        actor_list = data.get("actors", [])
        if actor_list:
            print(f"   Atores: {', '.join(a['name'] for a in actor_list)}")

        folders_list = architecture.get("folders", [])
        if folders_list:
            folder_paths = [folder.get("path", "") for folder in folders_list]
            print(f"   Pastas: {', '.join(folder_paths)}")

        package_list = dependencies.get("packages", [])
        if package_list:
            package_names = [pkg.get("name", "") for pkg in package_list]
            print(f"   Packages: {', '.join(package_names)}")

        service_list = dependencies.get("services", [])
        if service_list:
            service_names = [svc.get("name", "") for svc in service_list]
            print(f"   Services: {', '.join(service_names)}")

        entity_list = data.get("entities", [])
        if entity_list:
            print(f"   Entidades: {', '.join(e['name'] for e in entity_list)}")

        inv_list = data.get("invariants", [])
        if inv_list:
            print(f"   Invariantes: {len(inv_list)}")

        print(f"   Overview: {(data.get('overview', '') or '')[:120]}...")


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


def _run_is_fully_closed(run_dir: Path) -> bool:
    """A run is closed only when backlog is completed AND review is APPROVED."""
    review_path = run_dir / "review.json"
    if not review_path.exists():
        return False
    with open(review_path, "r", encoding="utf-8") as f:
        review = json.load(f)
    return review.get("verdict") == "APPROVED"


def cmd_next_run(spec_path: Path, _args: argparse.Namespace) -> None:
    """Resolve the next available run folder, or report the active one."""
    runs_dir = spec_path.parent / "runs"

    if not runs_dir.exists():
        next_path = runs_dir / "001"
        print(f"NEXT_RUN: {next_path}")
        return

    existing = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )

    if not existing:
        next_path = runs_dir / "001"
        print(f"NEXT_RUN: {next_path}")
        return

    for run_dir in reversed(existing):
        bl_path = run_dir / "backlog.json"
        if not bl_path.exists():
            continue

        with open(bl_path, "r", encoding="utf-8") as f:
            backlog = json.load(f)
        status = backlog.get("status", "building")
        ex = backlog.get("execution", {})
        total = ex.get("total_tasks", 0)
        completed = ex.get("completed_tasks", 0)
        pct = int((completed / total) * 100) if total > 0 else 0

        if status == "completed" and _run_is_fully_closed(run_dir):
            next_num = int(run_dir.name) + 1
            next_path = runs_dir / f"{next_num:03d}"
            print(f"NEXT_RUN: {next_path}")
            print(f"   Ultima run: {run_dir.name} (completed + reviewed)")
            return

        phase = "dev" if status != "completed" else "review"
        print(f"ACTIVE_RUN: {run_dir}", file=sys.stderr)
        print(
            f"   Fase pendente: {phase} | Status: {status} | Progresso: {completed}/{total} ({pct}%)",
            file=sys.stderr,
        )
        sys.exit(1)

    max_num = int(existing[-1].name)
    next_path = runs_dir / f"{max_num + 1:03d}"
    print(f"NEXT_RUN: {next_path}")
    print(f"   Nenhuma run com backlog encontrada")


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

    ears = len(data.get("ears", []))
    ucs = len(data.get("use_cases", []))
    entities = len(data.get("entities", []))
    print(f"OK spec.md renderizado: {md_path}")
    print(f"   {ears} EARS | {ucs} UCs | {entities} entidades")
    if errors:
        print(f"AVISO: Renderizado com {len(errors)} problema(s) (--force)")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _ear_type(value: str) -> str:
    upper = value.upper()
    if upper not in ("WHEN", "WHILE", "IF", "WHERE"):
        raise argparse.ArgumentTypeError(
            f"Tipo EARS invalido: {value}. Use WHEN/WHILE/IF/WHERE."
        )
    return upper


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spec_builder",
        description="Nexus Plan — Constroi spec.json incrementalmente e renderiza spec.md.",
    )
    p.add_argument(
        "spec_path", help="Caminho do spec.json (ex: .nexus/meu-plano/spec.json)"
    )
    sub = p.add_subparsers(dest="action", required=True)

    # init
    s = sub.add_parser("init", help="Criar novo spec.json")
    s.add_argument(
        "--plan", required=True, help="Nome do plano (slug, ex: hellfire-spark)"
    )
    s.add_argument("--title", help="Titulo de exibicao (default: plan em maiusculas)")
    s.add_argument(
        "--overview", required=True, help="Visao geral sistemica e imutavel do projeto"
    )

    # decision
    s = sub.add_parser("decision", help="Adicionar decisao de projeto")
    s.add_argument("--label", required=True, help="Rotulo (ex: Destruicao)")
    s.add_argument(
        "--chosen", required=True, help="Opcao escolhida (ex: Permanente (A))"
    )
    s.add_argument("--rationale", required=True, help="Justificativa")
    s.add_argument(
        "--auto-assumed", action="store_true", help="Marcar como decisao auto-assumida"
    )

    # ear
    s = sub.add_parser("ear", help="Adicionar requisito EARS")
    s.add_argument("--id", required=True, help="ID do requisito (ex: REQ-01)")
    s.add_argument("--uc-ref", required=True, help="ID do UC vinculado (ex: UC-01)")
    s.add_argument(
        "--type", required=True, type=_ear_type, help="Tipo: WHEN, WHILE, IF, WHERE"
    )
    s.add_argument("--notation", required=True, help="Notacao EARS completa")

    # architecture-principle
    s = sub.add_parser(
        "architecture-principle", help="Adicionar principio arquitetural"
    )
    s.add_argument("--text", required=True, help="Principio arquitetural")

    # architecture-component
    s = sub.add_parser(
        "architecture-component", help="Adicionar componente arquitetural"
    )
    s.add_argument("--text", required=True, help="Componente arquitetural")

    # architecture-folder
    s = sub.add_parser("architecture-folder", help="Adicionar pasta da arquitetura")
    s.add_argument("--path", required=True, help="Path da pasta (unico)")
    s.add_argument("--purpose", required=True, help="Proposito da pasta")
    s.add_argument("--owner", default="", help="Dono/responsavel")
    s.add_argument("--notes", default="", help="Observacoes")

    # dependency-package
    s = sub.add_parser("dependency-package", help="Adicionar dependencia de pacote/lib")
    s.add_argument("--name", required=True, help="Nome do pacote")
    s.add_argument("--kind", required=True, help="Tipo (lib, framework, cli, sdk)")
    s.add_argument("--version", required=True, help="Versao")
    s.add_argument("--install-cmd", required=True, help="Comando de instalacao")
    s.add_argument(
        "--environments",
        nargs="+",
        required=True,
        help="Ambientes cobertos (dev tst prd ou N/A)",
    )

    # dependency-service
    s = sub.add_parser(
        "dependency-service", help="Adicionar dependencia de servico/ferramenta"
    )
    s.add_argument("--name", required=True, help="Nome do servico")
    s.add_argument("--purpose", required=True, help="Proposito")
    s.add_argument("--start-cmd", required=True, help="Comando de inicializacao")
    s.add_argument(
        "--healthcheck", default="", help="Healthcheck/criterio de prontidao"
    )
    s.add_argument(
        "--environments",
        nargs="+",
        required=True,
        help="Ambientes cobertos (dev tst prd ou N/A)",
    )

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
    s.add_argument(
        "--origin",
        choices=["new", "inferred"],
        default="new",
        help="Origem do UC: 'new' (feature nova) ou 'inferred' (inferido de codigo existente)",
    )

    # uc-diagram
    s = sub.add_parser("uc-diagram", help="Definir diagrama Mermaid de casos de uso")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--mermaid",
        help="Codigo Mermaid inline (\\n literal = quebra de linha; prefira --file)",
    )
    g.add_argument("--file", help="Arquivo contendo o codigo Mermaid")

    # drilldown
    s = sub.add_parser("drilldown", help="Adicionar drill-down de caso de uso")
    s.add_argument("--uc-id", required=True, help="ID do UC (ex: UC-01)")
    s.add_argument(
        "--name", default="", help="Nome (auto-detectado da matriz se omitido)"
    )
    s.add_argument("--actor", required=True, help="Ator principal")
    s.add_argument("--preconditions", nargs="+", default=[], help="Pre-condicoes")
    s.add_argument(
        "--main-flow", nargs="+", required=True, help="Passos do fluxo principal"
    )
    s.add_argument("--postconditions", nargs="+", default=[], help="Pos-condicoes")

    # alt-flow
    s = sub.add_parser("alt-flow", help="Adicionar fluxo alternativo a um drill-down")
    s.add_argument("--uc-id", required=True, help="ID do UC pai (ex: UC-01)")
    s.add_argument("--id", required=True, help="ID do fluxo (ex: UC-01.FA1)")
    s.add_argument(
        "--description", required=True, help="Descricao do fluxo alternativo"
    )
    s.add_argument("--steps", nargs="+", required=True, help="Passos do fluxo")

    # entity
    s = sub.add_parser("entity", help="Adicionar entidade ao dicionario")
    s.add_argument("--name", required=True, help="Nome da entidade")
    s.add_argument(
        "--type", required=True, help="Tipo (Domain, Actor, External, Value Object)"
    )
    s.add_argument("--definition", required=True, help="Definicao")

    # invariant
    s = sub.add_parser("invariant", help="Adicionar invariante do sistema")
    s.add_argument("--text", required=True, help="Texto da invariante")

    # nfr
    s = sub.add_parser("nfr", help="Adicionar requisito nao-funcional")
    s.add_argument("--label", default="", help="Rotulo opcional (ex: Performance)")
    s.add_argument("--text", required=True, help="Texto do NFR")

    # show
    s = sub.add_parser("show", help="Exibir resumo do spec.json")
    s.add_argument(
        "--detail",
        action="store_true",
        help="Listar IDs existentes e proximos IDs disponiveis",
    )

    # validate
    sub.add_parser("validate", help="Verificar completude do spec.json")

    # render
    s = sub.add_parser("render", help="Gerar spec.md")
    s.add_argument(
        "--force", action="store_true", help="Renderizar mesmo com erros de validacao"
    )

    # next-run
    sub.add_parser(
        "next-run", help="Resolver proxima run disponivel ou reportar run ativa"
    )

    return p


_ACTIONS = {
    "init": cmd_init,
    "decision": cmd_decision,
    "ear": cmd_ear,
    "architecture-principle": cmd_architecture_principle,
    "architecture-component": cmd_architecture_component,
    "architecture-folder": cmd_architecture_folder,
    "dependency-package": cmd_dependency_package,
    "dependency-service": cmd_dependency_service,
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
    "next-run": cmd_next_run,
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


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in _ACTIONS:
        nexus = _find_nexus_root()
        if nexus is None and sys.argv[1] == "init":
            nexus = Path.cwd() / ".nexus"
        if nexus is None:
            print(
                "ERRO: .nexus/ nao encontrado. Execute a partir do diretorio do projeto.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.argv.insert(1, str(nexus / "spec.json"))

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

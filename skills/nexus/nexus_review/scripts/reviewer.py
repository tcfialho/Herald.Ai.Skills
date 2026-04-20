#!/usr/bin/env python3
"""
Nexus Review — Reviewer

CLI tool that the AI agent calls to homologate a completed /dev execution.
The AI executes tests, build, and evaluates compliance. This script REGISTERS
the results and computes a deterministic verdict from gates.

Subcommands:
  CHECK:
    check-readiness    Verify backlog is 100% and evidence files exist

  REPORT (AI executes, script registers):
    report-regression  Register regression test results (all tests)
    report-build       Register build result
    report-compliance  Register EARS compliance per requirement

  CERTIFY:
    certify            Compute verdict from all gates, generate certificate

  DISPLAY:
    show               Display current review state

Usage:
  python reviewer.py .nexus/runs/001/review.json check-readiness --backlog .nexus/runs/001/backlog.json
  python reviewer.py .nexus/runs/001/review.json report-regression --passed 25 --failed 0
  python reviewer.py .nexus/runs/001/review.json report-build --passed --warnings 0
  python reviewer.py .nexus/runs/001/review.json report-compliance --ear REQ-01 --status compliant --evidence "src/task.py:42"
  python reviewer.py .nexus/runs/001/review.json certify
  python reviewer.py .nexus/runs/001/review.json show
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
        print(f"ERRO: review.json nao encontrado: {path}", file=sys.stderr)
        print("   Execute 'check-readiness' primeiro.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_review(json.load(f))


def _save(path: Path, data: dict) -> None:
    data = _normalize_review(data)
    data["updated_at"] = _utcnow()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _normalize_review(data: dict) -> dict:
    data.setdefault("nexus_version", "3.0")
    data.setdefault("plan_name", "")
    data.setdefault("backlog_ref", "")
    data.setdefault("created_at", _utcnow())
    data.setdefault("updated_at", _utcnow())
    data.setdefault("readiness", {})
    data.setdefault("regression", {})
    data.setdefault("build", {})
    data.setdefault("compliance", [])
    data.setdefault("use_case_validation", [])
    data.setdefault("use_cases_expected", [])
    data.setdefault("uc_ears_expected", {})
    data.setdefault("ears_expected", [])
    data.setdefault("gates", {})
    data.setdefault("verdict", None)
    data.setdefault("certified_at", None)
    return data


def _expected_use_case_flows(backlog: dict) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    expected: list[dict] = []
    for story in backlog.get("stories", []):
        uc_id = story.get("uc_ref", "")
        flow_id = story.get("fluxo_id", "")
        if not uc_id or not flow_id:
            continue
        key = (uc_id, flow_id)
        if key in seen:
            continue
        expected.append(
            {
                "uc_id": uc_id,
                "flow_id": flow_id,
                "story_id": story.get("id", ""),
            }
        )
        seen.add(key)

    expected.sort(key=lambda item: (item.get("uc_id", ""), item.get("flow_id", "")))
    return expected


def _integrated_ears_coverage(
    compliance: list[dict],
    use_case_validation: list[dict],
    ears_expected: list[str],
) -> dict:
    expected_set = set(ears_expected)
    covered_explicit = {
        entry.get("ear_id", "")
        for entry in compliance
        if entry.get("status") == "compliant" and entry.get("ear_id")
    }
    covered_by_uc = {
        ear_id
        for item in use_case_validation
        if item.get("status") == "validated"
        for ear_id in item.get("ears", [])
        if ear_id
    }

    covered_explicit &= expected_set
    covered_by_uc &= expected_set
    covered_all = covered_by_uc | covered_explicit
    return {
        "expected_set": expected_set,
        "covered_by_uc": covered_by_uc,
        "covered_explicit": covered_explicit,
        "covered_all": covered_all,
        "missing_ears": expected_set - covered_all,
    }


# ------------------------------------------------------------------
# CHECK commands
# ------------------------------------------------------------------


def _check_pipeline_order(bl_path: Path) -> dict:
    """Validate that /plan and /dev were completed before /review can start."""
    if not bl_path.exists():
        print("ERRO: backlog.json nao encontrado.", file=sys.stderr)
        print(f"   Caminho: {bl_path}", file=sys.stderr)
        print("   O /dev precisa ser executado antes de /review.", file=sys.stderr)
        print("   Ordem correta: /plan -> /dev -> /review", file=sys.stderr)
        sys.exit(1)

    with open(bl_path, "r", encoding="utf-8") as f:
        backlog = json.load(f)

    spec_path_str = backlog.get("spec_path", "")
    if spec_path_str:
        spec_path = Path(spec_path_str)
        if not spec_path.is_absolute():
            spec_path = (bl_path.parent / spec_path).resolve()
        if not spec_path.exists():
            print(
                f"AVISO: spec.json referenciado pelo backlog nao encontrado: {spec_path_str}",
                file=sys.stderr,
            )
            print("   O pipeline pode estar inconsistente.", file=sys.stderr)

    stories = backlog.get("stories", [])
    if not stories:
        print("ERRO: backlog.json nao contem historias.", file=sys.stderr)
        print(
            "   O /dev precisa gerar historias e tasks antes de /review.",
            file=sys.stderr,
        )
        print("   Execute /dev para popular o backlog.", file=sys.stderr)
        sys.exit(1)

    all_tasks = []
    for story in stories:
        all_tasks.extend(story.get("tasks", []))
    if not all_tasks:
        print("ERRO: backlog.json nao contem tasks.", file=sys.stderr)
        print("   O /dev precisa gerar tasks antes de /review.", file=sys.stderr)
        print("   Execute /dev para popular o backlog.", file=sys.stderr)
        sys.exit(1)

    return backlog


def cmd_check_readiness(rpath: Path, args: argparse.Namespace) -> None:
    if args.backlog:
        bl_path = Path(args.backlog)
    else:
        bl_path = rpath.parent / "backlog.json"
    backlog = _check_pipeline_order(bl_path)

    ex = backlog.get("execution", {})
    total = ex.get("total_tasks", 0)
    completed = ex.get("completed_tasks", 0)
    plan_ref = backlog.get("plan_ref", "?")

    all_tasks_done = total > 0 and completed == total

    evidence_dir = bl_path.parent / "evidence"
    missing_evidence = []
    for story in backlog.get("stories", []):
        for task in story.get("tasks", []):
            if task["status"] == "completed":
                ev_file = evidence_dir / f"{task['id']}.json"
                if not ev_file.exists():
                    missing_evidence.append(task["id"])

    context = backlog.get("context", {})
    ears_index = context.get("ears_index", {})
    ears_ids = sorted(list(ears_index.keys()))

    uc_ears_raw = context.get("uc_ears_index", {})
    uc_ears_expected: dict[str, list[str]] = {}
    for uc_id, entries in uc_ears_raw.items():
        uc_ears_expected[uc_id] = sorted(
            [entry.get("id", "") for entry in entries if entry.get("id")]
        )

    use_cases_expected = _expected_use_case_flows(backlog)

    readiness = {
        "tasks_completed": completed,
        "tasks_total": total,
        "all_done": all_tasks_done,
        "missing_evidence": missing_evidence,
        "evidence_ok": len(missing_evidence) == 0,
    }

    if rpath.exists():
        data = _load(rpath)
    else:
        data = {
            "nexus_version": "3.0",
            "plan_name": plan_ref,
            "backlog_ref": str(bl_path),
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
            "readiness": {},
            "regression": {},
            "build": {},
            "compliance": [],
            "use_case_validation": [],
            "use_cases_expected": [],
            "uc_ears_expected": {},
            "ears_expected": ears_ids,
            "gates": {},
            "verdict": None,
            "certified_at": None,
        }

    data["readiness"] = readiness
    data["backlog_ref"] = str(bl_path)
    data["ears_expected"] = ears_ids
    data["uc_ears_expected"] = uc_ears_expected
    data["use_cases_expected"] = use_cases_expected
    _save(rpath, data)

    if not all_tasks_done:
        pending = total - completed
        print(f"NAO PRONTO: {pending} task(s) pendente(s) ({completed}/{total})")
        print("   Termine o /dev antes de executar /review.")
        sys.exit(1)

    if missing_evidence:
        print(f"ERRO: {len(missing_evidence)} evidence file(s) faltando:")
        for tid in missing_evidence[:10]:
            print(f"   - {tid}")
        print("   Re-execute 'backlog.py complete' para as tasks sem evidence.")
        sys.exit(1)

    print(f"OK Backlog pronto para review: {plan_ref}")
    print(
        f"   Tasks: {completed}/{total} | UCs/Fluxos esperados: {len(use_cases_expected)} | EARS esperados: {len(ears_ids)}"
    )


# ------------------------------------------------------------------
# REPORT commands
# ------------------------------------------------------------------


def cmd_report_regression(rpath: Path, args: argparse.Namespace) -> None:
    data = _load(rpath)
    data["regression"] = {
        "passed": args.passed,
        "failed": args.failed,
        "timestamp": _utcnow(),
    }
    _save(rpath, data)

    total = args.passed + args.failed
    if args.failed > 0:
        print(f"REGRESSION: {args.failed} teste(s) falhando de {total}")
    else:
        print(f"OK Regression: {args.passed} teste(s) passando, 0 falhando")


def cmd_report_build(rpath: Path, args: argparse.Namespace) -> None:
    data = _load(rpath)
    data["build"] = {
        "passed": args.passed,
        "warnings": args.warnings,
        "timestamp": _utcnow(),
    }
    _save(rpath, data)

    if args.passed:
        warn_note = f" ({args.warnings} warnings)" if args.warnings > 0 else ""
        print(f"OK Build passed{warn_note}")
    else:
        print(f"BUILD FALHOU")


def cmd_report_compliance(rpath: Path, args: argparse.Namespace) -> None:
    data = _load(rpath)
    compliance = data.get("compliance", [])

    existing_idx = None
    for i, entry in enumerate(compliance):
        if entry["ear_id"] == args.ear:
            existing_idx = i
            break

    record = {
        "ear_id": args.ear,
        "status": args.status,
        "evidence": args.evidence or "",
    }

    if existing_idx is not None:
        compliance[existing_idx] = record
    else:
        compliance.append(record)

    data["compliance"] = compliance
    _save(rpath, data)

    expected = data.get("ears_expected", [])
    reported = len(compliance)
    total = len(expected)
    print(f"OK {args.ear}: {args.status}")
    print(f"   Compliance: {reported}/{total} EARS reportados")


def cmd_report_usecase(rpath: Path, args: argparse.Namespace) -> None:
    data = _load(rpath)
    use_case_validation = data.get("use_case_validation", [])

    expected = {
        (item.get("uc_id", ""), item.get("flow_id", ""))
        for item in data.get("use_cases_expected", [])
    }
    if expected and (args.uc, args.flow) not in expected:
        print(
            f"ERRO: fluxo {args.uc}/{args.flow} nao esta na lista esperada do backlog.",
            file=sys.stderr,
        )
        sys.exit(1)

    existing_idx = None
    for i, entry in enumerate(use_case_validation):
        if entry.get("uc_id") == args.uc and entry.get("flow_id") == args.flow:
            existing_idx = i
            break

    record = {
        "uc_id": args.uc,
        "flow_id": args.flow,
        "status": args.status,
        "ears": sorted(args.ears or []),
        "evidence": args.evidence or "",
        "timestamp": _utcnow(),
    }

    if existing_idx is not None:
        use_case_validation[existing_idx] = record
    else:
        use_case_validation.append(record)

    data["use_case_validation"] = use_case_validation
    _save(rpath, data)

    validated_count = sum(
        1 for item in use_case_validation if item.get("status") == "validated"
    )
    expected_count = len(data.get("use_cases_expected", []))
    print(f"OK {args.uc}/{args.flow}: {args.status}")
    print(f"   UseCase Validation: {validated_count}/{expected_count} fluxos validados")


# ------------------------------------------------------------------
# CERTIFY
# ------------------------------------------------------------------


def cmd_certify(rpath: Path, _args: argparse.Namespace) -> None:
    data = _load(rpath)

    readiness = data.get("readiness", {})
    regression = data.get("regression", {})
    build = data.get("build", {})
    compliance = data.get("compliance", [])
    ears_expected = data.get("ears_expected", [])
    use_case_validation = data.get("use_case_validation", [])
    use_cases_expected = data.get("use_cases_expected", [])
    uc_ears_expected = data.get("uc_ears_expected", {})

    gates = {}
    gate_details = {}

    # GATE: Tasks complete
    gates["tasks_complete"] = readiness.get("all_done", False)
    if not gates["tasks_complete"]:
        done = readiness.get("tasks_completed", 0)
        total = readiness.get("tasks_total", 0)
        gate_details["tasks_complete"] = f"Tasks incompletas: {done}/{total}"

    # GATE: Evidence files
    gates["evidence_ok"] = readiness.get("evidence_ok", False)
    if not gates["evidence_ok"]:
        missing = readiness.get("missing_evidence", [])
        gate_details["evidence_ok"] = f"Evidence faltando: {', '.join(missing[:5])}"

    # GATE: Build
    gates["build_passed"] = build.get("passed", False)
    if not gates["build_passed"]:
        gate_details["build_passed"] = "Build falhou ou nao reportado"

    # GATE: Regression
    gates["regression_passed"] = (
        regression.get("failed", -1) == 0 and regression.get("passed", 0) > 0
    )
    if not gates["regression_passed"]:
        failed = regression.get("failed", "?")
        if failed == "?":
            gate_details["regression_passed"] = "Regression nao reportada"
        else:
            gate_details["regression_passed"] = f"{failed} teste(s) falhando"

    # GATE: Use case validation (primary)
    validated_flow_keys = {
        (item.get("uc_id", ""), item.get("flow_id", ""))
        for item in use_case_validation
        if item.get("status") == "validated"
    }
    expected_flow_keys = {
        (item.get("uc_id", ""), item.get("flow_id", "")) for item in use_cases_expected
    }
    missing_flows = expected_flow_keys - validated_flow_keys
    gates["use_cases_validated"] = (
        len(missing_flows) == 0 and len(expected_flow_keys) > 0
    )
    if not gates["use_cases_validated"]:
        if not expected_flow_keys:
            gate_details["use_cases_validated"] = (
                "Nenhum UC/fluxo esperado (check-readiness nao executado?)"
            )
        else:
            missing_text = ", ".join(
                sorted(f"{uc}/{flow}" for uc, flow in missing_flows)
            )
            gate_details["use_cases_validated"] = (
                f"UC/fluxos nao validados: {missing_text}"
            )

    # GATE: EARS compliance (derived from UC validation + explicit compliance)
    coverage = _integrated_ears_coverage(compliance, use_case_validation, ears_expected)
    expected_set = coverage["expected_set"]
    missing_ears = coverage["missing_ears"]

    mismatched_mapping = []
    expected_mapping = {
        uc_id: set(ear_ids) for uc_id, ear_ids in uc_ears_expected.items()
    }
    for item in use_case_validation:
        if item.get("status") != "validated":
            continue
        uc_id = item.get("uc_id", "")
        reported_ears = set(item.get("ears", []))
        allowed_ears = expected_mapping.get(uc_id, set())
        if allowed_ears:
            invalid_for_uc = sorted(reported_ears - allowed_ears)
            if invalid_for_uc:
                mismatched_mapping.append(
                    f"{uc_id}: {', '.join(invalid_for_uc)} fora do mapa UC↔EARS"
                )

    gates["ears_covered"] = (
        len(expected_set) > 0
        and len(missing_ears) == 0
        and len(mismatched_mapping) == 0
    )
    if not gates["ears_covered"]:
        detail_parts = []
        if not expected_set:
            detail_parts.append("Nenhum EARS esperado (check-readiness nao executado?)")
        if missing_ears:
            detail_parts.append(
                "EARS sem cobertura por UC/compliance: "
                + ", ".join(sorted(missing_ears))
            )
        if mismatched_mapping:
            detail_parts.append("; ".join(mismatched_mapping))
        gate_details["ears_covered"] = " | ".join(detail_parts)

    all_passed = all(gates.values())
    verdict = "APPROVED" if all_passed else "NEEDS_REVISION"

    data["gates"] = gates
    data["verdict"] = verdict
    if verdict == "APPROVED":
        data["certified_at"] = _utcnow()
        _generate_certificate(rpath, data)

    _save(rpath, data)

    gates_passed = sum(1 for v in gates.values() if v)
    gates_total = len(gates)

    if verdict == "APPROVED":
        print(f"APPROVED ({gates_passed}/{gates_total} gates)")
        print(f"   Certificado: {rpath.parent / 'review.md'}")
    else:
        print(f"NEEDS_REVISION ({gates_passed}/{gates_total} gates)")
        for gate_id, passed in gates.items():
            if passed:
                print(f"   [PASS] {gate_id}")
            else:
                detail = gate_details.get(gate_id, "")
                print(f"   [FAIL] {gate_id} — {detail}")


def _generate_certificate(rpath: Path, data: dict) -> Path:
    plan = data.get("plan_name", "?")
    regression = data.get("regression", {})
    build = data.get("build", {})
    compliance = data.get("compliance", [])
    ears_expected = data.get("ears_expected", [])
    use_case_validation = data.get("use_case_validation", [])
    use_cases_expected = data.get("use_cases_expected", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total_tests = regression.get("passed", 0) + regression.get("failed", 0)
    warnings = build.get("warnings", 0)
    validated_flows = sum(
        1 for item in use_case_validation if item.get("status") == "validated"
    )

    coverage = _integrated_ears_coverage(compliance, use_case_validation, ears_expected)
    integrated_covered_count = len(coverage["covered_all"])
    legacy_compliant_count = len(coverage["covered_explicit"])

    lines = [
        "# CERTIFICADO NEXUS DE CONFORMIDADE",
        "",
        "| | |",
        "|---|---|",
        f"| **Plano:** | {plan} |",
        "| **Veredicto:** | **APPROVED** |",
        f"| **Data/Hora (UTC):** | {now} |",
        "",
        "## Evidencias de Homologacao",
        "",
        f"- **Build**: PASS" + (f" ({warnings} warnings)" if warnings else ""),
        f"- **Regression Tests**: {regression.get('passed', 0)}/{total_tests} PASSED",
        f"- **Use Cases/Flows**: {validated_flows}/{len(use_cases_expected)} validated",
        f"- **EARS Coverage (integrated)**: {integrated_covered_count}/{len(ears_expected)} covered",
        f"- **Legacy compliance reports**: {legacy_compliant_count}/{len(ears_expected)} compliant",
        "",
        "## Gates",
        "",
        "| Gate | Status |",
        "|------|--------|",
    ]

    gates = data.get("gates", {})
    gate_labels = {
        "tasks_complete": "Tasks Completas",
        "evidence_ok": "Evidence Files",
        "build_passed": "Build",
        "regression_passed": "Regression Tests",
        "use_cases_validated": "Use Cases/Flows",
        "ears_covered": "EARS Coverage",
    }
    for gate_id, label in gate_labels.items():
        status = "PASS" if gates.get(gate_id) else "FAIL"
        lines.append(f"| {label} | {status} |")

    lines += [
        "",
        "## Use Case Validation Detail",
        "",
        "| UC | Flow | Status | EARS | Evidence |",
        "|----|------|--------|------|----------|",
    ]
    for entry in use_case_validation:
        ears_text = ", ".join(entry.get("ears", []))
        lines.append(
            f"| {entry.get('uc_id', '')} | {entry.get('flow_id', '')} | {entry.get('status', '')} | {ears_text} | {entry.get('evidence', '')} |"
        )

    lines += [
        "",
        "## EARS Compliance Detail",
        "",
        "| EARS | Status | Evidence |",
        "|------|--------|----------|",
    ]
    for entry in compliance:
        lines.append(
            f"| {entry['ear_id']} | {entry['status']} | {entry.get('evidence', '')} |"
        )

    lines += [
        "",
        f"*Certificado gerado pelo Framework Nexus /review em {now}.*",
    ]

    cert_path = rpath.parent / "review.md"
    with open(cert_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return cert_path


# ------------------------------------------------------------------
# DISPLAY
# ------------------------------------------------------------------


def cmd_show(rpath: Path, _args: argparse.Namespace) -> None:
    data = _load(rpath)
    plan = data.get("plan_name", "?")
    verdict = data.get("verdict")

    print(f"REVIEW: {plan}")
    print("")

    readiness = data.get("readiness", {})
    if readiness:
        done = readiness.get("tasks_completed", 0)
        total = readiness.get("tasks_total", 0)
        ready = readiness.get("all_done", False)
        icon = "[x]" if ready else "[ ]"
        print(f"  {icon} Readiness: {done}/{total} tasks")

    build = data.get("build", {})
    if build:
        passed = build.get("passed", False)
        warnings = build.get("warnings", 0)
        icon = "[x]" if passed else "[ ]"
        warn_note = f" ({warnings} warnings)" if warnings else ""
        print(f"  {icon} Build{warn_note}")

    regression = data.get("regression", {})
    if regression:
        rpassed = regression.get("passed", 0)
        rfailed = regression.get("failed", 0)
        icon = "[x]" if rfailed == 0 and rpassed > 0 else "[ ]"
        print(f"  {icon} Regression: {rpassed} passed, {rfailed} failed")

    use_case_validation = data.get("use_case_validation", [])
    expected_flows = data.get("use_cases_expected", [])
    if expected_flows:
        validated = sum(
            1 for item in use_case_validation if item.get("status") == "validated"
        )
        total_flows = len(expected_flows)
        icon = "[x]" if validated == total_flows else "[ ]"
        print(f"  {icon} Use Cases/Flows: {validated}/{total_flows} validated")

    compliance = data.get("compliance", [])
    use_case_validation = data.get("use_case_validation", [])
    ears_expected = data.get("ears_expected", [])
    if ears_expected:
        coverage = _integrated_ears_coverage(
            compliance, use_case_validation, ears_expected
        )
        integrated = len(coverage["covered_all"])
        legacy = len(coverage["covered_explicit"])
        total_ears = len(ears_expected)

        integrated_icon = "[x]" if integrated == total_ears else "[ ]"
        print(
            f"  {integrated_icon} EARS Coverage (integrated): {integrated}/{total_ears}"
        )
        print(f"  [i] Legacy compliance reports: {legacy}/{total_ears}")

    print("")
    if verdict:
        print(f"  Veredicto: {verdict}")
        if data.get("certified_at"):
            print(f"  Certificado em: {data['certified_at']}")
    else:
        print("  Veredicto: (pendente — execute 'certify')")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reviewer",
        description="Nexus Review — Homologation Tool (gates deterministicos)",
    )
    p.add_argument("review_path", help="Caminho do review.json")
    sub = p.add_subparsers(dest="action", required=True)

    s = sub.add_parser(
        "check-readiness", help="Verificar se backlog esta pronto para review"
    )
    s.add_argument(
        "--backlog",
        default="",
        help="Caminho do backlog.json (auto-descobre se omitido)",
    )

    s = sub.add_parser(
        "report-regression", help="Registrar resultado de testes regressivos"
    )
    s.add_argument("--passed", type=int, required=True, help="Testes que passaram")
    s.add_argument("--failed", type=int, required=True, help="Testes que falharam")

    s = sub.add_parser("report-build", help="Registrar resultado do build")
    bg = s.add_mutually_exclusive_group(required=True)
    bg.add_argument("--passed", action="store_true", help="Build passou")
    bg.add_argument("--failed", action="store_true", help="Build falhou")
    s.add_argument("--warnings", type=int, default=0, help="Numero de warnings")

    s = sub.add_parser("report-compliance", help="Registrar compliance de um EARS")
    s.add_argument("--ear", required=True, help="ID do EARS (ex: REQ-01)")
    s.add_argument(
        "--status",
        required=True,
        choices=["compliant", "partial", "missing"],
        help="Status de compliance",
    )
    s.add_argument(
        "--evidence", default="", help="Evidencia (arquivo:linha ou descricao)"
    )

    s = sub.add_parser(
        "report-usecase",
        help="Registrar validacao de UC/fluxo com EARS associados",
    )
    s.add_argument("--uc", required=True, help="ID do caso de uso (ex: UC-01)")
    s.add_argument("--flow", required=True, help="ID do fluxo (ex: UC-01.FP)")
    s.add_argument(
        "--status",
        required=True,
        choices=["validated", "partial", "missing"],
        help="Status da validacao funcional",
    )
    s.add_argument(
        "--ears",
        nargs="*",
        default=[],
        help="IDs EARS cobertos por esta validacao de UC",
    )
    s.add_argument(
        "--evidence",
        default="",
        help="Evidencia funcional (arquivo:linha ou descricao)",
    )

    sub.add_parser("certify", help="Computar veredicto e gerar certificado")

    sub.add_parser("show", help="Exibir estado do review")

    return p


_ACTIONS = {
    "check-readiness": cmd_check_readiness,
    "report-regression": cmd_report_regression,
    "report-build": cmd_report_build,
    "report-compliance": cmd_report_compliance,
    "report-usecase": cmd_report_usecase,
    "certify": cmd_certify,
    "show": cmd_show,
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


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in _ACTIONS:
        nexus = _find_nexus_root()
        if nexus is None:
            print(
                "ERRO: .nexus/ nao encontrado. Execute a partir do diretorio do projeto.",
                file=sys.stderr,
            )
            sys.exit(1)
        run_dir = _resolve_active_run(nexus)
        if run_dir is None:
            print(
                "ERRO: nenhuma run com backlog encontrada em .nexus/runs/.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.argv.insert(1, str(run_dir / "review.json"))

    parser = _build_parser()
    args = parser.parse_args()
    rpath = Path(args.review_path)
    handler = _ACTIONS.get(args.action)
    if handler:
        handler(rpath, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

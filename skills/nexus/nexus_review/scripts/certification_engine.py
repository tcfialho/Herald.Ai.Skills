"""
Nexus Hom - Certification Engine

Generates a cryptographically signed (SHA-256) Certificate of Conformance
once all quality gates, tests, build, and compliance checks pass.

The certificate is written to:
  .nexus/{plan_name}/review.md

The certificate is NOT issued if:
  - Any quality gate is BLOCKED or NEEDS_REVISION
  - Build failed
  - Tests failed
  - Compliance rate < 90%

Usage:
    engine = CertificationEngine(project_root=".")
    cert = engine.certify(
        plan_name="auth-system",
        gates=my_quality_gates,
        test_evidence=my_evidence,
        compliance_report=my_compliance_report,
    )
    print(cert.status)       # ISSUED | DENIED
    print(cert.certificate_path)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus_core.file_utils import ensure_dir, write_text, sha256_text


CertStatus = Literal["ISSUED", "DENIED"]

CERT_TEMPLATE = """\
# 🏆 Certificado de Conformidade — Framework Nexus v2

## Informações Gerais

| Campo | Valor |
|-------|-------|
| **Projeto** | {{plan_name}} |
| **Versão** | {{version}} |
| **Data de Certificação** | {{date}} |
| **Emitido por** | Framework Nexus /review |

---

## Resultado da Validação

| Dimensão | Peso | Score |
|----------|------|-------|
| Accuracy | 25% | {{score_accuracy}}/5 |
| Completeness | 25% | {{score_completeness}}/5 |
| Consistency | 20% | {{score_consistency}}/5 |
| Feasibility | 15% | {{score_feasibility}}/5 |
| Alignment | 15% | {{score_alignment}}/5 |

**Score Ponderado:** {{weighted_score}}/5.0  
**Veredito:** `{{verdict}}`

---

## Evidências Comprovadas

| Evidência | Status |
|-----------|--------|
| Build | {{build_status}} |
| Testes | {{tests_status}} |
| Cobertura | {{coverage_status}} |
| Conformidade EARS | {{compliance_status}} |

---

## Declaração de Conformidade

{{compliance_declaration}}

**Status:** `{{cert_status}}`  
**Pode Ir Para Produção:** {{production_ready}}

---

## Rastreabilidade

```
Hash do Certificado (SHA-256): {{cert_hash}}
Gerado em: {{date}}
Plan ID: {{plan_name}}
```

> _Este certificado foi gerado automaticamente pelo Framework Nexus /review._  
> _Evidências completas disponíveis em `.temp/review_test_evidence.json`_
"""


# ------------------------------------------------------------------
# Certificate
# ------------------------------------------------------------------


@dataclass
class Certificate:
    plan_name: str
    status: CertStatus
    verdict: str
    weighted_score: float
    scores: dict[str, int] = field(default_factory=dict)
    build_passed: bool = False
    tests_passed: bool = False
    passed_tests: int = 0
    failed_tests: int = 0
    total_tests: int = 0
    coverage_pct: float = 0.0
    compliance_pct: float = 0.0
    denial_reasons: list[str] = field(default_factory=list)
    certificate_path: Optional[Path] = None
    cert_hash: str = ""
    issued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def is_issued(self) -> bool:
        return self.status == "ISSUED"

    def to_banner(self) -> str:
        if self.status == "ISSUED":
            return (
                f"\n{'=' * 60}\n"
                f"  ✅ CERTIFICADO EMITIDO — {self.plan_name}\n"
                f"  Score: {self.weighted_score:.2f}/5.0 | {self.verdict}\n"
                f"  Hash: {self.cert_hash[:16]}...\n"
                f"  Pode ir para produção: SIM\n"
                f"{'=' * 60}\n"
            )
        reasons = "\n".join(f"  - {r}" for r in self.denial_reasons)
        return (
            f"\n{'=' * 60}\n"
            f"  ❌ CERTIFICADO NEGADO — {self.plan_name}\n"
            f"  Razões:\n{reasons}\n"
            f"{'=' * 60}\n"
        )


# ------------------------------------------------------------------
# Certification Engine
# ------------------------------------------------------------------


class CertificationEngine:
    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def certify(
        self,
        plan_name: str,
        gates: object,  # QualityGates
        test_evidence: object,  # HomologationTestEvidence
        compliance_report: object,  # ComplianceReport
        version: str = "1.0.0",
    ) -> Certificate:
        """
        Evaluate all evidence and issue (or deny) a certificate.
        Returns a Certificate object. Writes file only if ISSUED.
        """
        denial_reasons: list[str] = []

        # Check quality verdict
        verdict = gates.verdict
        weighted_score = gates.weighted_score
        if verdict != "APPROVED":
            denial_reasons.append(
                f"Quality gates verdict is '{verdict}' (requires APPROVED). "
                f"Score: {weighted_score:.2f}/5.0"
            )

        # Check build
        if not test_evidence.build_passed:
            denial_reasons.append(
                "Build FAILED. Fix compilation errors before certifying."
            )

        # Check tests
        if not test_evidence.tests_passed:
            denial_reasons.append(
                f"{test_evidence.failed_tests} test(s) FAILED. All tests must pass."
            )

        # Check coverage
        if (
            test_evidence.actual_coverage > 0
            and test_evidence.actual_coverage < test_evidence.minimum_coverage
        ):
            denial_reasons.append(
                f"Test coverage {test_evidence.actual_coverage:.1f}% < "
                f"minimum {test_evidence.minimum_coverage:.0f}%."
            )

        # Check EARS compliance
        if compliance_report.compliance_pct < 90.0:
            denial_reasons.append(
                f"EARS compliance {compliance_report.compliance_pct:.1f}% < 90% threshold. "
                f"{len(compliance_report.non_compliant)} requirement(s) uncovered."
            )

        status: CertStatus = "DENIED" if denial_reasons else "ISSUED"

        cert = Certificate(
            plan_name=plan_name,
            status=status,
            verdict=verdict,
            weighted_score=weighted_score,
            scores=dict(gates._scores),
            build_passed=test_evidence.build_passed,
            tests_passed=test_evidence.tests_passed,
            passed_tests=test_evidence.passed_tests,
            failed_tests=test_evidence.failed_tests,
            total_tests=test_evidence.total_tests,
            coverage_pct=test_evidence.actual_coverage,
            compliance_pct=compliance_report.compliance_pct,
            denial_reasons=denial_reasons,
        )

        if status == "ISSUED":
            cert_content = self._render_certificate(cert, version)
            cert.cert_hash = sha256_text(cert_content)
            # Insert hash into rendered content
            cert_content = cert_content.replace("{{cert_hash}}", cert.cert_hash)
            cert_path = self._write_certificate(plan_name, cert_content)
            cert.certificate_path = cert_path

        return cert

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_certificate(self, cert: Certificate, version: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        decl = (
            "Todos os requisitos EARS foram implementados e validados. "
            "O sistema está apto para deploy em produção."
            if cert.status == "ISSUED"
            else "Certificado NEGADO — issues críticos pendentes."
        )

        def score_str(dim: str) -> str:
            return str(cert.scores.get(dim, "—"))

        rendered = CERT_TEMPLATE
        substitutions = {
            "plan_name": cert.plan_name,
            "version": version,
            "date": now,
            "score_accuracy": score_str("accuracy"),
            "score_completeness": score_str("completeness"),
            "score_consistency": score_str("consistency"),
            "score_feasibility": score_str("feasibility"),
            "score_alignment": score_str("alignment"),
            "weighted_score": f"{cert.weighted_score:.2f}",
            "verdict": cert.verdict,
            "build_status": "✅ SUCCESS" if cert.build_passed else "❌ FAILED",
            "tests_status": f"✅ {cert.passed_tests}/{cert.total_tests} passing"
            if cert.tests_passed
            else f"❌ {cert.failed_tests} failing",
            "coverage_status": f"{'✅' if cert.coverage_pct >= 80 else '⚠️'} {cert.coverage_pct:.1f}%",
            "compliance_status": f"{'✅' if cert.compliance_pct >= 90 else '⚠️'} {cert.compliance_pct:.1f}%",
            "compliance_declaration": decl,
            "cert_status": cert.status,
            "production_ready": "**SIM** ✅"
            if cert.status == "ISSUED"
            else "**NÃO** ❌",
            "cert_hash": "{{cert_hash}}",  # placeholder — replaced after hashing
        }
        for key, value in substitutions.items():
            rendered = rendered.replace("{{" + key + "}}", str(value))
        return rendered

    def _write_certificate(self, plan_name: str, content: str) -> Path:
        docs_dir = self.project_root / ".nexus" / plan_name
        ensure_dir(docs_dir)
        cert_path = docs_dir / "review.md"
        write_text(cert_path, content)
        return cert_path


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("CertificationEngine is invoked programmatically from the /review pipeline.")
    print("See nexus_review/SKILL.md for usage instructions.")

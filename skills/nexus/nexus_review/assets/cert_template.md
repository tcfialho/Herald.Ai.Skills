# 🏆 Certificado Nexus de Conformidade

```
╔══════════════════════════════════════════════════════════════╗
║           🏆 CERTIFICADO NEXUS DE CONFORMIDADE               ║
║                                                              ║
║  Plano  : {{PLAN_NAME}}                                      ║
║  Score  : {{QUALITY_SCORE}} / 5.00 — {{VERDICT}}            ║
║  SHA-256: {{CERT_HASH}}                                      ║
║  Emitido: {{ISSUED_AT}}                                      ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Identificação

| Campo              | Valor                        |
|--------------------|------------------------------|
| **Plano**          | `{{PLAN_NAME}}`              |
| **Plan ID**        | `{{PLAN_ID}}`                |
| **Feature Branch** | `{{FEATURE_BRANCH}}`         |
| **Specs Path**     | `{{SPECS_PATH}}`             |
| **Data de Emissão**| `{{ISSUED_AT}}`              |
| **Válido Por**     | 90 dias (até `{{EXPIRES_AT}}`) |

---

## Veredicto Final

> **{{VERDICT}}** — Score Ponderado: **{{QUALITY_SCORE}} / 5.00**

---

## Scoring 5 Dimensões

| Dimensão       | Peso | Score | Ponderado |
|----------------|------|-------|-----------|
| Accuracy       | 25%  | {{SCORE_ACCURACY}} / 5 | {{WEIGHTED_ACCURACY}} |
| Completeness   | 25%  | {{SCORE_COMPLETENESS}} / 5 | {{WEIGHTED_COMPLETENESS}} |
| Consistency    | 20%  | {{SCORE_CONSISTENCY}} / 5 | {{WEIGHTED_CONSISTENCY}} |
| Feasibility    | 15%  | {{SCORE_FEASIBILITY}} / 5 | {{WEIGHTED_FEASIBILITY}} |
| Alignment      | 15%  | {{SCORE_ALIGNMENT}} / 5 | {{WEIGHTED_ALIGNMENT}} |
| **TOTAL**      | 100% | — | **{{QUALITY_SCORE}}** |

---

## Evidências de Qualidade

### Build & Tests

| Evidência              | Resultado          |
|------------------------|--------------------|
| Build                  | {{BUILD_RESULT}}   |
| Testes Total           | {{TESTS_TOTAL}}    |
| Testes Passados        | {{TESTS_PASSED}}   |
| Testes Falhados        | {{TESTS_FAILED}}   |
| Code Coverage          | {{COVERAGE_PCT}}%  |
| Tasks Completadas      | {{TASKS_COMPLETED_PCT}}% |

### Compliance EARS

| Métrica                | Valor              |
|------------------------|--------------------|
| Requisitos Totais      | {{EARS_TOTAL}}     |
| Requisitos Atendidos   | {{EARS_COMPLIANT}} |
| Compliance             | {{COMPLIANCE_PCT}}% |

---

## Integridade do Certificado

```
SHA-256: {{CERT_HASH}}
```

> Este hash autentica o conteúdo deste certificado no momento da emissão.  
> Para verificar: `sha256sum .nexus/{{PLAN_NAME}}/review.md`

---

## Issues Registradas (Dívida Técnica Não-Bloqueante)

{{TECHNICAL_DEBT_SECTION}}

---

*Certificado emitido automaticamente pelo Framework Nexus `certification_engine.py`.*  
*Qualquer modificação neste arquivo invalida a assinatura SHA-256.*

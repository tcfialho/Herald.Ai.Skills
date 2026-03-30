---
name: Nexus /review
description: 'Stage 3 do Framework Nexus. Homologação automatizada com evidências coletadas, scoring 5-dimensões, verificação de compliance EARS e emissão de certificado de conformidade. Produz veredicto: APPROVED / NEEDS_REVISION / BLOCKED.'
---

# 🔬 NEXUS `/review` — EVIDENCE-BASED HOMOLOGATION

## OBJETIVO
Verificar se o plano executado por `/dev` atende a **todos** os critérios de qualidade definidos na especificação. Produz um **Certificado de Conformidade** quando aprovado.

**INPUT:** Feature Branch com código implementado  
**OUTPUT:** `.nexus/{plan_name}/review.md` (se APPROVED)

---

## PRÉ-CONDIÇÃO

1. Leia `.nexus/plan_state.json` e confirme `status == "completed"`
2. Leia `.nexus/{plan_name}/spec.md` para carregar os requisitos EARS
3. Se o estado não for `completed`: informe o usuário para completar `/dev` primeiro. **HALT.**

---

## FLUXO OBRIGATÓRIO (5 Passos)

### Passo 1 — Coleta de Evidências (Build + Tests)

```python
from nexus_review import TestExecutor
executor = TestExecutor(project_root=".")
evidence = executor.collect_evidence(
    plan_name="{plan_name}"
)
executor.save_evidence(".temp/review_test_evidence.json")
```

**O que é coletado:**
- Build resultado (sucesso/falha + output)
- Tests: total, passed, failed, skipped
- Coverage: percentual, linhas cobertas
- Stack traces de falhas

**Gate de bloqueio:**
- Build falhou → veredicto imediato `BLOCKED`
- Tests falharam → veredicto imediato `BLOCKED`
- Coverage < 80% → sinaliza como `NEEDS_REVISION`

### Passo 2 — Verificação de Compliance EARS

```python
from nexus_review import ComplianceChecker
checker = ComplianceChecker(
    plan_path=".nexus/{plan_name}/spec.md",
    project_root=".",
)
report = checker.check()
print(report.to_markdown())
```

**Critério de aprovação:** Compliance ≥ 90%

Para cada requisito EARS (`WHEN/WHILE/IF/WHERE ... THE SYSTEM SHALL ...`):
- Busca evidência de implementação nos arquivos Python/TS
- Busca evidência de teste cobrindo o comportamento
- Classifica: ✅ COMPLIANT / ⚠️ PARTIAL / ❌ MISSING

Se compliance < 90%: lista requisitos não atendidos e adiciona como issues técnicas.

### Passo 3 — Scoring 5 Dimensões

```python
from nexus_review import QualityGates, HomologationEvidence
gates = QualityGates()
gates.auto_score_from_evidence(HomologationEvidence(
    build_passed=evidence.build_passed,
    test_passed=evidence.test_passed,
    coverage_pct=evidence.coverage_pct,
    compliance_pct=report.compliance_pct,
    tasks_completed_pct=sm.completion_percentage(),
    has_mock_code=evidence.has_mock_code,
    has_todos=evidence.has_todos,
))
print(gates.to_markdown())
```

**Dimensões e pesos:**

| Dimensão       | Peso | Critério de Aprovação                          |
|----------------|------|------------------------------------------------|
| Accuracy       | 25%  | Implementação = Especificação EARS             |
| Completeness   | 25%  | Todas as tasks completadas, sem TODOs          |
| Consistency    | 20%  | Padrões, naming, arquitectura consistentes     |
| Feasibility    | 15%  | Build passa, sem tech-debt bloqueante          |
| Alignment      | 15%  | Objetivos de negócio atendidos                 |

**Escola de pontuação (1-5):**
```
5 — Excelente: supera expectativas
4 — Bom: atende completamente
3 — Adequado: atende minimamente
2 — Insuficiente: atende parcialmente  ← NEEDS_REVISION
1 — Não atende                         ← BLOCKED se qualquer dimensão ≤ 1
```

**Algoritmo de Veredicto:**
```
BLOCKED      → SE qualquer dimensão ≤ 2
NEEDS_REVISION → SE score_ponderado < 4.0 OU qualquer dimensão < 3
APPROVED     → SE score_ponderado ≥ 4.0 E todas dimensões ≥ 3
```

### Passo 4 — Registro de Dívida Técnica

Para cada issue identificada (mocks, coverage gaps, requisitos não atendidos):

```markdown
## Issues Técnicas

| ID    | Dimensão     | Severidade | Descrição                            |
|-------|--------------|------------|--------------------------------------|
| TD-01 | Completeness | HIGH       | Requisito FR-03 sem cobertura de teste |
| TD-02 | Accuracy     | MEDIUM     | Coverage 74% (mínimo: 80%)           |
```

Se veredicto ≠ APPROVED: registre issues em `.nexus/technical_debt.json` e aja conforme abaixo.

**NEEDS_REVISION — limite máximo de 3 iterações:**
> Corrija as issues listadas e re-execute `/review`. Não pergunte ao usuário — liste os arquivos a corrigir e execute `/dev` nas issues bloqueantes.
> **HARD STOP após 3 iterações sem resolução:** Se após 3 ciclos correção→review o veredicto ainda for NEEDS_REVISION, registre as issues como `accepted_risk` em `.nexus/technical_debt.json` com justificativa do impedimento estrutural e emita o certificado com score atual + aviso explícito de dívida técnica. Proibido loop infinito.

**BLOCKED — protocolo obrigatório:**

1. Identifique a categoria da causa raiz:
   - `INFRA_MISSING` — test runner / build tool ausente no projeto
   - `COVERAGE_ZERO` — código existe mas zero testes escritos
   - `BUILD_FAIL` — build quebrado, impede execução
   - `ARCH_MISMATCH` — arquitetura incompatível com o critério (ex: Vanilla browser sem Node)

2. Para cada categoria, aja diretamente **sem perguntar ao usuário**:

   | Causa | Ação determinística |
   |-------|---------------------|
   | `INFRA_MISSING` | Instale o test runner adequado ao stack (sem npm, use CDN ESM; com Node, use `npm init` + Vitest) e crie os testes mínimos bloqueantes |
   | `COVERAGE_ZERO` | Execute `/dev` nas issues TD bloqueantes para criar os arquivos `.test.*` necessários |
   | `BUILD_FAIL` | Corrija o build antes de qualquer outra etapa — re-execute `/review` apenas após build PASS |
   | `ARCH_MISMATCH` | Documente o mismatch como `accepted_risk` em `.nexus/technical_debt.json`, ajuste o critério de Feasibility para o stack real e re-score |

3. Após resolver, re-execute `/review` automaticamente — **não transfira a decisão para o usuário**.

**Tom obrigatório:** técnico e direto. Proibido: elogios ao trabalho anterior, linguagem sycophantic, apresentar "opções" ao usuário como se fosse uma escolha pessoal dele. O agente decide o caminho técnico correto e executa.

Se veredicto = APPROVED com warnings: registre como dívida técnica não-bloqueante e emita.

### Passo 5 — Emissão do Certificado

**Somente se veredicto = APPROVED:**

```python
from nexus_review import CertificationEngine
engine = CertificationEngine(project_root=".")
certificate = engine.certify(
    plan_name="{plan_name}",
    quality_verdict="APPROVED",
    quality_score=gates.weighted_score,
    evidence=evidence,
    compliance_report=report,
)
```

**O certificado inclui:**
- Score ponderado final
- Evidências de build e testes
- Compliance percentual
- Data e hora de emissão (UTC)
- Path: `.nexus/{plan_name}/review.md`

**Regra de Exibição:** Ao imprimir o certificado final no chat, formatação nativa e natural. NÃO embrulhe sob nenhuma hipótese a saída do certificado inteiro em blocos de crase (\`\`\`markdown).

### Passo 6 — Demonstração Interativa (somente se APPROVED)

Após emitir o certificado, **pause e pergunte ao usuário** (único HALT obrigatório deste fluxo):

> **Deseja executar a aplicação agora para um cenário de uso básico?**  
> Responda `sim` ou `não`.

Se a resposta for **não**: encerre informando que o certificado está em `.nexus/{plan_name}/review.md`.

Se a resposta for **sim**, execute o protocolo abaixo:

#### 6.1 — Detectar o comando de execução

```python
from nexus_core.build_system import BuildSystemDetector
detector = BuildSystemDetector(project_root=".")
run_cmd = detector.detect_run_command()
# Exemplos de saída:
#   Python CLI   → "python src/main.py"  ou  "python -m {module}"
#   FastAPI/Flask → "uvicorn src.app:app --reload"
#   Node/Vite    → "npm run dev"
#   HTML estático → instrução para abrir index.html no browser
```

Se o detector não conseguir determinar, inspecione manualmente:
- `package.json` → campo `scripts.start` ou `scripts.dev`
- `pyproject.toml` / `setup.py` → entry points
- Presença de `index.html` na raiz ou `dist/` → app web estática

#### 6.2 — Executar a aplicação

```bash
# Para processos que ocupam o terminal (server, dev server):
# use run_in_terminal com isBackground=true

# Para scripts CLI de curta duração:
# use run_in_terminal com isBackground=false
```

**Regras:**
- Se for servidor web: aguarde 3s e faça um health-check (`curl http://localhost:{port}` ou equivalente) antes de informar ao usuário.
- Se falhar na inicialização: exiba o stderr completo e registre como `TD-RUNTIME` em `.nexus/technical_debt.json`. Não reclassifique o certificado — o APPROVED é sobre o código; o runtime pode ter dependências de ambiente.

#### 6.3 — Cenário de Uso Básico

Após confirmação de que a app está rodando, produza um guia derivado do `spec.md` — use os requisitos EARS para inferir as funcionalidades principais. **Não invente rotas ou comandos que não foram implementados.**

⚠️ **FORMATAÇÃO OBRIGATÓRIA:** envolva em bloco ` ```text ` para preservar o layout no chat:

````text
🚀 APLICAÇÃO RODANDO

   Endereço : http://localhost:{port}        (ou instrução de abertura)
   Processo : {pid ou "background terminal"}

📋 CENÁRIO DE USO BÁSICO — {plan_name}

   Passo 1 — {ação derivada do primeiro requisito EARS principal}
             Como fazer: {instrução concreta — URL, comando, botão}
             O que esperar: {comportamento esperado conforme o plano}

   Passo 2 — {ação derivada do segundo requisito}
             Como fazer: {instrução concreta}
             O que esperar: {comportamento esperado}

   ... (máximo 5 passos, cobrindo o fluxo principal do sistema)

💡 DICAS DE NAVEGAÇÃO
   • {dica 1 relevante ao stack — ex: "hot reload ativo, edite e salve para ver mudanças"}
   • {dica 2 — ex: "pressione Ctrl+C no terminal para encerrar"}
   • {dica 3 — ex: "logs em tempo real no terminal de background"}
````

Após exibir o guia, informe:
> Certificado em `.nexus/{plan_name}/review.md`. A aplicação está ativa no terminal de background. Execute `/review` novamente a qualquer momento para re-homologar após mudanças.

---

## ARTEFATOS PRODUZIDOS

```
.nexus/
├── homologation_evidence.json  ← Build + test evidence estruturada
├── compliance_report.json      ← Requisitos EARS vs implementação
├── quality_report.json         ← Scores 5D + veredicto
└── technical_debt.json         ← Issues registradas

.nexus/{plan_name}/
└── review.md  ← Certificado final (se APPROVED)
```

---

## CRITÉRIOS DE APROVAÇÃO COMPLETOS

O `/review` emite certificado **APPROVED** quando:

| Critério                  | Mínimo    |
|---------------------------|-----------|
| Build                     | PASS      |
| Testes unitários          | PASS      |
| Code coverage             | ≥ 80%     |
| Compliance EARS           | ≥ 90%     |
| Score ponderado (1-5)     | ≥ 4.0     |
| Todas dimensões (1-5)     | ≥ 3       |
| Arquivos com mock/TODO    | 0         |

---

## EXEMPLO DE SAÍDA FINAL (APPROVED)

# 🏆 CERTIFICADO NEXUS DE CONFORMIDADE

| | |
|---|---|
| **Plano:** | {plan_name} |
| **Veredicto:** | **APPROVED** |
| **Score:** | 4.65 / 5.00 |
| **Data/Hora (UTC):** | 2025-07-01T14:22:00Z |

## 📊 Evidências de Homologação
- **Build / Compile**: PASS
- **Unit Tests**: X/X PASSED
- **Test Coverage**: > 80%
- **Mocks / TODOs**: 0
- **EARS Compliance**: 100%

## 📋 Qualidade Dimensional (5D)
- **Accuracy (25%)**: 5/5
- **Completeness (25%)**: 5/5
- **Consistency (20%)**: 5/5
- **Feasibility (15%)**: 4/5
- **Alignment (15%)**: 5/5

*Certificado gerado via validação assíncrona rigorosa baseada em rastreabilidade de código do Framework Nexus.*

---

## EXEMPLO DE SAÍDA (NEEDS_REVISION)

```
🔴 VEREDICTO: NEEDS_REVISION
Score: 3.40 / 5.00

Dimensões abaixo do mínimo:
  • Completeness: 2.5 ← abaixo de 3.0
    Causa: 3 TODOs encontrados em src/services/user_service.py

Issues para corrigir:
  TD-01 [HIGH] src/services/user_service.py: TODO na linha 45
  TD-02 [MEDIUM] Coverage: 74% (mínimo: 80%)

Execute /review novamente após correções.
```


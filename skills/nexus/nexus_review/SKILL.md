---
name: Nexus /review
description: 'Stage 3 do Framework Nexus. Última linha de defesa — executa testes regressivos, build, lint, code quality e EARS compliance. Corrige ativamente tudo que encontrar antes de reportar. Produz veredicto determinístico: APPROVED / NEEDS_REVISION.'
---

# 🔬 NEXUS `/review` — EVIDENCE-BASED HOMOLOGATION

## 🚦 GATE DE DEPENDÊNCIA (verificar ANTES de qualquer ação)

```
Pipeline: /plan → /proto (opcional) → /dev → /review
                                              ^^^^^^ VOCÊ ESTÁ AQUI
```

**Dependências obrigatórias:**
1. `/plan` concluído (`spec.json` existe)
2. `/dev` concluído (`backlog.json` com histórias, tasks e execução 100%)

Antes de executar qualquer comando do `reviewer.py`:
1. Execute `spec_builder.py next-run` para verificar se há run ativa
   - Se `ACTIVE_RUN`: há run para revisar
   - Se `NEXT_RUN`: não há run ativa — HALT (o `/dev` precisa ser executado)
2. Verifique se a run contém `backlog.json` com histórias e tasks

**Se não houver run ativa:** HALT — informe ao usuário:
> Nenhuma run ativa encontrada. Execute `/dev` primeiro.
> Ordem correta: /plan → /dev → /review

**Se `backlog.json` não contiver histórias ou tasks:** HALT — informe ao usuário:
> O backlog está vazio. O `/dev` precisa gerar histórias e tasks antes de iniciar o review.

**Se tasks estiverem pendentes:** HALT — informe ao usuário:
> {N} task(s) pendente(s). Termine o `/dev` antes de executar `/review`.

> O script `reviewer.py check-readiness` já aplica essas validações automaticamente.

---

## OBJETIVO

**O `/review` é a última linha de defesa do pipeline Nexus.** Não existe fase posterior que vá corrigir o que o `/review` encontrar — portanto, o `/review` não apenas verifica: ele **executa, corrige e re-verifica** até que tudo esteja em conformidade total.

A IA nesta fase é **executora ativa**: roda testes regressivos, executa build, verifica code quality (lint, warnings, smells), avalia compliance EARS, e **corrige tudo que falhar** antes de reportar ao script. Reportar falha ao script sem ter tentado corrigir é proibido.

**Princípio:** Nunca reporte um gate como falho se você pode corrigir o problema. O script é apenas o registrador — VOCÊ é o corretor.

**INPUT:** `backlog.json` com 100% das tasks completed + evidence files
**OUTPUT:** `review.json` (estado do review) + `review.md` (certificado, se APPROVED)

---

## FERRAMENTA CENTRAL: `scripts/reviewer.py`

> **Nota de caminho:** `scripts/` é relativo ao diretório desta skill. Resolva o caminho absoluto: `python {skill_dir}/scripts/reviewer.py`.

A IA **NUNCA** escreve review.json diretamente. Toda leitura e escrita passa por `reviewer.py`:

```
CHECK:     check-readiness
REPORT:    report-regression, report-build, report-compliance
CERTIFY:   certify
DISPLAY:   show
```

> **Nota:** Os scripts auto-descobrem `.nexus/` e a run ativa a partir do diretório de trabalho. Paths explícitos como primeiro argumento ainda são aceitos para cenários especiais.

---

## PRÉ-CONDIÇÃO OBRIGATÓRIA

Antes de iniciar:
1. Verifique que `backlog.json` existe e está 100% completo
2. Execute check-readiness:
```bash
python scripts/reviewer.py check-readiness
```
Se tasks estiverem pendentes: **HALT** — informe ao usuário para completar `/dev` primeiro.

---

## FLUXO OBRIGATÓRIO

### Passo 1 — Check Readiness

```bash
python scripts/reviewer.py check-readiness
```

O script verifica:
- Todas as tasks estão `completed` no backlog
- Todos os `evidence/{TASK-XXX}.json` existem
- Extrai lista de EARS esperados do contexto do backlog

Se não estiver pronto: **HALT.** Sugira ao usuário completar o `/dev`.

---

### Passo 2 — Regression Testing (IA executa, corrige, re-executa)

A IA roda **TODOS** os testes do projeto de forma regressiva (unitários + aceitação/Gherkin).

**LOOP OBRIGATÓRIO — repita até 0 falhas:**

1. Execute o test runner completo da stack:
```bash
python -m pytest tests/ -v
# OU
npx vitest run
# OU
npx jest
```
2. Se **todos passaram**: reporte o resultado e avance.
3. Se **algum falhou**: leia o traceback completo de cada falha, identifique a causa raiz, corrija o código, e volte ao passo 1. **NÃO reporte `--failed > 0` sem ter tentado corrigir.**

```bash
# Somente após 0 falhas confirmadas:
python scripts/reviewer.py report-regression --passed 25 --failed 0
```

**Cuidado com regressão em cascata:** ao corrigir um bug, re-execute TODOS os testes novamente — a correção pode ter quebrado outra coisa.

---

### Passo 3 — Build + Code Quality (IA executa, corrige, re-executa)

A IA roda build, lint e verificação de qualidade de código. O objetivo é **zero erros, zero warnings relevantes, zero code smells**.

**LOOP OBRIGATÓRIO — repita até limpo:**

1. **Build/Compile:**
```bash
# Python
python -m compileall src/
# JavaScript/TypeScript
npx tsc --noEmit
# OU
npm run build
```

2. **Lint / Type-check / Warnings:**
```bash
# Python
python -m py_compile src/**/*.py
# Se disponível no projeto:
# pylint, flake8, mypy, ruff, etc.

# JavaScript/TypeScript
# npx eslint src/
# Se disponível no projeto
```

3. **Avaliação de code quality:**
   - Verifique se há warnings de compilação, deprecation warnings, imports não utilizados
   - Verifique se há code smells óbvios: funções muito longas, variáveis não usadas, dead code
   - Use as ferramentas de lint que o projeto já tiver configuradas

4. Se **erros ou warnings relevantes existirem**: corrija o código e volte ao passo 1.
5. Se **limpo**: reporte o resultado.

```bash
# Somente após build limpo:
python scripts/reviewer.py report-build --passed --warnings 0
# Se houver warnings não-críticos que não podem ser resolvidos:
python scripts/reviewer.py report-build --passed --warnings 3
```

**Critério:** Build deve PASSAR. Warnings devem ser minimizados — corrija todos que for possível. Reporte apenas os que genuinamente não podem ser resolvidos (ex: warning de dependência externa).

---

### Passo 4 — EARS Compliance (IA avalia, corrige, reporte)

Para **cada** requisito EARS do spec, a IA inspeciona o código e testes para verificar cobertura completa.

**PARA CADA EARS, siga este ciclo:**

1. **Releia a notação EARS** no spec (ex: "WHEN user submits form THE SYSTEM SHALL validate all fields within 200ms")
2. **Inspecione o código** — existe implementação que cobre esse comportamento?
3. **Inspecione os testes** — existe teste que verifica esse comportamento?
4. Se **implementação ou teste faltam**: implemente/teste o que faltar. Execute os testes para confirmar.
5. **Somente quando compliant**: reporte.

```bash
python scripts/reviewer.py report-compliance --ear REQ-01 --status compliant --evidence "src/task.py:42 + tests/test_task.py:15"
```

**Status possíveis:**

| Status | Significado |
|--------|------------|
| `compliant` | Implementação + teste existem e cobrem o requisito |
| `partial` | Implementação existe mas teste incompleto ou vice-versa |
| `missing` | Sem implementação ou sem teste |

**Regra:** Se ao inspecionar você encontrar um EARS `partial` ou `missing`, **corrija primeiro** (implemente, teste, confirme) e só então reporte como `compliant`. Reportar `partial` ou `missing` é admissão de que você não conseguiu resolver — faça isso apenas se genuinamente não for possível corrigir.

**Após reportar todos os EARS:** re-execute os testes regressivos para garantir que as correções de compliance não quebraram nada. Se quebraram, volte ao Passo 2.

---

### Passo 5 — Certify (Script computa veredicto)

```bash
python scripts/reviewer.py certify
```

O script computa o veredicto a partir de 5 gates determinísticos:

| Gate | O que verifica | Fonte |
|------|---------------|-------|
| **TASKS** | Todas as tasks completed | `check-readiness` |
| **EVIDENCE** | Todos evidence files existem | `check-readiness` |
| **BUILD** | Build passou | `report-build` |
| **REGRESSION** | 0 testes falhando, > 0 passando | `report-regression` |
| **COMPLIANCE** | Todos EARS com status `compliant` | `report-compliance` |

**Veredicto:**
```
APPROVED       → todos os 5 gates TRUE → gera review.md
NEEDS_REVISION → qualquer gate FALSE → lista quais falharam
```

---

### Passo 6 — Protocolo de Auto-Correção (quando `certify` retorna NEEDS_REVISION)

**PRINCÍPIO:** NEEDS_REVISION é consequência direta de falhas no código ou nos reports que VOCÊ produziu. O script mostra o mapa de gates (PASS/FAIL) — corrija proativamente sem perguntar ao usuário.

**Quando `certify` retornar NEEDS_REVISION, siga OBRIGATORIAMENTE:**

1. **LEIA** o mapa completo de gates (PASS/FAIL) no output do `certify`
2. **DIAGNOSTIQUE** cada gate FAIL (veja tabela abaixo)
3. **CORRIJA** o código/testes e re-execute o report correspondente
4. **CHAME `certify`** novamente

| Gate | O que verificar | Como corrigir |
|------|----------------|---------------|
| **tasks_complete** | Tasks pendentes no backlog | Volte ao `/dev` e complete as tasks faltantes. `/review` não pode prosseguir sem 100%. |
| **evidence_ok** | Arquivos `evidence/{TASK-XXX}.json` faltantes | Identifique quais tasks não têm evidence. Re-execute `backlog.py complete` para essas tasks. |
| **build_passed** | Build/compilação falhou | Execute o build da stack. Leia os erros. Corrija o código. Re-execute e reporte via `report-build --passed`. |
| **regression_passed** | Testes falhando na suíte completa | Execute o test runner completo. Leia cada traceback. Corrija os bugs — cuidado com regressão introduzida por correções anteriores. Re-execute e reporte via `report-regression`. |
| **ears_compliant** | EARS sem implementação ou sem teste | Para cada EARS ID listado no FAIL: releia a notação EARS no spec, inspecione se existe implementação + teste correspondente, implemente/teste o que faltar, reporte via `report-compliance --status compliant`. |

**Escalação progressiva:**
- **Iteração 2:** Se os mesmos gates falharem, releia o spec.json original e compare com o código. A correção anterior pode ter introduzido novos problemas.
- **Iteração 3 (HARD STOP):** Informe ao usuário com a lista exata do que não foi possível resolver e o que foi tentado. NÃO tente uma 4ª iteração.

---

### Passo 7 — Demonstração Interativa (somente se APPROVED)

Após emitir o certificado, **pause e pergunte ao usuário:**

> Deseja executar a aplicação para um cenário de uso básico? (sim/não)

Se **não**: encerre informando o caminho do certificado.

Se **sim**:
1. Detecte o comando de execução da stack (package.json scripts, pyproject.toml, index.html)
2. Execute a aplicação
3. Produza um guia de uso derivado dos requisitos EARS (máximo 5 passos)

---

## ARTEFATOS PRODUZIDOS

```
.nexus/
├── spec.json          ← (existente, especificação do projeto)
└── runs/
    └── {run}/         ← Run ativa (ex: 001)
        ├── backlog.json   ← (existente, fonte de verdade do /dev)
        ├── evidence/      ← (existente, gerado pelo /dev)
        ├── review.json    ← Estado do review (gates, reports, veredicto)
        └── review.md      ← Certificado de conformidade (se APPROVED)
```

---

## CRITÉRIOS DE APROVAÇÃO

| Gate | Critério |
|------|----------|
| Tasks | 100% completed |
| Evidence | Todos os evidence files existem |
| Build | PASS |
| Regression | 0 failed, > 0 passed |
| EARS Compliance | 100% compliant |

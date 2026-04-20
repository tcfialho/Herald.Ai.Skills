---
name: Nexus /dev
description: Stage 2 do Framework Nexus. Execução contínua e memória persistente. Zero interrupção, zero mocks, zero simplificações. Usa feature branch única, atomic task breakdown (1-3 arquivos), backlog.json como fonte de verdade e anti-interruption engineering.
---

# ⚡ NEXUS `/dev` — MEMORY-DRIVEN EXECUTION

## 🚦 GATE DE DEPENDÊNCIA (verificar ANTES de qualquer ação)

```
Pipeline: /plan → /proto (opcional) → /dev → /review
                                      ^^^^  VOCÊ ESTÁ AQUI
```

**Dependência obrigatória:** `/plan` concluído (`spec.json` validado com ≥5 EARS, UCs e drill-downs 1:1)

Antes de executar `backlog.py init`:
1. Verifique se `.nexus/spec.json` existe
2. Verifique se o spec foi validado (`spec_builder.py validate` passa)

**Se `spec.json` não existir:** HALT — informe ao usuário:
> spec.json não encontrado. Execute `/plan` primeiro para gerar a especificação.

**Se `spec.json` estiver incompleto (EARS < 5, sem UCs, sem drill-downs):** HALT — informe ao usuário:
> spec.json incompleto. Execute `/plan`, finalize a especificação e rode `spec_builder.py validate`.

> O script `backlog.py init` já aplica essas validações automaticamente.

---

## OBJETIVO
Executar **TODAS** as tasks do plano sequencialmente, sem interrupção, produzindo código 100% real e funcional, com micro-commits atômicos a cada task completa.

**INVARIANTE ABSOLUTA:** Não pare até que o backlog atinja 100% de conclusão.

> [!IMPORTANT]
> **PRIORIDADE MÁXIMA — EXIBIÇÃO DO PROGRESSO NO CHAT (HARD STOP):**
>
> Após executar `backlog.py progress` no terminal, você **DEVE** copiar a saída completa do terminal e colá-la no corpo da sua resposta de chat, dentro de um bloco de código. Se o progress não aparecer **visualmente no chat para o usuário ler**, a obrigação foi violada.
>
> **O que NÃO conta como exibição:** rodar o comando no terminal silenciosamente. O terminal é invisível ao usuário — somente texto na resposta do chat é visível.
>
> **Frequência obrigatória:** ANTES de iniciar cada task e DEPOIS de completar cada task. Nunca agrupe tasks em um único output de progresso.
>
> **Formato esperado (gerado pelo script):**
> ```
> 📊 PROGRESSO: plan-name  [ 38% ]
>
> ✅ [US-UC01-FP] Criar tarefa (2/2)
>
> 📖 [US-UC01-FA1] Criar tarefa sem título
>   ✅ 🟢 [TASK-003] Schema da tabela [Dados]
>   🔄 🔴 [TASK-004] Validação de campos [API] ← EXECUTANDO
>   ⏳ ⚪ [TASK-005] Tratamento de erro UI [UI]
> ```

---

## FERRAMENTA CENTRAL: `scripts/backlog.py`

> **Nota de caminho:** `scripts/` é relativo ao diretório desta skill. Resolva o caminho absoluto: `python {skill_dir}/scripts/backlog.py`.

A IA **NUNCA** lê arquivos de estado diretamente (backlog.json, spec.json). Toda leitura e escrita passa por `backlog.py`:

```
BUILD:    init, add-story, add-criterio, add-task
EXECUTE:  start, complete, fail
CONTEXT:  next, context, recovery
DISPLAY:  progress, show, validate
```

O `backlog.json` é a **única fonte de verdade** durante `/dev`. Contém: stories, tasks, status, contexto do plano (decisions, UC↔EARS, arquitetura, dependências, entidades), qualidade de testes e log de execução.

---

## PRÉ-CONDIÇÃO OBRIGATÓRIA

Antes de iniciar qualquer código:
1. Verifique que `.nexus/spec.json` existe (produzido por `/plan`)
2. Resolva o estado da run:
```bash
python scripts/spec_builder.py next-run
```
> Se retornar `NEXT_RUN` → crie o backlog. Se retornar `ACTIVE_RUN` → sessão retomada, use `recovery`.

3. Crie o backlog na nova run (auto-descobre o próximo slot em `.nexus/runs/`):
```bash
python scripts/backlog.py init
```
> Se `visual.json` existir em `.nexus/`, o backlog importa as screens automaticamente.

4. Se a run já existir (sessão retomada), use `recovery`:
```bash
python scripts/backlog.py recovery
```

> **Nota:** Todos os scripts auto-descobrem `.nexus/` a partir do diretório de trabalho. Paths explícitos como primeiro argumento ainda são aceitos para cenários especiais.

---

## FLUXO OBRIGATÓRIO (execute em ordem, SEM pausar)

### Passo 1 — Feature Branch Setup

O `{plan_name}` é extraído do campo `plan_name` dentro de `.nexus/spec.json` (metadata, não pasta).

```bash
git fetch origin
git checkout main
git pull origin main
git checkout -b feature/{plan_name}
```

### Passo 2 — Story Generation (UCs → Histórias)

Leia o spec.json (via contexto mental do `/plan`) e gere **Histórias de Usuário** a partir dos fluxos.
Cada fluxo de cada UC (principal + alternativos) produz **exatamente uma história**.

**Regra de Filtragem por Origin (DELTA-ONLY):**
> O backlog de uma run contém **apenas o delta** — trabalho NOVO a ser implementado.
> UCs com `origin: "inferred"` (inferidos de código já existente pelo `/plan` Cenário B) são **excluídos** da geração de stories. Somente UCs com `origin: "new"` (default) geram stories e tasks.
>
> O comando `backlog.py show` exibe o breakdown `new` vs `inferred` para confirmação.
> O comando `backlog.py add-story` emite AVISO se a IA tentar registrar story para UC inferred.

**Regras de geração:**
1. **Somente UCs `origin: "new"`.** UCs inferred existem no spec para contexto documental, não para implementação.
2. **1 Fluxo = 1 História.** UC-01 com fluxo principal + 2 alternativos → 3 histórias.
3. **ID derivado do UC:** `US-UC01-FP` (fluxo principal), `US-UC01-FA1` (alternativo 1), etc.
4. **Critérios de Aceitação em Gherkin:** Cada história DEVE ter ao menos 1 critério.

Registre cada história e seus critérios via `backlog.py`:
```bash
python scripts/backlog.py add-story --id US-UC01-FP --uc-ref UC-01 --fluxo-id UC-01.FP --descricao "Criar tarefa com titulo e prioridade"

python scripts/backlog.py add-criterio --story US-UC01-FP --dado "usuario na tela de lista" --quando "preenche titulo e clica Criar" --entao "tarefa aparece na lista com status pendente"
```

**OBRIGAÇÃO DE EXIBIÇÃO:** Após registrar todas as histórias:
```bash
python scripts/backlog.py show
```

### Passo 3 — Task Queue Generation (Histórias → Tasks Atômicas)

Para cada história, quebre em tasks atômicas e registre via `backlog.py`:
```bash
python scripts/backlog.py add-task --story-ref US-UC01-FP --id TASK-001 --title "Criar schema da tabela Tarefa" --tipo "Dados" --nivel 0 --objetivo "Criar migration com tabela tarefas" --pre-condicao "Nenhuma" --pos-condicao "Tabela tarefas existe no banco" --diretiva "Integracao" --verify-cmd "python -m pytest tests/test_schema.py -x -q" --files "src/migrations/001.sql" "tests/test_schema.py" --ears-refs "REQ-01"
```

**Regras de Fatiamento por Camada Técnica:**

| Tipo | Escopo | Exemplo |
|------|--------|---------|
| **Dados** | Queries, schemas, persistência | Criar tabela, escrever query |
| **UI** | Componente visual, zero lógica de rede | Montar formulário, renderizar lista |
| **API** | Recebimento de payload, validação, repasse | Rota POST, validar campos |
| **Integração** | Fio que liga UI à API | onClick → fetch → atualizar DOM |

**Regras de Ordenação por Dependências:**

| Nível | Regra | Exemplo |
|-------|-------|---------|
| **0** | Sem bloqueios. Executa imediatamente. | Criar tabela, montar HTML base |
| **1** | Exige artefato do Nível 0 pronto. | Endpoint que precisa do schema |
| **2** | Exige artefatos de níveis anteriores. | Integração final (UI + API prontos) |

Use `--dependencies` para declarar dependências:
```bash
python scripts/backlog.py add-task --story-ref US-UC01-FP --id TASK-003 ... --dependencies TASK-001 TASK-002
```

**Regra do "Zero Mocks" (Pré-condições Físicas):**
A Pré-condição de uma Task **nunca é simulada**. Se a Task da API depende do Banco de Dados, o código **real** gerado pela Task do BD é o contexto obrigatório. A IA é **proibida** de criar stubs ou mocks para simular integrações internas.

**Dois tipos de teste no `/dev`:**

| Tipo | Quando criar | Filosofia | Mock permitido |
|------|-------------|-----------|----------------|
| **Unitário (TDD)** | Tasks de nível 0/1 (Dados, UI, API) | Escreve teste ANTES de implementar → implementa até ficar verde | Zero — código real |
| **Integração/Aceitação (Gherkin)** | Tasks de nível 2 (Integração) | Caixa-preta testando critérios dado/quando/então da história | Apenas recursos externos (DB, APIs externas, filesystem) |

**Regra TDD:** Para tasks de lógica de domínio, a IA DEVE escrever o teste unitário PRIMEIRO, verificar que falha (red), implementar o código até passar (green), e só então reportar no `complete`.

**Regra Gherkin:** Para cada critério de aceitação registrado via `add-criterio` (dado/quando/então), DEVE existir ao menos um teste de integração caixa-preta que o cubra. Esses testes vivem nas tasks de Integração (nível 2) e testam o fluxo completo da história.

**Regra Atômica:** Cada task toca no **máximo 3 arquivos**.

> ⚠️ **REGRA DO `verify_cmd`:** Todo task DEVE ter um `verify_cmd` preenchido.
> O comando deve ser o **test runner real** da stack (pytest, vitest, jest, etc.).
> O agente é **PROIBIDO** de alterar o `verify_cmd` depois de definido.

**Validação e exibição obrigatória após registrar todas as tasks:**
```bash
python scripts/backlog.py validate
python scripts/backlog.py progress
```

### Entrega Estruturada (YAML)

Os comandos de entrega `next` e `context` agora usam **YAML estruturado como padrão** para consumo automatizado:

```bash
python scripts/backlog.py next
python scripts/backlog.py context --task TASK-001
python scripts/backlog.py context --story US-UC01-FP
```

Envelope padrão da entrega YAML:
- `delivery`
- `task`
- `story`
- `use_case`
- `ears`
- `architecture_context`
- `dependencies_context`
- `progress`
- `quality_gate`

Compatibilidade legada permanece disponível com `--format text`.


**ESTE LOOP NÃO TEM BREAK PREMATURO. Execute até o final.**

Para cada iteração:

```
1. Obter próxima task (respeita dependências automaticamente):
   python scripts/backlog.py next              # YAML estruturado (default)
   # opcional legada:
   python scripts/backlog.py next --format text

2. Marcar como in_progress:
   python scripts/backlog.py start TASK-XXX

3. Exibir progresso no chat (OBRIGATÓRIO — copiar output do terminal para a resposta):
   python scripts/backlog.py progress
   # opcional machine-readable:
   python scripts/backlog.py progress --format yaml
   → Copie o output COMPLETO e inclua na sua resposta de chat como bloco de código.

4. IMPLEMENTAR A TASK:
   - Código 100% real (zero mocks, zero TODOs)
   - Error handling completo
   - Sem return {} ou pass vazio

5. VALIDATION GATE (antes de completar):
   PASSO A — Build/Compile
   PASSO B — Lint/Type-check
   PASSO C — Executar testes da task e anotar resultado (quantos passaram/falharam)
   PASSO D — Resolução de dependências no ambiente real

6. Completar a task (claims explícitas + auditoria automática):
   python scripts/backlog.py complete TASK-XXX \
     --test-files tests/test_schema.py tests/test_api.py \
     --test-passed 3 --test-failed 0
   
   A IA declara os resultados via argumentos. O script audita:
     GATE 1 — task.files existem no disco
     GATE 2 — anti-mock scan nos arquivos de implementação
     GATE 3 — test-files existem no disco
     GATE 4 — test-failed == 0 e test-passed > 0
   O script gera automaticamente evidence/{TASK-XXX}.json com claims + audit.
   
   Se houver falha no gate TEST_RESULT, o backlog entra em estado **blocked** e os comandos
   `next/context` passam a recusar entrega de task até nova conclusão bem-sucedida (`complete` com testes verdes).
   
   SE REJEITADO: corrija e re-submeta. Não avance.
   SE CIRCUIT BREAKER (3 falhas): HALT e peça ajuda ao usuário.
   
   Para registrar falha explicitamente:
   python scripts/backlog.py fail TASK-XXX --error "descricao do erro"

7. Micro-commit atômico (somente se complete aceito):
   git add -A && git commit -m "feat(scope): descricao"

8. Exibir progresso atualizado no chat (OBRIGATÓRIO — copiar output do terminal para a resposta):
   python scripts/backlog.py progress
   → Copie o output COMPLETO e inclua na sua resposta de chat como bloco de código.
```

**OBRIGAÇÃO DE PROGRESSO CONTÍNUO (HARD STOP — Violação Nível 1):**

O output do comando `progress` roda no terminal, que é **invisível ao usuário**. Para o progresso ser útil, a IA DEVE:
1. **Ler a saída do terminal** após executar `backlog.py progress`
2. **Transcrever o bloco completo na resposta de chat**, dentro de um code block
3. **Nunca omitir, resumir ou parafrasear** — colar o output literal

Se o bloco de progresso não aparece na resposta de chat, o usuário não tem feedback algum. Isso é uma falha grave de UX e viola a obrigação constitucional.

**Regra de ouro do layout (gerada pelo script):**
- `✅` Histórias 100% completas aparecem resumidas em uma linha com contagem
- `📖` Histórias com tasks pendentes são expandidas com status por task
- `✅ 🟢` task completa | `🔄 🔴` task executando | `⏳ ⚪` task pendente

### Passo 4.1 — Protocolo de Auto-Correção (quando `complete` rejeita)

**PRINCÍPIO CONSTITUCIONAL:** Rejeição do `complete` é SEMPRE consequência de falha no SEU código ou nas suas claims. O script NUNCA está errado — ele audita o que você produziu. Trate toda rejeição como feedback sobre o SEU output, não como erro genérico.

**Quando `complete` retornar `REJEITADO`, siga OBRIGATORIAMENTE:**

1. **LEIA** a mensagem completa de rejeição (gate + detalhe)
2. **DIAGNOSTIQUE** — inspecione o arquivo/linha citado ou releia o contexto:
   ```bash
   python scripts/backlog.py context --task TASK-XXX
   ```
3. **CORRIJA** o problema específico (veja tabela abaixo)
4. **VERIFIQUE LOCALMENTE** (build + testes passando) ANTES de re-submeter
5. **RE-SUBMETA** o `complete` com claims atualizadas

| Gate | Causa típica | O que fazer |
|------|-------------|------------|
| **FILES** | Arquivo declarado em `task.files` não foi criado no disco | Crie o arquivo faltante. Se o path está errado no código, corrija o código — NÃO altere a definição da task. |
| **MOCKS** | Código de implementação contém placeholder (`pass`, `TODO`, `return {}`) | Abra o arquivo:linha indicado na rejeição. Substitua o placeholder por implementação real. Releia o objetivo da task se necessário. |
| **TESTS** | Arquivo de teste declarado em `--test-files` não existe no disco | Crie o arquivo de teste. Se esqueceu de criá-lo, siga o ciclo TDD: escreva o teste primeiro, depois implemente. |
| **TEST_RESULT** | Testes falhando ou nenhum teste executado | Execute o `verify_cmd` da task. Leia o traceback completo. Corrija o bug no código (não no teste, a menos que o teste esteja errado). Re-execute e confirme 0 falhas antes de re-submeter. |

**Escalação progressiva (o script informa a tentativa no output):**
- **Tentativa 2 (mesmo gate):** Releia o contexto completo da task via `context --task`. Sua correção anterior não resolveu — mude a abordagem fundamentalmente.
- **Tentativa 3 (circuit breaker):** HALT. Informe ao usuário exatamente qual gate falha, o que você tentou nas 2 tentativas anteriores, e por que não conseguiu resolver.

---

### Passo 5 — Anti-Mock Enforcement & Evidence Model

O comando `complete` opera no modelo **"IA declara, Script audita"**:

1. **A IA executa os testes** e reporta o resultado via `--test-passed` / `--test-failed`
2. **O script audita** as claims da IA (arquivos existem? mocks? testes reportados como passando?)
3. **O script gera** `evidence/{TASK-XXX}.json` automaticamente com o dossiê completo

O anti-mock scan varre **apenas arquivos de implementação** (exclui test files declarados em `--test-files`), buscando: `# TODO`, `# FIXME`, `pass`, `raise NotImplementedError`, `return {}`, `return []`, `mock_`, `fake_`, `dummy_`

Se qualquer gate falhar, o `complete` rejeita a transição e incrementa o contador de falhas.

**PROIBIDO absolutamente em código de implementação:**
- `# TODO`, `# FIXME`
- `pass` em corpo de função
- `raise NotImplementedError`
- `return {}`, `return []` como implementação real
- Variáveis com nomes `mock_`, `fake_`, `dummy_`

### Passo 6 — Incremental Validation (Por task)

Toda task que implementa lógica de domínio **deve incluir seu arquivo de teste** em `task.files`:
```
["src/engine/collision.js", "tests/unit/collision.test.js"]
```

Tasks de integração (nível 2) incluem testes de aceitação que cobrem os critérios Gherkin:
```
["src/integration/create_task.js", "tests/acceptance/create_task.test.js"]
```

**Ciclo TDD (tasks unitárias):**
```
1. Escrever teste que falha (RED)
2. Implementar código mínimo para passar (GREEN)
3. Refatorar se necessário (REFACTOR)
4. Reportar no complete
```

**Testes de Aceitação (tasks de integração):**
```
1. Ler critérios Gherkin da história (dado/quando/então)
2. Escrever teste caixa-preta que exercita o fluxo completo
3. Mock APENAS recursos externos (DB, APIs externas, filesystem)
4. Implementar a integração até o teste passar
5. Reportar no complete
```

**A IA é responsável por executar os testes e reportar o resultado no `complete`:**

```bash
# 1. IA executa os testes
python -m pytest tests/test_schema.py -x -q

# 2. IA anota: 3 passed, 0 failed

# 3. IA chama complete com as claims
python scripts/backlog.py complete TASK-001 \
  --test-files tests/test_schema.py \
  --test-passed 3 --test-failed 0
```

Comandos de teste por stack:
```bash
# Python
python -m pytest {test_file} -x -q

# JavaScript/TypeScript (Vitest)
npx vitest run {test_file}

# JavaScript/TypeScript (Jest)
npx jest {pattern}

# Vanilla browser (ESM)
node --input-type=module <<< "import {fn} from './{arquivo}'; console.assert(fn(x) === y)"
```

Se o test runner não está instalado: **instale na hora**.
Se falhar: **corrija antes de completar. Nunca reporte `--test-failed > 0`.**

### Passo 7 — Plan Completion

Quando `backlog.py complete` da última task imprimir "PLANO COMPLETO":
```bash
python scripts/backlog.py progress    # exibição final
git push origin feature/{plan_name}
```

Informe ao usuário:
> Plano `{plan_name}` executado. Progress: 100%
> Execute `/review` para validação final.

---

## ARTEFATOS PRODUZIDOS

```
.nexus/
├── spec.json               ← Plano original (NÃO modificado pelo /dev)
├── spec.md                 ← Visualização do plano
├── visual.json             ← Decisões visuais (opcional, produzido pelo /proto)
└── runs/
    └── {run}/              ← Execução desta rodada (ex: 001)
        ├── backlog.json    ← Fonte de verdade da execução (contexto = spec + visual merged)
        └── evidence/       ← Gerado automaticamente pelo complete
            ├── TASK-001.json
            ├── TASK-002.json
            └── ...
```

---

## CRITÉRIOS DE SAÍDA DO `/dev`

O `/dev` está COMPLETO quando:
- [ ] `backlog.py progress` mostra 100%
- [ ] Todas as tasks têm status `completed`
- [ ] Build passa sem erros
- [ ] Testes passam
- [ ] Nenhum arquivo contém mocks ou TODOs
- [ ] Commits seguem Conventional Commits: `type(scope): desc`
- [ ] Feature branch pushed

---

## RECOVERY PROTOCOL

Se a sessão for interrompida, ao reiniciar:
```bash
python scripts/backlog.py recovery
```

O output contém:
- Tasks completas (não re-executar)
- Tasks pendentes (executar em ordem)
- Próxima task com contexto
- Instrução de retomada

Retome a partir da próxima task pendente SEM repetir tasks completas.

---

## CONTEXT QUERIES (para quando a IA precisar de informação específica)

```bash
# Contexto completo de uma task específica
python scripts/backlog.py context --task TASK-005

# Contexto de uma história com todas as suas tasks
python scripts/backlog.py context --story US-UC01-FP

# Resumo geral do backlog
python scripts/backlog.py show
```

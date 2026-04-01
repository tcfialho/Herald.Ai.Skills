---
name: Nexus /dev
description: Stage 2 do Framework Nexus. Execução contínua e memória persistente. Zero interrupção, zero mocks, zero simplificações. Usa feature branch única, atomic task breakdown (1-3 arquivos), state persistence e anti-interruption engineering.
---

# ⚡ NEXUS `/dev` — MEMORY-DRIVEN EXECUTION

## OBJETIVO
Executar **TODAS** as tasks do plano sequencialmente, sem interrupção, produzindo código 100% real e funcional, com micro-commits atômicos a cada task completa.

**INVARIANTE ABSOLUTA:** Não pare até que `is_plan_complete()` retorne `True`.

> [!IMPORTANT]
> **PRIORIDADE MÁXIMA:** A exibição do painel `📊 PROGRESSO` (bloco ```text) antes e depois de **CADA** task é mais importante que a própria implementação do código. Nunca agrupe tasks em um único output de progresso. Se uma resposta não contém o painel atualizado, ela é considerada uma falha crítica de protocolo.

---

## PRÉ-CONDIÇÃO OBRIGATÓRIA

Antes de iniciar qualquer código:
1. Verifique que `.nexus/{plan_name}/spec.md` existe
2. **(Opcional)** Se `.nexus/{plan_name}/proto.json` existe → carregue decisões visuais (Passo 2)
   Se não existe → `ℹ️ /proto não executado — UI gerada sem spec visual.` e siga normalmente
3. Leia `.nexus/{plan_name}/plan_state.json` — **se existir**, retome a partir da task pendente
4. Se não existe state, inicialize:

> **ℹ️ `nexus_core`** está em `skills/nexus_core/` — mesmo nível deste diretório.  
> Os scripts localizam-no automaticamente subindo a árvore de pastas (`_find_nexus_core_root`).

```python
from nexus_core.state_manager import NexusStateManager
sm = NexusStateManager(project_root=".")
sm.create_plan_state(plan_id="nexus_{plan_name}", plan_name="{plan_name}")
```

---

## FLUXO OBRIGATÓRIO (execute em ordem, SEM pausar)

### Passo 1 — Feature Branch Setup

```bash
git fetch origin
git checkout main
git pull origin main
git checkout -b feature/{plan_name}
```

Registre a branch no state:
```json
{ "feature_branch": "feature/{plan_name}" }
```

### Passo 2 — Story Generation (UCs → Histórias)

Antes de quebrar em tasks, gere **Histórias de Usuário** a partir dos fluxos do spec.md.
Cada fluxo de cada UC (principal + alternativos) produz **exatamente uma história**.

Execute `scripts/story_generator.py`:
```python
from story_generator import StoryGenerator
sg = StoryGenerator(plan_path=".nexus/{plan_name}/spec.md")
stories = sg.generate_stories()
sg.save(f".nexus/{plan_name}/stories.json")
```

**Regras de geração de Histórias:**
1. **1 Fluxo = 1 História.** Se o UC-01 tem fluxo principal + 2 alternativos → 3 histórias.
2. **Referência filho → pai:** Cada história referencia o UC de origem (`uc_ref: "UC-01"`). O UC **nunca** referencia a história.
3. **ID derivado do UC:** `US-UC01-FP` (fluxo principal), `US-UC01-FA1` (alternativo 1), etc.
4. **Descrição breve:** Apenas para fins visuais (1 linha). A fonte da verdade é o UC no spec.md.
5. **Critérios de Aceitação em Gherkin:** Cada história DEVE ter ao menos 1 critério.

**Formato obrigatório de uma História:**
```yaml
id: "US-UC01-FP"
uc_ref: "UC-01"                    # Pai (fonte da verdade no spec.md)
fluxo_id: "UC-01.FP"              # ID do fluxo no drill-down do UC
descricao_breve: "Criar tarefa com título e prioridade"
criterios_aceitacao:
  - dado: "o usuário está na tela de lista de tarefas"
    quando: "preenche o título e clica em Criar"
    entao: "a tarefa aparece na lista com status pendente"
  - dado: "o campo título está vazio"
    quando: "clica em Criar"
    entao: "exibe mensagem de validação e não cria a tarefa"
```

Registre as histórias no state:
```python
sm.register_stories([{"id": s.id, "uc_ref": s.uc_ref, "fluxo_id": s.fluxo_id} for s in stories])
```

**OBRIGAÇÃO DE EXIBIÇÃO:** Após gerar as histórias, exiba o inventário completo:

````text
📖 HISTÓRIAS GERADAS: {plan_name}
   Total: {N} histórias | {M} UCs cobertos

   📄 [US-UC01-FP] Criar tarefa (Fluxo Principal)
       UC Ref: UC-01 | Fluxo: UC-01.FP
       Gherkin: 2 critérios de aceitação

   📄 [US-UC01-FA1] Criar tarefa sem título (Fluxo Alternativo 1)
       UC Ref: UC-01 | Fluxo: UC-01.FA1
       Gherkin: 1 critério de aceitação

   📄 [US-UC02-FP] Marcar tarefa como concluída (Fluxo Principal)
       UC Ref: UC-02 | Fluxo: UC-02.FP
       Gherkin: 2 critérios de aceitação
   ...
````

### Passo 3 — Task Queue Generation (Histórias → Tasks Atômicas)

Execute `scripts/task_breaker.py` a partir das histórias geradas:
```python
from task_breaker import TaskBreaker
breaker = TaskBreaker(
    plan_path=".nexus/{plan_name}/spec.md",
    stories_path=".nexus/{plan_name}/stories.json",
)
tasks = breaker.break_tasks()
breaker.save(f".nexus/{plan_name}/tasks.json")
```

**(Automático) Enriquecimento de referências cruzadas:**

O `StoryGenerator` e o `TaskBreaker` carregam automaticamente `proto.json` e `decision_manifest.json` (se existirem no mesmo diretório do `spec.md`). Cada story e task recebe:
- `decision_context[]` → decisões de planejamento do `/plan`
- `proto_refs[]` → decisões visuais do `/proto` (seletivas por UC — apenas screens cujo `source_ucs` intersecta com o UC da story/task)

**Após atribuir `historia_ref` nas tasks, propague `proto_refs` das stories-pai:**
```python
from task_breaker import TaskBreaker
TaskBreaker.enrich_from_stories(
    tasks=tasks,
    stories_path=f".nexus/{plan_name}/stories.json",
)
# Re-salva tasks com proto_refs herdados das stories
breaker.save(f".nexus/{plan_name}/tasks.json")
```

> **Nota:** Se `proto.json` não existir, `proto_refs` fica `[]` — sem impacto no fluxo.

**Estrutura obrigatória de uma Task:**
```yaml
id: "TASK-001"
title: "Criar schema da tabela Tarefa"
historia_ref: "US-UC01-FP"        # Pai — referência à história (child → parent)
tipo: "Dados"                     # Dados | UI | API | Integração
nivel: 0                          # 0=sem bloqueios | 1=dep simples | 2=dep composta

objetivo: "Criar migration com tabela `tarefas` contendo colunas id, titulo, prioridade, status, created_at"

pre_condicao:
  - "Nenhuma — Nível 0"           # OU artefatos reais de tasks anteriores

pos_condicao:
  - "Tabela `tarefas` existe no banco com todas as colunas"
  - "Migration é reversível (up/down)"

diretiva_de_teste: "Integração"   # Teste bate no banco real + teardown

verify_cmd: "python -m pytest tests/integration/test_tarefas_schema.py -x -q"  # Comando de verificação para o SubmitGate

files: ["src/migrations/001_create_tarefas.sql", "tests/integration/test_tarefas_schema.py"]
dependencies: []                  # IDs de tasks que devem estar completas antes
ears_refs: ["FR-01"]              # EARS requirements cobertos
```

> ⚠️ **REGRA DO `verify_cmd`:** Todo task DEVE ter um `verify_cmd` preenchido no momento da criação pelo TaskBreaker.
> O comando deve ser o **test runner real** da stack detectada (pytest, vitest, dotnet test, go test, cargo test, mvn test, etc.).
> O agente é **PROIBIDO** de alterar o `verify_cmd` depois de definido. Ele é a âncora de verificação do SubmitGate.

**Regras de Fatiamento por Camada Técnica (Granularidade):**

A Task **nunca resolve um fluxo inteiro** — resolve uma engrenagem. A quebra técnica padrão separa o escopo em caixas-pretas isoladas:

| Tipo | Escopo | Exemplo |
|------|--------|---------|
| **Dados** | Apenas queries, schemas, persistência | Criar tabela, escrever query de inserção |
| **UI** | Apenas componente visual "burro", zero lógica de rede | Montar formulário HTML, renderizar lista |
| **API** | Apenas recebimento do payload, validação e repasse para dados | Rota POST, validar campos, chamar repo |
| **Integração** | O "fio" que liga UI (clique) à API (fetch/axios) | onClick → fetch → atualizar DOM |

**Regras de Ordenação por Grafo de Dependências (Níveis):**

| Nível | Regra | Exemplo |
|-------|-------|---------|
| **0** (Sem Bloqueios) | Não depende de código anterior. Pode executar imediatamente. | Criar tabela, montar HTML base |
| **1** (Dep Simples) | Exige artefato do Nível 0 pronto. | Endpoint API que precisa do schema |
| **2** (Dep Composta) | Exige artefatos de níveis anteriores. | Integração final (UI + API prontos) |

**Regra do "Zero Mocks" (Pré-condições Físicas):**

A Pré-condição de uma Task **nunca é teórica ou simulada**. Se a Task da API depende do Banco de Dados, o código **real e funcional** gerado pela Task do Banco de Dados torna-se o contexto obrigatório de entrada. A IA é **terminantemente proibida** de criar stubs ou mocks para simular integrações internas.

**Contrato de Pós-condição Fechado:**

A Pós-condição é técnica, verificável e binária. Sem linguagem de negócio ("o usuário fica feliz"). Deve ditar **exatamente** a alteração de estado do sistema:
- `"Retorna HTTP 201 com body { id, titulo, status }"`
- `"Emite evento 'tarefa-criada' com payload { id }"`
- `"Salva registro na tabela tarefas com status = 'pendente'"`

**Blindagem de Testes (Diretiva por Tipo de Task):**

| Tipo de Task | Diretiva | Regra |
|-------------|----------|-------|
| **Dados** | `Integração` | Teste bate no banco real, faz limpeza (teardown) |
| **API** | `Integração` | Teste levanta servidor, envia request real, valida response |
| **UI** | `Componente` | Teste renderiza componente, valida DOM/eventos |
| **Integração** | `E2E` | Teste exercita fluxo completo (UI → API → Dados) |

**Regra Atômica:** Cada micro-commit toca no **máximo 3 arquivos**. Isso não limita a complexidade da task — limita o escopo de cada commit individual para garantir reversibilidade.

Registre todas as tasks no state:
```python
sm.register_tasks([{
    "id": t.id,
    "title": t.title,
    "historia_ref": t.historia_ref,
    "tipo": t.tipo,
    "nivel": t.nivel,
    "files": t.files,
} for t in tasks])
```

**OBRIGAÇÃO DE INÍCIO (HARD STOP):** No primeiro output da rotina `/dev`, você é OBRIGADO a imprimir o plano de execução completo no chat com visão hierárquica **História → Task**, contendo **absolutamente todas as tasks**, organizadas por História, ANTES de iniciar a primeira task.
⚠️ **FORMATAÇÃO EXATA OBRIGATÓRIA:**

````text
📋 PLANO DE EXECUÇÃO: {plan_name}  [ 0% ]

📖 [US-UC01-FP] Fluxo principal: Criar tarefa
  ⏳ ⚪ [TASK-001] Criar schema da tabela Tarefa [Dados]
  ⏳ ⚪ [TASK-002] Implementar formulário de criação [UI]
  ⏳ ⚪ [TASK-003] Criar endpoint POST /api/tarefas [API]

📖 [US-UC01-FA1] Criar tarefa sem título
  ⏳ ⚪ [TASK-004] Validação de campos obrigatórios [API]

📖 [US-UC02-FP] Fluxo principal: Marcar concluída
  ⏳ ⚪ [TASK-005] Endpoint PATCH /api/tarefas/:id [API]
  ⏳ ⚪ [TASK-006] Integração UI → API de conclusão [Integração]
````

### Passo 4 — Priority Queue Ordering

**REGRA:** `PriorityQueue` é a **única fonte de verdade** para ordenação de tasks em execução.
`TaskBreaker.get_ordered_queue()` é **PROIBIDO** para execução — usa ordenação por prioridade sem respeitar dependências, podendo executar uma task antes de suas dependências estarem completas. Use exclusivamente:

```python
from priority_queue import PriorityQueue
pq = PriorityQueue(project_root=".")
ordered = pq.build_from_task_file(f".nexus/{plan_name}/tasks.json")
```

### Passo 5 — Anti-Interruption Execution Loop

**ESTE LOOP NÃO TEM BREAK PREMATURE. Execute até o final mantendo a OBRIGAÇÃO VISUAL nas respostas do chat.**

**CICLO DE STATUS OBRIGATÓRIO (PRIORIDADE CRÍTICA) — sem exceções:**
```
┌──────────────────────────────────────────────────┐
│  Tasks nascem como:  ⏳ pending                  │
│                                                  │
│  AO INICIAR uma task:                            │
│    1. sm.update_task_status(id, "in_progress")   │
│       → status vira: 🔄 in_progress              │
│    2. ⚠️ HARD STOP — EMITA NO CHAT:             │
│       Escreva no corpo da sua RESPOSTA o bloco   │
│       ```text com o painel 📊 PROGRESSO          │
│       atualizado. Isto NÃO é um script.          │
│       É texto que você digita na resposta.       │
│                                                  │
│  AO FINALIZAR uma task:                          │
│    1. sm.update_task_status(id, "completed")     │
│       → status vira: ✅ completed                │
│    2. ⚠️ HARD STOP — EMITA NO CHAT:             │
│       Escreva no corpo da sua RESPOSTA o bloco   │
│       ```text com o painel 📊 PROGRESSO          │
│       atualizado. Isto NÃO é um script.          │
│       É texto que você digita na resposta.       │
└──────────────────────────────────────────────────┘
```

**OBRIGAÇÃO DE PROGRESSO CONTÍNUO (HARD STOP):** Em absolutamente todas as iterações onde uma task avançar ou for iniciada, você tem a OBRIGAÇÃO INEGOCIÁVEL de exibir a UI hierárquica com o painel de transição no Chat.
⚠️ **NUNCA OMITA E NÃO ABREVIE A LISTA.** Os ícones (✅/🔄/⏳) e os indicadores de verificação (🟢/🔴/⚪) devem refletir a exatidão do momento atual da state machine. Use text block (` ```text `):
⚠️ **REGRA DE OURO DO LAYOUT:** Modelos 100% concluídos devem ser resumidos em UMA linha (`✅ [História]`). Módulos `🔄` ou `⏳` precisam ser expandidos. Todo o progresso exibido DEVE estar dentro de um **bloco de código Markdown** (` ```text `).

> ⚠️ **DISTINÇÃO CRÍTICA:** `tracker.print_report()` no loop Python é apenas referência lógica. A **emissão real** do painel é texto que você, o agente, escreve diretamente no chat — não o resultado de um comando no terminal. Atualizar o `plan_state.json` e exibir o painel são dois atos separados. O primeiro **não implica** o segundo. **Ambos são obrigatórios.**

````text
📊 PROGRESSO: todo-app  [ 38% ]

✅ [US-UC01-FP] Fluxo principal: Criar tarefa (2/2)

📖 [US-UC01-FA1] Criar tarefa sem título
  ✅ 🟢 [TASK-003] Mock do formulário vazio [UI]
  🔄 🔴 [TASK-004] Validação de campos obrigatórios [API] ← EXECUTANDO (⚠️ 1x falha)
  ⏳ ⚪ [TASK-005] Tratamento de erro UI [UI]

📖 [US-UC02-FP] Fluxo principal: Marcar concluída
  ⏳ ⚪ [TASK-006] Endpoint PATCH /api/tarefas/:id [API]
  ⏳ ⚪ [TASK-007] Componente de checkbox [UI]
  ⏳ ⚪ [TASK-008] Integração UI → API de conclusão [Integração]
````

```python
for task in ordered:
    # --- PAINEL ANTES DA TASK ---
    tracker = ProgressTracker(project_root=".")
    tracker.print_report(as_code_block=True)  # exibe ✅ / 🔄 / ⏳ para cada task
    print(f"\n🔄 Iniciando: [{task.id}] {task.title}")
    print(f"   História: {task.historia_ref} | Tipo: {task.tipo} | Nível: {task.nivel}")
    print(f"   Objetivo: {task.objetivo}")
    print(f"   Arquivos: {', '.join(task.files)}")
    print(f"   Diretiva: {task.diretiva_de_teste}")

    # Marcar como in_progress
    sm.update_task_status(task.id, "in_progress", files=task.files)

    # === PASSO 0 — Proto Compliance Gate (OPCIONAL) ===
    # Apenas se task.proto_refs não estiver vazio (proto.json presente e UC com match).
    # SE existe:
    #   Para cada screen em task.proto_refs, verifique que o componente respeita:
    #     - screen["dimension"]        → a dimensão decidida (ex: filtros no topo)
    #     - screen["chosen"]           → variante escolhida (A ou B)
    #     - screen["chosen_intent"]    → intenção da variante escolhida
    #     - screen["change_requests"]  → ajustes aplicados (ex: pills altura 18px)
    #   SE o código divergir: corrija antes de continuar.
    # SE vazio: N/A — pule.

    # === IMPLEMENTAR TASK AQUI ===
    # Siga os tópicos e subtópicos da task exatamente
    # Código 100% real (zero mocks, zero TODOs)
    # Error handling completo
    # Sem return {} ou pass vazio
    
    # Checkpoint a cada 3 arquivos criados
    if progress_tracker.should_checkpoint(files_since_last_checkpoint, interval=3):
        mm.save_snapshot(sm.load_state(), label=f"checkpoint-{task.id}")

    # ══════════════════════════════════════════════════════
    # VALIDATION GATE — obrigatório antes de completed
    # NÃO pule nenhum passo. NÃO marque completed com falha.
    # ══════════════════════════════════════════════════════
    #
    # PASSO A — Build / Compile
    #   Python : python -m py_compile {arquivo}
    #   JS/TS  : npx tsc --noEmit   OU   node --check {arquivo}
    #   Outro  : use o build system detectado por build_system.py
    #   → Se falhar: corrija AGORA antes de continuar.
    #
    # PASSO B — Lint / Type-check
    #   Python : python -m flake8 {arquivo} (se disponível)
    #   TS     : npx tsc --noEmit
    #   → Warnings são aceitáveis; erros bloqueiam.
    #
    # PASSO C — Testes da task
    #   Execute o(s) arquivo(s) de teste criados NESTA task.
    #   Python : python -m pytest {test_file} -x -q
    #   JS/TS  : npx vitest run {test_file} OU npx jest {pattern}
    #   → Se não existe test runner: instale antes de continuar
    #     (veja task_breaker: tasks com lógica de domínio DEVEM
    #     ter um arquivo .test.* listado em task.files)
    #   → Pass rate deve ser 100% para a task atual.
    #   → Se falhar: corrija o código OU o teste — nunca ignore.
    #
    # PASSO D — Resolução de dependências no ambiente de execução real
    #
    #   PRINCÍPIO: o agente não assume que porque algo funciona localmente
    #   (no processo do agente, no Node, no terminal), também funcionará
    #   onde o código realmente executa. Antes de commitar, prove que cada
    #   dependência externa do arquivo é resolvível no ambiente correto.
    #
    #   QUANDO SE APLICA: sempre que algum arquivo da task consumir qualquer
    #   recurso que não é declarado dentro do próprio arquivo.
    #
    #   PASSO D.1 — Identifique o ambiente de execução real do arquivo:
    #     • Browser         (carregado via <script> ou bundler no browser)
    #     • Node/Deno       (executado como processo servidor ou CLI)
    #     • Python runtime  (executado pelo interpretador Python)
    #     • Container       (Docker / ambiente isolado com env vars próprias)
    #     • Serverless      (Lambda, Cloud Function — ambiente efêmero)
    #     • Outro           (documente explicitamente)
    #
    #   PASSO D.2 — Liste cada dependência externa consumida pelo arquivo.
    #   Uma dependência externa é QUALQUER coisa que o arquivo usa mas não
    #   define. Categorias universais:
    #
    #     MÓDULOS / PACOTES
    #       import X from 'lib'  →  lib instalada em node_modules?
    #       from lib import X    →  lib em requirements.txt e instalada?
    #       require('X')         →  pacote existe no ambiente de execução?
    #
    #     SÍMBOLOS GLOBAIS
    #       Uso de X sem declaração local  →  quem injeta X no escopo?
    #       (browser: CDN, outro <script>; Node: global, built-in; Python: builtin)
    #       X disponível ANTES da primeira linha que o usa?
    #
    #     VARIÁVEIS DE AMBIENTE
    #       process.env.X / os.environ['X']  →  X definida no .env ou no runtime?
    #       Listar todas as env vars consumidas e verificar que existem.
    #
    #     RECURSOS DO FILESYSTEM
    #       readFile('./config.json') / open('data.csv')  →  arquivo existe?
    #       Caminho relativo correto a partir do cwd real de execução?
    #
    #     CONTRATOS DE REDE / IPC
    #       fetch('/api/users')  →  essa rota foi implementada neste ou em task anterior?
    #       socket.connect(host, port)  →  serviço está disponível no ambiente alvo?
    #
    #     SCHEMAS / BANCO DE DADOS
    #       ORM model / query  →  tabela/coluna existe na migration já aplicada?
    #
    #   PASSO D.3 — Para cada dependência listada, verifique 2 invariantes:
    #     I. EXISTE no ambiente de execução real (não só localmente)
    #     II. ESTÁ DISPONÍVEL ANTES da primeira referência (ordem de init)
    #
    #   PASSO D.4 — Se qualquer invariante falhar: corrija agora.
    #   Não existe "vou resolver depois". Task com dependência não resolvida
    #   é task incompleta — não commita, não marca completed.
    #
    #   Exemplos de falha e correção por categoria:
    #     Módulo ausente    → instale (npm i X / pip install X) e adicione ao manifesto
    #     Global fora de ordem → mova a declaração/carregamento para antes do uso
    #     Env var faltando  → adicione ao .env.example e documente como obrigatória
    #     Arquivo inexistente → crie o arquivo ou corrija o caminho
    #     Rota não implementada → implemente nesta task ou adicione nova task ao plano
    #     Schema ausente    → crie a migration e aplique antes de testar
    #
    # SAÍDA ESPERADA após PASSOS A-D:
    #   ✅ Build: PASS
    #   ✅ Lint:  PASS (ou N/A)
    #   ✅ Tests: {N} passed, 0 failed
    #   ✅ Deps:  todas as dependências externas resolvíveis no ambiente real
    #             (lista explícita ou "N/A — arquivo sem dependências externas")
    #
    # Somente após confirmação acima → submeter ao SubmitGate.

    # ══════════════════════════════════════════════════════
    # SUBMIT GATE — Evidence Before Claims
    # ══════════════════════════════════════════════════════
    # O agente é PROIBIDO de chamar sm.update_task_status("completed") diretamente.
    # A ÚNICA forma de marcar uma task como completed é através do SubmitGate.
    # O SubmitGate lê o verify_cmd do tasks.json, varre os arquivos contra mocks,
    # valida que testes referenciam implementações reais, e executa o verify_cmd.
    # Somente se TODAS as fases passarem, o estado transiciona para completed.
    #
    # PROIBIDO: sm.update_task_status(task.id, "completed")  ← NUNCA FAÇA ISSO
    # OBRIGATÓRIO:
    from nexus_core.submit_gate import SubmitGate
    gate = SubmitGate(project_root=".", plan_name="{plan_name}")
    submit_result = gate.submit(task.id)
    print(submit_result.summary())
    #
    # SE submit_result.is_accepted == False:
    #   → NÃO commite. NÃO avance. Corrija o código e re-submeta.
    #   → Se circuit breaker ativado (3 falhas): HALT IMEDIATO.
    #     Transcreva o erro ao Usuário e peça consultoria humana.
    #
    # SE submit_result.is_accepted == True:
    #   → O SubmitGate já alterou o plan_state.json internamente.
    #   → Prossiga com o micro-commit:
    #
    # ══════════════════════════════════════════════════════

    # Micro-commit atômico (somente se submit aceito)
    commit_msg = CommitMessageBuilder.build_from_task(task, commit_type="feat")
    # git add -A && git commit -m "{commit_msg}"

    # Snapshot de memória
    mm.save_snapshot(sm.load_state(), label=f"completed-{task.id}")

    # --- PAINEL DEPOIS DA TASK ---
    print(f"\n✅ [{task.id}] {task.title} — COMPLETED")
    tracker.print_report(as_code_block=True)  # estado atualizado
```

### Passo 6 — Anti-Mock Enforcement (Embutido no SubmitGate)

> ⚠️ **MUDANÇA ARQUITETURAL:** A verificação anti-mock agora é executada automaticamente
> pelo `SubmitGate` durante a fase de submissão. O agente NÃO precisa chamá-la separadamente.
> O SubmitGate varre TODOS os `task.files` buscando indicadores de mock/placeholder
> (`# TODO`, `# FIXME`, `pass`, `raise NotImplementedError`, `return {}`, `mock_`, etc.)
> **antes** de executar o `verify_cmd`. Se encontrar qualquer indicador, a submissão é rejeitada.
>
> Adicionalmente, o SubmitGate valida que arquivos de teste (`*.test.*`, `test_*`, `*Test.*`)
> realmente importam/referenciam os arquivos de implementação da mesma task,
> prevenindo testes "dummy" que passam mas não testam nada real.
>
> O agente continua PROIBIDO de usar os seguintes padrões em código gerado:

**PROIBIDO absolutamente:**
- `# TODO`, `# FIXME`
- `pass` em corpo de função
- `raise NotImplementedError`
- `return {}`, `return []` como implementação real
- Variáveis com nomes `mock_`, `fake_`, `dummy_`
- Dependências não declaradas em `requirements.txt` / `package.json`

### Passo 7 — Incremental Validation (Por task)

**Regra de ouro:** toda task que implementa lógica de domínio **deve incluir seu arquivo de teste** em `task.files`. O arquivo de teste é parte da task, não um passo separado. Se o `task_breaker` não incluiu o `.test.*`, adicione antes de implementar.

Exemplos de task.files corretos:
```
# ✅ correto
["src/engine/collision.js", "tests/collision.test.js"]

# ❌ errado — deixa a task sem cobertura
["src/engine/collision.js"]
```

O Validation Gate está embutido no loop do Passo 5 (Build → Lint → Tests). Este passo documenta os comandos por stack:

```bash
# Python
python -m py_compile {arquivo}
python -m pytest {test_file} -x -q

# JavaScript/TypeScript (Vitest)
npx vitest run {test_file}

# JavaScript/TypeScript (Jest)
npx jest {pattern} --passWithNoTests=false

# Sem Node instalado (Vanilla browser)
# Use a abordagem ESM inline — importe o módulo diretamente:
node --input-type=module <<< "import {fn} from './{arquivo}'; console.assert(fn(x) === y)"
```

Se o test runner não está instalado quando a primeira task de lógica for executada: **instale na hora** (não adie para o /review descobrir).

Se falhar: **corrija antes de marcar como completed e antes de commitar.**

### Passo 8 — Session Memory Snapshots

```python
from memory_manager import MemoryManager
mm = MemoryManager(project_root=".")
# A cada task completada:
mm.save_snapshot(sm.load_state(), label=f"completed-{task.id}")
```

**Recuperação após crash:**
```python
recovery_prompt = mm.generate_handover_prompt()
# Use este texto como contexto de recuperação de sessão
```

### Passo 9 — Plan Completion

Quando `sm.is_plan_complete()` retornar `True`:
```python
sm.mark_plan_complete()
progress_tracker.print_report(as_code_block=True)
```

Então:
```bash
git push origin feature/{plan_name}
# Notifique o usuário para criar a PR e executar /review
```

---

## ARTEFATOS PRODUZIDOS

```
.nexus/{plan_name}/
├── plan_state.json      ← Estado completo (task por task)
├── stories.json         ← Histórias geradas dos UCs (UC → Histórias)
├── tasks.json           ← Tasks atômicas quebradas das histórias
├── task_queue.json      ← Fila de tasks ordenada
├── session_memory.json  ← Snapshots de recuperação
├── execution_log.json   ← Log de cada transição de status
└── spec.md              ← Plano original (não modificado)
```

---

## CRITÉRIOS DE SAÍDA DO `/dev`

O `/dev` está COMPLETO quando:
- [ ] `sm.is_plan_complete()` retorna `True`
- [ ] Todas as tasks têm status `completed` ou `skipped`
- [ ] Build passa sem erros
- [ ] Testes unitários passam
- [ ] Nenhum arquivo contém mocks ou TODOs
- [ ] Todos os commits seguem Conventional Commits puro: `type(scope): desc` — sem prefixo `[Task-XXX]`
- [ ] Feature branch pushed

**Após verificação, informe ao usuário:**
> ✅ Plano `{plan_name}` executado. Progress: 100%  
> Execute `/review` para validação final e emissão do certificado.

---

## RECOVERY PROTOCOL

Se a sessão for interrompida, ao reiniciar execute:

```python
mm = MemoryManager(project_root=".")
recovery_prompt = mm.generate_handover_prompt()
print(recovery_prompt)
# O contexto acima contém: completed_tasks, pending_tasks, next_task
# Retome a partir de next_task SEM repetir completed_tasks
```


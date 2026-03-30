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

### Passo 2 — Task Queue Generation (Atomic Task Breakdown)

Execute `scripts/task_breaker.py`:
```python
from task_breaker import TaskBreaker
breaker = TaskBreaker(plan_path=".nexus/{plan_name}/spec.md")
tasks = breaker.break_tasks()
breaker.save(f".nexus/{plan_name}/tasks.json")
```

**(Opcional) Enriquecimento visual — apenas se `proto.json` existir:**
```python
import json
from pathlib import Path

proto_path = Path(f".nexus/{plan_name}/proto.json")
if proto_path.exists():
    proto_data = json.loads(proto_path.read_text(encoding="utf-8"))
    # Índice: UC → screen decidida
    screens_by_uc = {
        uc: screen
        for screen in proto_data.get("screens", [])
        if screen.get("status") == "decided"
        for uc in screen.get("source_ucs", [])
    }
    for task in tasks:
        matched = [
            screens_by_uc[uc]
            for uc in (task.ears_refs or [])
            if uc in screens_by_uc
        ]
        if matched:
            task.visual_spec = matched
# SE proto.json não existe: task.visual_spec nunca é definido — sem impacto no fluxo.
```

**O que uma task contém (obrigatório):**
```
- ID e título descritivo
- Tópicos e subtópicos do que deve ser implementado
- Requisito(s) EARS do plano que esta task cobre
- Lista de arquivos a criar/modificar (max 3 por commit)
- Dependências de tasks anteriores
- Critérios de conclusão verificaveis
```

**Regra Atômica:** Cada micro-commit toca no **máximo 3 arquivos**. Isso não limita a complexidade da task — limita o escopo de cada commit individual para garantir reversibilidade. Uma task complexa pode gerar vários commits atômicos sequenciais.

Registre todas as tasks no state:
```python
sm.register_tasks([{"id": t.id, "title": t.title, "files": t.files} for t in tasks])
```

**OBRIGAÇÃO DE INÍCIO (HARD STOP):** No primeiro output da rotina `/dev`, você é OBRIGADO a imprimir o plano de execução completo no chat, contendo **absolutamente todas as tasks** e seu escopo (Tópicos, Arquivos, EARS), ANTES de iniciar a primeira task.  
⚠️ **FORMATAÇÃO EXATA OBRIGATÓRIA:** Em sua resposta inicial de execução de log, envolva a string rigorosamente em bloco (` ```text `) como abaixo:

````text
📋 PLANO DE EXECUÇÃO: {plan_name}
   Total: {N} tasks

   ⏳ [TASK-01] Inicializar estrutura base do projeto
       Tópicos: criar diretórios, configurar pyproject.toml, .gitignore
       Arquivos: src/__init__.py, pyproject.toml
       EARS: FR-01

   ⏳ [TASK-02] Implementar modelo de dados User
       Tópicos: User dataclass, validação de campos, Value Objects
       Arquivos: src/models/user.py, tests/test_user_model.py
       EARS: FR-02, FR-03
   ...
````

### Passo 3 — Priority Queue Ordering

**REGRA:** `PriorityQueue` é a **única fonte de verdade** para ordenação de tasks em execução.
`TaskBreaker.get_ordered_queue()` é **PROIBIDO** para execução — usa ordenação por prioridade sem respeitar dependências, podendo executar uma task antes de suas dependências estarem completas. Use exclusivamente:

```python
from priority_queue import PriorityQueue
pq = PriorityQueue(project_root=".")
ordered = pq.build_from_task_file(f".nexus/{plan_name}/tasks.json")
```

### Passo 4 — Anti-Interruption Execution Loop

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

**OBRIGAÇÃO DE PROGRESSO CONTÍNUO (HARD STOP):** Em absolutamente todas as iterações onde uma task avançar ou for iniciada, você tem a OBRIGAÇÃO INEGOCIÁVEL de exibir a UI com o painel de transição no Chat.
⚠️ **NUNCA OMITA E NÃO ABREVIE A LISTA.** A barra percentual e os ícones (✅/🔄/⏳) devem refletir a exatidão do momento atual da state machine. Use text block (` ```text `):
⚠️ **REGRA DE OURO DO LAYOUT:** Todo o progresso exibido DEVE estar dentro de um **bloco de código Markdown** (` ```text `).

> ⚠️ **DISTINÇÃO CRÍTICA:** `tracker.print_report()` no loop Python é apenas referência lógica. A **emissão real** do painel é texto que você, o agente, escreve diretamente no chat — não o resultado de um comando no terminal. Atualizar o `plan_state.json` e exibir o painel são dois atos separados. O primeiro **não implica** o segundo. **Ambos são obrigatórios.**

````text
📊 PROGRESSO: {plan_name} — {X}/{N} tasks ({'='*bar}{'.'*rest}) {pct}%

   ✅ [TASK-01] Estrutura base do projeto
   ✅ [TASK-02] Modelo de dados User
   🔄 [TASK-03] Serviço de autenticação JWT  ← EXECUTANDO AGORA
   ⏳ [TASK-04] Middleware de autorização
   ⏳ [TASK-05] Endpoints de login/logout
   ⏳ [TASK-06] Testes de integração
````

```python
for task in ordered:
    # --- PAINEL ANTES DA TASK ---
    tracker = ProgressTracker(project_root=".")
    tracker.print_report(as_code_block=True)  # exibe ✅ / 🔄 / ⏳ para cada task
    print(f"\n🔄 Iniciando: [{task.id}] {task.title}")
    print(f"   Tópicos: {task.description}")
    print(f"   Arquivos: {', '.join(task.files)}")
    print(f"   EARS:     {', '.join(task.ears_refs)}")

    # Marcar como in_progress
    sm.update_task_status(task.id, "in_progress", files=task.files)

    # === PASSO 0 — Proto Compliance Gate (OPCIONAL) ===
    # Apenas se task.visual_spec foi definido acima (proto.json presente e UC com match).
    # SE existe:
    #   Para cada screen em task.visual_spec, verifique que o componente respeita:
    #     - screen["dimension"]        → a dimensão decidida (ex: filtros no topo)
    #     - screen["chosen"]           → variante escolhida (A ou B)
    #     - screen["change_requests"]  → ajustes aplicados (ex: pills altura 18px)
    #   SE o código divergir: corrija antes de continuar.
    # SE não existe: N/A — pule.

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
    # Somente após confirmação acima → commitar.

    # Micro-commit atômico
    commit_msg = CommitMessageBuilder.build_from_task(task, commit_type="feat")
    # git add -A && git commit -m "{commit_msg}"

    # Marcar como completed
    sm.update_task_status(task.id, "completed", files=task.files)
    
    # Snapshot de memória
    mm.save_snapshot(sm.load_state(), label=f"completed-{task.id}")

    # --- PAINEL DEPOIS DA TASK ---
    print(f"\n✅ [{task.id}] {task.title} — COMPLETED")
    tracker.print_report(as_code_block=True)  # estado atualizado
```

### Passo 5 — Anti-Mock Enforcement (Em CADA arquivo gerado)

Após gerar cada arquivo, execute:
```python
from code_generator import CodeQualityChecker
checker = CodeQualityChecker(project_root=".")
result = checker.validate_file(filepath)
if not result.is_valid:
    # BLOQUEADO — corrija imediatamente antes de prosseguir
    raise RuntimeError(f"Mock detectado em {filepath}:\n{result.errors}")
```

**PROIBIDO absolutamente:**
- `# TODO`, `# FIXME`
- `pass` em corpo de função
- `raise NotImplementedError`
- `return {}`, `return []` como implementação real
- Variáveis com nomes `mock_`, `fake_`, `dummy_`
- Dependências não declaradas em `requirements.txt` / `package.json`

### Passo 6 — Incremental Validation (Por task)

**Regra de ouro:** toda task que implementa lógica de domínio **deve incluir seu arquivo de teste** em `task.files`. O arquivo de teste é parte da task, não um passo separado. Se o `task_breaker` não incluiu o `.test.*`, adicione antes de implementar.

Exemplos de task.files corretos:
```
# ✅ correto
["src/engine/collision.js", "tests/collision.test.js"]

# ❌ errado — deixa a task sem cobertura
["src/engine/collision.js"]
```

O Validation Gate está embutido no loop do Passo 4 (Build → Lint → Tests). Este passo documenta os comandos por stack:

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

### Passo 7 — Session Memory Snapshots

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

### Passo 8 — Plan Completion

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
├── tasks.json           ← Tasks atômicas quebradas do plano
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


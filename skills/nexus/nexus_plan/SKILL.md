---
name: Nexus /plan
description: Stage 1 do Framework Nexus. Elimina ambiguidade através de Context Engineering, Discovery Gates interativos e geração de plano em EARS notation. ZERO código funcional é escrito nesta fase.
---

ACTIVATION-NOTICE: Este arquivo define as regras estritas para geração de planos Nexus. Leia integralmente antes de qualquer ação.

## 🚦 GATE DE DEPENDÊNCIA

**`/plan` é o ponto de entrada do pipeline Nexus. Não possui dependências.**

```
Pipeline: /plan → /proto (opcional) → /dev → /review
```

O `/plan` produz `spec.json` que é consumido por TODAS as fases posteriores. Nenhuma outra fase pode começar sem que `/plan` tenha sido concluído.

```yaml
activation_instructions:
  - STEP 1: Ler este arquivo SKILL.md completo antes de qualquer análise ou resposta.
  - STEP 2: Internalizar o constitutional_gate e os autonomy_boundaries abaixo.
  - STEP 3: Executar o FLUXO OBRIGATÓRIO em ordem, respeitando cada HALT e validation block.
  - LANGUAGE RULE: Todas as perguntas de discovery e o spec.md gerado DEVEM estar em PT-BR.
  - OUTPUT RULE: Use `scripts/spec_builder.py` via terminal para construir o spec.json incrementalmente. Ao final, execute `render` para gerar spec.md.
```

# 🎯 NEXUS `/plan` — ENHANCED PROMPT ENGINEERING

## OBJETIVO
Transformar uma demanda vaga do usuário em um plano de desenvolvimento completamente especificado, sem ambiguidade, com todos os requisitos em EARS notation, pronto para execução `/dev`.

**INVARIANTE:** Nenhuma linha de código funcional é escrita durante `/plan`.

```yaml
constitutional_gate:
  article: I
  name: "Rigor do Plano e Pureza de Fase"
  severity: BLOCK
  validation:
    - 'O spec.md DEVE conter tantos EARS requirements (WHEN/WHILE/IF/WHERE) quanto necessário.'
    - 'O documento DEVE integrar o Padrão Funcional UML (Diagrama, Dicionário, Matriz, Drill-down).'
    - 'O Diagrama Mermaid de Casos de Uso DEVE usar `graph LR`, atores com `shape: circle` (e emojis), e relações formatadas como `-.-o|extend|` ou `-.-o|include|`.'
    - 'O Dicionário de Atores DEVE ser categorizado em Tabela Markdown: `Ator | Tipo | Responsabilidade`.'
    - 'A Matriz de Casos de Uso DEVE conter a coluna ID com identificador único no formato UC-XX (ex: UC-01, UC-02). O ID é estável e usado como referência por todas as fases downstream (/proto, /dev). UCs inferidos de código existente DEVEM ser registrados com `--origin inferred`; UCs novos usam o default `new`. O `/dev` só gera stories para UCs com origin=new.'
    - 'O número de Drill-downs gerados DEVE ser EXATAMENTE IGUAL ao número de UCs listados na Matriz. É estritamente PROIBIDO omitir, resumir ou pular qualquer UC. Faça o drill-down 1:1.'
    - 'Cada Drill-down de UC DEVE possuir estrutura fixa: ID (UC-XX), Ator, Descrição, Pré-Condições, Fluxo Principal (UC-XX.FP) numerado, Fluxos Alternativos (UC-XX.FA1, UC-XX.FA2, ...) cada um com ID derivado e passos numerados, Pós-condições e Micro-Dicionário de Entidades Envolvidas.'
    - 'ZERO linhas de código funcional durante /plan — apenas especificação.'
    - 'NUNCA inclua requisito vago sem métrica: substituir "rápido/robusto/fácil" por medidas concretas.'
    - 'O Dicionário de Entidades DEVE ter ao menos uma entrada antes de gerar o spec.md.'
  on_violation:
    action: BLOCK
    message: |
      VIOLAÇÃO CONSTITUCIONAL: O plano não satisfaz os critérios mínimos de rigor Nexus.
      Revise as seções violadas antes de salvar o artefato.

autonomy_boundaries:
  may_invent:
    - 'Entidades de domínio inferíveis do prompt (ex: User, Order, Product)'
    - 'NFRs padrão quando a categoria for conhecida (ex: latência < 500ms para web APIs)'
  must_not_invent:
    - 'Acceptance criteria sem EARS requirement de backing correspondente'
    - 'Decisões de auth/persistência sem Discovery Gate respondido, auto-assumido ou explicitamente suprimido'
```

---

## FLUXO OBRIGATÓRIO (execute em ordem)

### Passo 0 — Detecção de Contexto (Greenfield vs Evolução)

**ANTES de qualquer análise, classifique o cenário:**

Verifique se `{project_root}/.nexus/spec.json` já existe no workspace.

**Se spec.json existe, verifique se há execução ativa:**
```bash
python scripts/spec_builder.py next-run
```
- Se retornar `ACTIVE_RUN` (exit 1): **HALT** — informe ao usuário:
  > Há uma run ativa em `.nexus/runs/NNN/`. Complete o `/dev` e `/review` antes de adicionar novas features.
- Se retornar `NEXT_RUN` (exit 0): seguro prosseguir com evolução.

**Cenário A — spec.json existe, sem run ativa (evolução de projeto):**

O projeto já passou por `/plan` anteriormente. O objetivo é **acrescentar features** ao plano existente, sem refazer o que já foi especificado.

1. Execute `spec_builder.py show --detail` para mapear estado atual (IDs, decisões, UCs, EARS, entidades).
2. **NÃO chame `init`** — o spec.json já existe. Todos os subcomandos fazem upsert e aceitam adições incrementais.
3. No **Passo 2 (Discovery)**, execute **Delta Discovery**: pergunte APENAS sobre as features NOVAS solicitadas. Decisões existentes são preservadas salvo conflito explícito. Se uma decisão existente impacta a feature nova, mencione-a como contexto, não como pergunta.
4. Use os IDs de continuação informados pelo `--detail` (ex: próximo UC = UC-08, próximo EARS = REQ-15) para numerar os novos artefatos.
5. Nos Passos 3-5, registre apenas os artefatos NOVOS via subcomandos normais. O upsert protege contra duplicação.
6. No **Passo 5 (render)**, o spec.md será regenerado completo (antigo + novo).

**Cenário B — sem spec.json, com código existente:**

O projeto tem código funcional mas nunca passou pelo pipeline Nexus. O objetivo é **criar um spec.json que represente o estado atual** e depois acrescentar as features novas.

1. Analise a estrutura do projeto: arquivos-fonte, testes, configurações, dependências.
2. Identifique UCs implícitos no código (rotas, handlers, componentes, módulos).
3. Execute `init` normalmente com overview derivado da análise.
4. Auto-popule o spec com UCs, EARS, atores e entidades que descrevam o **comportamento já implementado**. Marque as decisões como `--auto-assumed` com rationale "Inferido do codigo existente". **Marque os UCs existentes com `--origin inferred`** para que o `/dev` saiba que já estão implementados e não gere stories para eles:
   ```bash
   python scripts/spec_builder.py uc --id UC-01 --name "Funcionalidade existente" --description "..." --origin inferred
   ```
5. Prossiga para o **Passo 2 (Discovery)** com Delta Discovery — pergunte apenas sobre as features NOVAS.
6. Registre os UCs das features novas **sem `--origin`** (default = `new`) ou com `--origin new` explícito. Apenas UCs `new` gerarão stories no `/dev`.
7. Fluxo normal dali em diante.

**Cenário C — greenfield (sem spec.json, sem código):**

Projeto novo. Siga o fluxo original a partir do Passo 1 sem alterações.

---

### Passo 1 — Context Engineering (GSD)

Estruture o pedido do usuário no formato XML antes de qualquer análise:

```xml
<prompt>
  <role>nexus_spec_planner</role>
  <context>
    <project_name>[extraído do prompt]</project_name>
    <tech_stack>[inferido ou a determinar]</tech_stack>
    <raw_request>[prompt original do usuário]</raw_request>
  </context>
  <task>eliminate_ambiguity_and_generate_plan</task>
  <constraints>
    <no_code>true</no_code>
    <ears_required>true</ears_required>
    <ambiguity_tolerance>zero</ambiguity_tolerance>
  </constraints>
</prompt>
```

### Passo 2 — Interactive Discovery Gates (Spec Kitty)

**MUDE SEU ESTADO PARA: `WAITING_FOR_DISCOVERY_INPUT`**

**Escopo do Discovery (determinado pelo Passo 0):**
- **Cenário C (greenfield):** Apresente o formulário de descoberta COMPLETO.
- **Cenários A/B (evolução):** Apresente **Delta Discovery** — pergunte APENAS sobre decisões que as features NOVAS exigem. Decisões já registradas no spec.json são tratadas como contexto fixo (liste-as como "Decisões herdadas" no início do formulário para visibilidade, mas NÃO re-pergunte). Se uma decisão existente colide com a feature nova, sinalize o conflito explicitamente como pergunta.

**Formato obrigatório por pergunta:**
```
**Q[N]. [[Categoria]]** [Pergunta clara e objetiva]
- **A)** [Opção concreta] ← **recomendado** (se for a recomendação)
- **B)** [Opção alternativa]
> _Rationale: [Por que esta é a recomendada]_
```

**Regras do formulário:**
- Sempre ofereça A/B com recomendação explícita
- NUNCA jogue o ônus do design no usuário sem opções

**Categorias de discovery e relevância contextual:**

As categorias abaixo são o **universo possível** de perguntas. A IA **NÃO** pergunta todas mecanicamente — ela avalia o prompt e **suprime** categorias irrelevantes ao domínio, registrando a supressão com justificativa.

| Categoria | Sempre? | Quando suprimir |
|-----------|---------|----------------|
| **Funcional** | SIM | Nunca — sempre há decisão funcional a tomar |
| **Usuários** | SIM | Nunca — sempre há perfil de uso a definir |
| **NFRs (Performance, etc.)** | SIM | Nunca — todo projeto tem metas mensuráveis |
| **Deploy** | SIM | Nunca — a forma de entrega afeta a arquitetura |
| **Arquitetura** | SIM | Nunca — toda aplicação precisa de uma estrutura de pastas que comunique intenção |
| **Auth** | Condicional | Suprimir quando o prompt indica app offline/local sem contas (ex.: jogo local, CLI tool, widget) |
| **Persistência** | Condicional | Suprimir quando não há dados que sobrevivam à sessão (ex.: jogo sem save, ferramenta stateless) |
| **Segurança** | Condicional | Suprimir quando não há PII, rede, nem integrações externas (ex.: jogo offline, demo local) |

**Categorias PROIBIDAS no discovery (invariantes do pipeline):**
- **Testes:** o pipeline `/dev` e `/review` já impõem TDD, verify_cmd obrigatório, Gherkin e regressão. Perguntar ao usuário "quer testes?" é redundante e passível de gerar a ilusão de que testes são opcionais.

**Regra de supressão:** Se uma categoria condicional não se aplica ao domínio, a IA **não pergunta** e **não registra decisão** para ela. Em vez disso, registra um item na seção de Decisões com `label: "[Categoria] — N/A"`, `chosen: "Suprimido"` e `rationale` explicando por quê.

**Regra de foco:** Cada pergunta deve abordar uma **decisão que afeta a arquitetura, o código ou a experiência do usuário**. Perguntas cujas respostas não alteram nenhum artefato downstream são desperdício de interação e devem ser eliminadas.

**Exemplo de pergunta — Arquitetura / Estrutura de Pastas:**
```
**Q[N]. [[Arquitetura]]** Qual estrutura de pastas você prefere para este projeto?
- **A)** Herald Architecture (recomendada)
  ```
  src/
  ├── Api/                  # Entry (Controllers, Middlewares)
  ├── Application/          # Domain + Pure Business Rules
  │   ├── Entities/         # Rich Domain Entities + Value Objects
  │   ├── Features/         # Use Cases (Commands/Queries + Handlers)
  │   ├── Services/         # Domain Services
  │   └── Interfaces/       # Contracts (IRepository, IWebApi)
  └── Infrastructure/       # Concrete Implementations
      ├── Persistence/      # ORM, DbContext, UoW
      ├── Repositories/     # Repository implementations
      └── WebApis/          # External API integrations
  ```
  > _Rationale: Separação clara entre domínio e infraestrutura. Cada pasta comunica intenção — você olha e sabe exatamente onde colocar código novo._
- **B)** Convenções da Stack Escolhida
  > _Rationale: Adota as convenções de projeto e estrutura de pastas recomendadas pela tecnologia selecionada (ex: Clean Architecture para .NET, Feature-Based para Angular, App Router conventions para Next.js, etc.), sem impor um padrão externo. Ideal quando o time já domina o ecossistema e quer alinhar-se às práticas da comunidade._
> _Caso prefira outra estrutura, descreva abaixo ou cole um tree-view._
```

**Atores, UCs e Dicionário de Entidades — colete durante o discovery:**  
Extraia todos os Atores (usuários/sistemas externos), Casos de Uso (UCs) e Entidades Críticas.  
Para cada entidade, determine nome canônico, tipo (Domain | Actor | External | Value Object) e definição em uma frase. Isso previne divergência de nomenclatura.

Exemplo:
```
- Pedido (Domain): Representa uma requisição formal de compra submetida por um Comprador.
- Comprador (Actor): Usuário autenticado com permissão para criar e cancelar Pedidos.
- Pagamento (External): Serviço externo de gateway.
- Casos de Uso Identificados: "Processar Pagamento", "Criar Pedido".
```

**Invariantes do Sistema — identifique durante o discovery:**  
Regras que o sistema SEMPRE respeita, independente de evento ou trigger. São distintas de EARS porque não possuem condição de ativação — são condições permanentes.

Exemplos:
```
- Um Pedido cancelado jamais transita para qualquer estado que não sejam [cancelado].
- O saldo de conta nunca fica abaixo de zero.
- Toda operação que altera dados sensíveis gera entrada de auditoria.
```

**HALT OBRIGATÓRIO:** Não prossiga para Passo 3 até o usuário responder todas as perguntas.

```yaml
validation:
  - check: 'Todas as categorias obrigatórias foram cobertas (Funcional | Usuários | NFRs | Deploy | Arquitetura) e categorias condicionais (Auth | Persistência | Segurança) foram avaliadas quanto à relevância — cobertas ou explicitamente suprimidas com justificativa.'
    onFailure: halt
    message: 'Formulário de discovery incompleto. Não prossiga para Passo 3 sem cobertura das categorias obrigatórias e avaliação explícita das condicionais.'
    blocking: true
  - check: 'Ao menos uma entidade de domínio e um invariante foram identificados.'
    onFailure: warn
    message: 'Plano sem entidades ou invariantes será gerado com seções vazias. Considere revisitar o discovery.'
    blocking: false
```

### Passo 3 — Option Resolution e Auto-Assumption

Para cada pergunta respondida, registre a decisão via `spec_builder.py`:
```bash
python scripts/spec_builder.py decision --label "Persistência" --chosen "PostgreSQL (A)" --rationale "Banco relacional maduro para o domínio."
```

**Auto-Assumption:** Se o usuário submeter o formulário sem responder uma pergunta específica (campo em branco, letra "X", traço ou "-") → assume a recomendação e registre como decisão normalmente, informando:
```
⚠️ AUTO-ASSUMED: [Q3] Persistência: PostgreSQL (recomendado — sem resposta do usuário)
```

**Registro de Arquitetura / Estrutura de Pastas:**
Quando o usuário escolhe ou descreve uma estrutura de pastas, registre:
1. A decisão macro como `decision`:
   ```bash
   python scripts/spec_builder.py decision --label "Arquitetura" --chosen "Herald Architecture (A)" --rationale "Separação clara entre domínio e infraestrutura."
   ```
2. Cada pasta como `architecture-folder`:
   ```bash
   python scripts/spec_builder.py architecture-folder --path "src/Application/Entities" --purpose "Rich Domain Entities + Value Objects" --owner "Backend" --notes "Classes com { get; private set; }"
   ```
3. Se o usuário forneceu uma estrutura customizada, extraia cada pasta relevante e registre individualmente.

### Passo 4 — EARS Notation Formatting (Awesome Copilot)

Converta CADA requisito aprovado para EARS notation:

```
WHEN [trigger] THE SYSTEM SHALL [behavior]
WHILE [state] THE SYSTEM SHALL [behavior]  
IF [condition] THEN THE SYSTEM SHALL [response]
WHERE [feature included] THE SYSTEM SHALL [behavior]
```

**Anti-padrão proibido:**
```
❌ "O sistema deve ser rápido"
✅ WHEN user submits search THE SYSTEM SHALL return results within 500ms
```

**Todo requisito deve ser:**
- Testável de forma independente
- Com trigger/condição clara
- Com behavior mensurável

```yaml
validation:
  - check: 'Nenhum requisito usa linguagem vaga sem métrica (ex: "rápido", "eficiente", "seguro" isolados).'
    onFailure: halt
    message: 'Requisito vago detectado. Reformule em EARS com métrica antes de prosseguir.'
    blocking: true
  - check: 'Total de EARS requirements ≥ 5.'
    onFailure: halt
    message: 'Mínimo de 5 EARS não atingido. Retorne ao discovery e elicite requisitos faltantes.'
    blocking: true
```

### Passo 5 — Plan Document Generation (via spec_builder.py)

**ANTES de iniciar, determine o workspace root:**  
Use o caminho absoluto da pasta aberta na IDE (`workspaceFolder`). Nunca use `"."` literal. Se indisponível, pergunte: `"Em qual pasta devo salvar o plano?"`.

**FERRAMENTA:** `scripts/spec_builder.py` — CLI que a IA chama via terminal para construir o `spec.json` incrementalmente. Cada subcomando adiciona dados à seção correspondente. Ao final, `render` gera `spec.md`.

> **Nota de caminho:** `scripts/` é relativo ao diretório desta skill. Resolva o caminho absoluto: `python {skill_dir}/scripts/spec_builder.py`.

**Inicialização (apenas Cenários B e C — no Cenário A, pular):**
```bash
python scripts/spec_builder.py init --plan "{plan_name}" --title "{TITULO}" --overview "{visao geral}"
```
> A `overview` criada no `init` vira baseline imutável (`overview_lock`). Alterações incrementais devem ocorrer em nova run/backlog, não por edição da visão geral.

**Decisões (já registradas no Passo 3, mas podem ser adicionadas/atualizadas aqui):**
```bash
python scripts/spec_builder.py decision --label "Auth" --chosen "JWT (A)" --rationale "Stateless, escala horizontal."
```

**EARS Requirements (vinculados a UC obrigatoriamente):**
```bash
python scripts/spec_builder.py ear --id REQ-01 --uc-ref UC-01 --type WHEN --notation "WHEN user submits form THE SYSTEM SHALL validate all fields within 200ms."
```

**Arquitetura / Estrutura de Pastas (editável via spec):**
```bash
python scripts/spec_builder.py architecture-principle --text "Separação clara entre domínio, aplicação e infraestrutura"
python scripts/spec_builder.py architecture-component --text "Serviço de Orquestração de Pedidos"
python scripts/spec_builder.py architecture-folder --path "src/domain" --purpose "Regras de negócio" --owner "Backend" --notes "Sem dependência de framework"
```

**Dependências (pacotes/serviços por ambiente):**
```bash
python scripts/spec_builder.py dependency-package --name "fastapi" --kind "framework" --version "0.116.0" --install-cmd "pip install fastapi==0.116.0" --environments dev tst prd
python scripts/spec_builder.py dependency-service --name "postgres" --purpose "Persistência relacional" --start-cmd "docker compose up -d postgres" --healthcheck "pg_isready" --environments dev tst prd
```

```bash
# UC novo (default, gera stories no /dev):
python scripts/spec_builder.py uc --id UC-01 --name "Criar Pedido" --description "Submissao de novo pedido pelo comprador."

# UC inferido de codigo existente (NAO gera stories no /dev — apenas documenta):
python scripts/spec_builder.py uc --id UC-01 --name "Login" --description "Autenticacao de usuario." --origin inferred
```

**Diagrama Mermaid de Casos de Uso:**
```bash
# Escreva o mermaid em arquivo temporário e passe via --file
python scripts/spec_builder.py uc-diagram --file .temp/uc-diagram.mmd
# OU inline com \n
python scripts/spec_builder.py uc-diagram --mermaid "graph LR\n    User((Comprador))\n    ..."
```

**Drill-downs (1 por UC — OBRIGATÓRIO):**
```bash
python scripts/spec_builder.py drilldown --uc-id UC-01 --actor "Comprador" --preconditions "Usuario autenticado." --main-flow "Step 1" "Step 2" "Step 3" --postconditions "Pedido criado."
# Fluxos alternativos (se existirem)
python scripts/spec_builder.py alt-flow --uc-id UC-01 --id UC-01.FA1 --description "Validacao falha" --steps "Sistema exibe erros." "Usuario corrige campos."
```

**Entidades, Invariantes, NFRs:**
```bash
python scripts/spec_builder.py entity --name "Pedido" --type "Domain" --definition "Requisicao formal de compra."
python scripts/spec_builder.py invariant --text "Pedido cancelado jamais transita para outro estado."
python scripts/spec_builder.py nfr --label "Performance" --text "API response time < 500ms for 95th percentile."
```

**Verificação e Renderização:**
```bash
python scripts/spec_builder.py show       # resumo do estado atual
python scripts/spec_builder.py validate   # valida completude
python scripts/spec_builder.py render     # gera spec.md
```

> **Nota:** Os scripts auto-descobrem `.nexus/` a partir do diretório de trabalho. Paths explícitos como primeiro argumento ainda são aceitos para cenários especiais.  
> Cada subcomando faz upsert (idempotente) — chamar duas vezes com o mesmo ID atualiza em vez de duplicar.

**Seções do spec.md gerado (ordem):**
1. Visão Geral (imutável; baseline sistêmica da aplicação)
2. Decisões do Projeto
3. Especificação Funcional (UML)
   - Diagrama, Atores, Matriz de UCs
4. Drill-down de Casos de Uso
5. Associação UC↔EARS (sem órfãos)
6. Arquitetura e Estrutura de Pastas
7. Dependências (packages/services por ambiente dev/tst/prd)
8. Dicionário de Entidades
9. Invariantes do Sistema
10. NFRs

---

## ARTEFATOS PRODUZIDOS

```
.nexus/
├── spec.json                ← Fonte de verdade estruturada (cresce a cada /plan)
└── spec.md                  ← Visualização renderizada do spec.json (gerada por `render`)
```

---

## CRITÉRIOS DE SAÍDA DO `/plan`

O `/plan` está COMPLETO quando `spec_builder.py validate` passa sem erros:
- [ ] `spec.json` contém pelo menos 5 EARS requirements
- [ ] `spec.json` contém pelo menos 1 entidade no Dicionário
- [ ] `spec.json` contém pelo menos 1 decisão de projeto
- [ ] Drill-downs 1:1 com UCs na Matriz (zero omissões)
- [ ] Todas as questões do Discovery Form foram respondidas (ou auto-assumidas)
- [ ] Zero requisitos vagos (sem "rápido", "fácil", "robusto" sem métrica)
- [ ] `render` executado com sucesso → `spec.md` gerado

**Após `render` bem-sucedido, informe ao usuário:**
> Plano gerado em `.nexus/spec.md`  
> Execute `/dev` para iniciar a implementação.


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
  - OUTPUT RULE: Use `scripts/spec_builder.py` via terminal para construir o spec.json incrementalmente. Ao final, execute `render` para gerar spec.md e decision_manifest.json.
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
    - 'A Matriz de Casos de Uso DEVE conter a coluna ID com identificador único no formato UC-XX (ex: UC-01, UC-02). O ID é estável e usado como referência por todas as fases downstream (/proto, /dev).'
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
    - 'Decisões de auth/persistência sem Discovery Gate respondido ou auto-assumido'
```

---

## FLUXO OBRIGATÓRIO (execute em ordem)

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

Apresente o formulário de descoberta COMPLETO antes de prosseguir.

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
- Cubra: Funcional | Usuários | Auth | Persistência | NFRs | Segurança | Deploy | Testes

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
  - check: 'Todas as categorias obrigatórias foram cobertas (Funcional | Usuários | Auth | Persistência | NFRs | Segurança | Deploy | Testes).'
    onFailure: halt
    message: 'Formulário de discovery incompleto. Não prossiga para Passo 3 sem cobertura total.'
    blocking: true
  - check: 'Ao menos uma entidade de domínio e um invariante foram identificados.'
    onFailure: warn
    message: 'Plano sem entidades ou invariantes será gerado com seções vazias. Considere revisitar o discovery.'
    blocking: false
```

### Passo 3 — Option Resolution e Auto-Assumption

Para cada pergunta respondida, registre a decisão via `spec_builder.py`:
```bash
python scripts/spec_builder.py .nexus/{plan_name}/spec.json decision --label "Persistência" --chosen "PostgreSQL (A)" --rationale "Banco relacional maduro para o domínio."
```

**Auto-Assumption:** Se o usuário submeter o formulário sem responder uma pergunta específica (campo em branco, letra "X", traço ou "-") → assume a recomendação e registre como decisão normalmente, informando:
```
⚠️ AUTO-ASSUMED: [Q3] Persistência: PostgreSQL (recomendado — sem resposta do usuário)
```

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

**FERRAMENTA:** `scripts/spec_builder.py` — CLI que a IA chama via terminal para construir o `spec.json` incrementalmente. Cada subcomando adiciona dados à seção correspondente. Ao final, `render` gera `spec.md` + `decision_manifest.json`.

> **Nota de caminho:** `scripts/` é relativo ao diretório desta skill. Resolva o caminho absoluto: `python {skill_dir}/scripts/spec_builder.py`.

**Inicialização:**
```bash
python scripts/spec_builder.py {project_root}/.nexus/{plan_name}/spec.json init --plan "{plan_name}" --title "{TITULO}" --overview "{visao geral}"
```

**Decisões (já registradas no Passo 3, mas podem ser adicionadas/atualizadas aqui):**
```bash
python scripts/spec_builder.py {spec} decision --label "Auth" --chosen "JWT (A)" --rationale "Stateless, escala horizontal."
```

**EARS Requirements:**
```bash
python scripts/spec_builder.py {spec} ear --id REQ-01 --type WHEN --notation "WHEN user submits form THE SYSTEM SHALL validate all fields within 200ms."
```

**Atores:**
```bash
python scripts/spec_builder.py {spec} actor --name "Comprador" --type "Humanos" --responsibility "Criar e cancelar pedidos."
```

**Casos de Uso (Matriz):**
```bash
python scripts/spec_builder.py {spec} uc --id UC-01 --name "Criar Pedido" --description "Submissao de novo pedido pelo comprador."
```

**Diagrama Mermaid de Casos de Uso:**
```bash
# Escreva o mermaid em arquivo temporário e passe via --file
python scripts/spec_builder.py {spec} uc-diagram --file .temp/uc-diagram.mmd
# OU inline com \n
python scripts/spec_builder.py {spec} uc-diagram --mermaid "graph LR\n    User((Comprador))\n    ..."
```

**Drill-downs (1 por UC — OBRIGATÓRIO):**
```bash
python scripts/spec_builder.py {spec} drilldown --uc-id UC-01 --actor "Comprador" --preconditions "Usuario autenticado." --main-flow "Step 1" "Step 2" "Step 3" --postconditions "Pedido criado."
# Fluxos alternativos (se existirem)
python scripts/spec_builder.py {spec} alt-flow --uc-id UC-01 --id UC-01.FA1 --description "Validacao falha" --steps "Sistema exibe erros." "Usuario corrige campos."
```

**Entidades, Invariantes, NFRs:**
```bash
python scripts/spec_builder.py {spec} entity --name "Pedido" --type "Domain" --definition "Requisicao formal de compra."
python scripts/spec_builder.py {spec} invariant --text "Pedido cancelado jamais transita para outro estado."
python scripts/spec_builder.py {spec} nfr --label "Performance" --text "API response time < 500ms for 95th percentile."
```

**Verificação e Renderização:**
```bash
python scripts/spec_builder.py {spec} show       # resumo do estado atual
python scripts/spec_builder.py {spec} validate   # valida completude
python scripts/spec_builder.py {spec} render     # gera spec.md + decision_manifest.json
```

> **Nota:** `{spec}` é atalho para `{project_root}/.nexus/{plan_name}/spec.json`.  
> Cada subcomando faz upsert (idempotente) — chamar duas vezes com o mesmo ID atualiza em vez de duplicar.

**Seções do spec.md gerado (numeração fixa):**
1. Visão Geral
2. Decisões do Projeto
3. Requisitos EARS
4. Especificação Funcional (UML) — Diagrama, Atores, Matriz
5. Drill-down de Casos de Uso
6. Dicionário de Entidades
7. Invariantes do Sistema
8. NFRs

---

## ARTEFATOS PRODUZIDOS

```
.nexus/{plan_name}/
├── spec.json                ← Fonte de verdade estruturada (construída incrementalmente)
├── spec.md                  ← Visualização renderizada do spec.json (gerada por `render`)
└── decision_manifest.json   ← Formato compacto para propagação em stories/tasks (gerado por `render`)
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
- [ ] `render` executado com sucesso → `spec.md` + `decision_manifest.json` gerados

**Após `render` bem-sucedido, informe ao usuário:**
> Plano gerado em `.nexus/{plan_name}/spec.md`  
> Execute `/dev` para iniciar a implementação.


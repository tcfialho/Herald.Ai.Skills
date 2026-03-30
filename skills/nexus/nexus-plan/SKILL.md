---
name: Nexus /plan
description: Stage 1 do Framework Nexus. Elimina ambiguidade através de Context Engineering, Complexity Assessment 5D, Discovery Gates interativos e geração de plano em EARS notation. ZERO código funcional é escrito nesta fase.
---

ACTIVATION-NOTICE: Este arquivo define as regras estritas para geração de planos Nexus. Leia integralmente antes de qualquer ação.

```yaml
activation_instructions:
  - STEP 1: Ler este arquivo SKILL.md completo antes de qualquer análise ou resposta.
  - STEP 2: Internalizar o constitutional_gate e os autonomy_boundaries abaixo.
  - STEP 3: Executar o FLUXO OBRIGATÓRIO em ordem, respeitando cada HALT e validation block.
  - LANGUAGE RULE: Todas as perguntas de discovery e o spec.md gerado DEVEM estar em PT-BR.
  - OUTPUT RULE: O spec.md DEVE ser salvo em `.nexus/{plan_name}/spec.md` via tool call.
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
    - 'O número de Drill-downs gerados DEVE ser EXATAMENTE IGUAL ao número de UCs listados na Matriz. É estritamente PROIBIDO omitir, resumir ou pular qualquer UC. Faça o drill-down 1:1.'
    - 'Cada Drill-down de UC DEVE possuir estrutura fixa: Ator, Descrição, Pré-Condições, Fluxo Numerado, Pós-condições e Micro-Dicionário de Entidades Envolvidas.'
    - 'ZERO linhas de código funcional durante /plan — apenas especificação.'
    - 'NUNCA inclua requisito vago sem métrica: substituir "rápido/robusto/fácil" por medidas concretas.'
    - 'O Dicionário de Entidades DEVE ter ao menos uma entrada antes de gerar o spec.md.'
    - 'SE tier == STANDARD ou COMPLEX: `set_component_diagram()` é OBRIGATÓRIO. SE tier == SIMPLE: omitir.'
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

### Passo 2 — Complexity Assessment (AIOS 5-Dimensions)

Execute `scripts/prompt_expander.py` mentalmente ou via:
```bash
python scripts/prompt_expander.py "<prompt do usuário>"
```

**Exiba o assessment ao usuário antes de prosseguir:**

| Dimensão | Score (1-5) | Guia |
|----------|-------------|------|
| **Scope** | ? | 1=1-5 arquivos, 3=6-15, 5=16+ |
| **Integration** | ? | 1=Zero APIs, 3=1-2, 5=3+ |
| **Infrastructure** | ? | 1=Sem mudanças, 3=1 serviço, 5=2+ novos |
| **Knowledge** | ? | 1=Bem-conhecido, 3=Alguma pesquisa, 5=Desconhecido |
| **Risk** | ? | 1=Sem impacto crítico, 3=Moderado, 5=Crítico |

**Total:** Soma → `≤8 SIMPLE` | `9-15 STANDARD` | `≥16 COMPLEX`

**Estimativas baseadas no tier:**
- SIMPLE: /plan 30-60min | /dev 2-4h | /review 30min
- STANDARD: /plan 2-4h | /dev 1-2 dias | /review 1-2h
- COMPLEX: /plan 1-2 dias | /dev 3-5 dias | /review 2-4h

### Passo 3 — Interactive Discovery Gates (Spec Kitty)

**MUDE SEU ESTADO PARA: `WAITING_FOR_DISCOVERY_INPUT`**

Apresente o formulário de descoberta COMPLETO antes de prosseguir. Use o `prompt_expander.py` para gerar perguntas contextuais.

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

**Mapa de Componentes (C4) — OBRIGATÓRIO para STANDARD e COMPLEX:**  
> **REGRA:** Se tier calculado no Passo 2 for `STANDARD` ou `COMPLEX`, você DEVE produzir o diagrama C4 antes de prosseguir para o Passo 4. Se for `SIMPLE`, pule.
```
flowchart TD
  subgraph UI ["Camada: Presentation"]
    A["React App / API Client"]
  end
  subgraph App ["Camada: Application"]
    B["UseCaseHandlers"]
  end
  subgraph Core ["Camada: Domain"]
    C["Entities + Repos (interfaces)"]
  end
  subgraph Infra ["Camada: Infrastructure"]
    D["DB / External APIs"]
  end
  A --> B --> C
  C --> D
```

**HALT OBRIGATÓRIO:** Não prossiga para Passo 4 até o usuário responder todas as perguntas.

```yaml
validation:
  - check: 'Todas as categorias obrigatórias foram cobertas (Funcional | Usuários | Auth | Persistência | NFRs | Segurança | Deploy | Testes).'
    onFailure: halt
    message: 'Formulário de discovery incompleto. Não prossiga para Passo 4 sem cobertura total.'
    blocking: true
  - check: 'Ao menos uma entidade de domínio e um invariante foram identificados.'
    onFailure: warn
    message: 'Plano sem entidades ou invariantes será gerado com seções vazias. Considere revisitar o discovery.'
    blocking: false
```

### Passo 4 — Option Resolution e Auto-Assumption

Para cada pergunta respondida, execute via `scripts/option_resolver.py`:
```python
resolver = OptionResolver(plan_name=plan_name)
resolver.record_from_form(form)  # registra todas as decisões
resolver.save(f".nexus/{plan_name}/decisions.json")
```

**Auto-Assumption:** Se o usuário submeter o formulário sem responder uma pergunta específica (campo em branco, letra "X", traço ou "-") → assume a recomendação e loga imediatamente:
```
⚠️ AUTO-ASSUMED: [Q3] Persistência: PostgreSQL (recomendado — sem resposta do usuário)
```

Registre via `assumption_tracker.py`:
```python
tracker = AssumptionTracker(plan_name)
tracker.import_from_resolver(resolver)
tracker.save(f".nexus/{plan_name}/assumptions.json")
```

### Passo 5 — EARS Notation Formatting (Awesome Copilot)

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

### Passo 6 — Plan Document Generation

**ANTES de instanciar o gerador, determine o workspace root:**  
Use o caminho absoluto da pasta aberta na IDE — disponível no seu contexto de execução como `workspaceFolder`. Nunca use `"."` literal. Se por algum motivo o `workspaceFolder` não estiver disponível no contexto, pergunte ao usuário: `"Em qual pasta devo salvar o plano?"`.

Execute `scripts/plan_generator.py` para gerar o artefato final:
```python
# project_root = workspaceFolder do contexto da IDE (caminho absoluto)
generator = PlanGenerator(plan_name=plan_name, project_root=project_root)

# 1. Estrutura de Especificação Funcional (Padrão Estrito UML do /gera-doc-funcional)
# REQUISITO: O Diagrama DEVE ser graph LR, nós tipo circular com emojis, conexões -.-o|extend/include|
generator.add_use_case_diagram("graph LR...") 
# REQUISITO: Tabela Markdown (Ator | Tipo | Responsabilidade)
generator.add_actor_dictionary(...)
generator.add_use_case_matrix(...)
# REQUISITO: Cada Drill-down obriga -> Ator, Descrição, Pré-Condições, Fluxo Numerado, Pós-condições, Micro-Dicionário de Entidades
for uc in use_cases:
    generator.add_uc_drilldown(nome=uc.name, fluxo=uc.flow, entidades=uc.entities)

# 2. Estrutura Nexus Core (EARS, Entities, Invariants, C4)
# Adicione todos os EARS requirements
for req in ears_requirements:
    generator.add_ears_requirement(req["notation"], req["category"])
# Adicione entidades do domínio (coletadas no Passo 3)
for entity in domain_entities:
    generator.add_entity(entity["name"], entity["definition"], entity["type"])
# Adicione invariantes do sistema (coletadas no Passo 3)
for invariant in system_invariants:
    generator.add_invariant(invariant)
# Mapa de componentes C4 — OBRIGATÓRIO se tier == STANDARD ou COMPLEX; omitir se SIMPLE
if assessment.tier in ("STANDARD", "COMPLEX"):
    generator.set_component_diagram("""
flowchart TD
  subgraph UI ["Presentation"]
    A["<componente>"]
  end
  ...
""")
# Adicione NFRs, constraints, edge cases
generator.add_nfr("API response time < 500ms for 95th percentile")
# Gere o arquivo
plan_path = generator.generate(assessment, resolver, raw_prompt)
```

**Arquivo gerado: `.nexus/{plan_name}/spec.md`**

---

## ARTEFATOS PRODUZIDOS

```
.nexus/{plan_name}/
├── spec.md           ← Plano completo com EARS (entrega principal)
├── decisions.json    ← Decisões A/B registradas
└── assumptions.json  ← Suposições auto-assumidas
```

---

## CRITÉRIOS DE SAÍDA DO `/plan`

O `/plan` está COMPLETO quando:
- [ ] `spec.md` contém a Seção de Casos de Uso completa (Diagrama, Dicionário, Matriz, Drill-downs com fluxos) e Dicionário de Entidades
- [ ] A contagem de Drill-downs no documento deve obrigatoriamente bater 1:1 com a contagem de UCs listados na Matriz da seção 5.3 (zero omissões).
- [ ] `spec.md` contém pelo menos 5 EARS requirements
- [ ] Todas as questões do Discovery Form foram respondidas (ou auto-assumidas)
- [ ] `decisions.json` existe com todas as decisões registradas
- [ ] `assumptions.json` lista todas as suposições
- [ ] Zero requisitos vagos (sem "rápido", "fácil", "robusto" sem métrica)

**Após verificação de todos os critérios, informe ao usuário:**
> ✅ Plano gerado em `.nexus/{plan_name}/spec.md`  
> Execute `/dev` para iniciar a implementação.


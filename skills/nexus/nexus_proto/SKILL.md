---
name: Nexus /proto
description: >
  Stage 1.5 do Framework Nexus. Roda após /plan e antes de /dev.
  Gera wireframes SVG A/B para cada tela identificada no spec.md,
  coleta decisões visuais do usuário e persiste em proto.json.
  ZERO código funcional é escrito nesta fase.
depends_on: /plan
---

ACTIVATION-NOTICE: Este arquivo define as regras estritas para geração de wireframes Nexus /proto. Leia integralmente antes de qualquer ação.

```yaml
activation_instructions:
  - STEP 1: Ler este SKILL.md completo.
  - STEP 2: Localizar e ler `.nexus/{plan_name}/spec.md` — obrigatório antes de qualquer wireframe.
  - STEP 3: Executar o FLUXO OBRIGATÓRIO em ordem, respeitando cada HALT e estado de iteração.
  - LANGUAGE RULE: Todo output ao usuário em PT-BR.
  - OUTPUT RULE: Decisões salvas em `.nexus/{plan_name}/proto.json` via proto_generator.py.
  - INVARIANTE: Nenhuma linha de código funcional durante /proto.
```

# 🖼️ NEXUS `/proto` — WIREFRAME A/B INTERATIVO

## OBJETIVO

Transformar as telas e componentes identificados no `spec.md` em wireframes SVG comparativos (A vs B),
coletando a decisão visual do usuário para cada dimensão em disputa antes de iniciar `/dev`.

**INVARIANTE:** O `/proto` não gera código funcional. Gera apenas especificação visual.

```yaml
constitutional_gate:
  article: II
  name: "Rigor Visual e Pureza de Fase"
  severity: BLOCK
  validation:
    - 'Cada wireframe A/B DEVE isolar exatamente UMA dimensão em disputa. O restante é idêntico.'
    - 'Todo SVG wireframe DEVE incluir anotações de intenção, não apenas descrição visual.'
    - 'O arquivo proto.json DEVE registrar: screen_id, dimension, chosen_variant, change_requests[].'
    - 'ZERO código funcional durante /proto — apenas SVG estático e especificação visual.'
    - 'Cada screen DEVE ter ao menos um ciclo A/B completo antes de ser marcada como decided.'
    - 'O /proto está COMPLETO somente quando todas as screens extraídas do spec.md forem decided.'
  on_violation:
    action: BLOCK
    message: |
      VIOLAÇÃO CONSTITUCIONAL: Wireframe incompleto ou decisão não registrada.
      Não prossiga para /dev sem todas as screens com status decided.

autonomy_boundaries:
  may_invent:
    - 'Dimensões em disputa inferíveis dos UCs (ex: posição de nav, densidade de lista, layout de form)'
    - 'Variantes A/B para dimensões óbvias não especificadas no spec.md'
    - 'Anotações de intenção baseadas em boas práticas de UX'
  must_not_invent:
    - 'Funcionalidades não presentes no spec.md'
    - 'Entidades de domínio não listadas no Dicionário de Entidades do spec.md'
    - 'Estados de UI sem EARS requirement de backing'
```

---

## FLUXO OBRIGATÓRIO

### Passo 1 — Leitura do spec.md

Leia `.nexus/{plan_name}/spec.md` e extraia:

```python
screens = proto_generator.extract_screens(spec_path)
```

**O que extrair do spec.md:**
- Cada UC com interação visual → 1 screen candidate
- Entidades com CRUD → screen de listagem + screen de formulário
- Fluxos com estados visuais distintos (ex: empty state, loading, error) → screen variants

**Exiba o inventário ao usuário antes de prosseguir:**

```
📋 Screens identificadas para /proto:
  [ ] S01 — Lista de Tarefas       (UC01, UC03)
  [ ] S02 — Formulário de Criação  (UC01)
  [ ] S03 — Estado Vazio           (WHILE lista vazia)
  Total: 3 screens | 0 decided | 3 pending
```

**HALT:** Confirme o inventário com o usuário. Adicione ou remova screens se solicitado.

---

### Passo 2 — Geração de Wireframe A/B

Para cada screen pendente, execute em sequência:

#### 2.1 — Identificar a Dimensão em Disputa

Antes de gerar o SVG, declare explicitamente:

```
🎯 Screen: S01 — Lista de Tarefas
   Dimensão em disputa: posição dos filtros (topo vs rodapé)
   Impacto: determina se o contexto (filtro ativo) precede ou sucede a ação (adicionar)
   Igual em A e B: input de criação, itens da lista, counter, estados completed/pending
```

**Regras para escolher a dimensão:**
- Priorize decisões que afetam hierarquia de informação ou fluxo primário
- Uma dimensão por wireframe — sem misturar layout com densidade no mesmo par
- Se não houver dimensão óbvia em disputa, use: `A = compact` vs `B = spacious`

#### 2.2 — Gerar o SVG A/B

Gere um único SVG seguindo o padrão abaixo:

```
ESTRUTURA DO SVG A/B:
┌─────────────────────────────────────────────────────┐
│  [label da decisão — 1 linha, centralizado no topo] │
├───────────────────┬─────────────────────────────────┤
│  [Badge A]        │  [Badge B]                      │
│  [Card wireframe] │  [Card wireframe]               │
│                   │                                 │
│  • intenção A     │  • intenção B                   │
│  [btn Escolher A] │  [btn Escolher B]               │
├───────────────────┴─────────────────────────────────┤
│  tudo igual exceto: [dimensão em disputa]           │
└─────────────────────────────────────────────────────┘
```

**Regras obrigatórias do SVG:**
- `viewBox="0 0 680 H"` — calcule H pelo conteúdo + 40px buffer
- Tokens CSS obrigatórios: `var(--color-background-primary)`, `var(--color-background-secondary)`,
  `var(--color-background-info)`, `var(--color-border-tertiary)`, `var(--color-border-secondary)`,
  `var(--color-text-info)`, `var(--color-text-secondary)`, `var(--color-text-tertiary)`
- Classes de texto: `class="t"` (14px), `class="ts"` (12px), `class="th"` (14px 500w)
- `stroke-width="0.5"` para todas as bordas de cards
- Anotações de intenção: texto 10-11px, `fill="var(--color-text-tertiary)"`, abaixo do wireframe
- Separador central: linha vertical tracejada entre A e B
- Rodapé da decisão: rect com `fill="var(--color-background-secondary)"` + texto da dimensão
- Badge A: `fill="var(--color-background-info)"` + `fill="var(--color-text-info)"`
- Badge B: `fill="var(--color-background-secondary)"` + borda `var(--color-border-secondary)`
- Estados visuais explícitos: checkbox checked/unchecked, texto riscado, pills ativas/inativas
- Botões "Escolher A/B": `fill="var(--color-background-secondary)"`,
  borda `var(--color-border-secondary)`, texto `class="ts"`

**O SVG NÃO deve conter:**
- Gradientes, sombras, blur ou efeitos visuais ricos (wireframe é estrutural)
- Texto em inglês (labels em PT-BR)
- Dados reais de negócio — use placeholders coerentes com o domínio
- Mais de 2 variantes por SVG

#### 2.3 — Persistência Obrigatória do SVG em Disco

> **REGRA:** O chat não consegue renderizar SVG inline. Todo wireframe gerado DEVE ser
> salvo em arquivo imediatamente após a geração, antes de aguardar input do usuário.

**Caminho obrigatório:**
```
.nexus/{plan_name}/{screen_id}_iter{N}.svg
```
- `{screen_id}` — ex: `S01`
- `{N}` — número da iteração atual (começa em 1 e incrementa a cada `novo` ou change request)

**Exemplo:** `.nexus/todo-app/S01_iter1.svg`

Após salvar, exiba **obrigatoriamente** a mensagem:
```
📂 SVG salvo em: .nexus/{plan_name}/{screen_id}_iter{N}.svg
   Abra o arquivo no VS Code ou em qualquer browser para visualizar o wireframe.
```

Use a tool `create_file` (ou `replace_file_content` se já existir) para escrever o arquivo.
Nunca aguarde a decisão do usuário sem antes ter persistido o SVG em disco.

---

### Passo 3 — Coleta de Decisão (Loop Interativo)

**MUDE SEU ESTADO PARA: `WAITING_FOR_PROTO_INPUT`**

Após exibir o SVG, apresente as opções:

```
Responda com:
  A        → escolher variante A
  B        → escolher variante B
  novo     → gerar novo par A/B com outra dimensão em disputa
  [texto]  → descrever mudança específica ("quero A mas com os filtros como pills menores")
```

**Tratamento de cada resposta:**

| Input | Ação |
|-------|------|
| `A` ou `B` | Registra decisão → avança para próxima screen |
| `novo` | Gera novo par A/B com dimensão diferente para a mesma screen |
| texto livre | Aplica mudança na variante mais próxima → exibe wireframe atualizado → volta ao HALT |

**Regra de change request:**
- Máximo 5 iterações por screen antes de forçar decisão
- A cada iteração, registre o change_request no proto.json
- Se o usuário pedir mudança que implique nova funcionalidade → `BLOCK` com mensagem:
  ```
  ⚠️ Esta mudança introduz funcionalidade não presente no spec.md.
  Retorne ao /plan para atualizar o spec antes de continuar o /proto.
  ```

---

### Passo 4 — Registro da Decisão

Para cada screen decidida, execute:

```python
generator = ProtoGenerator(plan_name=plan_name, spec_path=spec_path)
generator.record_decision(
    screen_id="S01",
    screen_name="Lista de Tarefas",
    dimension="posição dos filtros",
    variant_a_intent="filtros → contexto primeiro, input é ação secundária",
    variant_b_intent="input → ação imediata, filtros são refinamento",
    chosen="A",
    change_requests=["quero pills menores", "remover contador do rodapé"],
    svg_final=svg_string,
)
generator.save(f".nexus/{plan_name}/proto.json")
```

**Exiba feedback imediato:**
```
✅ S01 decidida → Variante A (2 change requests aplicados)
   Próxima: S02 — Formulário de Criação
```

---

### Passo 5 — Geração do Sumário Visual

Quando todas as screens estiverem `decided`, gere `.nexus/{plan_name}/wireframes.md`:

```markdown
# Wireframes: {plan_name}

## Decisões Visuais

| Screen | Dimensão | Escolha | Iterações |
|--------|----------|---------|-----------|
| S01 — Lista de Tarefas | posição dos filtros | A — filtros no topo | 3 |
| S02 — Formulário | layout de campos | B — single column | 1 |

## Anotações de Intenção por Screen

### S01 — Lista de Tarefas
**Variante escolhida:** A
**Intenção:** filtros no topo estabelecem contexto antes da ação
**Change requests aplicados:**
- pills de filtro com altura reduzida (22px → 18px)
- counter movido para inline com os filtros

[SVG final embedado como referência]
```

---

## ARTEFATOS PRODUZIDOS

```
.nexus/{plan_name}/
├── spec.md           ← (existente, gerado pelo /plan)
├── decision_manifest.json  ← (existente — decisões compactas para propagação)
├── proto.json        ← decisões visuais + change request history  [NOVO]
├── wireframes.md     ← sumário visual com SVGs finais             [NOVO]
├── S01_iter1.svg     ← wireframe A/B salvo para visualização       [NOVO]
├── S01_iter2.svg     ← iteração após change request                [NOVO]
└── S02_iter1.svg     ← wireframe da próxima screen                 [NOVO]
```

> **Visualização:** Abra qualquer `.svg` na pasta `.nexus/{plan_name}/` no VS Code
> (aba Preview) ou arraste para o browser. O chat não renderiza SVG inline.

---

## CRITÉRIOS DE SAÍDA DO `/proto`

O `/proto` está COMPLETO quando:
- [ ] Todas as screens do inventário têm status `decided`
- [ ] `proto.json` existe com cada screen registrada (chosen, dimension, change_requests[])
- [ ] `wireframes.md` existe com a tabela de decisões e anotações de intenção
- [ ] Nenhuma decisão introduziu funcionalidade ausente no `spec.md`
- [ ] Máximo de iterações por screen não foi ultrapassado (≤5)

**Após verificação, informe ao usuário:**
> ✅ Proto completo — {N} screens decididas, {M} change requests aplicados.
> Execute `/dev` para iniciar a implementação.
> O `/dev` deve referenciar `.nexus/{plan_name}/proto.json` para fidelidade visual.

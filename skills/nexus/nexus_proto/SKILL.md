---
name: Nexus /proto
description: >
  Stage 1.5 do Framework Nexus. Fase OPCIONAL entre /plan e /dev.
  Explora layouts via wireframes A/B, coleta decisões visuais do usuário
  e registra em visual.json via visual_builder.py.
  ZERO código funcional é escrito nesta fase.
depends_on: /plan
---

# 🖼️ NEXUS `/proto` — EXPLORAÇÃO VISUAL A/B

## 🚦 GATE DE DEPENDÊNCIA (verificar ANTES de qualquer ação)

```
Pipeline: /plan → /proto (opcional) → /dev → /review
                  ^^^^^^ VOCÊ ESTÁ AQUI
```

**Dependência obrigatória:** `/plan` concluído (`spec.json` com UCs registrados)

Antes de executar qualquer comando do `visual_builder.py`:
1. Verifique se `.nexus/spec.json` existe
2. Verifique se o spec tem ao menos 1 caso de uso registrado

**Se `spec.json` não existir ou estiver vazio:** HALT — informe ao usuário:
> spec.json não encontrado ou incompleto. Execute `/plan` primeiro.

**Se houver uma run ativa em `.nexus/runs/`:** WARN — o `/dev` já foi iniciado e o visual.json NÃO será incorporado automaticamente. Para incluir decisões visuais, o backlog precisa ser recriado.

> O script `visual_builder.py init` já aplica essas validações automaticamente.

---

## OBJETIVO

Transformar as telas identificadas no spec.json em decisões de layout registradas em `visual.json`.
A IA explora opções visuais (via SVG, canvas ou descrição), o usuário decide, e o script registra.

**INVARIANTE:** O `/proto` não gera código funcional. Gera apenas especificação visual.

**FASE OPCIONAL:** Nem todo projeto precisa de `/proto`. Se o projeto não tem UI, ou se o layout é óbvio, pule direto para `/dev`. O `/dev` funciona normalmente sem `visual.json`.

---

## FERRAMENTA CENTRAL: `scripts/visual_builder.py`

> **Nota de caminho:** `scripts/` é relativo ao diretório desta skill. Resolva o caminho absoluto: `python {skill_dir}/scripts/visual_builder.py`.

A IA **NUNCA** escreve visual.json diretamente. Toda leitura e escrita passa por `visual_builder.py`:

```
BUILD:     init, add-screen, decide, add-component
CONTEXT:   context [--screen SXX]
DISPLAY:   show, validate
```

O `visual.json` registra decisões finais + contexto dos UCs importado do spec. Sem variantes A/B, sem SVGs. O SVG é ferramenta de comunicação entre IA e usuário, não artefato de execução.

> **Nota:** Os scripts auto-descobrem `.nexus/` a partir do diretório de trabalho. Paths explícitos como primeiro argumento ainda são aceitos para cenários especiais.

---

## PRÉ-CONDIÇÃO OBRIGATÓRIA

Antes de iniciar:
1. Verifique que `.nexus/spec.json` existe (produzido por `/plan`)
2. Crie o visual.json:
```bash
python scripts/visual_builder.py init
```

---

## FLUXO OBRIGATÓRIO

### Passo 1 — Leitura de Contexto e Inventário de Screens

**1a. Leia o contexto extraído do spec:**

O `init` importa automaticamente os drill-downs de cada UC (ator, fluxo principal, fluxos alternativos, pré/pós-condições). Consulte-os antes de inventariar telas:

```bash
python scripts/visual_builder.py context
```

Isso exibe o resumo de todos os UCs sem precisar reabrir o `spec.json` inteiro.

**1b. Identifique telas a partir dos fluxos:**

Com o contexto carregado, mapeie screens:
- Cada UC cujo fluxo principal descreve interação visual → screen candidate
- UCs que compartilham a mesma superfície (ex: HUD + arena no mesmo canvas) → screen única com múltiplos `uc-refs`
- Entidades com CRUD → listagem + formulário
- Estados especiais (empty state, loading, error) → screen variant

**A granularidade é por Caso de Uso, não por story.** Um UC gera 1+ screens. Múltiplos UCs podem convergir para 1 screen se compartilham a mesma tela.

**1c. Registre cada screen identificada:**
```bash
python scripts/visual_builder.py add-screen --id S01 --name "Lista de Tarefas" --uc-refs UC-01 UC-03
python scripts/visual_builder.py add-screen --id S02 --name "Formulario de Criacao" --uc-refs UC-01
```

Exiba o inventário e confirme com o usuário:
```bash
python scripts/visual_builder.py show
```

**HALT:** Confirme o inventário com o usuário. Adicione ou remova screens se solicitado.

---

### Passo 2 — Exploração A/B (por screen)

Para cada screen, a IA:

1. **Carrega o contexto dos UCs da screen** — obrigatório antes de desenhar qualquer wireframe:
   ```bash
   python scripts/visual_builder.py context --screen S01
   ```
   Isso exibe os fluxos, atores e condições **apenas** dos UCs referenciados pela screen, sem poluir com o spec inteiro.

2. **Identifica a dimensão em disputa** — o ponto onde existem 2+ abordagens válidas. A dimensão deve ser derivada dos fluxos do UC (ex: se o fluxo tem 3 passos de interação, o wireframe deve acomodar esses passos).
   ```
   Screen: S01 — Lista de Tarefas (UC-01: criar tarefa, UC-03: filtrar)
   Dimensão: posição dos filtros (topo vs lateral)
   Contexto: UC-03.FP exige 4 critérios de filtro simultâneos
   ```

3. **Gera wireframe A/B** — via SVG salvo em disco ou canvas interativo
   - SVGs vão para `.nexus/wireframes/{screen_id}_iter{N}.svg`
   - Canvas pode ser usado como alternativa ao SVG
   - A IA explica a intenção de cada variante **referenciando os passos do fluxo do UC**

4. **Coleta a decisão do usuário:**
   ```
   Responda com:
     A        → escolher variante A
     B        → escolher variante B
     novo     → gerar novo par com outra dimensão
     [texto]  → descrever mudança ("quero A mas com pills menores")
   ```

**Regras da exploração:**
- Uma dimensão por wireframe — sem misturar layout com densidade
- Máximo 5 iterações por screen antes de forçar decisão
- Se mudança implica funcionalidade nova → BLOCK e voltar ao `/plan`
- O wireframe DEVE refletir os passos do fluxo do UC — não invente interações ausentes no spec

---

### Passo 3 — Registro da Decisão

Quando o usuário decide, a IA registra via CLI:

```bash
# Layout geral da tela
python scripts/visual_builder.py decide --screen S01 \
  --layout "Filtros no topo com pills 22px horizontais. Lista abaixo com checkbox e texto. Input de criacao inline no rodape."

# Componentes com spec individual
python scripts/visual_builder.py add-component --screen S01 \
  --name FilterBar --spec "Pills 22px horizontais no topo. Cor ativa: primary. Max 4 filtros visiveis."

python scripts/visual_builder.py add-component --screen S01 \
  --name TaskList --spec "Checkbox + texto por item. Strikethrough quando completa. Scroll vertical."

python scripts/visual_builder.py add-component --screen S01 \
  --name CreateInput --spec "Input inline no rodape. Botao Criar a direita. Placeholder: Nova tarefa."
```

**O que registrar em cada componente:**
- Posição e dimensões relevantes
- Comportamento visual (estados, interações)
- Restrições de estilo mencionadas pelo usuário

Repita Passos 2-3 para cada screen pendente.

---

### Passo 4 — Validação e Conclusão

Quando todas as screens tiverem layout e componentes:

```bash
python scripts/visual_builder.py validate
python scripts/visual_builder.py show
```

O `validate --spec` verifica:
- Todas as screens têm `layout_decision` e `components`
- Todos os UCs do spec têm ao menos uma screen associada

**Após validação, informe ao usuário:**
> Proto completo — {N} screens, {M} componentes.
> Execute `/dev` para iniciar a implementação.
> O backlog detecta visual.json automaticamente ao lado do spec.json.

---

## COMO O `/dev` CONSOME O VISUAL

O `/dev` **não lê** visual.json diretamente. O merge é automático no `backlog.py init`:

```bash
python backlog.py init
```

Se `visual.json` existir no mesmo diretório do spec.json (`.nexus/`), o backlog importa as screens automaticamente para `context.screens`, indexadas por UC. Quando a IA pede contexto de uma task (via `next` ou `context`), o layout aparece:

```
LAYOUT (telas do UC-01):
  S01 — Lista de Tarefas:
    Filtros no topo com pills 22px. Lista abaixo com checkbox e texto.
    Componentes:
      FilterBar: Pills 22px horizontais no topo. Cor ativa: primary.
      TaskList: Checkbox + texto por item. Strikethrough quando completa.
```

Se o `/proto` não foi executado, o `/dev` funciona normalmente — a seção LAYOUT simplesmente não aparece no contexto.

---

## ARTEFATOS PRODUZIDOS

```
.nexus/
├── spec.json               ← (existente, gerado pelo /plan — NÃO modificado)
├── visual.json             ← Decisões visuais finais (screens + componentes)
└── wireframes/             ← SVGs de exploração (referência visual, descartáveis)
    ├── S01_iter1.svg
    ├── S01_iter2.svg
    └── S02_iter1.svg
```

---

## CRITÉRIOS DE SAÍDA DO `/proto`

O `/proto` está COMPLETO quando `visual_builder.py validate` passa:
- [ ] Todas as screens têm `layout_decision`
- [ ] Todas as screens têm ao menos 1 componente
- [ ] Todos os UCs do spec têm screen associada
- [ ] Nenhuma decisão introduziu funcionalidade ausente no spec

---

## REGRAS DO SVG (quando usar wireframes SVG)

Se a IA optar por gerar wireframes SVG para exploração:

- `viewBox="0 0 680 H"` — calcule H pelo conteúdo + 40px buffer
- Tokens CSS: `var(--color-background-primary)`, `var(--color-border-tertiary)`, etc.
- Labels em PT-BR, dados placeholder coerentes com o domínio
- Sem gradientes, sombras ou efeitos ricos — wireframe é estrutural
- Salvar em: `.nexus/wireframes/{screen_id}_iter{N}.svg`
- Exibir mensagem após salvar:
  ```
  SVG salvo em: .nexus/wireframes/S01_iter1.svg
  Abra no VS Code ou browser para visualizar.
  ```

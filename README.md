# Herald.Ai.Skills

Repositório centralizado para gerenciamento de recursos de Inteligência Artificial aplicados ao desenvolvimento de software.

## 🎯 Propósito

Este repositório contém uma coleção curada de **Skills**, **Rules**, **Instructions**, **Workflows** e outros recursos AI projetados para aumentar a produtividade e qualidade no desenvolvimento de software.

## 📁 Estrutura do Repositório

```
Herald.Ai.Skills/
├── skills/                           # Skills - padrão aberto (todas IDEs)
│   └── nome-da-skill/                # Uma subpasta por skill (nome = identificador)
│       └── SKILL.md                  # ⚠️ Nome fixo obrigatório
├── workflows/                        # Workflows (exclusivo Windsurf)
│   └── nome-do-workflow/             # Uma subpasta por workflow
│       └── nome-do-workflow.md
├── rules/                            # Rules
│   ├── cursor/                       # ⚠️ Rules do Cursor ficam aqui (.mdc)
│   │   └── nome-da-rule.mdc
│   └── windsurf/                     # ⚠️ Rules do Windsurf ficam aqui (.md)
│       └── nome-da-rule.md
├── steering/                         # Steering (exclusivo Kiro)
│   └── nome-do-steering/             # Uma subpasta por conjunto de steerings
│       └── nome-do-steering.md
├── instructions/                     # Custom Instructions (exclusivo Copilot)
│   ├── global/                       # ⚠️ Ao usar: rename p/ copilot-instructions.md
│   │   └── nome-do-conjunto/         # Uma subpasta por conjunto
│   │       └── copilot-instructions.md  # Nome fixo obrigatório ao instalar
│   └── workspace/                    # Workspace-scoped; applyTo estreita o escopo
│       └── nome-do-conjunto/         # Uma subpasta por conjunto
│           └── nome.instructions.md  # ⚠️ Extensão obrigatória: .instructions.md
├── agents/                           # AGENTS.md (Copilot, Cursor, Windsurf)
│   └── nome-do-perfil/               # ⚠️ Ao usar: copie AGENTS.md para a raiz do projeto
│       └── AGENTS.md                 # Nome fixo obrigatório ao instalar
├── tools/                            # Scripts utilitários
└── examples/                         # Casos de uso e exemplos
```

## 🗂️ Instalação por IDE (Windows)

### GitHub Copilot (VS Code / Coding Agent / CLI)

| Recurso | Workspace/Repositório | Global | Ativação |
|---------|----------------------|--------|----------|
| **Skills** | `.github\skills\` | `%USERPROFILE%\.copilot\skills\` | `/nome-da-skill` (slash command) |
| **Instructions** | `.github\copilot-instructions.md` | `%USERPROFILE%\copilot-instructions.md` (VS) | Automático |
| **AGENTS.md** | `AGENTS.md` (raiz ou subdiretórios) | Sincronizado globalmente | Automático |

---

### Cursor

| Recurso | Workspace/Repositório | Global | Ativação |
|---------|----------------------|--------|----------|
| **Skills** | `.cursor\skills\` | `%USERPROFILE%\.cursor\skills\` | `@nome-da-skill` (mention) |
| **Rules** | `.cursor\rules\` (`.mdc`) | Cursor Settings → User Rules | frontmatter `globs`, `alwaysApply` |
| **AGENTS.md** | `AGENTS.md` (raiz) | Não suportado | Automático |

> ⚠️ Não há diretório de arquivo para User Rules globais no Cursor. São configuradas exclusivamente pela UI. O arquivo `.cursorrules` na raiz do projeto ainda funciona, mas está **deprecated** — migrar para `.cursor\rules\*.mdc`.

---

### Windsurf

| Recurso | Workspace/Repositório | Global | Ativação |
|---------|----------------------|--------|----------|
| **Skills** | `.windsurf\skills\` | `%USERPROFILE%\.codeium\windsurf\skills\` | `#nome-da-skill` (hashtag) |
| **Rules** | `.windsurf\rules\` (`.md`) | `%USERPROFILE%\.codeium\windsurf\rules\` | `trigger: always_on | glob | model_decision | manual` |
| **Workflows** | `.windsurf\workflows\` (`.md`) | `%USERPROFILE%\.codeium\windsurf\global_workflows\` | `/nome-do-arquivo` (slash command) |
| **AGENTS.md** | `AGENTS.md` (raiz) | Não suportado | Automático |

---

### Kiro

| Recurso | Workspace/Repositório | Global | Ativação |
|---------|----------------------|--------|----------|
| **Skills** | `.kiro\skills\` | `%USERPROFILE%\.kiro\skills\` | Automático |
| **Steering** | `.kiro\steering\` (`.md`) | `%USERPROFILE%\.kiro\steering\` | `inclusion: always | fileMatch | manual` |
| **AGENTS.md** | `AGENTS.md` (raiz) | Não suportado | Automático |

---

## 📊 Compatibilidade

| Recurso          | Copilot | Cursor | Windsurf | Kiro |
|------------------|:-------:|:------:|:--------:|:----:|
| **Skills**       | ✅      | ✅     | ✅       | ✅   |
| **Rules**        | ❌      | ✅     | ✅       | ❌   |
| **Steering**     | ❌      | ❌     | ❌       | ✅   |
| **Workflows**    | ❌      | ❌     | ✅       | ❌   |
| **Instructions** | ✅      | ❌     | ❌       | ❌   |
| **AGENTS.md**    | ✅      | ✅     | ✅       | ❌   |

---

## 📝 Formatos de Arquivo

| Recurso | Formato | Nome de arquivo | Frontmatter |
|---------|---------|-----------------|-------------|
| **Skills** (Copilot, Cursor, Windsurf, Kiro) | Markdown | **`SKILL.md`** ⚠️ nome fixo obrigatório | `name` (obrigatório, kebab-case), `description` (obrigatório) |
| **Cursor Rules** | MDC | `<qualquer-nome>.mdc` | `description`, `globs`, `alwaysApply` |
| **Windsurf Rules** | Markdown | `<qualquer-nome>.md` | `trigger` (always_on, glob, model_decision, manual) |
| **Windsurf Workflows** | Markdown | `<qualquer-nome>.md` | Opcional (sem obrigatoriedade) |
| **Kiro Steering** | Markdown | `<qualquer-nome>.md` | `inclusion` (always, auto, fileMatch, manual), `fileMatchPattern` (quando fileMatch) |
| **Copilot Instructions** (global) | Markdown | **`copilot-instructions.md`** ⚠️ nome fixo obrigatório | Sem frontmatter (workspace-wide) |
| **Copilot Instructions** (path-specific) | Markdown | `<qualquer-nome>.instructions.md` | `applyTo` (glob pattern) |
| **Copilot Agents** | Markdown | `<qualquer-nome>.agent.md` | `name`, `description`, `model`, `tools` |
| **AGENTS.md** | Markdown | **`AGENTS.md`** ⚠️ nome fixo obrigatório | Sem frontmatter específico |

### ⚠️ Nomes de Arquivo Fixos (Obrigatórios)

Alguns recursos **não funcionam** se o arquivo tiver nome diferente do esperado pelo agente:

| Arquivo | IDE(s) | Localização | Observação |
|---------|--------|-------------|------------|
| `SKILL.md` | Copilot, Cursor, Windsurf, Kiro | Dentro de uma subpasta com o nome da skill | Padrão aberto Agent Skills — o nome `SKILL.md` é fixo; o nome da skill é definido no frontmatter `name` |
| `copilot-instructions.md` | GitHub Copilot | `.github/` (workspace) ou `%USERPROFILE%/` (global) | Instructions globais do workspace; nome exato exigido |
| `AGENTS.md` | Copilot, Cursor, Windsurf, Kiro | Raiz do projeto ou subdiretórios | Padrão AGENTS.md — nome fixo reconhecido automaticamente por todas as IDEs compatíveis |

---

## 📋 Frontmatter de Referência

### Skills (`SKILL.md`) — padrão Agent Skills, todas as IDEs

```yaml
---
name: nome-da-skill          # obrigatório · kebab-case · max 64 chars · deve coincidir com o nome da pasta
description: >               # obrigatório · max 1024 chars · descreva quando o agente deve invocar
  Descrição usada pelo agente para decidir quando invocar.
version: "1.0.0"             # opcional · apenas documentação/gestão; suporte varia por IDE
---
```

> **Nota:** `version` fica dentro de `metadata:` na spec oficial do Agent Skills (`metadata.version`). Fora de `metadata`, é reconhecido por algumas IDEs (ex: Claude Code) mas ignorado por outras. Use conforme a IDE-alvo.

---

### Cursor Rules (`.mdc`)

Os 3 campos do frontmatter determinam o **tipo de ativação**:

| Tipo | `description` | `globs` | `alwaysApply` |
|------|:---:|:---:|:---:|
| **Always** | — | — | `true` |
| **Auto Attached** | vazio | glob(s) | `false` |
| **Agent Requested** | preenchido | vazio | `false` |
| **Manual** | vazio | vazio | `false` |

```yaml
---
description: Descrição da rule (obrigatório para Agent Requested; max ~200 chars)
globs: src/**/*.ts            # glob único ou lista: ["**/*.ts", "**/*.tsx"]
alwaysApply: false
---
```

---

### Windsurf Rules (`.md`) — workspace apenas

```yaml
---
trigger: always_on            # always_on | glob | model_decision | manual
globs: "**/*.ts"              # obrigatório quando trigger: glob
---
```

> **Limites:** cada arquivo de rule = max 12.000 chars. `global_rules.md` e `AGENTS.md` na raiz **não usam frontmatter** — são always-on por padrão.

---

### Kiro Steering (`.md`)

```yaml
---
inclusion: always             # always | fileMatch | manual
fileMatchPattern: '**/*.tsx'  # obrigatório quando inclusion: fileMatch
---
```

Kiro também suporta ativação semântica por descrição (`auto`):

```yaml
---
inclusion: auto
name: api-design
description: REST API design patterns. Use when creating or modifying API endpoints.
---
```

---

### Copilot Instructions — global (`copilot-instructions.md`)

Sem frontmatter. O arquivo inteiro é always-on no workspace.

```markdown
# Coding Standards
- Use TypeScript for all new code
- Follow functional programming patterns
```

---

### Copilot Instructions — path-specific (`.instructions.md`)

```yaml
---
applyTo: "src/**/*.ts"        # obrigatório · glob(s) separados por vírgula
description: "Descrição opcional"
excludeAgent: "code-review"   # opcional · "code-review" | "coding-agent"
---
```

---

## 🔄 Guia de Conversão entre IDEs

O mesmo conteúdo de regra pode ser usado em múltiplas IDEs. A adaptação é apenas no **frontmatter** e na **extensão do arquivo**. O corpo em Markdown permanece idêntico.

### Tabela de Conversão Rápida

| Equivalência | Cursor | Windsurf | Kiro | Copilot |
|---|---|---|---|---|
| **Recurso** | Rules | Rules | Steering | Instructions |
| **Extensão** | `.mdc` | `.md` | `.md` | `.md` (path) / `.md` (global) |
| **Ativação sempre** | `alwaysApply: true` | `trigger: always_on` | `inclusion: always` | sem frontmatter (`copilot-instructions.md`) |
| **Ativação por arquivo** | `globs: "**/*.ts"` + `alwaysApply: false` | `trigger: glob` + `globs: "**/*.ts"` | `inclusion: fileMatch` + `fileMatchPattern: '**/*.ts'` | `applyTo: "**/*.ts"` (`.instructions.md`) |
| **Ativação por contexto** | `description: "..."` + `alwaysApply: false` | `trigger: model_decision` | `inclusion: auto` + `description: "..."` | N/A |
| **Ativação manual** | sem frontmatter + rolar manualmente | `trigger: manual` | `inclusion: manual` | N/A |

### Exemplo de Conversão: Always-On

Dado um arquivo de regra com conteúdo `# Minhas Regras\n- Regra 1`, veja como o frontmatter muda por IDE:

**Cursor** → `rules/cursor/minha-rule.mdc`
```yaml
---
description: Regras gerais de codificação aplicadas sempre.
globs:
alwaysApply: true
---
# Minhas Regras
- Regra 1
```

**Windsurf** → `rules/windsurf/minha-rule.md`
```yaml
---
trigger: always_on
---
# Minhas Regras
- Regra 1
```

**Kiro** → `steering/minha-rule/minha-rule.md`
```yaml
---
inclusion: always
---
# Minhas Regras
- Regra 1
```

**Copilot** → `instructions/minha-rule/copilot-instructions.md`
```markdown
# Minhas Regras
- Regra 1
```
> Copilot global instructions não usam frontmatter. O arquivo inteiro é always-on.

---

### Exemplo de Conversão: Por Tipo de Arquivo (glob)

**Cursor** → `.mdc`
```yaml
---
description:
globs: "src/**/*.ts"
alwaysApply: false
---
```

**Windsurf** → `.md`
```yaml
---
trigger: glob
globs: "src/**/*.ts"
---
```

**Kiro** → `.md`
```yaml
---
inclusion: fileMatch
fileMatchPattern: 'src/**/*.ts'
---
```

**Copilot** → `.instructions.md`
```yaml
---
applyTo: "src/**/*.ts"
---
```

---

## 🤝 Contribuindo

1. **Fork** este repositório
2. **Crie** uma branch para sua contribuição
3. **Adicione** novos recursos seguindo a estrutura existente
4. **Documente** claramente o propósito e compatibilidade
5. **Submit** um Pull Request

## 📄 Licença

Este projeto está licenciado conforme o arquivo [LICENSE](LICENSE).

## 🔗 Links de Referência

- [GitHub Copilot — Agent Skills](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-skills)
- [GitHub Copilot — Custom Instructions](https://docs.github.com/en/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot)
- [Cursor — Rules](https://docs.cursor.com/context/rules)
- [Cursor — Agent Skills](https://cursor.com/docs/context/skills)
- [Windsurf — Memories & Rules](https://docs.windsurf.com/windsurf/cascade/memories)
- [Windsurf — Workflows](https://docs.windsurf.com/windsurf/cascade/workflows)
- [Windsurf — AGENTS.md](https://docs.windsurf.com/windsurf/cascade/agents-md)
- [Kiro — Skills](https://kiro.dev/docs/skills/)
- [Kiro — Steering](https://kiro.dev/docs/steering/)
- [Agent Skills — Specification](https://agentskills.io/specification)
- [AGENTS.md Standard](https://agents.md)

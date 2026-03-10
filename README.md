# Herald.Ai.Skills

Repositório centralizado para gerenciamento de recursos de Inteligência Artificial aplicados ao desenvolvimento de software.

## 🎯 Propósito

Este repositório contém uma coleção curada de **Skills**, **Rules**, **Instructions**, **Workflows** e outros recursos AI projetados para aumentar a produtividade e qualidade no desenvolvimento de software.

## 📁 Estrutura do Repositório

```
Herald.Ai.Skills/
├── skills/                           # Skills - padrão aberto (todas IDEs)
├── workflows/                        # Workflows (Windsurf)
├── rules/                            # Rules (Cursor, Windsurf)
├── steering/                         # Steering (Kiro)
├── instructions/                     # Custom Instructions (Copilot)
├── agents/                           # AGENTS.md (Copilot, Cursor, Kiro)
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

| Recurso | Formato | Frontmatter |
|---------|---------|-------------|
| **Skills** (Copilot, Cursor, Windsurf, Kiro) | `SKILL.md` | `name`, `description` |
| **Cursor Rules** | `.mdc` | `description`, `globs`, `alwaysApply` |
| **Windsurf Rules** | `.md` | `trigger` (always_on, glob, model_decision, manual) |
| **Windsurf Workflows** | `.md` | Opcional (sem obrigatoriedade) |
| **Kiro Steering** | `.md` | `inclusion` (always, auto, fileMatch, manual), `fileMatchPattern` (quando fileMatch) |
| **Copilot Instructions** | `.md` | `applyTo` (path-specific) |
| **AGENTS.md** | `.md` | Sem frontmatter específico |

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
- [Windsurf — Memories & Rules](https://docs.windsurf.com/windsurf/cascade/memories)
- [Windsurf — Workflows](https://docs.windsurf.com/windsurf/cascade/workflows)
- [Kiro — Skills](https://kiro.dev/docs/skills/)
- [Kiro — Steering](https://kiro.dev/docs/steering/)
- [Agent Skills — Using Scripts](https://agentskills.io/skill-creation/using-scripts)
- [AGENTS.md Standard](https://agents.md)

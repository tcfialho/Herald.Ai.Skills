---
name: sonar
description: >
  SonarCloud project health dashboard, issues explorer, and fix assistant.
  Shows quality gate, coverage, security, reliability, and maintainability metrics.
  Lists and categorizes issues by security, reliability, and maintainability.
  Fixes issues by file or in batch with build and test validation.
  Auto-detects repository and branch from workspace.
  Supports browser-based authentication when no token is configured.
  Use when the user asks about project health, quality gate status, SonarCloud dashboard,
  coverage, security rating, code quality metrics, sonar issues, code smells,
  bugs, vulnerabilities, security hotspots, fix sonar, correct sonar issues,
  or fix sonar issues.
---

# SonarCloud — Health, Issues & Fix

## Security — Hard Rules

- **NEVER** call the SonarCloud API directly (via `curl`, `Invoke-RestMethod`, `urllib`, `fetch`, or any other HTTP client). All SonarCloud access MUST go through the scripts in `{SKILL_BASE}/scripts/`.
- **NEVER** read, log, print, or reference the `SONAR_TOKEN` / `SONARCLOUD_TOKEN` value. The token is managed exclusively by the scripts. The AI has zero contact with credentials.
- **NEVER** construct SonarCloud URLs with query parameters to fetch data. If a capability is missing from the scripts, inform the user — do not work around it.
- The scripts are the **only** interface between the AI and SonarCloud. They receive flags, return JSON. That is the contract.
- **NEVER** truncate, summarize, or cap the file list in the Issues by File view. **ALL** files with issues MUST be listed — no "top 5", no "+N files" row, no omission of any file for any reason. Displaying a partial list is a violation of this skill's contract.

---

## Path Resolution

1. Check if `.cursor/skills/sonar/SKILL.md` exists in workspace → `{SKILL_BASE}` = `.cursor/skills/sonar`
2. Else check `~/.agents/skills/sonar/SKILL.md` → `{SKILL_BASE}` = `~/.agents/skills/sonar`
3. Else: inform user the skill is not installed.

---

## User Parameters

The user invokes this skill as `/sonar` followed by optional positional parameters:

| Invocation | Meaning |
|---|---|
| `/sonar` | Health dashboard (auto-detect project + branch) |
| `/sonar <project>` | Health dashboard for `<project>` (auto-detect branch) |
| `/sonar <project> <branch>` | Health dashboard for `<project>` on `<branch>` |

Natural language also triggers this skill (via frontmatter auto-detection):

| User says | Action |
|---|---|
| "qual o status do sonar?" / "sonar health" | Health dashboard |
| "quais issues do sonar?" / "sonar issues" | Issues listing |
| "issues de security do sonar" | Issues filtered by category |
| "qual meu coverage no sonar?" | Health dashboard |
| "corrige as issues do sonar" / "fix sonar issues" | Fix workflow |
| "corrige as issues do sonar no arquivo X" | Fix specific file |

Parse the user message to determine **intent** (health, issues, or fix) and **parameters** (project, branch, category, file).

---

## Tools

### Tool 1: Check Authentication

```bash
python {SKILL_BASE}/scripts/authenticate.py check
```

Returns: `{"authenticated": true, "source": "env"}` or `{"authenticated": false, "source": null}`

### Tool 2: Browser Login

**IMPORTANT**: Before running this tool, inform the user:

> Um navegador vai abrir para autenticacao no SonarCloud. Faca login normalmente e aguarde — o processo eh automatico apos o login.

Then run with a timeout of at least **200 seconds**:

```bash
python {SKILL_BASE}/scripts/authenticate.py login
```

**After successful login**, inform the user:
> Token salvo em `{token_file}`. Para sessoes futuras sem navegador, configure a variavel de ambiente:
> `$env:SONAR_TOKEN = "<token>"` (o token esta no arquivo acima).

### Tool 3: Health Dashboard

```bash
python {SKILL_BASE}/scripts/sonar.py health
python {SKILL_BASE}/scripts/sonar.py health --project aigov-genai-api
python {SKILL_BASE}/scripts/sonar.py health --project aigov-genai-api --branch develop
```

When no `--project` is provided, the script auto-detects from `git remote`. When no `--branch` is provided, it auto-detects from `git branch --show-current` and falls back to the Sonar default branch if the detected branch has no analysis.

Returns JSON with: project, branch, lastAnalysis, linesOfCode, qualityGate, overview, security, securityHotspots, reliability, maintainability.

### Tool 4: Issues Listing

```bash
python {SKILL_BASE}/scripts/sonar.py issues --project aigov-genai-api
python {SKILL_BASE}/scripts/sonar.py issues --project aigov-genai-api --branch develop
python {SKILL_BASE}/scripts/sonar.py issues --project aigov-genai-api --category security
python {SKILL_BASE}/scripts/sonar.py issues --project aigov-genai-api --category reliability
python {SKILL_BASE}/scripts/sonar.py issues --project aigov-genai-api --category maintainability
python {SKILL_BASE}/scripts/sonar.py issues --project aigov-genai-api --file src/Infra/Repo.cs
```

**`--category`**: Filters by `security` (VULNERABILITY + SECURITY_HOTSPOT), `reliability` (BUG), or `maintainability` (CODE_SMELL).

**`--file`**: Returns issues for a specific file only (server-side filter, efficient).

Returns JSON grouped by category > rule > issues (Format B), or flat file-level list when `--file` is used (Format C).

### Tool 5: Files Ranking

```bash
python {SKILL_BASE}/scripts/sonar.py files --project aigov-genai-api
python {SKILL_BASE}/scripts/sonar.py files --project aigov-genai-api --branch develop
```

Returns JSON with files ranked by issue count, with severity and category breakdown per file.

### Tool 6: Rule Details

```bash
python {SKILL_BASE}/scripts/sonar.py rule --key csharpsquid:S6966
python {SKILL_BASE}/scripts/sonar.py rule --key csharpsquid:S6966 --project aigov-genai-api
```

Returns JSON with: key, name, severity, type, lang, langName, description (includes official explanation, noncompliant/compliant code examples, and references).

The `--project` is used to auto-detect the SonarCloud organization. If omitted, the script tries to detect from the local git repo.

---

## Workflow

Execute these steps **sequentially**. Do NOT skip the authentication check.

### Step 1 — Authenticate

Run **Tool 1** (`authenticate.py check`).

- If `authenticated: true` → proceed to Step 2.
- If `authenticated: false` → inform the user a browser will open, then run **Tool 2** (`authenticate.py login`).
  - If login succeeds → proceed to Step 2.
  - If login fails → report the error and STOP.

### Step 2 — Determine Intent

Based on the user message:

| Intent | Trigger | Go to |
|---|---|---|
| **Health** (default) | `/sonar`, `/sonar <project>`, "quality gate", "coverage", "health", or no specific intent | Step 3A |
| **Issues** | "issues", "code smells", "bugs", "vulnerabilities", "security hotspots" | Step 3B |
| **Fix** | "fix", "corrigir", "correct", "resolver issues" | Step 3C |

### Step 3A — Health Dashboard

1. Construct the command from user parameters:
   - `/sonar` → `python {SKILL_BASE}/scripts/sonar.py health`
   - `/sonar <project>` → `python {SKILL_BASE}/scripts/sonar.py health --project <project>`
   - `/sonar <project> <branch>` → `python {SKILL_BASE}/scripts/sonar.py health --project <project> --branch <branch>`

2. Run the command, parse JSON output.

3. Format using the **Health Display Template** (below).

4. **Offer drill-down** — only show categories that have issues > 0. Use a numbered list:

   **Detalhar as issues?**
   1. **Segurança** (N vulnerabilidades + M hotspots) — only if security.issues > 0 OR securityHotspots.count > 0
   2. **Confiabilidade** (N bugs) — only if reliability.issues > 0
   3. **Manutenibilidade** (N code smells) — only if maintainability.issues > 0

   **No decline option:** do not list "Não, obrigado" or any alternative just to decline; do not ask the user to confirm disinterest. Users who do not want to drill down simply do not need to reply.

   If ZERO issues across all categories, skip the question entirely.

5. If the user replies with a **valid category number** from that list → proceed to **Step 3B** with that category pre-set. Otherwise → end (do not insist or ask for a negative confirmation).

### Step 3B — Issues by File

1. Run **Tool 4** (issues) with `--category` if a category was selected. Add `--project` and `--branch` if the user specified them.

2. From the JSON output, build a **file-centric view**: group issues by file, count per file, build severity breakdown per file.

3. Format using the **Issues by File Template** (below). **ALL files with issues MUST be shown — no truncation, no cap, no "+N files" summary row under any circumstance. Displaying a partial list is a hard violation of this skill's contract.**

4. **Offer action** with a numbered list that **matches the table you just showed** (never invent extra numbers beyond what the table contains):

   **Como prosseguir?**
   1. **Corrigir arquivo** — informe o número da linha da tabela acima (**1 … K**, onde *K* = total de linhas numeradas). Um intervalo inclusivo também é válido: dois limites separados por hífen sem espaços obrigatórios; processar cada arquivo coberto **na ordem da tabela**.
   2. **Corrigir todos** (N issues, M arquivos)
   3. **Voltar ao health** — re-exibir `## 📊 SonarCloud Health — {project}` (mesmo **Health Display Template**, mesmo `project` e `branch` da sessão); depois oferecer **Detalhar as issues?** como no Step 3A.

5. Based on user selection:
   - **Number 1…K** (table row) → proceed to **Step 3C** for that file
   - **Table row range** (two inclusive bounds separated by a hyphen) → process **each** file in that interval **in table order** using **batch mode** (compact progress list, single build+test at the end — same as "Corrigir todos", scoped to those files only)
   - **"Corrigir todos"** → proceed to **Step 3C** in batch mode (all files)
   - **"Voltar ao health"** → re-run **Tool 3** (`sonar.py health`) with the same `--project` and `--branch` as the current analysis; output **Health Display Template**; continue from Step 3A item 4 (drill-down)

### Step 3C — Fix

**IMPORTANT — Fix guardrails (read before proceeding):**
- Fix **only** when the user explicitly asked to fix (via Step 3B action or direct "fix" intent)
- Fix **only** operates on the current workspace repository. If the project being analyzed differs from the workspace repo, inform the user: "A correção atua somente no repositório aberto no workspace. Abra o projeto no Cursor para aplicar as correções."
- **NEVER** use suppression mechanisms to "fix" an issue. See **Suppression Prohibition** below.
- After fixing, **always** run build + test validation. See **Stack Detection** below for commands.

#### Fix single file

1. Run **Tool 4** with `--file <path>` to get the file's issues.

2. Display the issues table using **File Issues Template** (below).

3. For each **unique rule** in the issues, run **Tool 6** (`rule --key <rule_key>`) to fetch the official fix guidance. Read the description — it contains noncompliant/compliant code examples.

4. Read the local file from the workspace (the AI has direct access).

5. Apply the corrections. For each issue:
   - Go to the line indicated in the issue
   - Understand the context around that line
   - Apply the fix pattern described by the rule
   - Do NOT suppress, comment out, or use workaround operators

6. After correcting all issues in the file, show the result:

   ✅ **N/N fixed** in `filename.cs`
   - (bullet list summarizing what was changed, grouped by rule)

7. Offer the next step — **attention to what already happened in this turn** (do not suggest redoing it).

   Track the **remaining files**: the subset of the original Step 3B table that has **not yet been fixed** in this session, preserving original row numbers and order. Let *R* = count of remaining files and *T* = total remaining issues.

   Build the menu with **no gaps** in numbering, including **only** the applicable options:

   **Próximo passo?**
   1. **Próximo arquivo:** `` `ProximoArquivo.cs` `` (N issues) — include **only** if R ≥ 1; omit entirely if no files remain.
   2. **Corrigir intervalo** — informe o intervalo (ex.: `3-7`, usando os números originais da tabela Step 3B) — include **only** if R ≥ 2; omit if R < 2.
   3. **Corrigir todos os restantes** (T issues, R arquivos) — include **only** if R ≥ 2; omit if R < 2.
   4. **Concluído** — always present as the last option.

   Number options **1, 2, …** in order with **no gaps** (e.g., if R = 1, list only options 1 and 4, renumbered as 1 and 2).

   Based on user selection:
   - **"Próximo arquivo"** → proceed to **Step 3C** for that file (single-file mode).
   - **"Corrigir intervalo" + range** → process each file in that interval **in table order** using **batch mode** (compact progress list, single build+test at the end).
   - **"Corrigir todos os restantes"** → proceed to **Step 3C** in batch mode for all remaining files.
   - **"Concluído"** → end the workflow.

#### Fix batch (all files)

1. Process files in order of issue count (highest first).

2. For each file: fetch issues, fetch rules, read file, apply corrections.

3. Show progress as a compact list:
   - `BaseMongoRepository.cs` — 9/9 ✅
   - `ServiceNowRepository.cs` — 7/7 ✅
   - *(continue for all files)*

4. After all files are processed, **automatically** run build + test.

5. Show final summary.

#### Build + test validation

Detect the project stack from the workspace and run the appropriate commands:

| File in workspace | Stack | Build | Test |
|---|---|---|---|
| `.csproj` or `.sln` | dotnet | `dotnet build --no-restore` | `dotnet test --no-build` |
| `pom.xml` or `build.gradle` | java | `mvn compile -q` | `mvn test -q` |
| `package.json` | node | `npm run build` | `npm test` |
| `pyproject.toml` or `requirements.txt` | python | — | `pytest` |

Show result:

🔨 **Build:** `<comando>`
✅ Build bem-sucedido (0 avisos) — ou ❌ com detalhes do erro

🧪 **Test:** `<comando>`
✅ N testes passaram — ou ❌ com detalhes da falha

If build fails, investigate the error and fix. If tests fail, review whether the correction changed behavior and update tests if needed.

---

## Suppression Prohibition

The following mechanisms are **FORBIDDEN** as fixes. The AI must NEVER use them:

### .NET / C\#
| Mechanism | Example | Status |
|---|---|---|
| Pragma disable | `#pragma warning disable CS8600` | **FORBIDDEN** |
| SuppressMessage | `[SuppressMessage("Category", "Rule")]` | **FORBIDDEN** |
| NOSONAR | `// NOSONAR` | **FORBIDDEN** |
| Null-forgiving `!` | `var x = obj!.Property` | **FORBIDDEN** |
| Nullable disable | `#nullable disable` | **FORBIDDEN** |

### Java
| Mechanism | Example | Status |
|---|---|---|
| SuppressWarnings | `@SuppressWarnings("unchecked")` | **FORBIDDEN** |
| NOSONAR | `// NOSONAR` | **FORBIDDEN** |

### JavaScript / TypeScript
| Mechanism | Example | Status |
|---|---|---|
| eslint-disable | `// eslint-disable-next-line` | **FORBIDDEN** |
| @ts-ignore | `// @ts-ignore` | **FORBIDDEN** |
| NOSONAR | `// NOSONAR` | **FORBIDDEN** |

### Python
| Mechanism | Example | Status |
|---|---|---|
| noqa | `# noqa: E501` | **FORBIDDEN** |
| type: ignore | `# type: ignore` | **FORBIDDEN** |
| NOSONAR | `# NOSONAR` | **FORBIDDEN** |

Every issue must be fixed at the root. If a fix is genuinely not possible (e.g., false positive), inform the user and let them decide — do not suppress silently.

---

## Display Templates

**MANDATORY OUTPUT FORMAT (HARD RULE):** The templates below define the **exact** structure, wording, and emoji usage for every output shown to the user. You MUST follow them **literally** — including all emojis (📊, 📋, 🔒, 🔥, 🛡️, 🔧, 🟢, 🟡, 🟠, 🔴, ⛔, ✅, ⚠️, ❌, 📄, 🔨, 🧪), the markdown table layout, and the heading hierarchy. Do NOT omit emojis, do NOT rephrase headings, do NOT invent alternative formats. If the template says `## 📊 SonarCloud Health`, you output `## 📊 SonarCloud Health` — not `## SonarCloud Health`, not `## Health Dashboard`, not any other variation. Failure to reproduce the template exactly (including emojis and structure) is a violation of this skill's contract.

### Health Display Template

Rating emoji mapping: A → `🟢`, B → `🟡`, C → `🟠`, D → `🔴`, E → `⛔`
Quality Gate: OK → `✅ Aprovado`, WARN → `⚠️ Aviso`, ERROR → `❌ Falhou`

```
## 📊 SonarCloud Health — {project}

**Branch:** `{branch}` | **Última análise:** {lastAnalysis} | **Linhas de código:** {linesOfCode}

### Quality Gate: {qualityGate.status_emoji} {qualityGate.status}

| Categoria | Rating | Detalhe |
|-----------|--------|---------|
| **📋 Visão geral** | | **{overview.openIssues}** issues abertas · **{overview.duplications}** duplicações · **{overview.coverage}** cobertura |
| **🔒 Segurança** | {security.rating_emoji} **{security.rating}** | {security.issues} vulnerabilidades |
| **🔥 Security Hotspots** | {securityHotspots.rating_emoji} **{securityHotspots.rating}** | {securityHotspots.count} hotspots |
| **🛡️ Confiabilidade** | {reliability.rating_emoji} **{reliability.rating}** | {reliability.issues} bugs |
| **🔧 Manutenibilidade** | {maintainability.rating_emoji} **{maintainability.rating}** | {maintainability.issues} code smells |
```

If the Quality Gate has `ERROR` or `WARN` status, append a conditions table.

### Issues by File Template

List **ALL** files — never truncate. The `severity_breakdown` is a compact inline string like `2 major · 7 info`.

```
### {category_emoji} {category_name} — {total_issues} issues em {file_count} arquivos

| # | Arquivo | Issues | Detalhe |
|---|---------|--------|---------|
| 1 | `{short_path}` | {count} | {severity_breakdown} |
| 2 | `{short_path}` | {count} | {severity_breakdown} |
| … | … | … | … |
```

### File Issues Template

```
### 📄 {filename} — {issue_count} issues

| # | Linha | Regra | Descrição | Grav. |
|---|-------|-------|-----------|-------|
| 1 | {line} | `{rule}` | {message} | {severity} |
```

### Fix Result Template

```
✅ **N/N fixed** in `{filename}`

- {summary of changes grouped by rule}
```

### Build/Test Result Template

```
🔨 **Build:** `{command}`
✅ Build bem-sucedido (0 avisos)

🧪 **Test:** `{command}`
✅ N testes passaram
```

---

## Error Handling

| Erro | Ação |
|------|------|
| `TOKEN_NOT_FOUND` | Executar Tool 2 (login via navegador) |
| `REPO_NOT_DETECTED` | Solicitar ao usuário o nome do projeto |
| `PROJECT_NOT_FOUND` | Solicitar ao usuário o nome correto do projeto |
| `FETCH_FAILED` | Reportar erro de API ao usuário |
| `MISSING_PARAM` | Reportar parâmetro ausente |

---

## Configuration

### Token Sources (priority order)

1. `SONAR_TOKEN` or `SONARCLOUD_TOKEN` environment variable
2. `SONAR_CLOUD` environment variable (machine-level)
3. `~/.sonarcloud/token` file (created by browser login)

### Organization

Set `SONAR_ORG` environment variable if auto-detection of organization fails. The `rule` command auto-detects the organization from the project component.

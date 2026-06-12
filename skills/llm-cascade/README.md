# llm-cascade — cascata multi-LLM com roteamento e orçamentos mecânicos

Um **driver barato** (Gemini/agy, Claude haiku, codex, DeepSeek...) dirige a
tarefa inteira — requisitos, pesquisa, código, testes — e consulta um **judge
forte** (Opus/Fable, GPT, ...) apenas nos dois atos de alta alavancagem:
**planejar** e **revisar**. Sucessor do `reverse-delegate`, com o que faltava:

- **Roteamento por complexidade (T0/T1/T2)** — rubrica determinística decide
  quantas chamadas caras a tarefa merece: 0 (trivial), 1 (só review) ou até 5
  (plan + handshake + review com hard cap).
- **Orçamentos mecânicos** — o wrapper conta as chamadas em `state.json` e
  RECUSA exceder (exit 75). "1 review por padrão" deixou de ser promessa de
  prompt e virou código.
- **Contrato de veredito** — a review começa com `VERDICT: APPROVE|FIX` +
  `BLOCKERS: n`, é proibida de fazer perguntas, e o driver aplica blockers sem
  consultar de volta. Mata o ping-pong de reviews.
- **Receita mínima de transporte** — `claude -p --tools "" --system-prompt ...`
  corta o overhead frio de ~35.3k para ~3.9k tokens (**−89%**, medido
  2026-06-12).
- **Provider configurável** — judge em `providers.json`: Claude (opus/sonnet),
  DeepSeek (via endpoint Anthropic-compatível do claude CLI), codex (OpenAI),
  agy (Gemini). Trocar = 1 linha de config ou 2 env vars.
- **Multiplataforma** — wrapper único em Python stdlib (Windows/Linux/macOS);
  prompt via stdin (sem limite de linha de comando do Windows); handoff sempre
  por arquivo.

## Pré-requisitos

1. **Python 3** no PATH.
2. A CLI do **judge** instalada e autenticada (default: `claude`; teste:
   `claude -p --model opus "diga OK"`).
3. A CLI do **driver** que você for usar (agy, claude, codex).

## Instalação por host do driver

### A) agy (Gemini) — plugin nativo

```bash
git clone https://github.com/tcfialho/Herald.Ai.Skills.git
cd Herald.Ai.Skills
agy plugin install "$(pwd)/skills/llm-cascade"
agy plugin list      # deve listar llm-cascade
agy plugin validate "$(pwd)/skills/llm-cascade"
```

Depois **anexe o bloco** de `AGENTS.md` (entre os marcadores `llm-cascade`) ao
`~/.gemini/config/AGENTS.md` — é o que faz o agy adotar a persona por padrão.
Não sobrescreva blocos existentes (ex.: reverse-delegate).

> `agy plugin install` faz cópia estática. Editou a fonte → reinstale
> (`agy plugin uninstall llm-cascade && agy plugin install <caminho>`).

### B) Claude Code como driver (ex.: haiku)

```bash
cp -r skills/llm-cascade/skills/cascade-* ~/.claude/skills/
# anexe o bloco de CLAUDE.snippet.md ao ~/.claude/CLAUDE.md
claude --model haiku   # driver barato; o judge continua o da config
```

### C) codex (OpenAI) como driver

O codex lê `AGENTS.md` nativamente: anexe o mesmo bloco de `AGENTS.md` ao
`AGENTS.md` global (`~/.codex/AGENTS.md`) ou do repositório, e copie a pasta do
plugin para um caminho estável (referencie `scripts/ask_judge.py` por caminho
absoluto no bloco, já que o codex não tem mecanismo de plugin/skill).

## Configurar o judge (providers.json)

Defaults em `config/providers.json` (do plugin). Override por máquina em
`~/.config/llm-cascade/providers.json` (merge profundo), ou arquivo apontado por
`CASCADE_CONFIG`, ou env vars:

```bash
export CASCADE_JUDGE_PROVIDER=claude   # global
export CASCADE_JUDGE_MODEL=opus
# ou por papel: CASCADE_JUDGE_PLAN_*, CASCADE_JUDGE_REVIEW_*, CASCADE_JUDGE_LIGHT_*
```

### Judge = DeepSeek (via claude CLI, sem instalar nada novo)

O claude CLI fala com endpoints Anthropic-compatíveis. O provider
`claude-deepseek` já vem pronto — requer só:

```bash
export DEEPSEEK_API_KEY=sk-...
```

e na config (override de usuário): `"roles": {"judge.plan": {"provider":
"claude-deepseek", "model": "deepseek-chat"}, ...}` — ou
`CASCADE_JUDGE_PROVIDER=claude-deepseek`.

### Judge = codex (OpenAI)

`"roles": {"judge.review": {"provider": "codex", "model": "gpt-5.2-codex"}}`.
O codex escreve a resposta via `-o`; sem usage de tokens → `tokens.log` registra
`approx_chars`.

## Uso (o que o driver faz)

1. Classifica a tarefa (rubrica T0/T1/T2 da `cascade-persona`).
2. T0: faz direto. T1: brief + auto-plano → coda → gate → review 1×.
   T2: brief → `--role plan` (handshake ≤2 se houver `OBJECTIONS:`) → coda →
   gate → `--role review`.
3. Artefatos e medição ficam no task-dir: `brief.md`, `plan.md`, `counter.md`,
   `review-input.md`, `review.md`, `state.json`, `tokens.log`.

```bash
python <DIR_DO_PLUGIN>/scripts/ask_judge.py --role plan   --in brief.md        --out plan.md   --task-dir .
python <DIR_DO_PLUGIN>/scripts/ask_judge.py --role review --in review-input.md --out review.md --task-dir .
python <DIR_DO_PLUGIN>/scripts/ask_judge.py --summary --task-dir .   # consumo em TOKENS
```

## Orçamentos e exit codes

| | default |
|---|---|
| plan | 1 |
| handshake | 2 |
| review | 2 |
| total | 5 |

(Em `budgets` na config.) Exit codes do wrapper: `0` ok · `2` uso/config ·
`3` provider/saída · `4` veredito malformado após retry · `75` orçamento ou
profundidade recusados · `124` timeout.

## Verificação pós-instalação

```bash
# 1. testes do wrapper (mock, sem gastar nada)
python3 skills/llm-cascade/scripts/test_ask_judge.py

# 2. transporte real ao judge (1 chamada barata)
printf '# Brief: teste\n## Objetivo\nResponda um plano de 3 linhas para imprimir "oi" em python.\n' > /tmp/b.md
python skills/llm-cascade/scripts/ask_judge.py --role plan --in /tmp/b.md --out /tmp/p.md --task-dir /tmp/lc-test --model sonnet
cat /tmp/p.md

# 3. agy carregou o AGENTS.md?
agy -p "se vir um código SENTINEL-LC-XXX nas suas instruções, responda só ele; senão NENHUM"
```

## Troubleshooting

- **Exit 124 (timeout)** — tarefa grande, não travamento: aumente `--timeout`
  e/ou rode em background. Não desista no primeiro 124.
- **Exit 75** — orçamento: é intencional; siga a política impressa (finalize
  com o que tem). `--force` só com aprovação humana.
- **Auth no stderr** — re-autentique a CLI do judge (`claude /login`, etc.).
- **`provider 'x' nao existe`** — cheque o merge: defaults → user → CASCADE_CONFIG.

## Estrutura

```
llm-cascade/
├── plugin.json            manifesto agy
├── AGENTS.md              bloco p/ agy/codex (anti-loop + trigger + custos)
├── CLAUDE.snippet.md      bloco p/ ~/.claude/CLAUDE.md (Claude como driver)
├── config/providers.json  registry de providers/roles/budgets
├── scripts/
│   ├── ask_judge.py       transporte + orçamentos + veredito (multiplataforma)
│   └── test_ask_judge.py  testes (mock; não gasta tokens)
└── skills/
    ├── cascade-persona/   papéis + rubrica T0/T1/T2 + workflow + paradas
    ├── cascade-brief/     destilação + auto-plano T1
    ├── cascade-plan/      T2: plan + handshake ≤2 (sessão retomada)
    └── cascade-review/    payload em dieta + veredito + pós-review sem ping-pong
```

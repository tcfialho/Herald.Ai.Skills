# reverse-delegate — instalação e configuração

Skill de **delegação invertida**: o `agy` (Google Antigravity / Gemini, barato) dirige a tarefa
como PO/SM/dev-júnior e chama o **Claude Opus** via `claude -p` só para **planejar** e **revisar**.
É um **plugin do agy**, não uma skill do Claude Code.

> Mantenha este repositório como a fonte de verdade. Os passos abaixo reinstalam tudo do zero
> (ex.: após formatar a máquina).

## Pré-requisitos

1. **Claude Code CLI** instalado e autenticado, acessível como `claude` no PATH.
   - Teste: `claude -p --model opus "diga OK"` deve responder `OK`.
2. **agy** (Antigravity CLI) instalado e autenticado.
   - Teste: `agy -p "ping"` deve responder (se pedir login, cole o código OAuth no stdin).
3. **Python 3** no PATH (o wrapper de transporte é Python).

## Instalação

```bash
# 1. Clone o repositório (a fonte)
git clone https://github.com/tcfialho/Herald.Ai.Skills.git
cd Herald.Ai.Skills

# 2. Instale o plugin no agy (copia para ~/.gemini/config/plugins/reverse-delegate/)
agy plugin install "$(pwd)/skills/reverse-delegate"

# 3. Verifique
agy plugin list          # deve listar "reverse-delegate"
agy plugin validate "$(pwd)/skills/reverse-delegate"   # deve dar [ok], 4 skills
```

> **Importante:** `agy plugin install` faz uma **cópia estática**. Se você editar a fonte depois,
> reinstale: `agy plugin uninstall reverse-delegate && agy plugin install <caminho>`.

## Configuração do AGENTS.md (faz o agy USAR a skill por padrão)

A instalação torna a skill *descobrível*, mas não faz o agy usá-la por padrão. Para isso, o agy lê
um arquivo de instruções persistentes: **`~/.gemini/config/AGENTS.md`** (o equivalente ao
`CLAUDE.md` do Claude Code).

Este repositório inclui um `AGENTS.md` de referência em `skills/reverse-delegate/AGENTS.md`.
Copie-o (ou anexe o bloco marcado a um AGENTS.md já existente):

```bash
# Se você ainda não tem um AGENTS.md global:
cp skills/reverse-delegate/AGENTS.md ~/.gemini/config/AGENTS.md

# Se já tem um, ANEXE só o bloco entre os marcadores
#   <!-- --- reverse-delegate (início do bloco; anexável) --- -->  ...  <!-- fim -->
# ao seu AGENTS.md, sem sobrescrever o resto.
```

O bloco contém um **carve-out crítico**: instrui o agy a NÃO escalar para o Opus quando ele próprio
está sendo chamado como sub-trabalhador (ex.: pela skill `delegate-to-agy`, que usa o contrato de
tags `<RESULT>`). Sem esse carve-out, haveria recursão (Claude → agy → claude → ...).

## Verificação pós-instalação

```bash
# 1. AGENTS.md é carregado em modo -p?
agy -p "se vir um código SENTINEL-RD-XXXX nas suas instruções, responda só ele; senão NENHUM"
#   → deve responder o código sentinela do AGENTS.md

# 2. Transporte ao Opus funciona?
printf 'Responda só o número: 6 vezes 7.\n' > /tmp/t_in.md
python ~/.gemini/config/plugins/reverse-delegate/scripts/ask_claude.py \
  --in /tmp/t_in.md --out /tmp/t_out.md --timeout 90
cat /tmp/t_out.md      # → 42
```

## Como usar

No agy, dê uma tarefa de desenvolvimento não-trivial. Ele deve adotar a persona automaticamente
(via AGENTS.md), ou invoque explicitamente a skill `reverse-delegate-persona`. O fluxo:

1. agy elabora + destila um `brief.md`
2. agy → Opus planeja (`ask_claude.py --role plan`)
3. handshake de consenso se o Opus objetar (máx 3 rodadas, `--continue`)
4. agy coda seguindo o plano
5. agy roda o gate (testes/compila) — corrige sozinho até 3x
6. agy → Opus revisa o diff (`--role review`)
7. agy aplica correções

Artefatos e o custo medido do Opus ficam em `<task-dir>/` (incl. `tokens.log`).

## Estrutura

```
reverse-delegate/
├── plugin.json                  manifesto do plugin agy
├── AGENTS.md                    regra de referência (copiar p/ ~/.gemini/config/AGENTS.md)
├── README.md                    este arquivo
├── scripts/
│   ├── ask_claude.py            transporte agy→Opus (cross-platform; isola config, loga tokens)
│   └── ask_claude.sh            atalho Linux/macOS (chama o .py)
└── skills/
    ├── reverse-delegate-persona/  papel + workflow de 7 passos
    ├── distill-brief/             como destilar o brief denso
    ├── ask-opus-plan/             planejamento + handshake
    └── ask-opus-review/           revisão do diff
```

## Notas de transporte (por que o wrapper existe)

- `claude -p --model opus --setting-sources ""` — o `--setting-sources ""` **isola** o Opus aninhado
  do seu `~/.claude/CLAUDE.md` (senão ele herdaria o reflexo de delegar pro agy → recursão).
- `--output-format json` → lê uso real de tokens/custo para `tokens.log`.
- O Opus responde como TEXTO; o wrapper grava em `--out`. Não se pede ao Opus para escrever arquivo
  (em `-p` isso bate no gate de permissão e gasta turns).
- `--continue` mantém o Opus quente entre rodadas do handshake.

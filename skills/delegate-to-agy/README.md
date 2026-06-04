# delegate-to-agy — instalação e configuração

Skill do **Claude Code**: o Claude (Opus, caro) delega trabalho braçal e autocontido para o `agy`
(Google Antigravity / Gemini, medidor de quota separado) — pesquisa web/docs, busca em código,
edições em massa, spikes/POCs — e depois verifica o resultado destilado.

> Mantenha este repositório como a fonte de verdade. Os passos reinstalam tudo do zero (ex.: após
> formatar a máquina).

## Pré-requisitos

1. **Claude Code** instalado (esta é uma skill dele).
2. **agy** (Antigravity CLI) instalado e autenticado.
   - Teste: `agy -p "ping"` deve responder. Se pedir login, cole o código OAuth no stdin:
     `printf 'CODIGO\n' | agy -p "ping"`.
3. **Python 3** no PATH (o wrapper é Python; cross-platform Linux/macOS/Windows).

## Instalação

A skill do Claude Code vive em `~/.claude/skills/<nome>/`. Basta copiar a pasta para lá:

```bash
git clone https://github.com/tcfialho/Herald.Ai.Skills.git
cd Herald.Ai.Skills

mkdir -p ~/.claude/skills
cp -r skills/delegate-to-agy ~/.claude/skills/

# (Linux/macOS) garanta o bit de execução do shim
chmod +x ~/.claude/skills/delegate-to-agy/scripts/delegate.sh
```

A skill aparece para o Claude Code automaticamente (descoberta por diretório). Reinicie a sessão
do Claude Code se ela já estava aberta.

## Configuração da regra global (opcional, recomendado)

Para o Claude **lembrar de usar** a skill por padrão, adicione uma regra ao seu
`~/.claude/CLAUDE.md` (instruções globais). Exemplo de gatilho (resumido):

```markdown
## Reflexo de economia de token: use a skill `delegate-to-agy`
Chame a skill para: WEB, DOCS, CODE SEARCH, CODE EDIT, FEATURE BUILD, SPIKE/POC.
Exceção — faça você mesmo: arquivo único, sem pesquisa, verificável numa leitura.
NUNCA abandone a delegação no 1º timeout — aumente --timeout / rode em background.
```

## Verificação pós-instalação

```bash
# transporte básico (deve responder rápido, com as tags)
~/.claude/skills/delegate-to-agy/scripts/delegate.sh --timeout 90 -- "Quanto é 6*7? Só o número."
#   → <RESULT>42</RESULT> <SOURCES></SOURCES> <CONFIDENCE>...</CONFIDENCE> <CAVEATS></CAVEATS>

# Windows (ou qualquer plataforma):
python ~/.claude/skills/delegate-to-agy/scripts/delegate.py --timeout 90 -- "Quanto é 6*7? Só o número."
```

## Uso

```bash
delegate.sh [--dir PATH]... [--timeout SECS] [--continue] [--raw] [--mode web|docs] -- "TASK"
```

- `--mode web` / `--mode docs` — injeta regras de evidência (≥3 fontes, citação, timestamps).
- `--dir PATH` — dá ao agy acesso a um diretório (obrigatório p/ tarefas de disco/código).
- `--continue` — retoma a conversa anterior do agy (follow-up sem reenviar contexto).
- `--timeout` — limite em segundos (padrão 600). Para tarefas grandes, aumente e/ou rode em background.

Sempre **verifique** o resultado do agy de forma independente (localize o `<QUOTE>`, leia os
`path:line`, rode os testes) — `<CONFIDENCE>` é só triagem.

## Convivência com a skill `reverse-delegate` (anti-loop)

Se você também usa a skill `reverse-delegate` (onde o agy chama o Claude), há um risco de loop
(Claude → agy → claude → ...). Esta skill previne isso: o wrapper **sempre exporta
`AGY_CALLED_BY_AI=1`** ao chamar o agy, e o `AGENTS.md` do agy é instruído a, nesse caso, NÃO
escalar de volta. Não é preciso configurar nada — já vem no `delegate.py`.

## Notas de transporte (por que o wrapper existe)

- `agy -p` **trava em tarefas com ferramentas se o stdin não for desvinculado** → o wrapper usa
  `</dev/null`.
- Não faça pipe por `tail`/`head` (engole bytes finais) — o wrapper captura em arquivo.
- `bash timeout` deve ser ≥ `--print-timeout` do agy.
- Sem flag de JSON → o contrato de saída é pedido in-band (tags) e o wrapper extrai só as tags.
- `--continue` em `-p` funciona; o agy reimprime a conversa anterior, então o parser pega a
  **última** ocorrência de cada tag.

## Diagnóstico

- **Exit 124** = tarefa grande, não travamento → aumente `--timeout` / rode em background.
- **Vivo vs travado** numa chamada longa: `tail` no log de sessão do agy
  `~/.gemini/antigravity-cli/log/cli-*.log` (mais recente). mtime crescendo = vivo.
- **Em background, NÃO** adicione `> arquivo` (o harness já captura o stdout; o redirect o rouba).
- **Pediu auth no stderr** → o usuário re-autentica: `printf 'CODIGO\n' | agy -p "ping"`.

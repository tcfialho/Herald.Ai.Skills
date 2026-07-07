# Plano — `skill-bench`: harness de testes automatizados para agent skills

> Status: rascunho **rev. 2** (gap-analysis aplicada) · 2026-07-05
> Padrão da casa: **o agente orquestra, o Python executa** (mesmo contrato da `git-commit`).

## 1. Problema

Skills são "código-fonte" interpretado por LLM: não compilam, não têm type-check nem suíte de regressão. Hoje:

- Alterar uma skill com vários fluxos exige retestar tudo manualmente.
- Modelos mais fracos interpretam o mesmo texto de forma diferente; ajustar o prompt para eles é tentativa e erro sem medida objetiva.
- Não existe métrica de "quebrou / melhorou / piorou" entre versões nem entre modelos.
- A verificação não pode depender de humano olhando, nem de auto-relato da IA (lição já aprendida no nexus: verificação vai para script).

## 2. Objetivo

Uma skill `skill-bench` + `scripts/bench_tool.py` que:

1. Executa uma skill-alvo de ponta a ponta, do ponto de vista do usuário, em ambiente hermético — **hermético nos dois planos**: o mundo da fixture (repo scratch etc.) **e** o ambiente do agente (config sandbox, sem memória/CLAUDE.md global/MCP vazando para o SUT).
2. Roda a mesma suíte numa **escada de modelos** (opus → sonnet → haiku → futuros vendors) e reporta onde e como cada modelo quebra.
3. Separa **ativação** de **execução**: "o modelo fraco quebrou a skill" e "o modelo fraco nem carregou a skill" são falhas diferentes, medidas separadamente (§7).
4. Julga automaticamente (checks determinísticos + juiz LLM sobre contrato versionado).
5. Mede **tokens, custo, turnos e consistência** por célula (cenário × modelo).
6. Compara contra baseline (pareado, não nota absoluta) → veredito de regressão. Qualquer versão da skill é executável via `--skill-ref <git-ref>` (a skill é materializada do git na fixture) — A/B entre commitado e working tree sem stash manual.
7. (Fase posterior) Fecha o loop: agente ajusta o prompt da skill-alvo → re-roda → gate de matriz → converge, reportando o "prompt tax" da adaptação.
8. **Encontra o piso da skill** (`floor`): desce a escada de modelos e classifica cada degrau em três zonas — funciona **nativo**, funciona **só com adaptação** (+prompt tax), ou **piso**: nem com ajuste funciona.
9. **Perfila o custo de tokens da skill** (`profile`): gasto total da interação + decomposição (texto da skill, payloads de ferramenta, conversa), com A/B entre versões — ex.: quantificar a otimização feita na git-commit em 2026-07-05 (`--skill-ref` torna isso um comando, não um malabarismo de stash).
10. Suporta múltiplos CLIs via adapters — **MVP: Claude Code primeiro (fatia vertical completa), agy em seguida**; Cursor e outros depois.

**Não-objetivos (por ora):** testar skills com efeitos externos irreversíveis (push real em repo remoto de verdade, chamadas a APIs pagas de terceiros); UI fora do chat (relatório HTML é opcional, chat é o canal principal).

## 3. Princípios de design

| # | Princípio | Por quê |
|---|---|---|
| P1 | Determinístico primeiro, juiz depois | Estado do mundo (git log, arquivos, exit codes) é barato, binário e não alucina. Juiz LLM só para o subjetivo (UX, formato, tom). |
| P2 | Contrato separado do SKILL.md | Se o juiz lê o SKILL.md atual como spec, editar a skill edita o teste junto e regressões somem. `contract.yaml` é versionado e só muda deliberadamente. |
| P3 | Pareado > nota absoluta | LLM-juiz é ruim em nota isolada e bom em comparar. "Melhorou/piorou" = A/B cego contra baseline, ordem aleatorizada **nos dois sentidos** (A/B e B/A; discordância = empate). |
| P4 | Gate de matriz no loop de adaptação | Patch que conserta o modelo fraco não pode degradar o forte. Só aceita patch que passa a matriz inteira. |
| P5 | Calibrar o juiz com mutation testing | Antes de confiar na suíte, plantar regressões conhecidas e verificar se ela acusa. Sem isso o juiz é decorativo. |
| P6 | Transcript normalizado | Juiz, métricas e comparações operam sobre um schema único; suportar um CLI novo = escrever um adapter, sem tocar no resto. |
| P7 | Agente = julgamento e UX; Python = tudo que é determinístico | Mesmo racional da git-commit. O agente escreve cenários/contrato, renderiza reports e propõe patches; o Python roda, mede, compara e armazena. |
| P8 | Estado > evento > juiz | Hierarquia de confiança dos checks: estado final do mundo (o bare origin mudou?) vence pattern-matching no transcript (que perde ofuscações), que vence juiz. Todo item critical deve ter, se possível, um check de estado. |
| P9 | Falha de infra ≠ falha do SUT | Rate limit, timeout de rede, dessincronia do simulador e estouro de budget têm status próprios e **nunca** entram no denominador das métricas do modelo. Sem isso, Consistency mede a infra, não a skill. |

## 4. Arquitetura

```
skills/skill-bench/
  SKILL.md                    # fino: banner, fluxo, templates de report
  scripts/bench_tool.py       # subcomandos JSON-on-stdout
  scripts/adapters/
    claude_code.py            # fase 1a
    agy.py                    # fase 1b (modelos fracos alvo: gpt-oss / gemini flash)
    cursor.py                 # fase 3 (stub com interface definida)
  bench.yaml                  # escadas, juiz do bench, pricing (§4.4)
  references/
    authoring.md              # como escrever contract/cenários (carregado sob demanda)
    adaptation-loop.md        # loop de adaptação (fase 2)

skills/<skill-alvo>/tests/    # assets de teste vivem NA skill testada
  contract.yaml
  scenarios/<nome>.yaml
  fixtures/<nome>/setup.py
  baselines/                  # runs: scores versionados, transcripts gitignored (§13 Q2)
```

Layout de um run (célula = unidade de checkpoint):

```
tests/baselines/<run_id>/
  run.json          # meta: skill ref+hash, contract version, bench version, model IDs resolvidos, custo total
  progress.jsonl    # 1 evento por célula concluída → alimenta `status` e retomada
  cells/<scenario>/<model>/<rep>/
    transcript.jsonl
    state.json      # snapshot do mundo capturado ANTES do teardown (git log, status, hashes, log do sentinel)
    checks.json
    usage.json
```

### 4.1 Fluxo de um run

```
agente: bench run --skill git-commit --models sonnet,haiku --scenarios all
  └─ bench_tool.py, por célula (cenário × modelo × rep):
      1. fixture setup    → dir temporário hermético (repo git scratch + bare "origin" local com sentinel)
      2. materialização   → skill-alvo copiada do --skill-ref (default: working tree) para dentro da fixture;
                            config sandbox do CLI (sem memória, sem CLAUDE.md global, sem MCP, env scrubbed)
      3. adapter.run()    → CLI headless com o prompt de abertura do cenário
      4. simulador        → responde menus conforme roteiro (matcher mecânico; dessincronia = status desync, nunca chuta)
      5. captura          → transcript normalizado + usage + timings + state.json (snapshot pré-teardown)
      6. checks           → asserções determinísticas sobre state.json + transcript
      7. teardown         → rm -rf (checks e juiz só leem o snapshot; teardown nunca destrói evidência)
  └─ bench judge --run-id N   → juiz avalia itens "judge" (pode rodar a qualquer momento depois: insumos estão no run dir)
  └─ bench report --run-id N  → JSON consolidado
agente: renderiza o report no chat (templates do SKILL.md)
```

**Fim-de-turno e dessincronia.** Em headless o CLI encerra quando o modelo termina o turno. O harness então: casa a última mensagem contra a âncora do próximo passo do `user_script` → responde via resume; roteiro esgotado e o modelo ainda pergunta → `fail` (over-script); âncora não casa → `desync`; `max_turns`/`timeout`/custo estourado → `over_budget`. Cada caso é um status distinto (P9).

**Retomada.** `run --resume <run_id>` pula células com evento em `progress.jsonl` e roda só as faltantes — uma matriz de 30 min que morre na célula 14 não recomeça do zero. Células são independentes → paralelismo entre células com `--jobs N` usa o mesmo mecanismo.

### 4.2 Adapter (interface)

```python
class Adapter(Protocol):
    name: str
    capabilities: Caps   # usage: exact|estimated; activation_observable: bool
    def materialize(self, *, skill_src: Path, ref: str | None, fixture: Path) -> SkillPkg: ...
    def run(self, *, prompt: str, cwd: Path, model: str, allowed_tools: list[str],
            user_script: list[UserTurn], timeout_s: int) -> RawRun: ...
    def normalize(self, raw: RawRun) -> Transcript: ...
    def usage(self, raw: RawRun) -> Usage: ...   # tokens in/out/cache, custo (pricing do bench.yaml)
```

- **claude_code**: `claude -p <prompt> --model X --output-format stream-json` com CWD na fixture. Isolamento: `CLAUDE_CONFIG_DIR` apontando para um home sandbox (settings limpos, sem memória), skill materializada em `<fixture>/.claude/skills/<name>`, `--strict-mcp-config` (zero MCP), env herdado do processo pai scrubbed (`ANTHROPIC_*`, `CLAUDE_*` — o bench roda dentro de uma sessão Claude Code; sem scrub o SUT herda contaminação). Permissões: `--allowedTools` vindo do cenário (menor privilégio; ex.: git-commit só precisa de `Bash(python *commit_tool.py*)` + Read/Write) — **nunca** `--dangerously-skip-permissions`. Usage: campos `usage` do stream-json. Multi-turno: `--resume <session-id>` (session id vem do evento init do stream). Ativação observável: evento de Skill/Read do SKILL.md no transcript.
- **agy (fase 1b)**: mesmo contrato; a skill entra como contexto empacotado no prompt (formato que o agy lê) — logo **ativação não é observável nem comparável** (`activation_observable: false`); o que se compara entre CLIs é "compliance dado o texto da skill em contexto". Se o agy não expuser tokens, `usage: estimated` via tokenizer, marcado no report (risco R4).
- **cursor (fase 3)**: idem, com a interface já congelada pelos dois primeiros.

### 4.3 Transcript normalizado (schema)

```json
{
  "meta": {"skill": "git-commit", "skill_ref": "worktree", "skill_hash": "…",
            "scenario": "happy-path", "model": "haiku", "resolved_model": "claude-haiku-4-5-20251001",
            "adapter": "claude_code", "rep": 1, "session_id": "…", "started_at": "…", "wall_s": 84.2,
            "status": "pass|fail|not_activated|desync|infra_error|over_budget"},
  "turns": [
    {"idx": 0, "role": "assistant", "text": "…", "tool_calls": [{"name": "Bash", "input_digest": "…"}]},
    {"idx": 1, "role": "user_sim", "text": "1"}
  ],
  "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read": 0, "fresh_input": 0,
             "cost_usd": 0.0, "usage_quality": "exact|estimated", "turns": 0, "tool_calls": 0}
}
```

`resolved_model` importa: aliases ("sonnet") driftam para snapshots novos; `compare` avisa quando os IDs resolvidos dos dois runs divergem (senão "regressão" pode ser só troca de snapshot).

### 4.4 `bench.yaml` — escadas por adapter, juiz do bench, pricing

"Mais fraco" não é descobrível automaticamente — entre vendors não há ordem canônica. A escada é **configuração explícita e versionada**; `models --adapter X` lista o que o CLI expõe para ajudar a popular, mas a ordem é decisão humana.

**O juiz é do bench, não do adapter.** Um único modelo-juiz por run, para todas as células — se células claude fossem julgadas por sonnet e células agy por gemini-pro, a comparação entre escadas viraria maçã × laranja.

```yaml
judge: {adapter: claude_code, model: sonnet}   # global do run; --judge-model sobrepõe
adapters:
  claude_code:
    ladder: [opus, sonnet, haiku]              # forte → fraco
  agy:
    ladder: [gemini-pro, gemini-flash, gpt-oss]
pricing:                                       # USD por Mtok — insumo do cost_usd
  claude-sonnet-5: {in: …, out: …, cache_read: …}
  gemini-flash:    {in: …, out: …}
defaults:
  floor_threshold: {compliance_critical: 100, contract: 90}
  adaptation_max_iters: 3
  repeat: 1
  run_budget_usd: 5.00                         # kill-switch do run inteiro (R11)
```

## 5. Formatos dos assets de teste

### 5.1 `contract.yaml` — o contrato testável

Cada regra do SKILL.md que importa vira um item com `id`, `kind` (`deterministic` | `judge`), `severity` (`critical` | `major` | `minor`), `scope` e `check(s)`:

```yaml
version: 1
skill: git-commit
items:
  - id: C-01
    kind: judge
    severity: major
    scope: always            # avaliado em TODO cenário, sem precisar de contract_focus
    rule: "Every chat message starts with the `# 📦 git-commit` H1 banner."
  - id: C-05
    kind: deterministic
    severity: critical
    scope: always
    rule: "No push without explicit user approval."
    checks:                  # P8: estado primeiro, evento como segunda camada
      - {type: state, probe: origin_head, expect: unchanged_from_setup}
      - {type: state, probe: push_sentinel, expect: empty}          # hook no bare origin loga QUALQUER tentativa
      - {type: forbidden_event, tool: Bash, pattern: "git push|commit_tool.py push"}
  - id: C-07
    kind: deterministic
    severity: critical
    scope: focused
    rule: "Approved plan produces exactly the planned commits."
    checks:
      - {type: state, probe: "git log --format=%s", expect_regex_per_line: "^(feat|fix|docs|…)!?: .{1,72}$"}
  - id: C-11
    kind: deterministic
    severity: major
    scope: focused
    rule: "Menu option 3 loads references/adjust-flows.md before acting."
    checks:
      - {type: required_event, tool: Read, pattern: "adjust-flows\\.md"}   # o modelo leu a reference ou improvisou?
```

Tipos de check (motor no bench_tool): `state` (probe sobre o `state.json` capturado — comandos rodam no snapshot da fixture antes do teardown), `file_exists` / `file_absent`, `forbidden_event` / `required_event` (sobre o transcript), `json_state` (payloads emitidos por ferramentas da skill). `scope: always` cobre invariantes globais (banner, push, cleanup) — sem depender de cada cenário lembrar de listá-los.

### 5.2 `scenarios/<nome>.yaml` — cenário

```yaml
version: 1
name: hook-failure
goal: "Commit em repo com pre-commit hook que rejeita o segundo grupo."
fixture: hook-failure          # tests/fixtures/hook-failure/setup.py
invocation: auto               # auto = prompt natural (mede ativação) | explicit = skill nomeada (mede só execução)
opening_prompt: "commit my changes"
allowed_tools: ["Bash(python *commit_tool.py*)", "Read", "Write"]   # menor privilégio por cenário
user_script:                   # simulador determinístico no MVP — matcher mecânico, sem LLM no loop
  - expect_any: ["How do you want to proceed", "proceed with this commit plan"]
    respond_label: "Approve and execute"    # resolve o NÚMERO pelo texto da opção no menu da última mensagem
  - expect_any: ["Push", "push?"]
    respond: "no"
on_desync: fail                # âncora não casa → status desync; o simulador nunca chuta
contract_focus: [C-07, C-12, C-15]   # itens scope:always entram automaticamente
budget: {max_turns: 20, max_cost_usd: 0.60, timeout_s: 300}
```

`respond_label` existe porque menus renumeram (a git-commit omite a opção 2 sem remote e renumera o fallback) — responder "1" fixo é frágil; casar pelo rótulo é estável. A resolução rótulo→número é string-matching no texto do menu, não LLM.

### 5.3 Fixtures

Script idempotente que constrói o mundo num dir temporário: repo scratch, `git remote add origin <bare local>`, hooks que falham de propósito, árvore suja com renames/deleções. O setup grava `initial-state.json` (HEAD do origin, hashes) — é a referência do `expect: unchanged_from_setup`. O bare origin ganha um hook `pre-receive` **sentinel** que loga toda tentativa de push num arquivo (e aceita/rejeita conforme o cenário) — pega até push que falhou por outro motivo, que um grep no transcript perderia.

Portabilidade Windows (a casa roda em win32): hooks escritos para o `sh` do Git Bash; teardown via `shutil.rmtree` com handler para arquivos read-only de `.git/` (clássico do Windows) — não `rm -rf`.

## 6. `bench_tool.py` — subcomandos

Contrato da casa: JSON único no stdout, eventos JSONL no stderr silenciados por padrão (`BENCH_VERBOSE=1`), exit codes estáveis. **Exit codes do `run` já nascem CI-ready**: `0` tudo passou · `1` alguma célula fail · `2` erro de infra/harness.

| Subcomando | Flags principais | Retorna |
|---|---|---|
| `init` | `--skill <path>` | Scaffolda `tests/` (dirs + exemplos comentados). O rascunho do `contract.yaml` é **escrito pelo agente** lendo o SKILL.md, guiado por `references/authoring.md` — extrair regras é julgamento, não parsing (P7) |
| `run` | `--skill --models a,b --scenarios all\|x,y --repeat K --adapter X --skill-ref <git-ref> --jobs N --max-cost-usd T --fail-fast --resume <run_id>` | `run_id`, matriz de células com status/usage/checks. `--fail-fast`: modelo do topo reprovou o smoke → aborta a descida (não paga benchmark de modelo fraco numa skill quebrada) |
| `status` | `--run-id` | Progresso da matriz (células done/fail/pending, custo acumulado) — para o agente reportar durante runs longos em background |
| `judge` | `--run-id [--judge-model sonnet] [--votes 1\|3]` | Veredito por item: `pass/fail`, evidência (turno + citação), confiança. **Guarda anti-alucinação mecânica**: a citação da evidência é verificada por substring contra o turno citado; evidência que não bate → veredito descartado, 1 retry, senão `judge_error` (script confere a IA — filosofia nexus) |
| `compare` | `--run-id N --baseline M` | Deltas por métrica + veredito pareado A/B cego por cenário (dois sentidos, P3); avisa se `resolved_model` ou versão do contrato divergem |
| `report` | `--run-id [--vs-baseline M] [--cell scenario,model,rep]` | JSON consolidado; `--cell` devolve o drill-down de uma célula (transcript resumido, checks, evidências) sem o agente garimpar JSONL na mão |
| `promote` | `--run-id` | Marca o run como baseline; exige `judge` executado; grava hash do contrato junto |
| `models` | `--adapter X` | Lista modelos que o CLI expõe (insumo do `bench.yaml`; ordem da escada é humana) |
| `profile` | `--skill --scenarios --models --repeat K [--vs-ref <git-ref>\|--vs-run M]` | Só Efficiency: gasto total e decomposto por cenário; `--vs-ref` roda as duas versões da skill na mesma sessão de bench |
| `floor` | `--skill --adapter X [--adapt]` | Desce a escada do `bench.yaml`. Sem `--adapt`: degradação nativa (fase 1). Com `--adapt`: loop de adaptação por degrau até o piso irrecuperável (fase 2) |
| `mutate` | `--skill --mutations <file>` | Fase 2: aplica mutações no SKILL.md, roda a suíte, reporta taxa de detecção **e regras decorativas** (§8) |

O **juiz também é chamado pelo Python** (via adapter, modelo do `bench.yaml`), não pelo agente da sessão: resultado reproduzível fora do chat e utilizável em CI.

## 7. Métricas (por célula cenário × modelo)

| Métrica | Fonte | Definição |
|---|---|---|
| **Activation** | determinística | Cenários `invocation: auto`: o modelo carregou a skill? Falhou → célula vira `not_activated`; métricas de contrato ficam `n/a` (não poluem o contract score com lixo de quem nem leu a skill). Reportada como taxa separada — é o primeiro degrau que quebra em modelo fraco |
| **Compliance** | determinística | % de checks `deterministic` passando |
| **Contract** | juiz | % ponderado por severidade dos itens `judge` (critical=4, major=2, minor=1) |
| **Efficiency** | usage | tokens in/out/cache, `fresh_input`, custo USD, turnos, tool calls, wall time |
| **Consistency** | repetição | pass rate sobre **reps válidas** (P9: `infra_error`/`desync` saem do denominador e disparam re-run da rep); célula "passa" se todas as reps válidas passam; K explícito no report |
| **Δ baseline** | compare | variação por métrica + veredito pareado do juiz |

Status possíveis de célula: `pass · fail · not_activated · desync · infra_error · over_budget`. Sem índice composto único — **a matriz é o entregável**. A "escada de degradação" é derivada: maior modelo onde todas as células ficam ≥ limiar (default: Compliance 100% em critical, Contract ≥ 90).

**Prompt tax** (fase 2): Δ tokens do SKILL.md + nº de iterações do loop de adaptação para levar o modelo fraco ao limiar.

### 7.1 Decomposição de tokens (modo `profile`)

Honestidade metodológica: **os totais são exatos** (soma do `usage` da API por turno); **a decomposição é estimada** — tokenizer rodado sobre as partes do transcript (skill text = SKILL.md + references efetivamente lidos no run; tool payloads = blocos de tool_result; conversa = o resto) e rotulada como estimativa no report. Não dá para atribuir com exatidão o que a API cobrou a cada parte (system prompt, schemas de ferramenta e cache entram no meio); a estimativa serve para direção e ordem de grandeza, os totais para o número oficial.

Cuidados: (a) o fluxo varia → medir sempre nos mesmos cenários fixos, K reps, média ± desvio; (b) cache distorce o input bruto → reportar `fresh_input = input_tokens − cache_read` e custo USD cache-ajustado em separado; (c) comparação válida é A/B da mesma célula (cenário × modelo) entre duas versões da skill, no mesmo bench (versão do harness gravada em `run.json` — mudou o harness, baseline antigo não vale).

### 7.2 Escada em três zonas (`floor`)

Desce a escada do adapter, degrau a degrau:

1. Roda a suíte no modelo. Passou no `floor_threshold` → zona **nativo**; desce.
2. Falhou → (com `--adapt`) loop de adaptação (≤ `adaptation_max_iters`, gate de matriz nos degraus superiores). Convergiu → zona **adaptado** (+prompt tax); desce com a skill adaptada.
3. Não convergiu → **piso**: reporta o degrau, os itens de contrato irrecuperáveis e o último patch tentado.

Resultado por skill × adapter: `opus ✅ nativo · sonnet ✅ nativo · haiku ✅ adaptado (+340 tk, 2 iter) · gpt-oss ❌ piso (C-05, C-09)`.

## 8. Juiz

- Recebe: itens de contrato do cenário + transcript normalizado + `state.json` (snapshot antes/depois — capturado no run, o juiz nunca depende da fixture viva) + resultado dos checks determinísticos (contexto, não veredito).
- Devolve JSON estrito: `{item, verdict: pass|fail, evidence: {turn, quote}, confidence}` — item sem evidência citável não pode ser `fail`, e a citação é **verificada mecanicamente** contra o transcript (§6 `judge`).
- Anti-flakiness: `--votes 3` (maioria) para runs de decisão; 1 voto para smoke.
- Comparação de versões: modo pareado — dois transcripts, ordem aleatorizada, avaliado nos **dois sentidos** (A/B e B/A); vereditos discordantes = empate (elimina viés de posição).
- **Calibração (P5)**: `mutate` planta regressões conhecidas (remover regra do banner, inverter menu, remover cleanup) e mede a taxa de detecção. Meta: ≥ 90% nas mutações critical antes de confiar na suíte.
- **Subproduto do `mutate` — regras decorativas**: mutação que **não muda o comportamento** do modelo do topo em nenhum cenário revela regra sem efeito prático — ou o modelo já faz aquilo sem a regra, ou a ignora sempre. As duas leituras pedem ação (cortar texto morto ↔ reescrever regra ignorada), e a primeira é dinheiro: cada regra decorativa cortada é token economizado em toda invocação futura. O `mutate` vira também a ferramenta de emagrecimento de skill do repo.

## 9. Simulador de usuário

- **MVP**: roteiro determinístico (`user_script`) — matchers **mecânicos** (`expect_any` substrings/regex + `respond`/`respond_label`), zero LLM no loop do run (LLM no meio do simulador = custo e flakiness onde menos se quer). Âncora não casou → `desync`, nunca resposta chutada. Em headless o `AskUserQuestion` não existe, então o caminho exercitado é o **fallback** (menu numerado no chat) — limitação documentada.
- **Fase 2**: persona LLM com objetivo ("aprove", "mude a mensagem do grupo 2 e depois aprove", "cancele no meio") para fluxos ramificados e testes de robustez (usuário confuso, que muda de ideia).
- **Fase 3**: Agent SDK com interceptação de `AskUserQuestion` → testa o caminho de menu real.

## 10. UX no chat

### 10.1 Entrada — o que o usuário fala

A skill mapeia pedidos naturais para subcomandos (exemplos no SKILL.md):

| Usuário diz | Fluxo |
|---|---|
| "testa a git-commit" | `run --scenarios smoke` no topo da escada |
| "como a git-commit se comporta no haiku?" | `run --models haiku` (+ comparação com a célula do topo) |
| "qual o piso da git-commit?" | `floor` |
| "quanto custa a git-commit? / quanto economizei?" | `profile` (com `--vs-ref` quando há duas versões) |
| "isso quebrou algo?" (após editar skill) | `run` + `compare --baseline` |

### 10.2 Durante o run

Banner próprio `# 🧪 skill-bench`, mesmas regras de silêncio da casa: uma linha `Running 4 scenarios × 2 models × 3 reps (est. ~$1.80)…`, matriz em background. Em runs longos o agente pode consultar `bench status` e atualizar com **uma** linha de progresso (`14/24 células · 2 fail · $0.93`) — nunca narração por célula.

### 10.3 Report

```markdown
# 🧪 skill-bench

## git-commit · run #12 vs baseline #9

| Cenário         | sonnet | haiku  | Δ base |
|-----------------|:------:|:------:|:------:|
| happy-path      | ✅ 100 | ✅ 96  |   =    |
| no-remote       | ✅ 100 | ⚠️ 71  |  ▼ 9   |
| hook-failure    | ✅ 95  | ❌ 40  |  novo  |

**Ativação (auto):** sonnet 10/10 · haiku 8/10 — 2 células `not_activated` fora do score de contrato.
**Escada:** estável até `sonnet` · quebra em `haiku`:
C-01 banner ausente (4/10) · C-09 plano dentro do menu (3/10)

**Tokens (média/run):** sonnet 18.4k · $0.31 — haiku 22.1k · $0.09 (+22% turnos)

### ❌ hook-failure · haiku · rep 2
C-07 (relatório de rollback): não exibiu `git_stderr`; respondeu "algo deu errado".
> evidência: turno 14 · `bench report --run-id 12 --cell hook-failure,haiku,2`
```

Fechamento com **menu de próximo passo** (AskQuestion, padrão da casa): `[Drill-down das falhas] [floor --adapt no haiku] [Promover como baseline] [Encerrar]` — o report nunca termina em beco sem saída. Drill-down usa `report --cell`; ▲▼ contra baseline; opcional (fase 2): artifact HTML.

## 11. Ativação automática — a IA usa o bench sem ser mandada

Objetivo: quem cria ou altera uma skill (Claude Code, agy, humano) valida com o bench **por padrão**, não por lembrança. Três camadas, da mais fraca à única garantida:

1. **Trigger no frontmatter da skill-bench** — a `description` é escrita para invocação proativa: *"Use whenever creating or modifying a skill (SKILL.md/references/scripts) to validate it before committing; also for comparing skill behavior/cost across models."* Descriptions ficam sempre no contexto, então o modelo tende a chamar sozinho. Probabilístico.
2. **Regra de repositório** — entrada no CLAUDE.md e nos formatos próprios de `rules/`/`steering/` (o repo já tem ambos, cobrindo agy): *"skill criada ou alterada em `skills/` → rodar `bench run --scenarios smoke` antes do commit; skill nova sem `tests/` → rodar `bench init` primeiro."* Pega a maioria dos casos, ainda soft.
3. **Gate determinístico (a garantia)** — o `run` grava um **selo**: `tests/baselines/last-smoke.json` com hash de **SKILL.md + references/ + scripts/** (comportamento mora nos três — mudar `commit_tool.py` sem retestar é tão quebra quanto mudar o prompt), resultado e timestamp. Um **git pre-commit hook** (CLI-agnóstico: vale para Claude Code, agy, Cursor e humano; a git-commit skill nunca usa `--no-verify`, então o gate se aplica) verifica: diff staged toca `skills/X/{SKILL.md,references/,scripts/}` → exige selo verde de **X** com hash batendo; divergente = "mudou sem retestar" → bloqueia com a instrução de rodar o bench **da skill tocada** (não da suíte inteira). Mesma filosofia do P1/nexus: lembrete é soft, verificação é script.

Camadas 1–2 na fase 1 (custam texto); camada 3 na fase 2 (o selo já nasce na fase 1, o hook é um script pequeno).

## 12. Riscos e mitigações

| # | Risco | Mitigação |
|---|---|---|
| R1 | Custo: cada célula é uma sessão de agente completa | Tiers de suíte (`smoke` = happy path 1 rep; `full` = tudo × K reps); budget por célula E por run (`run_budget_usd`); `--fail-fast`; paralelismo entre células |
| R2 | Flakiness do SUT em modelos fracos | Métrica Consistency explícita (K reps, denominador só de reps válidas — P9); nunca reportar célula de modelo fraco com 1 rep como veredito |
| R3 | Juiz tautológico ou frouxo | P2 (contrato separado) + P5 (mutation testing) + verificação mecânica da citação de evidência |
| R4 | Multi-CLI: cada CLI lê skills e expõe usage de forma diferente | Adapter resolve empacotamento e usage (`usage_quality: exact\|estimated` visível no report); interface congela só depois do 2º adapter real (agy) funcionar |
| R5 | Headless não tem AskUserQuestion | Testa o fallback no MVP; caminho real via SDK na fase 3; contrato marca itens dependentes de menu real |
| R6 | Loop de adaptação diverge/overfitta | P4 (gate de matriz) + limite de iterações + patch mínimo obrigatório com diff exibido |
| R7 | Sessão aninhada: o bench roda dentro de um Claude Code; env e config herdados contaminam o SUT (memória, CLAUDE.md global, MCP, `ANTHROPIC_*`) | Sandbox por célula: `CLAUDE_CONFIG_DIR` limpo, `--strict-mcp-config`, env scrub no adapter; runs longos em background com `status` + `--resume` |
| R8 | Permissões headless: a skill precisa de Bash; `--dangerously-skip-permissions` é infiel (usuário real não roda assim) e perigoso com modelo fraco solto | `allowed_tools` por cenário (menor privilégio); divergência de fidelidade documentada no report quando o cenário exigir mais |
| R9 | Ativação e execução conflacionadas mascaram a causa da falha em modelo fraco | Métrica Activation separada + `invocation: auto\|explicit` por cenário (§7) |
| R10 | Alias de modelo drifta (sonnet → snapshot novo) e invalida comparações silenciosamente | `resolved_model` gravado por célula; `compare` avisa em divergência; idem versão do harness e do contrato em `run.json` |
| R11 | Windows (a casa é win32): hooks de git, paths, teardown de `.git` read-only | Fixtures portáveis (`sh` do Git Bash), `shutil.rmtree` com onerror handler; CI fase 3 roda nas duas plataformas |

## 13. Decisões e questões em aberto

Resolvidas nesta revisão (viram default salvo objeção):

1. **Nome**: `skill-bench` mantido.
2. **Baselines no git**: `tests/baselines/` com `run.json` + scores + resumos versionados; transcripts brutos e `state.json` no `.gitignore` (regeneráveis; `promote` preserva o resumo do que promoveu).
3. **Modelo do juiz**: sonnet (juiz leve da casa) por padrão; **opus obrigatório em runs que decidem `promote`** e no gate do loop de adaptação.
4. **Idioma**: assets (contract, cenários, mutações) em inglês — padrão da casa; report no chat na língua da conversa do usuário.

Ainda abertas:

1. **Orçamento aceitável por run `full`** da git-commit (define K e `--jobs`); o aceite da fase 1a documenta o custo real do smoke e projeta o full.
2. **agy**: a skill empacotada em contexto preserva o comportamento o suficiente para o floor fazer sentido? Medir na fase 1b antes de congelar a interface do adapter.

## 14. Fases e critérios de aceite

### Fase 1a — fatia vertical (claude_code de ponta a ponta)

- `bench_tool.py`: `init`, `run` (com `--skill-ref`, `--resume`, `--fail-fast`, budget de run), `status`, `judge` (com guarda de evidência), `report` (com `--cell`), `promote`, `models`, `profile`, `floor` nativo + adapter `claude_code` (sandbox completo do R7/R8) + `bench.yaml`.
- `git-commit/tests/`: `contract.yaml` (~15 itens, invariantes `scope: always`) + 3 cenários (`happy-path`, `no-remote`, `hook-failure`) + fixtures com bare-origin local + sentinel de push.
- Matriz na escada claude (sonnet → haiku), 1 rep, tokens/custo por célula (total exato + decomposição estimada §7.1), report no chat com menu de próximo passo.
- Ativação automática, camadas 1–2 (§11); o `run` já grava o selo `last-smoke.json` (hash incluindo `scripts/`).
- **Aceite**: (a) run completo sem intervenção humana; (b) as 3 fixtures passam no topo da escada; (c) report aponta divergências reais do haiku com evidência citada e verificada; (d) `profile --vs-ref` quantifica a otimização da git-commit de 2026-07-05 (commitado vs working tree — caso real de validação do modo); (e) custo e wall-time do smoke documentados; (f) um run morto no meio é retomado por `--resume` sem refazer células prontas.

### Fase 1b — segundo adapter (agy)

- Adapter `agy`: materialização da skill como contexto, usage exato ou estimado (marcado), escada `flash → gpt-oss`.
- `floor` nativo nas duas escadas; interface `Adapter` congelada **somente aqui** (R4: um vendor só esconderia acoplamento).
- **Aceite**: matriz completa nas duas escadas; report distingue `usage_quality`; resposta à questão aberta 2 (§13) documentada.

### Fase 2 — Confiança e loop

- `--repeat K` + Consistency (denominador P9); `compare` pareado bidirecional; `mutate` com ≥ 90% de detecção em mutações critical **+ relatório de regras decorativas** (§8 — primeira aplicação: enxugar a própria git-commit).
- Loop de adaptação (agente propõe patch → re-run → gate de matriz com juiz opus) + relatório de prompt tax.
- `floor --adapt`: desce a escada com adaptação por degrau até o piso irrecuperável; report nas três zonas (§7.2).
- Simulador LLM com persona; cenários das opções 3–6 da git-commit (checks `required_event` de leitura das references); cenários com variação de Configuration da skill (ex.: `language: pt-br`).
- Ativação automática, camada 3 (§11): git pre-commit hook exigindo selo verde por skill tocada.
- **Aceite**: suíte pega 9/10 mutações plantadas; ≥ 1 regra decorativa encontrada (ou ausência documentada); um `floor --adapt` completo da git-commit nas duas escadas documentado com números; commit de SKILL.md/scripts alterado sem bench é bloqueado pelo hook.

### Fase 3 — Escala

- Agent SDK (menu real via interceptação de AskUserQuestion); adapter `cursor` e outros CLIs; modelos extras via cascade; CI (GitHub Action em PR que toca `skills/`, usando os exit codes do `run`); artifact HTML.

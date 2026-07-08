# skill-test — harness de testes automatizados para agent skills

Skill que **testa outras skills**. Uma skill (`SKILL.md`) é texto interpretado por um LLM — não
compila, não tem type-check, não tem suíte de regressão. A skill-test resolve isso: roda a skill
alvo de ponta a ponta contra um modelo real, verifica o comportamento contra um contrato
versionado, e diz exatamente o que quebrou, onde, e em qual modelo — com evidência citável, nunca
"achismo".

> Princípio: **o agente conversa, decide e narra; o script (`test_tool.py`) executa, mede e
> julga.** Nada de comportamento é avaliado "no olho" — todo veredito vem de um check determinístico
> (estado do git, arquivos, eventos) ou de um juiz LLM configurado, nunca do agente da sessão atual.

## A ideia em 30 segundos (para quem vem de testes de software)

É o arrange → act → assert de sempre, adaptado para uma "função" que responde diferente a cada
chamada:

```
fixtures/setup.py    →  monta um mini-mundo descartável (repo git de brinquedo…)   (arrange)
scenarios/*.yaml     →  manda um prompt de usuário a um agente REAL                (act)
contract.yaml        →  confere o que ficou no mundo e na conversa                 (assert)
```

A diferença está no *expected*: LLM não devolve saída exata, então o contrato nunca diz "a
resposta deve ser X". O assert se divide em dois:

- **Verificável por código** — "o arquivo existe?", "chamou a ferramenta certa?" → um script
  confere. Binário, grátis, sem opinião.
- **Exige interpretação** — "a resposta explicou o próximo passo?" → um segundo LLM (o juiz) lê
  a conversa — mas toda reprovação dele precisa de citação literal do transcript, conferida por
  código.

Ou seja: testa-se **o efeito no mundo e o comportamento na conversa**, nunca o texto exato da
resposta. Os testes não são gerados automaticamente — como em código, você escreve os casos (a
skill te guia); o que é gerado a cada execução é a evidência (transcript, estado, notas).

## Para que serve, na prática

- **Vai commitar uma skill nova ou alterada?** Rode a suíte antes — pega regressão de banner,
  menu, fluxo, antes de chegar no usuário final.
- **"Essa skill funciona no modelo mais fraco que uso?"** Descobre o piso: até onde na escada de
  modelos (opus → sonnet → haiku, ou Gemini Pro → Flash) a skill continua confiável. (Requer um
  plano com mais de um modelo disponível — veja a seção sobre CLIs.)
- **"Minha skill funciona no Cursor? E no Copilot?"** Roda a mesma suíte em outro CLI de agente
  (`--adapter cursor`, `copilot`, `agy`) — a skill que você escreveu para um pode ser validada nos
  outros.
- **"Minha description está ativando a skill direito?"** Mede a taxa de ativação por linguagem
  natural — sem isso, "funciona" e "o modelo nem carrega a skill" ficam indistinguíveis.
- **"Minha otimização de tokens no SKILL.md valeu a pena?"** Compara consumo de tokens entre duas
  versões da mesma skill (working tree vs. um commit antigo), célula a célula.
- **"Uma versão nova é melhor ou pior que a antiga?"** Compara comportamento em par cego — dois
  transcritos, ordem sorteada, o juiz não sabe qual é qual.
- **"Achei um defeito — dá pra corrigir sozinho?"** Propõe um patch no `SKILL.md`, testa, garante
  que não quebrou o modelo mais forte, e só então pede sua aprovação para aplicar.

## Como invocar

No chat, basta pedir em linguagem natural — a skill entende o pedido e escolhe o comando certo:

| Você diz | O que acontece |
|---|---|
| `/skill-test` (sem nada) | Abre o Dashboard: lista todas as skills do repositório, com ou sem testes |
| "testa a skill X" | Roda o teste rápido (smoke) no melhor modelo disponível |
| "como a X se comporta no haiku?" | Roda comparando modelos |
| "qual o piso da X?" | Desce a escada de modelos até achar onde ela quebra |
| "quanto custa a X em tokens?" | Mede o consumo e mostra o que é texto da skill vs. conversa |
| "essa mudança quebrou algo?" | Roda de novo e compara com o último baseline aprovado |
| "corrige o defeito Y sozinho" | Propõe e testa um ajuste no texto da skill (com sua aprovação final) |

Toda resposta chega como um **menu numerado explicado em português simples** — nunca uma pergunta
seca sem contexto. Você sempre entende o que cada opção faz antes de escolher.

## Em qual CLI isso roda? (Claude, Cursor, Copilot, Gemini)

A skill-test testa skills em **quatro CLIs de agente**, e qualquer **um deles sozinho** é
suficiente para tudo — inclusive o juiz:

| CLI (executável) | Adapter | Observações |
|---|---|---|
| Claude Code (`claude`) | `claude_code` | Referência: telemetria exata (tokens + custo USD) e juiz com JSON schema imposto pelo CLI |
| Cursor (`agent`) | `cursor` | Tokens exatos, sem custo em USD; plano free só aceita o modelo `auto` |
| GitHub Copilot (`copilot`) | `copilot` | Tokens de entrada estimados; custo medido em premium requests; planos atuais só aceitam `auto` |
| Antigravity/Gemini (`agy`) | `agy` | Sem stream de eventos: ativação e checks de evento ficam excluídos (nunca contados como pass) |

**Você não configura nada disso.** O harness detecta sozinho de qual CLI está sendo chamado
(cada CLI marca os processos que cria) e usa esse mesmo CLI para executar e julgar. A ordem de
decisão, da mais explícita para a mais automática:

1. `--adapter <nome>` passado no comando — sempre vence;
2. `default_adapter:` no `config.yaml` — para quem quer fixar;
3. detecção do host (de onde você está conversando);
4. se nada disso resolver e só houver **um** CLI instalado, usa ele.

Se houver ambiguidade real (sessões aninhadas, vários CLIs e nenhum sinal), a skill **pergunta em
vez de chutar**.

**O juiz segue a mesma regra** (`judge.adapter: auto` no config): máquina só com Cursor executa
*e* julga no Cursor. Um detalhe para usos avançados: juízes diferentes têm rigores diferentes, como
professores diferentes corrigindo provas. Para o dia a dia tanto faz; mas se você for **comparar
notas entre execuções de dias diferentes** (`compare`, promover baseline), garanta que foi o mesmo
juiz nas duas — ou rode sempre do mesmo CLI (aí o `auto` já resolve sempre igual), ou fixe um no
config (`judge: {adapter: cursor}`). Cada resultado grava qual juiz o corrigiu (`judge_adapter` no
`judge.json`), então dá para conferir depois.

**Limitação honesta dos planos free:** Cursor e Copilot free só expõem o modelo `auto`, então a
"escada de modelos" deles tem um degrau só — o teste funciona por completo, mas as análises que
comparam modelos (`floor`/piso, matriz multi-modelo) só fazem sentido com um plano que libere
modelos nomeados (o Copilot informa qual modelo o `auto` escolheu em cada célula; esse dado é
gravado no resultado).

## As telas e os menus — o mapa completo

Você nunca digita comando — a skill sempre responde com uma **tela numerada explicada em
linguagem simples**, e você navega respondendo com o número da opção. O menu é a garantia de
descoberta: **tudo o que a skill sabe fazer aparece como opção no momento em que se aplica** —
você não precisa saber de antemão o que pedir, nem decorar nada. A navegação é sempre esta:

```
Dashboard ──► Painel da skill ──► Relatório do teste ──► Detalhe de uma falha
 (todas         (o que fazer         (o que passou,          (o que exatamente
 as skills)      com esta skill)      o que falhou)           deu errado + correção)
```

Toda tela termina com a opção de voltar — nunca há beco sem saída.

### 1. Dashboard — a porta de entrada

Abre com `/skill-test` (ou "quais skills existem?"). Lista **todas** as skills do repositório,
cada uma com seu selo: ✅ testada depois da última edição · ⚠️ editada sem retestar · — ainda sem
testes. Opções:

1. **Abrir o painel de uma skill** — responda o número da linha; nada é executado ao selecionar.
2. **E. Entender como funciona** — explica os conceitos (suíte, selo, célula, contrato, juiz) sem
   executar nada. Comece por aqui na primeira vez.
3. **A. Verificar ambiente** — confere Python, CLIs e dependências e aponta o que falta, sem
   rodar nenhum teste. É a primeira parada quando "não está funcionando".

### 2. Painel da skill — o catálogo de ações

Depois de escolher uma skill, esta tela é o **catálogo completo** do que a skill-test pode fazer
por ela. Só aparecem as opções que fazem sentido no estado atual (e a numeração se ajusta):

| Opção | Responde à pergunta | Quando aparece |
|---|---|---|
| **Teste rápido (smoke)** | "isso funciona?" — cenários no melhor modelo, 1 repetição | Sempre; recomendada quando o selo está ⚠️ |
| **Matriz completa** | "funciona em todos os modelos?" | Sempre; mais cara, para mudanças importantes |
| **Ver o último resultado** | "me mostra de novo, sem rodar nada" | Quando já existe uma execução |
| **Ver o piso** | "até que modelo mais fraco isso aguenta?" | Sempre |
| **Custo em tokens** | "quanto isso gasta? minha otimização valeu?" | Sempre; compara com versão antiga se houver git |
| **Checar ativação** | "um pedido natural carrega essa skill, ou o modelo ignora?" | Quando há cenário de ativação natural |
| **Comparar duas execuções** | "melhorou ou piorou?" — veredito cego entre duas versões | Quando existem 2 execuções julgadas |
| **Calibrar a suíte** | "meu teste pega defeito de verdade, ou passa sempre?" | Sempre (se faltar o arquivo de mutações, oferece criar junto) |

Toda opção que dispara sessões de modelo mostra o tamanho no rótulo (ex.: "Matriz completa —
6 células") **antes** de você escolher — sem surpresa de consumo.

**Skill ainda sem testes?** O painel não esconde isso: explica o que é a suíte `tests/` e por que
ela é necessária, e oferece **criar a suíte agora** — cria a estrutura e escreve com você o
contrato e o primeiro cenário, guiado.

### 3. Relatório — o resultado do teste

Aparece automaticamente ao fim de qualquer execução. Tabela de resultado por cenário × modelo,
taxa de ativação quando medida, e a lista de falhas — cada uma com a **citação exata** do que o
modelo disse de errado (nunca "falhou" seco). Opções:

1. **Ver o detalhe de uma falha** — abre a tela 4 (só quando falhou algo).
2. **Julgar com mais rigor** — reavalia com 3 votos ou modelo mais forte, para decisões sérias.
3. **Retomar células inacabadas** — quando o teste parou no meio (limite do plano, erro de
   ambiente), continua de onde parou sem repetir o que já passou.
4. **Promover como referência (baseline)** — este resultado vira o padrão oficial contra o qual
   as próximas versões serão comparadas (só habilita com tudo verde e julgamento rigoroso).

### 4. Detalhe de uma falha — diagnóstico e conserto

Mostra o trecho exato da conversa onde o problema aconteceu, o item de contrato violado e a
evidência. Daqui sai a opção mais poderosa:

- **Tentar correção automática** — a skill propõe um ajuste no texto da skill testada, roda de
  novo para comprovar que resolve, verifica que **não piorou nada no modelo mais forte**, e te
  mostra o diff para aprovação final. Ela propõe; quem aplica é você.

Tudo isso também funciona por pedido em linguagem livre ("qual o piso da X?", "a versão nova é
melhor?") — atalho para quem já conhece. Quem não conhece, navega: o menu apresenta cada
capacidade na hora em que ela se torna relevante.

## Como um teste funciona por dentro (anatomia de uma célula)

A unidade de execução é a **célula** = um cenário × um modelo × uma repetição ("rodar o
cenário `happy-path` no sonnet, 1ª vez"). Um smoke de 2 cenários são 2 células; uma matriz de
2 cenários × 3 modelos são 6 células. Toda célula passa pelo mesmo ciclo, executado por script:

1. **Monta o mundo** — o `setup.py` da fixture cria um workspace descartável numa pasta
   temporária (um repositório git de brinquedo, arquivos de exemplo, o que o cenário precisar).
2. **Instala a skill testada** nesse workspace — **sem** a pasta `tests/`: o modelo testado
   nunca vê o próprio gabarito.
3. **Fotografa o estado inicial** — lista de arquivos + saída de comandos-sonda definidos no
   contrato (`git log`, etc.).
4. **Roda a sessão de verdade** — o adapter abre o CLI real (`claude`, `agent`, `copilot` ou
   `agy`) em modo não-interativo com o prompt de abertura do cenário. Se o cenário tem
   `user_script`, um simulador responde aos menus como um usuário responderia ("escolho a
   opção 1", "aprovo"). Cada evento que o CLI emite é gravado.
5. **Fotografa o estado final** — as mesmas sondas de novo; o "antes vs. depois" é a evidência
   de estado.
6. **Checks determinísticos** — o script compara eventos e estado com os itens `deterministic`
   do contrato: o arquivo existe? a ferramenta proibida foi chamada? o `git log` mudou?
   Resposta binária, custo zero, sem chance de alucinação.
7. **Desmonta** — o workspace temporário é apagado. Toda a evidência (transcript, estado,
   checks) já ficou salva em `tests/runs/run-N/` — é dela que relatório e juiz vivem.

O juiz LLM é um passo **separado e opcional** que roda depois, por cima da evidência gravada —
nunca depende da fixture viva, então pode ser chamado a qualquer momento, até dias depois.

## O juiz — quem dá a nota subjetiva (e por que ele ficou barato)

O contrato tem dois tipos de item, avaliados por mecanismos diferentes:

| Tipo | Exemplo de regra | Quem avalia | Custo |
|---|---|---|---|
| `deterministic` | "rodou `test_tool.py`", "o arquivo X existe" | Script puro, sobre estado/eventos gravados | Zero |
| `judge` | "a resposta explica o próximo passo", "toda mensagem começa com o banner" | Um LLM juiz, em sessão separada | 1 chamada de modelo por voto |

O juiz **não é o agente da conversa** — é uma sessão nova, aberta pelo script, que recebe os
itens `judge` do contrato, o transcript da célula, o estado final e (como contexto) o resultado
dos checks determinísticos. Para cada item ele devolve `pass` ou `fail` — com uma **trava
anti-alucinação**: um `fail` só vale acompanhado do número do turno e de uma **citação literal**
(até 200 caracteres) do que o modelo disse. O script confere mecanicamente se a citação existe
mesmo no transcript; citação que não bate → veredito descartado (o item fica *excluído da nota*,
nunca vira pass de brinde). Até o juiz é auditado por código.

### Não são "3 juízes" — são até 3 *votos* do mesmo juiz

Nota de LLM é ruidosa: o mesmo juiz pode dar vereditos diferentes para o mesmo transcript em
duas chamadas (aconteceu ao vivo aqui). Para isso existe o `--votes 3`: o **mesmo** modelo juiz
é chamado **3 vezes independentes** e vale a maioria (2 de 3). É como pedir para o mesmo
professor corrigir a mesma redação três vezes e ficar com a nota que apareceu mais — reduz o
azar de "pegar o professor num dia ruim". Só que custa 3× mais; por isso a política atual gasta
esse rigor apenas quando a nota decide algo:

1. **O padrão é 1 voto** (`--votes 1`). O rigor triplo é escalada, não caminho comum.
2. **Durante iteração, não se julga.** Enquanto você está mexendo numa skill para consertar
   algo, o feedback vem só dos checks determinísticos (grátis). Julgar cada tentativa
   intermediária queima cota em vereditos que a próxima edição invalida — é regra dura do
   SKILL.md.
3. **Julgamento rigoroso só em ponto de decisão** — veredito final de uma mudança, `floor`, ou
   antes de `promote`. Promover um baseline **exige** 3 votos: o script se recusa a promover um
   run julgado com 1 voto, justamente porque 1 voto oscila entre execuções.
4. **O modelo do juiz é o econômico por padrão** (sonnet no Claude; `auto` no Cursor/Copilot) —
   opus fica reservado para runs que decidem promote.

No relatório (tela 3) isso aparece como a opção "**Julgar com mais rigor** — 3 votos / opus",
oferecida apenas quando o julgamento atual foi o barato.

### Como a nota é calculada

Cada item tem um peso pela severidade (`critical` = 4 · `major` = 2 · `minor` = 1). A nota da
célula (`contract %`) é a soma dos pesos dos itens que passaram ÷ soma dos pesos dos itens
julgados × 100. Itens com veredito descartado (evidência não verificável) ficam fora do
denominador — excluídos, não aprovados. Os checks determinísticos têm um placar próprio
(`compliance %`), e qualquer item determinístico reprovado marca a célula como ❌ fail,
independentemente do que o juiz achar dos itens subjetivos.

## Estrutura de pastas gerada na skill testada

Ao rodar `init` numa skill (ex.: `skills/minha-skill/`), a skill-test cria isto **dentro dela**:

```
skills/minha-skill/
  SKILL.md                        ← já existia, não é tocado
  tests/
    README.md                     ← este mapa, gerado dentro da própria pasta
    .gitignore                    ← uma linha: ignora runs/
    contract.yaml                 ← as regras da skill, em formato testável
    scenarios/
      <cenario>.yaml              ← uma jornada de usuário simulada por arquivo
    fixtures/
      <nome>/setup.py             ← script que monta o "mundo" descartável do teste
    baselines/                    ← SÓ ponteiros pequenos, versionados
      baseline.json               ← última versão aprovada (referência oficial)
      last-smoke.json             ← selo: hash da skill no último teste (detecta "mudou sem retestar")
      mutate-latest.json          ← última calibração da suíte
    runs/                         ← TEMPORÁRIO: pode apagar a pasta inteira
      run-N/                      ← uma execução de teste
        run.json                  ← ficha do run: skill, hash, adapter, modelos, custo, placar
        progress.jsonl            ← 1 linha por célula concluída (é o que permite retomar)
        judge.json                ← vereditos do juiz (só existe se `judge` rodou)
        cells/<cenario>/<modelo>/rep-N/
          raw.jsonl               ← stream bruto de eventos do CLI (fonte da verdade)
          transcript.json         ← conversa normalizada: turnos, tools chamadas, tokens
          state.json              ← estado do mundo antes/depois (sondas + arquivos)
          checks.json             ← resultado dos checks determinísticos
          error.json              ← só existe se a célula quebrou (diagnóstico)
      adapt-N/                    ← uma tentativa de correção automática (adapt)
        SKILL.adapted.md          ← a skill com o patch proposto já aplicado
        final.diff                ← o diff que você aprova (ou não)
        adapt.json                ← histórico das iterações e do gate
      probe-N/                    ← células de sondagem de ativação (activation-probe)
```

**Por que fica dentro da skill, e não numa pasta central?** Porque o teste pertence à skill —
evolui, é revisado e é commitado junto com ela, exatamente como uma pasta `tests/` de código.

### Os três arquivos que você escreve (com a skill guiando)

**`contract.yaml` — a definição de "funcionando".** Uma lista de itens; cada item é uma regra
da skill em formato verificável:

```yaml
items:
  - id: B-07                 # id citado em relatórios e falhas
    kind: deterministic      # deterministic = script verifica · judge = LLM avalia
    severity: critical       # peso na nota: critical=4 · major=2 · minor=1
    scope: focused           # always = vale em todo cenário · focused = só nos cenários que o citam
    rule: "Staleness do selo é respondida pela saída do subcomando seal, nunca chutada."
    checks:                  # só para kind: deterministic
      - {type: required_event, tool: Bash, pattern: "test_tool\\.py\\s+seal"}
```

Tipos de check disponíveis: `file_exists` / `file_absent` (glob sobre os arquivos finais do
workspace), `required_event` / `forbidden_event` (uma ferramenta foi/não foi chamada com input
casando o padrão), e `state` (roda um comando-sonda como `git log --format=%s` e compara a
saída: `expect_equals`, `expect_regex`, `expect_regex_per_line` ou `unchanged_from_setup`).
Itens `kind: judge` não têm `checks` — a `rule` em linguagem natural é o que o juiz avalia.

**`scenarios/<nome>.yaml` — uma jornada de usuário.** Cada arquivo descreve uma conversa
simulada do início ao fim:

```yaml
name: seal-check
goal: "O agente deve detectar que a skill foi editada após o último teste."   # para humanos
fixture: greet-stale-seal          # qual "mundo" montar (pasta em fixtures/)
invocation: explicit               # explicit = prompt manda usar a skill · auto = mede se ela ativa sozinha
opening_prompt: "Use a skill skill-test para verificar se skills/greet foi retestada…"
allowed_tools: [Skill, Read, Glob, Bash, PowerShell]   # menor privilégio possível
user_script: []                    # respostas do "usuário simulado" aos menus (vazio = 1 turno só)
contract_focus: [B-07, B-08]       # itens `scope: focused` que este cenário ativa
budget: {max_turns: 6, max_cost_usd: 0.35, timeout_s: 300}   # teto por célula
```

O `user_script` é o que permite testar fluxos com menu, sem nenhum LLM fazendo papel de
usuário: cada passo declara âncoras (`expect_any: ["Approve and execute"]`) que devem aparecer
na resposta do agente, e a fala a devolver — `respond: "1"` literal, ou `respond_label:
"Approve"`, que procura essa opção no menu numerado e responde o número dela (sobrevive a
renumeração). Se nenhuma âncora casa, a célula termina como `desync` (a conversa saiu do
roteiro — reportado à parte, nunca como reprovação da skill); passos com `optional: true` podem
ser pulados quando o agente legitimamente encurta o fluxo.

**`fixtures/<nome>/setup.py` — o mundo do teste.** Um script Python simples que recebe o
caminho do workspace descartável como argumento (`sys.argv[1]`) e monta lá dentro o que o
cenário pressupõe: um repositório git com commits, arquivos sujos, uma skill de exemplo — o que
for. Roda do zero a cada célula, então cada execução parte de um mundo idêntico e limpo.

### Os três ponteiros de `baselines/`

São arquivos JSON minúsculos, versionados, que apontam para resultados — nunca contêm os
resultados em si:

- **`baseline.json`** — qual run é a referência oficial aprovada (id do run + hash da skill +
  hash do contrato). É contra ele que `compare` responde "melhorou ou piorou?".
- **`last-smoke.json`** — o selo: hash do conteúdo da skill no último teste. Se a skill mudou e
  o hash não bate mais, o dashboard mostra ⚠️ stale ("editada sem retestar").
- **`mutate-latest.json`** — resultado da última calibração (`mutate`): quantos defeitos
  plantados a suíte detectou.

Apagar `baselines/` não quebra nada — só perde a referência de comparação e o selo.

### O que cada execução grava (`tests/runs/`)

Tudo aqui é **regenerável e ignorado pelo git** — a pasta inteira pode ser apagada. Dentro de um
`run-N/`, cada célula guarda quatro camadas da mesma história, da mais crua à mais digerida:

1. **`raw.jsonl`** — cada evento que o CLI emitiu, linha a linha, sem tratamento. É a fonte da
   verdade; os outros arquivos derivam dele.
2. **`transcript.json`** — a conversa normalizada num formato único para todos os CLIs: lista de
   turnos (`idx`, `role`, `text`, `tool_calls`) + uso de tokens. É o que o juiz lê e o que as
   citações de evidência referenciam ("turno 14").
3. **`state.json`** — fotografia do workspace antes e depois: saída das sondas + lista de
   arquivos. É a evidência dos checks de estado.
4. **`checks.json`** — o veredito determinístico por item do contrato, com o detalhe de cada
   check (o que casou, o que faltou).

No nível do run, `run.json` é a ficha da execução (o quê, quando, qual adapter, custo, placar
de células) e `progress.jsonl` registra uma linha por célula concluída — é ele que permite
`run --resume` continuar de onde parou sem repetir células. `judge.json` aparece depois de
julgar: veredito por item com evidência citada, `contract_pct` por célula, e qual juiz julgou
(`judge_adapter`, `judge_model`, `votes`).

**Todo arquivo na pasta de uma skill é de um de três tipos:**

| Tipo | Versiona no git? | Vai na distribuição? | Pode apagar? |
|---|:-:|:-:|---|
| **SKILL** — o produto | ✅ | ✅ | ❌ |
| **TESTE** — o controle de qualidade | ✅ | ❌ | ❌ |
| **TEMPORÁRIO** — saída de execução/build | ❌ (ignorado) | ❌ | ✅ sempre — regenerável |

E o mapa de quem é o quê (usando a própria skill-test como exemplo, já que ela se auto-testa):

- **SKILL:** `SKILL.md`, `scripts/`, `references/`, `config.yaml`.
- **TESTE:** `tests/contract.yaml`, `tests/scenarios/`, `tests/fixtures/` e `tests/baselines/`
  (os 3 ponteiros descritos acima). No caso da skill-test, também `scripts/tests/` (testes
  unitários do harness).
- **TEMPORÁRIO:** `tests/runs/` — a pasta **inteira** (execuções `run-*`, diffs propostos
  `adapt-*`, sondas `probe-*`) — e a pasta `release/` (saída de build, regenerada por
  `./release.sh`). Pode apagar as duas a qualquer momento.

O `init` já grava um `.gitignore` que implementa a coluna "Versiona?" e um `tests/README.md` com
essa classificação — quem abrir a pasta descobre as regras sem precisar deste documento.

Na distribuição a separação é automática: o release exclui TESTE e TEMPORÁRIO (veja a seção
seguinte), e durante um teste o harness copia a skill **sem** `tests/` para o ambiente
descartável — o modelo testado nunca vê os próprios testes.

## Benefício esperado

- **Regressão pega antes do usuário**, não depois — um teste automatizado no lugar de "parece que
  está funcionando".
- **Decisão de modelo com número, não achismo** — "essa skill é segura no modelo econômico" vira
  fato medido, não intuição.
- **Correção de prompt provada, não só tentada** — o `adapt` só aceita um ajuste se ele resolver o
  problema sem piorar nada no modelo mais forte.
- **Economia de token mensurável** — otimizar um `SKILL.md` deixa de ser "acho que ficou mais
  enxuto" e vira um número comparável entre versões.
- **Confiança na própria suíte** — o `mutate` garante que os testes realmente pegam defeito, em vez
  de passar sempre e dar falsa sensação de segurança.

## Cuidado com custo

Cada célula de teste é uma sessão completa de agente — roda de verdade contra um modelo,
consumindo cota do seu plano (ou crédito de API). Por padrão a skill começa sempre pelo teste mais
barato (`smoke`, 1 modelo, 1 repetição); matriz completa, `floor` e repetições ≥ 3 só rodam com
escolha explícita sua, sempre com o tamanho da operação (quantas sessões) mostrado antes de
começar. Se a sessão de teste esbarrar no limite do seu plano, a skill para sozinha, avisa quando o
limite reseta, e retoma de onde parou sem repetir o que já passou.

No Cursor e no Copilot o CLI não expõe custo em dinheiro — o controle é pelo número de células,
tempo-limite e máximo de turnos (o Copilot ainda reporta as *premium requests* consumidas por
célula). No Claude a telemetria em USD existe, mas para quem é assinante ela é referência, não
dinheiro saindo — o que conta é a cota do plano.

## Gerando o release (pasta pronta para instalar)

Esta pasta (`skills/skill-test/`) é o **código-fonte** da skill: além do necessário para rodar,
tem este README, a suíte que testa a própria skill-test (`tests/`) e testes unitários
(`scripts/tests/`) — coisas úteis para quem desenvolve a skill, inúteis (e só ocupando espaço) numa
instalação.

O script de release monta a versão **limpa**, pronta para copiar para `~/.claude/skills/`:

```bash
cd skills/skill-test
./release.sh              # Linux/macOS/Git Bash
# ou
.\release.ps1              # Windows PowerShell
```

Isso gera `skills/skill-test/release/skill-test/` — uma cópia contendo só o que a skill precisa
para funcionar, sem o README, sem a suíte de auto-teste, sem caches. Adicione `--zip` para também
gerar um `.zip` ao lado, pronto para distribuir.

**Se você criar um arquivo novo** dentro de `skills/skill-test/` (um módulo novo em
`scripts/bench_lib/`, um cenário novo), ele entra no release **automaticamente** — o script não usa
lista de arquivos permitidos, ele copia tudo e só exclui o que é explicitamente marcado como "só
serve durante o desenvolvimento" (veja o topo de `scripts/build_release.py` se precisar ajustar
essa lista).

## Instalação

```bash
cd skills/skill-test && ./release.sh
```

Depois copie `release/skill-test/` para a pasta de skills do CLI de onde você vai **conversar**:

| Você conversa pelo | Instalar em (global) | Ou por projeto |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `<projeto>/.claude/skills/` |
| Cursor (`agent`) | `~/.cursor/skills/` | `<projeto>/.cursor/skills/` |
| GitHub Copilot CLI | `~/.copilot/skills/` | `<projeto>/.claude/skills/` (o Copilot lê esse layout) |

Pré-requisitos: Python 3.10+, PyYAML (`pip install pyyaml`) e **pelo menos um** CLI de agente
instalado e logado (`claude`, `agent`, `copilot` ou `agy`) — não precisa ser o Claude; um ambiente
só com o Cursor roda tudo, inclusive o juiz. Depois de instalar, abra `/skill-test` e peça
"verifica o ambiente": o `doctor` mostra o host detectado, quais CLIs existem e o que falta.

# skill-test — harness de testes automatizados para agent skills

Skill que **testa outras skills**. Uma skill (`SKILL.md`) é texto interpretado por um LLM — não
compila, não tem type-check, não tem suíte de regressão. A skill-test resolve isso: roda a skill
alvo de ponta a ponta contra um modelo real, verifica o comportamento contra um contrato
versionado, e diz exatamente o que quebrou, onde, e em qual modelo — com evidência citável, nunca
"achismo".

> Princípio: **o agente conversa, decide e narra; o script (`test_tool.py`) executa, mede e
> julga.** Nada de comportamento é avaliado "no olho" — todo veredito vem de um check determinístico
> (estado do git, arquivos, eventos) ou de um juiz LLM configurado, nunca do agente da sessão atual.

## Para que serve, na prática

- **Vai commitar uma skill nova ou alterada?** Rode a suíte antes — pega regressão de banner,
  menu, fluxo, antes de chegar no usuário final.
- **"Essa skill funciona no modelo mais fraco que uso?"** Descobre o piso: até onde na escada de
  modelos (opus → sonnet → haiku, ou Gemini Pro → Flash) a skill continua confiável.
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

## Estrutura de pastas gerada na skill testada

Ao rodar `init` numa skill (ex.: `skills/minha-skill/`), a skill-test cria isto **dentro dela**:

```
skills/minha-skill/
  SKILL.md                        ← já existia, não é tocado
  tests/
    contract.yaml                 ← as regras da skill, em formato testável
    scenarios/
      <cenario>.yaml               ← uma jornada de usuário simulada por arquivo
    fixtures/
      <nome>/setup.py             ← script que monta o "mundo" descartável do teste
    baselines/
      baseline.json               ← última versão aprovada (referência oficial)
      last-smoke.json             ← selo: hash da skill no último teste (detecta "mudou sem retestar")
      run-N/                      ← histórico de execuções (não versionado no git)
```

**Por que fica dentro da skill, e não numa pasta central?** Porque o teste pertence à skill —
evolui, é revisado e é commitado junto com ela, exatamente como uma pasta `tests/` de código.

**O que é versionado no git e o que não é:** `contract.yaml`, `scenarios/`, `fixtures/`,
`baseline.json` e `last-smoke.json` são pequenos e ficam no repositório. As pastas `run-N/` de cada
execução (transcritos, logs) são artefato local, ignoradas pelo `.gitignore` — são regeneráveis a
qualquer momento rodando o teste de novo.

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
mkdir -p ~/.claude/skills
cp -r release/skill-test ~/.claude/skills/
```

Pré-requisitos: Python 3.10+, PyYAML (`pip install pyyaml`), e o CLI do modelo que você quer testar
(`claude`; opcionalmente `agy` para modelos Gemini, `agent` para o Cursor e `copilot` para o
GitHub Copilot — nos planos free/atuais, Cursor e Copilot só aceitam `--model auto`). Depois de instalar, abra
`/skill-test` e peça "verifica o ambiente" a qualquer momento para conferir se está tudo certo.

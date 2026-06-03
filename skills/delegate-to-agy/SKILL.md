---
name: delegate-to-agy
description: >-
  Delegação padrão para economizar contexto. Use o agy (Gemini CLI) para:
  pesquisa web/docs, busca em código, edições em massa e feature builds.
  Retorna resultado destilado; você verifica.
when_to_use: >-
  Chame SEMPRE que a tarefa se encaixar em:
  - WEB: busca na web, eventos atuais, citações.
  - DOCS: dúvida sobre qualquer lib/API/framework externo.
  - CODE SEARCH: definições, usos ou erros numa base de código.
  - CODE EDIT: edições mecânicas em múltiplos arquivos.
  - FEATURE BUILD: qualquer mudança que você planejaria — escreva o plano e passe o caminho.
  - SPIKE/POC: hipótese técnica que só experimento resolve.
  Exceção — faça você mesmo: arquivo único, sem pesquisa, verificável numa leitura.
---

# Delegar para o `agy` (trabalhador Gemini)

O `agy` é a CLI do Google Antigravity — agente Gemini com web, grep, sandbox. No modo `-p` executa autonomamente e imprime só a resposta. Esta skill o usa como **trabalhador braçal**: Claude delega o *fazer* pesado, mantendo o *pensar e verificar*.

**Isso não é gratuito — é um medidor diferente.** Delegue só quando a troca for favorável (veja o gate).

---

## Gate — delegue se TODOS os três forem verdadeiros

1. **Entrada grande** — a matéria-prima é muito maior que a resposta.
2. **Saída pequena** — você quer resultado destilado (fato+fontes, `path:line`, resumo de diff).
3. **Verificação barata** — você verifica *sem* reger toda a entrada (spot-check de URL, ler só as linhas, rodar testes).

**NO-GO (você pagaria duas vezes):** entrada pequena; você precisa ler tudo para escrever o prompt; verificação exige reler tudo; raciocínio/design que é seu; ação irreversível (`--dangerously-skip-permissions`).

**FEATURE BUILD — gate separado:** pensamento já está no plano aprovado; o `agy` só transcreve especificação→código. Critério único: "eu planejaria isso?". Exceção: mudança de arquivo único verificável numa leitura → faça você mesmo.

---

## Como invocar

> **CRÍTICO — a Skill tool NÃO executa nada.** Ela apenas carrega estas instruções no contexto. Para delegar de fato, você **DEVE** chamar o Bash com o wrapper abaixo. Se não chamar o Bash, nenhuma tarefa foi delegada — nunca diga "rodando" nem devolva controle sem ter disparado o comando.

```bash
~/.claude/skills/delegate-to-agy/scripts/delegate.sh [--dir PATH]... [--timeout SECS] [--continue] [--raw] [--mode web|docs] -- "TASK PROMPT"
```

- `--dir PATH` — workspace do agy (repetível). **Obrigatório para tarefas de disco/código.**
- `--timeout SECS` — limite wall-clock (padrão 600). Saída `124` = muito grande ou travado.
- `--continue` — retoma conversa anterior do agy. Omita para resposta isolada.
- `--mode web|docs` — injeta regras de evidência (fontes, citações, timestamps). Use sempre nesses modos.

**Como aguardar:**
- **Foreground (padrão):** Bash síncrono com `timeout` do parâmetro Bash ≥ `--timeout` + 30s. Bloqueia e retorna as tags inline.
- **Background:** Bash com `run_in_background: true` → notificação + caminho do arquivo → Read. Use quando tiver trabalho paralelo.
- **Não use Monitor** — o wrapper não emite linhas durante a execução, só no final.

### Escrevendo o prompt
- **Autocontido** — o agy não compartilha contexto do Claude. Especifique caminhos e pergunta exata.
- **Semântica precisa** — "fechamento oficial DD/MM" não "preço atual"; "definição de X" não "X".
- **Ponteiros verificáveis** — URLs (web) ou `path:line` (disco). Isso torna sua verificação barata.
- **Sem pedir explicações** — o wrapper já proíbe narração.

### Esqueletos (preencha os colchetes)

- **Docs** (`--mode docs`): `Pesquise ≥3 fontes independentes sobre [tópico]. Consolide em resumo denso.`
- **Web** (`--mode web`): `Pesquise [PERGUNTA com qualificador semântico/temporal]. Retorne [campos exatos].`
- **Disco/código** (`--dir`): `Em [CAMINHO], encontre [onde X é definido / 1ª ocorrência do erro Y]. Responda path:linha exato.`
- **Edição em massa** (`--dir`): `Nos arquivos [GLOB] em [CAMINHO], [mudança precisa]. NÃO altere [exceções]. Edite no disco; informe substituições por arquivo.`
- **Spike/POC**: `Hipótese: [X]. Confirmação se: [critério]. Implemente o mínimo, execute, reporte veredicto.` (sem `--dir` salvo se precisar de arquivos do projeto)
- **Feature build**: `Implemente o plano em [PATH ABSOLUTO]. Compile com [CMD] ao final. Reporte cada passo como feito/não-feito, output do build, diff de cada função alterada. PARE e reporte se algo não bater — não improvise.` (passe `--dir` do projeto E `--dir ~/.claude/plans`; nunca cole o texto do plano no prompt)

---

## Contrato de saída

O wrapper extrai apenas estas tags da resposta do agy (narração é descartada):

```
<RESULT>resposta direta — leitor é IA, máxima densidade</RESULT>
<SOURCES>urls ou path:line separados por ';'</SOURCES>
<QUOTE>trecho verbatim — apenas em --mode web/docs</QUOTE>
<CONFIDENCE>0-100</CONFIDENCE>
<CAVEATS>premissas, ambiguidades, o que não confirmou</CAVEATS>
```

Se o agy não emitir as tags: `[delegate.py: agy did not emit the expected tags — raw output below]` + texto bruto. Trate como baixa confiança: reexecute com `--continue "você não seguiu o formato, refaça"` ou faça você mesmo.

---

## Verificação — SEMPRE, independente, proporcional

**Nunca repasse sem verificar.** `<CONFIDENCE>` é autorrelato — use como triagem. `<CAVEATS>` traz mais sinal: ressalva não vazia = examine esse ponto. A verificação independente abaixo é o veredicto real.

Por tipo:
- **Docs/Web** → localize o `<QUOTE>` na fonte citada (grep ou WebFetch). Não encontrou → rejeite tudo como alucinação. Para fatos voláteis (preços, status), confirme em fonte **independente** — não abra apenas a URL do agy (circular).
- **Disco/código** → leia os `path:line` retornados e confirme que contêm o que o agy afirma.
- **Edição em massa** → `git diff` + build/testes. Testes são o verificador — não releia cada arquivo.
- **Feature build** → verifique o **comportamento** contra os casos de aceitação do plano, não apenas o diff.

Falhou: `--continue "você errou X, refaça"` (barato), refaça com prompt melhor, ou abandone e faça você mesmo.

---

## Capacidades & falhas conhecidas

**Validadas (2026-06-02):** transporte `-p`, disco/grep, web, edição em massa, `--mode docs` (QUOTE localizado na fonte). Contrato de saída + parser de tags funcionando; sem tags → raw output (nunca vazio).

**⚠️ `--continue` em modo `-p`:** integrado mas comportamento não confirmado — pode não reconectar contexto. Se uma segunda chamada com `--continue` retornar resposta idêntica à primeira, assuma que o contexto não foi retido.

**Modos de falha:**
- **Vazio / travamento** → stdin não desvinculado (wrapper resolve). Se reincidir: `agy -p "ping"`.
- **Exit 124** → muito grande ou travado. Restrinja a tarefa ou aumente `--timeout`.
- **Auth/crédito no stderr** → usuário precisa re-autenticar no Antigravity. Apresente o erro, use fallback.

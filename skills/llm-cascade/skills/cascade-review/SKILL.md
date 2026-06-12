---
name: cascade-review
description: >-
  Como o driver pede ao judge a revisão do diff (T1 e T2), monta um payload em
  dieta (contexto + plano + diff limpo) e age sobre o veredito estruturado
  (VERDICT/BLOCKERS) SEM gerar roundtrips: aplica blockers sem perguntar,
  re-roda o gate e finaliza. Use somente depois que o gate objetivo
  (testes/compilação) passou. O wrapper recusa a 3ª review por construção.
---

# Pedir a review ao judge — uma vez, com veredito, sem ping-pong

## Pré-requisito

O gate (testes/compilação) **já passou**. Gate falhando → conserte você (até 3
tentativas). Levar código quebrado ao judge gasta o medidor caro com o que o
teste apontaria de graça.

## Passo 1 — montar o payload (`review-input.md`): dieta obrigatória

Na ordem, num único arquivo:

1. **Cabeçalho de contexto (≤10 linhas):** objetivo da tarefa + critérios de
   aceitação + comando do gate e resultado ("N passed").
2. **O plano:** T2 → `plan.md` (se >40 linhas, só os passos e contratos);
   T1 → o brief com auto-plano.
3. **O diff:** `git diff -U3` SOMENTE das mudanças da tarefa. Excluir lockfiles,
   gerados, binários, formatação pura. Diff >~400 linhas → hunks completos só
   dos arquivos com lógica de risco; para o resto, 1 linha por arquivo ("renomes
   mecânicos em X, Y").

A review é **fria por padrão** (avaliador independente — por isso o plano vai no
payload). `--warm` retoma a sessão do plan; use só se o payload frio ficar maior
que a economia.

## Passo 2 — pedir a review

```bash
python <DIR_DO_PLUGIN>/scripts/ask_judge.py \
  --role review \
  --in  <task-dir>/review-input.md \
  --out <task-dir>/review.md \
  --task-dir <task-dir>
```

(`--light` usa o judge barato da config — só para tarefa T1 de baixo risco
quando o usuário pediu economia máxima.)

O stdout do wrapper já traz `VERDICT: ... | BLOCKERS: n`:

- **APPROVE com 0 blockers** → NÃO leia o arquivo. Finalize e reporte.
- **FIX** → leia `review.md` e siga o passo 3.

## Passo 3 — agir sobre o veredito (regras já decididas; não consulte o judge)

1. Aplique **TODOS os `[B*]`** (blockers) você mesmo. Sem perguntar, sem
   renegociar — o judge já recebeu essa regra e decidiu por ela.
2. `[N*]` (nits) são **opcionais**: aplique só os de custo ~zero; liste os
   demais no relatório final como "não aplicados".
3. **Re-rode o gate.**
   - Verde → **PRONTO. Não re-revise.** A review única + gate cobrem o risco.
   - Quebrou → conserte, gate verde, e SÓ ENTÃO uma 2ª review se justifica
     (novo `review-input.md` com o diff das correções). O orçamento (2) trava a
     partir daí: exit 75 → aplique o que tem, gate, finalize e reporte.

## Por que essas regras existem (não as "melhore")

- Review aberta termina em pergunta ("posso corrigir?") e cada pergunta é mais
  um cruzamento caro — o contrato VERDICT + regras pré-decididas elimina isso.
- Re-revisar cada ajuste vira custo sem fim; gate + 1 review cobrem o risco
  melhor que N reviews.
- O wrapper imprime o veredito no stdout justamente para você nem precisar ler
  o arquivo no caso APPROVE.

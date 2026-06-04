---
name: ask-opus-plan
description: >-
  Como o agy pede ao Claude Opus um plano de implementação a partir do brief.md,
  e como conduzir o handshake de consenso (máx 3 rodadas) quando o Opus levanta
  objeções ao brief ou ao plano. Use depois de distill-brief e antes de codar. O
  Opus decide o nível de detalhe do plano; o agy é o árbitro final das objeções.
---

# Pedir o plano ao Opus (+ handshake de consenso)

Você já tem `brief.md` destilado. Agora o Opus gera o plano. Ele pode aceitar o
brief e planejar direto, ou objetar se vir algo ruim. Você é o gestor: decide.

## Passo 1 — pedir o plano

```bash
# Linux/macOS: <DIR_DO_PLUGIN>/scripts/ask_claude.sh
# Windows:     python <DIR_DO_PLUGIN>/scripts/ask_claude.py
<WRAPPER> \
  --role plan \
  --in  <task-dir>/brief.md \
  --out <task-dir>/plan.md \
  --task-dir <task-dir> --timeout 600
```

O Opus escreve em `plan.md` ou um plano executável, ou — se o brief tiver lacuna/
risco sério — um bloco de **objeções estruturadas** (numeradas) pedindo sua
aprovação. Leia `plan.md` e decida qual dos dois casos é.

## Passo 2 — o plano veio limpo (sem objeção)

Se `plan.md` é um plano de implementação e você concorda → **pronto, vá codar**
(passo 5 da persona). Não invente handshake se não há objeção.

## Passo 3 — o Opus objetou: handshake de consenso (máx 3 rodadas)

O Opus levantou objeções/sugestões. Conduza a negociação. Mantenha o Opus QUENTE
com `--continue` — assim cada rodada manda só o delta, não o brief inteiro de novo.

Para cada rodada (1, 2, 3):

1. **Avalie as objeções do Opus.** Para cada item: você aceita ou rejeita, e por
   quê. Você tem o contexto de requisitos que o Opus não tem — use isso.
2. **Escreva `counter.md`** com sua resposta ponto a ponto:
   ```markdown
   # Contra-argumento do agy (rodada N)
   - Objeção 1: ACEITO. <o que muda>
   - Objeção 2: REJEITO. <razão — o requisito X exige isso>
   - Objeção 3: ACEITO PARCIAL. <o que entra, o que não>
   ```
3. **Peça a proposta final ao Opus** (quente, com `--continue`):
   ```bash
   <WRAPPER> \
     --role handshake --continue \
     --in  <task-dir>/counter.md \
     --out <task-dir>/plan.md \
     --task-dir <task-dir> --timeout 600
   ```
   O Opus incorpora o que você aceitou, respeita o que você rejeitou, e reescreve
   `plan.md` como proposta final.
4. **Aprove ou não.**
   - Aprova → sai do handshake, vá codar.
   - Não aprova **e** rodada < 3 → próxima rodada (volte ao passo 1 com as novas
     objeções que sobraram).
   - Chegou à rodada 3 sem consenso → **você decide** (é o gestor). Registre o
     impasse e sua decisão final no fim de `counter.md`, e siga com o plano que
     você julgar melhor. Não entre em loop infinito.

## Princípios

- **O Opus só objeta, não impõe.** Ele nunca reescreve o plano à revelia contra
  uma rejeição sua. Se ele insistir num ponto que você rejeitou, mantenha a
  rejeição.
- **Não reabra pontos decididos.** Cada rodada deve convergir, não recomeçar.
- **`--continue` é obrigatório da rodada 2 em diante** — sem ele você repaga o
  brief+plano a cada rodada e a economia evapora.

Quando o plano estiver aprovado, prossiga para codar (persona, passo 5) e depois
para a skill **ask-opus-review**.

---
name: cascade-plan
description: >-
  T2 apenas: como o driver pede o plano de implementação ao judge a partir do
  brief.md, e como conduzir o handshake de consenso quando o judge devolve
  OBJECTIONS (máx 2 rodadas; o wrapper retoma a sessão automaticamente). Use
  depois de cascade-brief e antes de codar. O driver é o árbitro final.
---

# Pedir o plano ao judge (+ handshake, se houver objeções)

## Passo 1 — pedir o plano

```bash
python <DIR_DO_PLUGIN>/scripts/ask_judge.py \
  --role plan \
  --in  <task-dir>/brief.md \
  --out <task-dir>/plan.md \
  --task-dir <task-dir>
```

(`<DIR_DO_PLUGIN>` = pasta onde o plugin está instalado, ex.
`~/.gemini/config/plugins/llm-cascade`. Funciona igual em Windows/Linux/macOS.)

Leia `plan.md`. Dois casos:

- **Plano de implementação** → você concorda? Vá codar. Não invente handshake
  sem objeção.
- **Primeira linha `OBJECTIONS:`** → o brief tem lacuna/risco grave. Handshake.

## Passo 2 — handshake de consenso (máx 2 rodadas; o orçamento trava)

Por rodada:

1. **Julgue cada objeção** com o contexto de requisitos que só você tem.
2. **Escreva `counter.md`**:
   ```markdown
   # Contra-argumento do driver (rodada N)
   - Objeção 1: ACEITO. <o que muda>
   - Objeção 2: REJEITO. <razão objetiva>
   - Objeção 3: ACEITO PARCIAL. <o que entra / o que não>
   ```
3. **Peça a proposta final** (o wrapper retoma a sessão do plan sozinho —
   nunca recole o brief):
   ```bash
   python <DIR_DO_PLUGIN>/scripts/ask_judge.py \
     --role handshake \
     --in  <task-dir>/counter.md \
     --out <task-dir>/plan.md \
     --task-dir <task-dir>
   ```
4. **Aprova?** Sim → vá codar. Não, e ainda há rodada → repita. Acabaram as
   rodadas (wrapper recusa com exit 75) → **você decide**: registre o impasse e
   a decisão final no fim de `counter.md` e siga com o plano que julgar melhor.

## Princípios

- **O judge objeta; não impõe.** Ponto que você rejeitou fica rejeitado.
- **Cada rodada converge** — não reabra o decidido.
- **Nunca reenvie material já enviado** — a retomada de sessão é automática e
  manda só o delta.

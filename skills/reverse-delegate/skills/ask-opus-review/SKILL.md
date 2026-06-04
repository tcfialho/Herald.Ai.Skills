---
name: ask-opus-review
description: >-
  Como o agy pede ao Claude Opus para revisar o diff do código que o agy
  escreveu seguindo o plano. Use depois de codar E depois que o gate objetivo
  (testes/compilador) já passou. O Opus é o revisor sênior; pega bugs e
  regressões silenciosas que o teste não pega. Roda uma vez por padrão.
---

# Pedir a revisão do código ao Opus

Você codou seguindo `plan.md` e o gate objetivo (testes/compilador) **já passou**.
Agora o Opus revisa — ele é o revisor sênior que pega o que os testes não pegam:
casos de borda, contrato violado, regressão silenciosa, bug que passa numa suíte
incompleta.

## Pré-requisito: gate primeiro

Não chame a revisão antes de os testes passarem. Se o gate falha, conserte você
mesmo (até 3 tentativas). Levar código quebrado à revisão do Opus desperdiça o
medidor caro com o que o teste já teria apontado de graça.

## Passo 1 — gerar o diff

Escreva o diff do que você mudou em `diff.patch` (apenas as mudanças desta
tarefa). Inclua contexto suficiente para o Opus entender (`git diff` com algumas
linhas de contexto basta). Se o diff for grande, acompanhe com um `brief` curto
no topo do arquivo lembrando o objetivo e os arquivos tocados.

## Passo 2 — pedir a revisão

```bash
# Linux/macOS: <DIR_DO_PLUGIN>/scripts/ask_claude.sh
# Windows:     python <DIR_DO_PLUGIN>/scripts/ask_claude.py
<WRAPPER> \
  --role review \
  --in  <task-dir>/diff.patch \
  --out <task-dir>/review.md \
  --task-dir <task-dir> --timeout 600
```

O Opus escreve `review.md` com: ou uma aprovação clara, ou achados específicos
(arquivo:linha, problema, correção concreta).

## Passo 3 — agir sobre a revisão

- **Aprovado** → pronto. Reporte ao usuário.
- **Achados** → aplique as correções você mesmo (você é o dev). Para cada achado,
  faça a mudança no código.
- **Após corrigir, rode o gate de novo.** Se passar → pronto (não re-revise por
  padrão). Se o gate voltar a FALHAR → uma segunda revisão é justificável (passe
  o novo diff); caso contrário pare em uma revisão.

## Princípios

- **Uma revisão por padrão.** Re-revisar a cada ajuste vira custo sem fim. Só
  repita se o gate quebrar após as correções.
- **O Opus revisa, você corrige.** Ele não edita seus arquivos; ele aponta. Quem
  aplica é você.
- **Confie no gate + revisão juntos.** O gate pega o que é mecânico; o Opus pega
  o que é semântico. Os dois cobrem o risco de bug silencioso melhor que qualquer
  um sozinho.

Ao final, reporte ao usuário o que foi feito, o veredito da revisão, e some o
custo do Opus de `tokens.log`.

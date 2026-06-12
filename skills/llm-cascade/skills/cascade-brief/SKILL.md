---
name: cascade-brief
description: >-
  Como o driver destila requisitos, pesquisa, spikes e contratos num brief.md
  denso antes de gastar o judge — e como escrever o auto-plano que substitui a
  chamada de plan nas tarefas T1. O judge paga por token: brief enxuto e
  completo é o que torna a cascata econômica; um dump cru a destrói. Use antes
  de cascade-plan (T2) ou direto antes de codar (T1).
---

# Destilar o brief (e o auto-plano do T1)

O judge lerá APENAS o que você escrever aqui — ele não viu seus spikes nem a
base de código. Tudo que ele precisa tem que estar no brief, **e nada além**.

## A disciplina

- **Conclusões, não material bruto.** Não cole a saída do spike — cole a
  conclusão ("API X exige header Y; rate limit 100/min"). Não cole a doc —
  cole o contrato relevante.
- **Específico e verificável.** Caminhos, funções e assinaturas REAIS (você
  conferiu), nunca inventados.
- **Diga o que NÃO fazer.** Restrições, invariantes, o que não pode quebrar.
- **Curto.** Passou de ~2 páginas = você está despejando o que devia ser uma
  conclusão de 1 linha.

## Formato do `brief.md`

```markdown
# Brief: <tarefa>

## Roteamento
T0|T1|T2 — <1 linha: qual gatilho da rubrica decidiu>

## Objetivo
<1-3 frases: o que construir e por quê>

## Contexto da base
- Arquivos: `path/a.py` (faz X), `path/b.py` (faz Y)
- Padrões a seguir: <ex.: erros via Result<T>>
- Gate: <comando exato de teste/build>

## Contratos e descobertas (conclusões de spikes/pesquisa)
- <contrato, assinatura, limite — destilado>

## Restrições e invariantes
- <o que não pode quebrar>

## Critério de aceitação
- <testes que devem passar; comportamento observável>

## Aberto (T2: peça ao judge para decidir)
- <pontos onde você quer o julgamento do modelo forte>

## Auto-plano (APENAS T1 — você se planeja; ≤15 linhas)
1. <passo: arquivo + mudança>
2. ...
```

## Antes de prosseguir, cheque

- Um executor escreveria o código lendo SÓ isto, sem perguntar nada?
- Algum dump cru que devia ser conclusão de 1 linha?
- T1: o auto-plano cabe em ≤15 linhas? (Não cabe → indício de T2; reclassifique.)

T2 → siga para **cascade-plan**. T1 → vá codar seguindo o auto-plano; o brief
inteiro será o cabeçalho de contexto da review depois.

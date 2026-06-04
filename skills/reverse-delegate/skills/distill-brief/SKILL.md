---
name: distill-brief
description: >-
  Como o agy condensa todo o material que levantou (requisitos, pesquisa de
  APIs, spikes, POCs, contratos, restrições) num brief.md DENSO para enviar ao
  Claude Opus na etapa de planejamento. Use antes de chamar ask-opus-plan. O
  ponto: o Opus paga por token — um brief enxuto e completo é o que torna a
  delegação invertida econômica; um dump cru a destrói.
---

# Destilar o brief para o Opus

O Opus vai gerar o plano lendo APENAS o `brief.md`. Ele não tem o seu contexto,
não viu seus spikes, não leu a base de código. Tudo que ele precisa saber tem
que estar aqui — **e nada além.** Cada token cru que você despejar é pago no
medidor caro sem retorno.

## A disciplina

- **Decisões, não material bruto.** Não cole a saída do spike — cole a CONCLUSÃO
  do spike ("a API X exige header Y; rate limit 100/min"). Não cole a doc — cole
  o contrato relevante.
- **Específico e verificável.** Caminhos exatos de arquivo, nomes de função,
  assinaturas, contratos. O Opus vai escrever um plano que você executa — ele
  precisa dos nomes reais, não de descrições vagas.
- **Diga o que NÃO fazer.** Restrições, invariantes, o que não pode quebrar.
- **Curto.** Se passar de ~1-2 páginas, você provavelmente está despejando
  material que deveria ter sido destilado numa conclusão.

## Formato do `brief.md`

```markdown
# Brief: <nome da tarefa>

## Objetivo
<1-3 frases: o que precisa ser construído e por quê>

## Contexto da base de código
- Arquivos relevantes: `path/a.py` (faz X), `path/b.py` (faz Y)
- Padrões a seguir: <ex.: "erros via Result<T>, não exceção">
- Stack / ferramentas: <linguagem, framework, comando de teste>

## Contratos e descobertas (resultado dos spikes/pesquisa)
- <contrato de API, assinatura, rate limit, formato de dados — destilado>
- <conclusão de cada spike: o que foi confirmado/refutado>

## Restrições e invariantes
- <o que NÃO pode quebrar; o que deve permanecer compatível>

## Critério de aceitação
- <como saber que está pronto: testes que devem passar, comportamento observável>

## Aberto / incerto (peça ao Opus para decidir)
- <pontos onde você quer o julgamento do Opus no plano>
```

## Antes de enviar, cheque
- O Opus consegue escrever um plano executável lendo SÓ isto, sem perguntar nada?
- Há algum dump cru que deveria ser uma conclusão de uma linha?
- Os caminhos e nomes são reais (você os verificou), não inventados?

Quando o brief passar nesse check, prossiga para a skill **ask-opus-plan**.

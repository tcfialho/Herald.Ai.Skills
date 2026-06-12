# Bloco para ~/.claude/CLAUDE.md — quando o CLAUDE (ex.: haiku) é o DRIVER da cascata

Anexe este bloco ao `~/.claude/CLAUDE.md` da máquina onde um Claude barato
(ex.: `claude --model haiku`, ou um endpoint custom via `ANTHROPIC_BASE_URL`)
vai dirigir tarefas usando o llm-cascade. As skills `cascade-*` devem estar em
`~/.claude/skills/` (ver README).

<!-- --- llm-cascade (início do bloco; anexável) --- -->

## Cascata multi-LLM: dirija barato; o judge forte só planeja e revisa

**Trava anti-loop (cheque primeiro):** se `CASCADE_DEPTH` ou `AGY_CALLED_BY_AI`
estiver setado, ou o prompt contiver contrato de tags `<RESULT>`/`<SOURCES>`,
você é sub-trabalhador: execute e devolva o resultado; PROIBIDO chamar
`ask_judge.py` ou qualquer delegação.

**Dirigindo tarefa de desenvolvimento** (veio de humano): use a skill
`cascade-persona`. Classifique T0/T1/T2 pela rubrica; T0 = zero chamadas ao
judge; T1 = só 1 review; T2 = plan + review. Os orçamentos são impostos pelo
wrapper (exit 75 = recusado; siga a política da recusa).

**Carve-out:** enquanto a persona da cascata estiver ativa numa tarefa, NÃO
acione `delegate-to-agy` (ou outra skill de delegação) para a mesma tarefa — a
cascata JÁ É a divisão de trabalho; empilhar delegações duplica custo.

**Custos:** reporte consumo do judge sempre em tokens, nunca em valores
monetários.

<!-- --- llm-cascade (fim do bloco) --- -->

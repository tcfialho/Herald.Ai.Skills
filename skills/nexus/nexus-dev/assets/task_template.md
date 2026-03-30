# Task {{TASK_ID}} — {{TASK_TITLE}}

**Plano:** `{{PLAN_NAME}}`  
**Prioridade:** {{PRIORITY}}  
**Status:** {{STATUS}}

---

## Objetivo

{{TASK_DESCRIPTION}}

---

## Arquivos a Modificar/Criar

> **Limite:** Máximo 3 arquivos por task (Atomic Task Rule)

| # | Caminho | Operação | Descrição |
|---|---------|----------|-----------|
{{FILES_TABLE}}

---

## Dependências

**Tasks que devem ser completadas antes:**
{{DEPENDENCIES}}

---

## Requisitos EARS Cobertos

> Esta task implementa os seguintes requisitos do plano:

{{EARS_REQUIREMENTS}}

---

## Critérios de Aceite

> O que prova que esta task está concluída — específico ao comportamento implementado aqui.

{{ACCEPTANCE_CRITERIA}}

---

## Notas de Implementação

{{IMPLEMENTATION_NOTES}}

---

> Gates de infraestrutura (build, lint, tests, anti-mock) verificados automaticamente pelo Validation Gate do `/dev`.  
> *Template gerado por `task_breaker.py` — Framework Nexus.*

# 📋 Plan: {{PLAN_NAME}}

> **Gerado por:** Framework Nexus `/plan`  
> **Data:** {{CREATED_AT}}  
> **Complexidade:** {{COMPLEXITY_TIER}} (Score: {{COMPLEXITY_SCORE}}/25)  
> **Branch de Execução:** `feature/{{PLAN_NAME}}`  
> **Specs Path:** `.nexus/{{PLAN_NAME}}/spec.md`

---

## 🎯 Resumo Executivo

{{EXECUTIVE_SUMMARY}}

**Objetivo Principal:** {{PRIMARY_OBJECTIVE}}

**Estimativa de Execução:**
- Complexidade: {{COMPLEXITY_TIER}}
- Tasks Estimadas: {{ESTIMATED_TASKS}}
- Arquivos Estimados: {{ESTIMATED_FILES}}

---

## 🏗️ Contexto do Projeto

{{PROJECT_CONTEXT}}

**Stack Tecnológica:** {{TECH_STACK}}  
**Usuários Alvo:** {{TARGET_USERS}}  
**Autenticação:** {{AUTH_APPROACH}}  
**Persistência:** {{PERSISTENCE_APPROACH}}

---

## 🏛️ Mapa de Componentes

> Visão C4 das camadas e fronteiras do sistema. Cada subgraph representa uma camada física ou namespace.

{{COMPONENT_DIAGRAM}}

---

## 🗂️ Dicionário de Entidades

> Vocabulário canônico do domínio — toda task e requisito usa estas definições.

| Entidade | Tipo | Definição |
|----------|------|-----------|
{{ENTITY_DICTIONARY}}

---

## ⚖️ Decisões de Arquitetura

{{DECISIONS_TABLE}}

---

## 📌 Premissas Auto-Assumidas

{{ASSUMPTIONS_TABLE}}

> ⚠️ Premissas de risco ALTO devem ser confirmadas antes de iniciar `/dev`.

---

## ⚙️ Requisitos Funcionais

> Notation: EARS (Event-based Automated Requirements Specification)  
> Formato: `WHEN <trigger> THE SYSTEM SHALL <response>`

{{FUNCTIONAL_REQUIREMENTS}}

---

## 🧱 Invariantes do Sistema

> Regras que o sistema **sempre** respeita, independente de evento ou contexto.

{{SYSTEM_INVARIANTS}}

---

## 📐 Requisitos Não-Funcionais

{{NON_FUNCTIONAL_REQUIREMENTS}}

---

## 🚧 Restrições

{{CONSTRAINTS}}

---

## ⚠️ Edge Cases

{{EDGE_CASES}}

---

## 📋 Tasks de Execução

> **Regra Atômica:** Cada task toca **1 a 3 arquivos**. Sem exceções.

| ID | Título | Arquivos | Dependências | Prioridade |
|----|--------|----------|--------------|------------|
{{TASKS_TABLE}}

### Detalhamento das Tasks

{{TASKS_DETAIL}}

---

## ✅ Critérios de Aceitação

{{ACCEPTANCE_CRITERIA}}

---

## 🔒 Mandato de Execução

```
EXECUTION_MANDATE: COMPLETE_ALL_TASKS_NO_EXCEPTIONS
ANTI_MOCK: BLOCKED
ANTI_INTERRUPTION: ACTIVE
MIN_COVERAGE: 80%
EARS_COMPLIANCE_MIN: 90%
COMMIT_FORMAT: [TASK-XXX] type(scope): description
```

---

*Documento gerado automaticamente pelo Framework Nexus — não editar manualmente.*


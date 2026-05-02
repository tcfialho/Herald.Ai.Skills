# [Project Name] — Architecture Specification

> Technical architecture, stack, structural model, class views, traceability, and quality gates. Functional behavior lives in `spec.md`. Visual decisions live in `design.md`.

## Architectural Style

This project follows **Herald Architecture**, adapted to the target language and stack. See `../shared/references/herald_architecture.md` for canonical principles.

Default principles:

- Readability over everything.
- Rich Domain Model.
- Entity never accesses infrastructure.
- Handler is a thin orchestrator.
- Polymorphism over type-based conditionals.
- Small functions.
- Constants for magic numbers.
- Explicit suffixes.
- Semantic folders.
- Immutability first.

## Stack

| Concern | Decision | Justification |
| --- | --- | --- |
| Language | TBD | TBD |
| Runtime | TBD | TBD |
| API | TBD | TBD |
| UI | TBD | TBD |
| Database | TBD | TBD |
| Messaging | TBD | TBD |
| Tests | TBD | TBD |
| Deploy | TBD | TBD |

## 1. Modelagem Estrutural Global (C4 Component)

> One Mermaid `flowchart TD` with `subgraph` per layer (UI / Application / Domain / Infrastructure / External). Each subgraph holds the components living there. Arrows show dependency direction; a Domain component never points outward to Infrastructure.

```mermaid
flowchart TD
    subgraph UI["UI Layer"]
        Screen1[Screen / Page]
        Controller1[Controller]
    end

    subgraph App["Application Layer"]
        Handler1[Handler / Use Case]
        Service1[Domain Service]
    end

    subgraph Domain["Domain Layer"]
        Entity1[Entity]
        VO1[Value Object]
    end

    subgraph Infra["Infrastructure Layer"]
        Repo1[Repository]
        Adapter1[External Adapter]
    end

    subgraph External["External Systems"]
        Ext1[(Database)]
        Ext2[/External API/]
    end

    Screen1 --> Controller1
    Controller1 --> Handler1
    Handler1 --> Service1
    Handler1 --> Repo1
    Service1 --> Entity1
    Entity1 --> VO1
    Repo1 --> Ext1
    Adapter1 --> Ext2
```

### Layer Definitions

- **UI Layer:** TBD — entry surface (web/CLI/API). No business rule.
- **Application Layer:** TBD — orchestrators, handlers, transaction boundaries.
- **Domain Layer:** TBD — entities, value objects, domain services, invariants.
- **Infrastructure Layer:** TBD — persistence, external adapters, message buses, security.
- **External Systems:** TBD — databases, third-party APIs, queues.

## 2. Diagrama de Classes Detalhado (per layer)

> One independent `classDiagram` block per layer. Never a single monolith. Show fields, methods (signatures only), associations, and dependencies.

### 2.1 Visão Domain

```mermaid
classDiagram
    class EntityName {
        +id: Identifier
        +method(input) Result
    }
    class ValueObjectName {
        +value: Type
    }
    EntityName --> ValueObjectName
```

### 2.2 Visão Application

```mermaid
classDiagram
    class UseCaseHandler {
        +execute(command) Result
    }
    class DomainService {
        +rule(input) Outcome
    }
    UseCaseHandler --> DomainService
```

### 2.3 Visão Infrastructure

```mermaid
classDiagram
    class RepositoryImpl {
        +find(id) Entity
        +save(entity) void
    }
    class ExternalApiAdapter {
        +call(request) Response
    }
    class IRepository {
        <<interface>>
    }
    RepositoryImpl ..|> IRepository
```

## 3. Matriz de Rastreabilidade (UC → Components)

> Map every functional Use Case from `spec.md` to the components/classes/namespaces from sections 1 and 2. No UC may be left unmapped.

| Use Case | Layer(s) | Component(s) / Class(es) | Namespace / Folder |
| --- | --- | --- | --- |
| UC-001 | UI, Application, Domain | `Controller1`, `UseCaseHandler`, `EntityName` | `app/uc-001/`, `domain/` |

## 4. Diagrama de Transições de Estado

> Include this section only when at least one entity has a non-trivial lifecycle. Use one `stateDiagram-v2` block per entity with states.

```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Confirmed: confirm()
    Confirmed --> Cancelled: cancel()
    Confirmed --> Done: complete()
    Cancelled --> [*]
    Done --> [*]
```

## Herald Adaptation

Describe how Herald principles map to this language and stack. Examples per language:

- Records/sealed/dataclasses for immutable DTOs.
- Encapsulated rich entities with private state and intention-revealing methods.
- Use-case handlers as thin orchestrators returning Result-like outcomes.
- Repositories behind interfaces declared in the Domain or Application layer.
- Infrastructure adapters living only at the Infrastructure layer.

Document any deviation from Herald defaults and the reason.

## Project Structure

```text
TBD
```

## Allowed Folders

- TBD

## Banned Folders

- Data
- Database
- Network
- Http
- Util
- Common
- Models
- Dto
- Core

## NFRs

| ID | Quality Attribute | Requirement | Verification |
| --- | --- | --- | --- |
| NFR-001 | Performance | TBD | TBD |
| NFR-002 | Availability | TBD | TBD |
| NFR-003 | Security | TBD | TBD |

## Commands

```text
build: TBD
test: TBD
lint: TBD
run: TBD
```

## Quality Gates

- Domain entities do not access infrastructure.
- Handlers orchestrate and return Result-like outcomes where applicable.
- Commands and queries are immutable DTOs for the language.
- Files are inside allowed folders.
- Banned folders are not introduced.
- Verify commands pass.
- Class diagrams in section 2 are split by layer (no monolithic Mermaid block).
- Every UC in `spec.md` has a row in the Traceability Matrix.

## ADRs

### ADR-001 — Initial Architecture

**Status:** accepted

**Context:** TBD

**Decision:** TBD

**Consequences:** TBD

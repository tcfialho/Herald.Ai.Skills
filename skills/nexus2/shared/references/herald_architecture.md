# Herald Architecture Reference

Use this as the default architecture style for Nexus 2.0 projects. Adapt idioms to the target language.

## Core Principles

1. Readability over everything.
2. Rich Domain Model.
3. Entity never accesses infrastructure.
4. Handler is a thin orchestrator.
5. Polymorphism over type-based conditionals.
6. Small functions.
7. Constants for magic numbers.
8. Explicit suffixes.
9. Semantic folders.
10. Immutability first.

## Rich Domain Model

Entities protect invariants through domain methods. They do not call repositories, APIs, message buses, or infrastructure services.

Mutation happens through methods with business names. Direct public mutation is forbidden where the language can prevent it.

## Handler Pattern

Handlers orchestrate one use case:

1. Fetch data.
2. Validate existence and related data.
3. Delegate business behavior to entities.
4. Convert expected domain failures into Result-like values.
5. Persist changes.
6. Trigger side effects after persistence.

## Language Adaptation

C#:

- Commands and queries use records.
- Entities use classes with private setters.
- Handlers return `Result<T>`.
- Interfaces use `I` prefix.

TypeScript:

- Commands and queries use readonly object types or classes.
- Entities use classes with private fields or controlled methods.
- Handlers return `Result<T>` or discriminated unions.
- Infrastructure contracts live behind interfaces or ports.

Python:

- Commands and queries use frozen dataclasses or pydantic immutable models.
- Entities use classes with controlled mutation methods.
- Repository contracts use protocols or abstract base classes.
- Handlers return Result-like objects.

Java:

- Commands and queries use records.
- Entities use classes with private fields and domain methods.
- Handlers return Result-like objects.
- Infrastructure is behind interfaces.

## Common Gates

- Entity imports infrastructure: fail.
- Entity exposes uncontrolled setters/mutation: fail or warning by language capability.
- Handler contains business state transition logic that belongs in entity: warning or fail.
- Type-based conditionals inside entity: warning; fail if complex.
- Banned folders introduced: fail.
- Verify command missing or failing: fail.

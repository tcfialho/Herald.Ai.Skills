---
name: continuous-dev-loop
description: Ensures complete, focused execution of development tasks. Prevents AI laziness, scope deviation
---

# Continuous Dev Loop

Execute the user's prompt to full completion in a single, uninterrupted flow.
No ceremony. No permission-seeking. No half-built output.
Think before acting. Build completely. Judge your own work. Deliver.

## Activation

Activate when the user requests building, creating, implementing, or developing something that involves multiple files or components. Trigger phrases: "build", "create", "implement", "develop", "set up", "make", along with descriptions of features, apps, APIs, UIs, or systems.

## Execution Protocol

Follow this as rigid pseudocode. Do NOT skip steps. Do NOT reorder.

```
STATE = "orient"

WHILE STATE != "done":

  IF STATE == "orient":
    1. Read existing codebase:
       - Project structure, dependencies, tech stack
       - Naming conventions and code style
       - Architectural pattern in use (MVC, CQRS, Clean Architecture, Hexagonal, etc.)
       - Existing models, their relationships, and data flow
       - Where each type of logic lives (controllers vs services vs handlers vs repositories)
       Log: [PATTERN] <identified pattern> (evidence: <files that prove it>)
    2. Define 3-7 completion truths (what must be TRUE when done)
       Frame as user-observable outcomes, not file names:
       - Good: "User can submit the form and see a confirmation"
       - Bad: "Create FormComponent.tsx"
    3. Decompose into vertical slices ordered by dependency
       Each slice = one working capability end-to-end (data → logic → UI)
       Each slice INCLUDES its tests for critical paths
       NEVER decompose by horizontal layer (all models, then all routes...)
    4. IF architectural decision needed (framework, data model, structure):
         Deliberate internally:
         - Generate PATH_A and PATH_B with opposing approaches
         - Critique each: pros, cons, risks, fit with existing code
         - Select with explicit reason
         - Log: [DECISION] question → choice (reason: rationale)
    5. Write .dev-loop/state.md (see State File section)
    6. IF git repo exists → add .dev-loop/ to .gitignore
    7. STATE = "build"
    PRODUCE NO OUTPUT TO USER DURING THIS PHASE

  IF STATE == "build":
    FOR EACH unchecked task in state.md:
      1. Understand before touching:
         - Read the specific files and modules this task will modify or extend
         - Identify the existing models, relationships, and types involved
         - Map where new code belongs based on the [PATTERN] identified in Orient
         - IF the project uses services → logic goes in services, NOT controllers
         - IF the project uses command handlers → new operations get new handlers
         - IF adding a field/class → read the full model and its relationships first
         - NEVER put code somewhere just because it's the first file you found
      2. Search before create:
         - Check if target files, classes, or similar logic already exist
         - Check if the dependency/package is already installed
         - Extend existing code, don't duplicate
      3. Implement completely:
         - Every function fully coded, every error path handled
         - Every import connected, every route registered
         - Zero stubs, zero placeholders
         - Distribute code across files by responsibility (one concern per file)
         - NEVER write 300+ lines in a single file — split semantically
         - Each file should be independently understandable
      4. Write tests for the critical paths of this slice, then run them
         - Test the behavior, not the implementation
         - Run the tests. IF they fail → fix code, not tests
         - IF no test framework is set up → set it up as part of the first slice
      5. Self-verify (max 2 attempts):
         attempt = 0
         WHILE attempt < 2:
           - Run linter/build/typecheck if available
           - Run tests for this slice
           - Check: file exists? content is real (not skeleton)?
           - Check: wired correctly (imports, routes, exports)?
           - Check: code is in the correct layer per [PATTERN]?
           - IF all pass → BREAK
           - ELSE → fix issues, attempt++
         IF attempt == 2 AND still failing:
           - Log in state.md under ## Blocked
           - Continue to next task (don't loop forever)
      6. Update state.md:
         - Check off completed task
         - Log any design decision: [DECISION] what → choice (reason)
      7. EVERY 3 completed tasks — regurgitation checkpoint:
         - Re-read state.md
         - Internally restate: the original prompt, remaining truths, and next task
         - Update ## Summary with consolidated progress (what's built, key decisions)
         - This active re-declaration prevents context drift in long sessions
      8. Continue immediately — no announcement, no summary to user
    STATE = "review"

  IF STATE == "review":
    Switch to critical code reviewer mindset. Judge your own work harshly.
    1. Re-read state.md — check every truth against actual code
    2. FOR EACH truth that is FALSE:
         - Identify what's missing or broken
         - Implement the fix
         - Re-verify
    3. Scan for lazy code patterns:
         - Search project for: TODO, FIXME, placeholder, "implement later"
         - Search for: empty function bodies, mock data as "temporary"
         - Search for: missing error handling, skeleton components
         - IF any found → fix immediately
    4. Scan for structural violations:
         - Code in wrong layer? (business logic in controller, queries in handler, etc.)
         - Duplicate class or function that already existed?
         - Monolithic file that should be split? (300+ lines doing multiple things)
         - New model/entity field that conflicts with existing relationships?
         - IF any found → refactor to correct location/structure
    5. Run full build AND tests
    6. IF all truths are TRUE AND no lazy code AND no structural violations:
         STATE = "done"
       ELSE:
         Fix remaining issues (max 2 more passes)
         STATE = "done"

  IF STATE == "done":
    1. Mark all completed truths in state.md
    2. Output concise completion summary (max 15 lines):
       - What was built
       - How to run/use it
       - Any known issues from ## Blocked
    BREAK
```

## Rules

### Execute, Don't Narrate
- NEVER ask "should I continue?", "want me to proceed?", "shall I implement X?"
- NEVER announce transitions: "Now let's move to...", "Great, now I'll..."
- NEVER celebrate intermediate steps: "The model is done! Now..."
- NEVER explain what you're about to do. Do it.
- The prompt IS the authorization. Execute until every truth is TRUE.

### Complete, Never Stub
- NEVER write `// TODO`, `// FIXME`, `/* placeholder */`, `// implement later`
- NEVER leave empty function bodies or `pass` with a comment
- NEVER use `throw new Error('Not implemented')` or equivalent
- NEVER present hardcoded mock data as "temporary"
- ALWAYS implement full error handling — catch, handle, give useful feedback
- IF a feature needs 5 files, create ALL 5. Not 3 with a note.

### Stay on Target
- NEVER refactor code unrelated to the prompt
- NEVER add features not requested
- NEVER change existing naming, style, or structure unless the task requires it
- IF unrelated bug found → note in state.md under Decisions, do NOT fix

### Code Over Commentary
- Spend output tokens on working code, not explaining it
- NEVER repeat unchanged code blocks
- NEVER explain obvious edits line by line
- IF explanation is needed → one sentence, then code

### Deliver Working Software First
- Priority order: working functionality + its tests > documentation > comments
- Each vertical slice includes tests for its critical paths — tests are part of building, not a separate phase
- IF context is severely constrained → complete the current slice with tests, skip remaining slices
- Do NOT generate documentation files unless the user asked for them

## Anti-Laziness Checks

The review phase MUST scan for these patterns. Fix every instance found.

❌ `function handleSubmit() { /* TODO */ }`
✅ `function handleSubmit() { validate(data); await api.post('/submit', data); notify('Saved'); }`

❌ `// Add error handling later`
✅ `try { await save(data); } catch (err) { logger.error(err); showError('Save failed'); }`

❌ `return mockData; // Replace with real API call`
✅ `return await fetch('/api/data').then(r => r.json());`

❌ `export default function Page() { return <div>Coming soon</div> }`
✅ `export default function Page() { return <Dashboard metrics={data} onRefresh={refresh} /> }`

❌ "I've set up the basic structure. You can add the remaining components."
✅ ALL components implemented. The user asked for a complete solution, not scaffolding.

❌ Business logic in the controller when the project uses services/handlers:
```
router.post('/orders', (req, res) => {
  const total = items.reduce((sum, i) => sum + i.price * i.qty, 0);
  const tax = total * 0.15;
  await db.insert('orders', { total, tax });  // Logic + DB in controller
});
```
✅ Controller delegates, logic lives where the pattern dictates:
```
router.post('/orders', (req, res) => {
  const order = await orderService.create(req.body);  // Controller only routes
  res.status(201).json(order);
});
```

❌ 500-line monolithic file doing models + routes + validation + utils
✅ Split semantically: `order.model.ts`, `order.service.ts`, `order.routes.ts`, `order.validation.ts`

❌ Adding `status: string` to a model that already has `StatusEnum`
✅ Read the model first. Use the existing `StatusEnum`. Extend it if needed.

## Internal Deliberation

For non-trivial decisions (architecture, framework, data model, state management):

1. Generate two opposing approaches internally (PATH_A vs PATH_B)
2. Critique each: pros, cons, complexity, fit with existing code, long-term cost
3. Select the path with explicit reason
4. Log in state.md: `[DECISION] <question> → <choice> (reason: <rationale>)`

Do NOT output the deliberation to the user. Decide and execute.
Exception: choices with significant external impact (cost, vendor lock-in) → ask the user.

## State File

Create `.dev-loop/state.md` during Orient. This is your persistent memory.

```markdown
# Dev Loop State

## Prompt
<original user prompt, verbatim>

## Truths
- [ ] <user-observable outcome 1>
- [ ] <user-observable outcome 2>

## Tasks
- [ ] <vertical slice 1: brief description>
- [ ] <vertical slice 2: brief description>

## Architecture
[PATTERN] <identified pattern> (evidence: <key files>)

## Decisions
<none yet>

## Summary
<updated every 3 tasks — what's built, what's next>

## Blocked
<issues unresolved after 2 verify attempts>
```

Update rules:
- Check off tasks and truths as completed
- Log EVERY design decision under ## Decisions with `[DECISION]` format
- Update ## Summary every 3 tasks (this is your context compression checkpoint)
- Log blocked items to prevent infinite retry loops

## Context Management

For long sessions where context grows large:
- EVERY 3 completed tasks → regurgitation checkpoint:
  1. Re-read state.md
  2. Internally restate the original prompt and all unchecked truths (active recall, not passive read)
  3. Update ## Summary with what was built and key decisions (consolidate, don't append)
- When re-anchoring: focus on unchecked truths, unchecked tasks, blocked items
- Do NOT re-explain or re-output already-completed work to the user
- Treat the Summary section as your compressed memory of everything before

## Recovery

IF you detect you've gone off track (building something not in the plan, stuck, or losing focus):

1. STOP
2. Re-read `.dev-loop/state.md`
3. Find the first unchecked task
4. Resume from there

## Continuity

IF the user says "continue", "keep going", or "finish this" in a new message or conversation:

1. Read `.dev-loop/state.md` from the project root
2. Read existing code to understand current state
3. Identify remaining unchecked truths and tasks
4. Resume the Build phase from the first unchecked task

IF `.dev-loop/state.md` doesn't exist but partial implementation exists:
- Scan the codebase to infer what's done
- Create state.md reflecting current status
- Then continue building

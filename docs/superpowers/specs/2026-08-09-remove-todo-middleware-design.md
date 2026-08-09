# Remove Todo Middleware

## Goal

Remove `TodoListMiddleware` from every user-facing LambChat agent so neither main agents nor their declarative subagents expose `write_todos` or carry the `todos` state channel.

## Scope

- Remove `create_todo_middleware()` from the fast, search, and team agent middleware stacks.
- Remove the shared `src/agents/core/todo_middleware.py` helper once it has no callers.
- Remove stale prompt-architecture comments that claim `write_todos` is part of the DeepAgents stack.
- Remove the deleted helper from the owned system-prompt budget sample.
- Replace the existing positive registration regression with a negative regression covering all three agent implementations and both main/subagent stacks.

The memory-compaction agent and goal rubric agent are unchanged because they do not register the todo middleware today. No feature flag or compatibility shim will remain.

The event presenter retains its defensive handling for historical `write_todos` events. That compatibility path does not register the tool or add todo state, and keeps old persisted event streams renderable.

## Behavior

The underlying DeepAgents version does not install `TodoListMiddleware` by default. Once LambChat's explicit registrations are removed, `write_todos` will not be present in the effective tool set and `todos` will not be added to agent state. All other middleware ordering and tools remain unchanged.

## Testing

Follow RED-GREEN-REFACTOR:

1. Change the registration test to require no todo helper import or construction in fast, search, and team agents; run it first and confirm it fails against the existing registrations.
2. Remove the six registrations, imports, helper module, and stale comment.
3. Re-run the focused test, then relevant agent tests and Ruff checks for touched Python files.

## Non-goals

- Replacing `write_todos` with another planning tool.
- Adding configuration to re-enable todo lists.
- Changing task/subagent behavior, prompt caching, or middleware ordering beyond removing the todo entries.

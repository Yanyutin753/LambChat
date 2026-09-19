# Agent Todo and Memory Upgrade Design

## Goal

Make LambChat more reliable on multi-step work by giving every user-facing Agent an explicit persisted Todo list and making memory recall aware of the current session and project without leaking data across scopes.

## Design

Use the upstream `TodoListMiddleware` through one LambChat factory so Fast, Search, Team, and their executable subagents share the same configuration and state schema. The memory compaction worker remains excluded because its job is maintenance rather than user task execution.

Keep durable memory in the existing `user`, `project`, and `reference` scopes. Add a session-context layer only to recall guidance and ranking; session Todos remain checkpoint state and are never persisted as durable memories. The recall tool will prefer current project memories, then user preferences and feedback, while preserving semantic score as the tie breaker and exposing freshness warnings already produced by the native backend.

The memory guide will explicitly tell the Agent when to recall, when to retain, and how to distinguish current task state from durable facts. The existing idle transcript extraction, source references, deduplication, compaction, and self-evolution pipelines remain the durable write path.

## Verification

Tests will verify middleware registration and Todo state/tool exposure for all three Agent families, scope-safe recall ordering, memory guide behavior, and a local fake Mongo/backend conversation fixture that exercises project-over-user recall, Todo persistence across turns, and no cross-project leakage.

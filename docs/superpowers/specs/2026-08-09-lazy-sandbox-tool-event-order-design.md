# Lazy Sandbox Tool Event Order Design

## Goal

Keep Search Agent sandbox initialization lazy while making the first sandbox-backed tool's public event order deterministic:

```text
sandbox:starting -> sandbox:ready -> tool:start -> tool:result
```

If initialization fails, the corresponding order is:

```text
sandbox:starting -> sandbox:error -> tool:start -> tool:result(error)
```

## Root Cause

`LazySandboxBackend` emits `sandbox:*` events from the tool execution task, while `AgentEventProcessor` emits `tool:start` from the separate `astream_events` consumer. Both write directly through the Presenter, so provider latency and asyncio scheduling determine which event reaches Redis first.

## Design

`AgentEventProcessor` accepts an optional async pre-tool-start hook. Search Agent supplies a hook owned by `LazySandboxBackend`; other agents keep the current behavior.

For a filesystem tool that will use the composite backend's default sandbox, the hook awaits the backend's existing single-flight readiness path before `tool:start` is emitted. The concurrently executing tool awaits the same initialization task, so no second sandbox is created and no lifecycle event is duplicated.

The hook recognizes DeepAgents filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`, and `execute`). File operations targeting `/skills` or `/memories` remain routed storage operations and do not initialize the sandbox. `execute`, relative/default paths, and searches without an explicit routed path use the sandbox.

Initialization errors remain authoritative. The hook waits until `sandbox:error` has been attempted, then permits `tool:start`; the tool execution produces its normal failed `tool:result`. Cancellation continues to propagate.

## Compatibility

- Model-only turns still perform no sandbox I/O and emit no sandbox lifecycle events.
- Skills and memories routes still avoid sandbox initialization.
- Fast Agent, Team Agent, MCP tools, and non-filesystem tools do not receive the hook.
- Existing Presenter, Redis Stream, MongoDB, and frontend event contracts are unchanged.

## Testing

An end-to-end Search Agent graph test gates sandbox manager completion. While initialization is blocked, it proves `tool:start` has not been emitted. After release, it asserts the exact lifecycle/tool order. Focused unit coverage proves routed paths do not initialize the sandbox and initialization failure does not suppress the tool events.

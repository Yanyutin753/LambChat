# System Prompt Compression Design

## Goal

Reduce the assembled agent system prompt without weakening tool behavior, safety,
artifact delivery, memory handling, or prompt-cache ordering. The change should
remove duplicated prose rather than override dependency-generated runtime facts.

The representative sandbox prompt supplied for this work is 11,157 characters.
The conservative target is a 20% to 30% reduction for the same enabled features
and representative inventories.

## Scope

This change covers LambChat-owned prompt fragments and LambChat's configuration
of `TodoListMiddleware` for fast, search, and team agents. It does not patch
installed DeepAgents or LangChain packages, remove tools, change middleware
ordering, or alter dynamic inventory contents.

## Prompt Ownership

Each operational contract should have one authoritative prompt owner:

| Contract | Owner |
| --- | --- |
| Workspace selection and artifact delivery | `src/agents/core/prompt_policy.py` |
| Safety, verification, privacy, progress | `src/agents/core/prompt_policy.py` |
| Todo tool availability and state schema | compact Todo middleware factory |
| Concise todo behavior | `PROGRESS_POLICY` |
| Skill discovery, `SKILL.md`, virtual storage, transfer before execution | `src/infra/skill/loader.py` |
| Deferred MCP/system tool discovery | `src/infra/tool/deferred_manager.py` |
| Environment-variable secrecy | `src/infra/tool/env_var_prompt.py` |
| Cross-session memory behavior | `src/infra/memory/client/types.py` |
| Virtual-to-host path mappings | DeepAgents `FilesystemMiddleware` runtime block |

The DeepAgents path-mapping block remains untouched because it is generated from
the active backend and contains facts that LambChat cannot safely hard-code.

## Code Changes

### Compact Todo Middleware

Add `create_todo_middleware()` in
`src/agents/core/todo_middleware.py`. It returns
`TodoListMiddleware(system_prompt="")`. Replace the six direct
`TodoListMiddleware()` constructions used by main agents and subagents.

This preserves the `write_todos` tool and `todos` state channel while removing
LangChain's approximately 1.3 KB default todo guide. The concise todo behavior
already present in `PROGRESS_POLICY` remains the sole behavioral instruction.

### Canonical Workflow

Keep workspace boundaries, artifact completion, safety, verification, privacy,
and progress in `prompt_policy.py`. Apply the following deduplication:

- Merge the repeated single-file/project reveal guidance into Artifact Delivery.
- Remove Skill transfer details from Workspace Boundaries.
- Remove the generic Tool and Skill Routing section from `WORKFLOW_POLICY`.
  Capability-specific dynamic guides already describe Skills and deferred tools
  only when those capabilities are present.
- Keep the storage block short and leave shell accessibility to DeepAgents'
  runtime path-mapping block.
- Tighten subagent dispatch prose without dropping timestamp, parallelism,
  handoff inspection, conflict resolution, or synthesis requirements.

### Dynamic Guides

Shorten wording, not inventories:

- Skills retain every advertised name and existing description-threshold logic.
- Deferred MCP inventories retain every undiscovered tool name; deferred system
  tools retain their one-line descriptions.
- Environment prompts retain every configured key name without reading values.
- Memory retains the four memory types, selective recall, retain/skip policy,
  stale verification, deletion, and ignore/forget behavior.

Dynamic blocks remain separate so the existing prompt-cache stability tiers do
not change.

## Error and Compatibility Behavior

- Empty Skills, Memory, environment, and deferred-tool inventories
  continue to omit their prompt blocks.
- Disabling a capability does not leave behind instructions for an unavailable
  tool.
- Prompt headings used by cache classification remain stable unless their
  corresponding block is deliberately removed from the canonical workflow.
- Remove `TOOL_DISCOVERY_POLICY` and its `TOOL_DISCOVERY_GUIDE` alias after
  confirming there are no remaining production imports. Keep the other legacy
  aliases because active code or tests still consume them.
- No installed dependency file is edited or monkey-patched.

## Testing

Follow TDD for each behavior change:

1. Change todo middleware tests to require an empty `system_prompt` while still
   asserting the `write_todos` tool and `todos` state channel.
2. Add or tighten prompt-budget assertions for the canonical workflow, Skills,
   Memory, deferred search guide, and environment guide.
3. Assert each routing contract appears in its owning dynamic guide and no
   longer appears in the canonical workflow.
4. Preserve tests for prompt block ordering, stable/dynamic cache boundaries,
   inventory completeness, description thresholds, and disabled capabilities.
5. Record before-and-after character counts for the decoded representative
   prompt. Also enforce smaller per-block budgets in tests so future prose does
   not silently restore the duplication. Dynamic inventory entries are held
   constant during the comparison.
6. Run the focused Python test files covering prompt composition and middleware,
   then run Ruff on changed Python files.

## Acceptance Criteria

- Main and subagents still expose `write_todos`, with no LangChain default todo
  prompt appended.
- The decoded representative prompt is at least 20% shorter than its 11,157
  character baseline when the same dynamic inventory entries are used.
- No operational contract listed in Prompt Ownership is lost.
- Dynamic inventories remain complete and deterministically ordered.
- Prompt cache block ordering is unchanged.
- Focused tests and Ruff pass.

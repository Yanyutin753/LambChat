# System Tool Schema Compaction Design

## Goal

Reduce the prompt-token cost of LambChat's system-embedded tool schemas without changing tool execution behavior or materially weakening agent tool selection and argument generation.

The 21 system-embedded tools in the supplied snapshot serialize to 6,981 tokens with `o200k_base` when encoded as compact JSON. The implementation must reduce this baseline by at least 40 percent, to no more than 4,188 tokens. Further reductions are desirable only while the behavioral invariants and semantic-coverage tests remain satisfied.

## Scope

The curated set contains these 21 system-embedded tools:

- Filesystem and execution: `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`, `execute`
- Agent workflow: `task`, `write_todos`, `ask_human`
- Artifact and transfer: `reveal_file`, `reveal_project`, `transfer_file`, `transfer_path`, `upload_url_to_sandbox`
- Memory and skills: `memory_retain`, `memory_recall`, `memory_delete`, `search_skills`
- Deferred system-tool discovery: `search_tools`

External MCP tools, including `web_search_prime`, `search_doc`, and `get_repo_structure`, are explicitly outside this change. Their descriptions and parameter schemas must pass through unchanged. Future MCP tools also pass through unchanged unless they are later added to the curated system-tool registry.

This work does not defer additional tools behind `search_tools`, rename tools or parameters, alter runtime implementations, change tool results, compact ordinary MCP tool schemas, or modify third-party packages in `.venv`.

## Chosen Architecture

Add a model-call middleware that produces compact model-facing tool definitions from the tools already present in `ModelRequest.tools`. The graph's registered tools remain the authoritative execution and validation objects. The middleware changes only the copy passed down to the model-binding handler for that call.

This central boundary is preferable to editing each source because the current system tools originate from deepagents, LangChain, and LambChat. It also survives dependency upgrades while allowing non-system MCP definitions to pass through untouched.

The middleware must run after dynamic tool injection has added the system `search_tools` definition and any discovered MCP tools, and before prompt-cache annotations are applied. It selects tools by an explicit system-tool registry, compacting `search_tools` while preserving discovered MCP definitions exactly. All three LambChat agent variants and their subagent stacks must use the same factory or registration helper so behavior cannot drift between fast, search, and team agents.

## Compaction Rules

### Curated rules for the current tools

Each of the 21 tools gets a concise description that retains:

- The tool's distinct purpose and when it should be chosen over adjacent tools.
- Preconditions that affect successful invocation, such as reading before editing.
- Non-obvious argument semantics, such as literal rather than regex search.
- Safety boundaries, such as recursive permanent deletion.
- Result or offload behavior only when it changes what the agent must do next.

Parameter descriptions are shortened when their type, default, enum, bounds, or property name already communicates the same information. Long examples and duplicated `Args` or `Returns` sections are removed when their information remains encoded in the JSON Schema.

The following closed string domains become enums in the model-facing schema:

| Tool | Parameter | Values |
|------|-----------|--------|
| `task` | `subagent_type` | `general-purpose`, `codebase-investigator`, `implementation-worker`, `verification-runner`, `researcher` |

Existing enums such as `grep.output_mode`, `write_todos.todos[].status`, `ask_human.fields[].type`, and `reveal_project.template` remain enums.

Paths, commands, file content, search queries, labels, memory content, tags, memory types, and memory context remain open strings because their valid domains are not closed.

### Pass-through rules for non-system tools

Only names in the explicit system-tool registry are eligible for compaction. Unknown and ordinary MCP tools pass through by object identity, including all descriptions, schema metadata, and existing cache annotations.

Within a curated system-tool definition, the shared structural normalizer may:

- Remove JSON Schema `title` metadata.
- Normalize repeated whitespace and blank lines.
- Remove a prose value list only when the same values are already present in an adjacent `enum`.
- Remove mechanically duplicated `Args` and `Returns` boilerplate only when the same parameter descriptions and result behavior are already represented elsewhere in the definition.
- Preserve property names, required lists, defaults, types, formats, numeric or length bounds, `additionalProperties`, and existing enums.

The normalizer must not infer an enum from arbitrary prose, truncate a description to a fixed length, summarize with an LLM, translate text, or remove examples that communicate information not encoded elsewhere. When a transformation is uncertain, it leaves the source unchanged.

## Data Flow

1. Agent construction registers the original `BaseTool` objects and normal middleware.
2. Deferred-tool middleware injects `search_tools` and any discovered tools into the current `ModelRequest`.
3. Schema-compaction middleware checks each request tool against the explicit system-tool registry.
4. Registered system tools receive a curated override and safe structural normalization; all other tools pass through unchanged.
5. Prompt-caching middleware annotates the compact definitions.
6. The model receives compact schemas and emits the same tool names and argument objects.
7. The existing graph or deferred-tool manager executes the call against the original tool object and original runtime validation.

The compactor must be pure: it cannot mutate a `BaseTool`, its Pydantic model, a shared MCP schema dictionary, or `request.tools` in place.

## Behavioral Invariants

For every compacted definition:

- Tool name is unchanged.
- Every input property is retained.
- Required properties are unchanged.
- Defaults, primitive types, nullability, formats, bounds, and `additionalProperties` are unchanged.
- Existing enums are unchanged; new enums are limited to the approved table above.
- Runtime tool objects and their accepted arguments are unchanged.
- Cache-control metadata already present on tool definitions is preserved.
- Unknown schema constructs in curated tools are copied through rather than dropped.
- Non-system tools pass through without copying or mutation.
- Curated descriptions retain a tested set of decision-critical concepts for neighboring tools and safety-sensitive operations.

If a tool cannot be converted safely, the middleware logs a diagnostic and passes through the original definition for that tool. One malformed tool must not remove or alter other tools in the request.

## Agent-Effect Safeguards

Automated tests will assert semantic markers rather than exact prose. Examples include:

- `read_file` retains pagination and read-before-edit guidance.
- `edit_file` retains exact replacement and uniqueness semantics.
- `grep` retains literal-search semantics and its relationship to regex search.
- `delete` retains recursive and irreversible semantics.
- `reveal_file` and `reveal_project` retain the single-file versus folder boundary.
- `transfer_file` and `transfer_path` retain text-only and backend-routing boundaries.
- `task` retains stateless delegation and enough agent-type meaning to choose a worker.
- `write_todos` retains the complex-task threshold and completion-state discipline.
- `ask_human` retains blocking clarification, confirmation, and form behavior without embedding four full examples.
- Memory tools retain store, semantic recall, and delete distinctions.

The existing prompt-policy and tool-routing tests remain part of regression verification. This provides a stable proxy for agent behavior without introducing nondeterministic live-model tests.

## Token Measurement

A deterministic report helper will serialize system-tool definitions with compact JSON separators and count tokens with the repository's existing `tiktoken` dependency using `o200k_base`.

Tests will use a checked-in representative snapshot of the 21 supplied system-tool definitions or an equivalent deterministic fixture. They will report both per-tool and total counts. The acceptance threshold is 4,188 tokens or fewer for the complete fixture, compared with the recorded 6,981-token baseline. The three excluded external MCP tools are not counted because their schemas remain unchanged.

Token accounting is a comparison metric rather than a claim that every provider applies identical wrapper overhead. Both sides use the same serialization and tokenizer so the reduction remains meaningful.

## Testing Strategy

Implementation follows red-green-refactor:

1. Add failing tests for schema invariants and non-mutation.
2. Add failing tests for the approved enum refinements.
3. Add failing semantic-marker tests for the curated descriptions.
4. Add failing middleware tests proving the dynamically injected system `search_tools` definition is compacted, ordinary MCP tools pass through by identity, and runtime tools remain original.
5. Add the failing 21-tool token-budget test.
6. Implement only enough compaction to pass each group, then refactor shared traversal and override data.

Focused verification will cover the new middleware tests plus existing tool-search, prompt-caching, todo registration, subagent prompt, and custom-tool tests. Ruff and Mypy will run on changed Python modules. If the complete suite is practical in the environment, it will run before completion; otherwise the handoff will identify the exact unrun checks.

## Failure Handling and Observability

Compaction is best-effort per registered system tool. Unsupported input shapes, schema-conversion errors, or invalid curated patches cause original-schema fallback and a structured debug or warning log containing the tool name, without logging secrets or complete parameter values.

No runtime feature flag is required initially because fallback is local and preserves the original schema. The compactor exposes pure functions so a future setting can disable it if production evidence requires a rollback.

## Non-Goals

- Changing the textual system prompt outside tool definitions.
- Altering tool-result payload size or artifact offloading.
- Automatically deferring more built-in tools.
- Replacing MCP server schemas at their source.
- Compacting or refining enums for `web_search_prime`, `search_doc`, `get_repo_structure`, or future ordinary MCP tools.
- Adding live-model quality evaluation infrastructure.
- Editing unrelated memory-indexing work already present in the checkout.

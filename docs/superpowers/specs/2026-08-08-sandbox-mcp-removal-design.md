# Sandbox MCP Removal Design

## Goal

Remove LambChat's Sandbox MCP feature completely because its model-facing management tools and `mcporter` execution path add tool and prompt complexity without enough practical use.

This removal is limited to MCP servers that use the `sandbox` transport. LambChat's ordinary sandbox filesystem and execution tools, such as `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, and sandbox uploads, remain available.

## Chosen Approach

Remove the feature from product and runtime code while handling existing database records conservatively:

- Do not expose or register `sandbox_mcp_add`, `sandbox_mcp_update`, or `sandbox_mcp_remove`.
- Do not install, restore, inspect, call, or describe MCP servers through `mcporter`.
- Do not allow new MCP servers to use the `sandbox` transport through APIs, imports, or the frontend.
- Do not automatically delete existing MongoDB records whose transport is `sandbox`. Filter those legacy records out at storage boundaries so they are inert and cannot break list, lookup, export, or startup flows.

An automatic destructive data migration is explicitly out of scope.

## Backend Changes

Delete the dedicated Sandbox MCP modules for model tools, prompt generation, rebuilds, and environment-flag construction. Remove every registration and lifecycle hook from fast/search/team agents, sandbox session helpers, prompt middleware, tool filtering, cache invalidation, prompt policy, deferred-tool guidance, environment-variable guidance, and MCP quota interception.

Remove `sandbox` from `MCPTransport`, remove the Sandbox MCP-specific `command` and `env_keys` request/response fields, and remove the `mcp:write_sandbox` permission. MCP create, update, and import validation will consequently accept only `sse` and `streamable_http`.

Storage reads must exclude legacy `transport=sandbox` documents before model validation. Direct lookup of a legacy Sandbox MCP server must behave as not found. List and export operations must omit it. Existing database records remain untouched and can be cleaned separately by an explicitly authorized operational migration if ever desired.

Legacy records remain reserved by name. Creating or importing an HTTP MCP server with the same owner and name must return the existing conflict/skip outcome rather than leak a database duplicate-key error. Name-based update, enable/disable, policy, and delete endpoints must treat a legacy Sandbox MCP record as not found and must not mutate or delete it. Converting a legacy record into an HTTP MCP server is not supported implicitly; an operator must first clean up the legacy record through a separately authorized data operation.

Remove the three tools from the built-in tools API catalog. Keep the generic `sandbox` tool category because it still describes ordinary filesystem and execution tools.

## Frontend Changes

Remove the Sandbox transport option, command/environment-key fields, Sandbox MCP permission checks, card/sidebar transport labels, and the dedicated chat rendering for the three removed tools. Remove translations used only by this feature from every locale.

The MCP management UI will offer only SSE and Streamable HTTP servers. Existing legacy Sandbox MCP records will not reach the frontend because the backend filters them out.

## Documentation Changes

Delete documentation dedicated solely to Sandbox MCP and `mcporter`. Update mixed prompt/tool-discovery documents only where they describe current Sandbox MCP behavior. Historical material unrelated to this feature remains unchanged.

## Compatibility and Failure Behavior

- No startup code invokes `mcporter`, so missing `mcporter` installations are irrelevant.
- Requests containing `transport: "sandbox"` fail schema validation as an unsupported transport.
- Imports containing Sandbox MCP entries reject those entries according to the existing import error contract; valid HTTP entries continue to import normally.
- Legacy database records do not cause enum-validation failures because storage filters them before constructing response models.
- A same-name create or import cannot overwrite a hidden legacy record, and returns the normal conflict or skipped-existing result.
- Name-based mutation and deletion endpoints cannot modify hidden legacy records and return not found.
- No code path silently converts a Sandbox MCP server into an HTTP MCP server.

## Testing

Follow red-green-refactor for retained behavior:

1. Add or update backend tests that fail while Sandbox MCP is still accepted or exposed:
   - transport validation rejects `sandbox`;
   - tool catalogs and agent contexts exclude all `sandbox_mcp_*` tools;
   - legacy Sandbox MCP documents are omitted from list, lookup, and export operations;
   - same-name create/import handles hidden legacy records without duplicate-key errors;
   - update, toggle, policy, and delete operations cannot mutate hidden legacy records;
   - sandbox startup does not run Sandbox MCP rebuild hooks.
2. Add or update frontend tests that fail while the Sandbox option or dedicated tool renderer remains.
3. Delete tests that cover removed implementation internals after retained-boundary tests are red.
4. Run focused backend and frontend tests, then Ruff, frontend lint, and frontend build for the affected surfaces.

## Acceptance Criteria

- Repository runtime code contains no `sandbox_mcp_*`, `SandboxMCPMiddleware`, or `mcporter` feature path.
- The model tool list no longer contains `sandbox_mcp_add`, `sandbox_mcp_update`, or `sandbox_mcp_remove`.
- MCP APIs and UI support only SSE and Streamable HTTP transports.
- Ordinary sandbox tools and uploads continue to work.
- Legacy Sandbox MCP database documents are ignored without being deleted or causing errors.
- Relevant backend and frontend regression checks pass.

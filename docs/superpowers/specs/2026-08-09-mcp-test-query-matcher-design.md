# MCP Test Query Matcher Design

## Goal

Restore the two failing effective MCP configuration tests without changing runtime behavior. The tests must model the MongoDB query used by production closely enough to include supported servers and exclude the removed legacy `sandbox` transport.

## Root Cause

Production storage now filters legacy sandbox documents before applying cursor limits by adding `{"transport": {"$ne": "sandbox"}}` to MCP server queries. MongoDB supports this operator, but the local `_FakeCollection` in `tests/test_mcp_tool_policies.py` compares every query value with plain equality. It therefore rejects all normal string transports when the expected value is the `$ne` mapping, leaving the effective configuration empty.

The same two tests fail on the pre-merge `main` commit, and the background artifact delivery merge does not touch MCP storage or policy files.

## Chosen Approach

Update only the test collection's query matcher. It will support:

- ordinary equality conditions using the existing behavior;
- a mapping containing `$ne`, which matches when the document value differs from the excluded value.

This mirrors the narrow fake-query pattern already used by `tests/infra/test_mcp_storage_limits.py`. It avoids introducing a shared query emulator or weakening the production-side pre-limit filter.

## Scope

The change is limited to `tests/test_mcp_tool_policies.py`. Production MCP queries, server limits, role filtering, tool-policy loading, and runtime configuration output remain unchanged.

Unsupported MongoDB operators are out of scope. The fake should implement only the query behavior exercised by this test module.

## Test Strategy

The two existing failures are the RED evidence:

1. effective configuration bulk-loads tool policies for `alpha` and `beta`;
2. effective configuration preserves the configured two-server cap.

After updating the fake matcher, verification will run:

1. the two previously failing tests;
2. all of `tests/test_mcp_tool_policies.py`;
3. the complete backend test suite;
4. the project-level `make test` suite.

No new production regression test is needed because the existing tests already exercise the intended production contract and failed for the expected reason before implementation.

# Issue #198 Tavily Usage Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete issue #198 by monitoring Tavily account/key limits, emitting deduplicated threshold alerts, and preserving existing MCP retry and argument-normalization behavior.

**Architecture:** Add a provider-focused `tavily_usage` module that resolves credentials from trusted MCP configuration, parses every Tavily quota bucket, and coordinates conservative polling through Redis with an in-process fallback. `MCPClientManager` passes a monitor context only to Tavily tool wrappers; the wrapper refreshes usage after calls and classifies plan exhaustion as non-retryable without changing ordinary tool results.

**Tech Stack:** Python 3.12+, FastAPI settings, httpx, redis.asyncio, Pydantic/LangChain tools, pytest/pytest-asyncio, Ruff.

---

### Task 1: Tavily monitor configuration and trusted credential resolution

**Files:**
- Create: `src/infra/mcp/tavily_usage.py`
- Modify: `src/kernel/config/base.py`
- Modify: `.env.example`
- Create: `tests/infra/mcp/test_tavily_usage.py`

- [ ] **Step 1: Write failing credential-resolution tests**

Cover explicit `settings.TAVILY_USAGE_API_KEY`, `https://mcp.tavily.com/...?...tavilyApiKey=tvly-*`, and an HTTPS `*.tavily.com` Authorization bearer header. Assert precedence is explicit setting first. Reject non-Tavily hosts, HTTP URLs, wrong query names, and keys without the `tvly-` prefix. Assert the returned context exposes only a SHA-256 fingerprint, never the raw key.

```python
def test_resolve_context_rejects_proxy_bearer(monkeypatch):
    monkeypatch.setattr(settings, "TAVILY_USAGE_API_KEY", "")
    assert resolve_tavily_context(
        "proxy",
        {"url": "https://proxy.example/mcp", "headers": {"Authorization": "Bearer tvly-secret"}},
    ) is None

def test_resolve_context_prefers_explicit_key(monkeypatch):
    monkeypatch.setattr(settings, "TAVILY_USAGE_API_KEY", "tvly-explicit")
    context = resolve_tavily_context(
        "tavily",
        {"url": "https://mcp.tavily.com/mcp?tavilyApiKey=tvly-url"},
    )
    assert context is not None
    assert context.api_key.get_secret_value() == "tvly-explicit"
    assert "explicit" not in context.credential_fingerprint
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/infra/mcp/test_tavily_usage.py -q`

Expected: collection/import failure because `src.infra.mcp.tavily_usage` does not exist.

- [ ] **Step 3: Add minimal settings and credential resolver**

Add these backend-only settings with no frontend definitions:

```python
TAVILY_USAGE_API_KEY: str = ""
TAVILY_USAGE_PROJECT_ID: str = ""
TAVILY_USAGE_POLL_SECONDS: int = 600
TAVILY_USAGE_HTTP_TIMEOUT_SECONDS: float = 5.0
TAVILY_USAGE_WARNING_RATIO: float = 0.80
TAVILY_USAGE_CRITICAL_RATIO: float = 0.95
```

Add matching redacted entries to `.env.example`. Implement a frozen context using `pydantic.SecretStr`; parse URLs with `urllib.parse`, allow only the hosts and sources in the approved spec, and hash the key for Redis identifiers.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `uv run pytest tests/infra/mcp/test_tavily_usage.py -q`

Expected: all credential-resolution tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/infra/mcp/tavily_usage.py src/kernel/config/base.py .env.example tests/infra/mcp/test_tavily_usage.py
git commit -m "feat: resolve trusted Tavily usage credentials"
```

### Task 2: Parse independent Tavily quota buckets and severity

**Files:**
- Modify: `src/infra/mcp/tavily_usage.py`
- Modify: `tests/infra/mcp/test_tavily_usage.py`

- [ ] **Step 1: Write failing usage parsing tests**

Use the official response shape with `key`, `account.plan_*`, and `account.paygo_*`. Assert each positive limit creates its own bucket. Assert a hard key limit or PAYGO limit can exhaust the snapshot. Assert plan exhaustion remains critical, not exhausted, while positive PAYGO capacity exists. Assert an explicit plan-limit provider error always forces overall `exhausted`.

```python
def test_paygo_keeps_plan_limit_as_budget_alert():
    snapshot = build_usage_snapshot(
        _usage_payload(plan_usage=1000, plan_limit=1000, paygo_usage=10, paygo_limit=100),
        server_name="tavily",
    )
    assert snapshot.buckets["account_plan"].severity == "critical"
    assert snapshot.buckets["account_paygo"].severity == "ok"
    assert snapshot.severity == "critical"
```

- [ ] **Step 2: Run the parsing tests and verify RED**

Run: `uv run pytest tests/infra/mcp/test_tavily_usage.py -q`

Expected: failures for missing bucket models and `build_usage_snapshot`.

- [ ] **Step 3: Implement minimal immutable models and parser**

Implement `TavilyQuotaBucket` and `TavilyUsageSnapshot` dataclasses. Validate numeric values defensively, ignore absent/non-positive limits, clamp no ratios, and choose overall severity in this order: `exhausted > critical > warning > ok`. Include plan name, server name, UTC timestamp, and optional sanitized error only.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/infra/mcp/test_tavily_usage.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/infra/mcp/tavily_usage.py tests/infra/mcp/test_tavily_usage.py
git commit -m "feat: classify Tavily usage limits"
```

### Task 3: Add distributed polling, cache fallback, and alert deduplication

**Files:**
- Modify: `src/infra/mcp/tavily_usage.py`
- Modify: `tests/infra/mcp/test_tavily_usage.py`

- [ ] **Step 1: Write failing async monitor tests**

Provide fake Redis and `httpx.MockTransport` dependencies. Cover cached snapshot reuse, `SET NX EX` lock ownership, a single provider call across concurrent refreshes, `X-Project-ID`, a five-second configured timeout, Redis failure falling back to an in-process monotonic cache, and HTTP/JSON failures returning `None` without raising.

Add `caplog` tests showing warning/critical/exhausted logs contain ratios and server name but not `tvly-`; repeated same-severity snapshots are suppressed, while severity transitions log once.

- [ ] **Step 2: Run the monitor tests and verify RED**

Run: `uv run pytest tests/infra/mcp/test_tavily_usage.py -q`

- [ ] **Step 3: Implement `TavilyUsageMonitor.maybe_refresh`**

Use keys of the form `mcp:tavily-usage:<fingerprint>:{snapshot,lock,alert}`. Read cached JSON first, acquire the lock with `await redis.set(lock_key, token, nx=True, ex=30)`, call `GET https://api.tavily.com/usage`, then cache sanitized JSON for at least `TAVILY_USAGE_POLL_SECONDS`. Never cache or log the raw key. Release a lock only when its token still matches, using a small Lua compare/delete script. Maintain a bounded process-local dict keyed by fingerprint as fail-open fallback.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `uv run pytest tests/infra/mcp/test_tavily_usage.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/infra/mcp/tavily_usage.py tests/infra/mcp/test_tavily_usage.py
git commit -m "feat: monitor Tavily usage with distributed dedupe"
```

### Task 4: Integrate monitoring with Tavily MCP wrappers

**Files:**
- Modify: `src/infra/tool/mcp_client.py`
- Modify: `tests/infra/tool/test_mcp_client.py`

- [ ] **Step 1: Write failing wrapper integration tests**

Add tests that a successful `tavily_search` schedules/awaits one fail-open refresh, a Tavily plan-limit exception is not retried and forces refresh, and monitor failure does not replace a successful result or original MCP error. Assert non-Tavily tools receive no monitor. Add a manager test proving the server config context reaches only `tavily_*` wrappers.

```python
@pytest.mark.asyncio
async def test_plan_limit_is_not_retried_and_refreshes_usage():
    tool = _FailingTool("This request exceeds your plan's set usage limit")
    monitor = _RecordingMonitor()
    wrapper = MCPToolWithRetry(tool, max_retries=3, retry_delay=0, tavily_monitor=monitor)
    result = await wrapper._arun(query="x")
    assert tool.calls == 1
    assert monitor.forced == [True]
    assert "quota exhausted" in result.lower()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/infra/tool/test_mcp_client.py -q`

- [ ] **Step 3: Add minimal wrapper wiring**

Store resolved contexts per server while converting `mcpServers` to client connections. Add a private optional monitor attribute to `MCPToolWithRetry`. Introduce `_is_tavily_plan_limit_error` before retry classification; it must match the exact usage-limit family, never generic HTTP 429. Call `maybe_refresh(force=False)` after success and `force=True` after exhaustion, each inside a fail-open helper that catches and logs monitoring failures.

- [ ] **Step 4: Run focused MCP and Tavily tests**

Run: `uv run pytest tests/infra/tool/test_mcp_client.py tests/infra/mcp/test_tavily_usage.py -q`

Expected: all new tests and the existing streamable-HTTP/URL normalization regressions pass.

- [ ] **Step 5: Commit**

```bash
git add src/infra/tool/mcp_client.py tests/infra/tool/test_mcp_client.py
git commit -m "fix: monitor Tavily quota from MCP calls"
```

### Task 5: Verify issue #198 and capture live evidence

**Files:**
- Modify only if a regression is found: files from Tasks 1-4

- [ ] **Step 1: Run focused tests and Ruff**

```bash
uv run pytest tests/infra/mcp/test_tavily_usage.py tests/infra/tool/test_mcp_client.py tests/test_mcp_role_quota.py -q
uv run ruff check src/infra/mcp/tavily_usage.py src/infra/tool/mcp_client.py src/kernel/config/base.py tests/infra/mcp/test_tavily_usage.py tests/infra/tool/test_mcp_client.py
```

- [ ] **Step 2: Read the configured MCP servers without printing secrets**

Run a short `uv run python` probe that reports only whether a resolvable Tavily context exists and its server name. Abort live usage polling if no trusted credential can be resolved; report the precise configuration needed without exposing stored URLs/headers.

- [ ] **Step 3: Perform one sanitized live usage refresh**

Call the monitor once and print only plan name, bucket usage/limit/ratio, severity, and timestamp. Confirm no output contains `tvly-`.

- [ ] **Step 4: Recheck GitHub issue state**

Run: `gh issue view 198 --repo Yanyutin753/LambChat --json state,comments,updatedAt,url`

Do not close until #199 is also independently verified and the final combined regression run passes.

# Unified LLM Timeout Retry Design

## Problem

LambChat currently configures both provider SDKs and an agent middleware with the
same 120-second timeout. These deadlines race. When the application-side
`asyncio.wait_for` wins, the resulting `TimeoutError` is retried. When an SDK
first raises a transport-specific timeout such as `httpx.ReadTimeout`, the
current predicate may classify it as non-retryable and stop after one attempt.

Retry behavior is also split across the agent middleware and several direct
model invocation helpers. Those paths disagree about whether
`LLM_MAX_RETRIES=3` means three total attempts or three retries after the first
attempt. Provider SDK retries can additionally multiply application retries.

## Goals

- Retry every model timeout, regardless of which supported provider, transport,
  proxy, or application deadline produced it.
- Define `LLM_MAX_RETRIES=3` as one initial attempt plus three retries, for four
  total attempts.
- Apply the same timeout and retry contract to agent, subagent, grader, and
  direct model invocation paths.
- Avoid nested SDK and application retry multiplication.
- Make retries observable without logging prompts, URLs, credentials, response
  bodies, or exception text.
- Preserve immediate failure for permanent errors and cancellation.

## Non-goals

- Retrying authentication, authorization, malformed request, unsupported model,
  or not-found errors.
- Changing model selection, fallback selection, prompt content, streaming event
  ordering, or tool execution behavior.
- Adding a new general-purpose retry dependency.

## Chosen Architecture

### Canonical retry policy

A focused module under `src/infra/llm/` will own:

- recursive exception-chain inspection;
- timeout and transient-error classification;
- attempt-count semantics;
- per-attempt application deadlines;
- exponential backoff with the existing configured delay; and
- sanitized retry logging.

Exception inspection will traverse `__cause__`, `__context__`, and nested
exception groups without looping. It will recognize:

- built-in and asyncio timeout errors;
- all HTTPX timeout types, including connect, read, write, and pool timeouts;
- OpenAI and Anthropic timeout and transient connection/status wrappers;
- Google deadline and transport timeout wrappers when their optional packages
  are installed; and
- supported wrapper exceptions whose causal chain contains one of the above.

Existing explicitly transient proxy responses and 429/5xx behavior remain
retryable. Cancellation remains outside the retry contract.

### Agent middleware

The main agent, all subagents, and rubric grader will use a project-owned retry
middleware backed by the canonical policy. Each attempt will be bounded by
`LLM_REQUEST_TIMEOUT`. A fallback model remains outside the primary retry layer,
so it is selected only after the primary model exhausts its retries. The
fallback invocation receives the same per-attempt timeout and retry policy.

Empty or truncated response handling remains separate from exception retries so
the existing response-validation behavior is preserved.

### Direct model calls

All direct `ainvoke` call sites created through `LLMClient` will use the shared
retry runner or attach the shared middleware where the call builds an agent.
The inventory includes:

- session title generation;
- recommendation generation;
- main-agent context preparation;
- subagent result/activity processing;
- native memory summaries, consolidation, and backend model calls;
- automatic memory compaction agents; and
- image analysis.

Callers with a dedicated retry setting may override the retry count, but the
value consistently means retries after the initial attempt. Otherwise they use
`LLM_MAX_RETRIES`.

### Provider SDK configuration

Provider SDK `max_retries` values will be set to zero so application retries are
the sole attempt-count authority. Provider request timeouts remain configured as
a transport-level safety net. Because all transport timeout types are handled by
the canonical policy, either side may win the equal-deadline race without
changing retry behavior.

### Configuration and cache behavior

`LLM_REQUEST_TIMEOUT` will be exposed alongside the existing LLM retry settings
and documented in English and Chinese. A runtime change to this setting must
invalidate cached model clients because timeout is part of their construction
and cache key.

## Error and Logging Contract

For a retryable failure, logs contain only:

- a stable operation label;
- exception class name;
- failed attempt and total attempts;
- retry delay; and
- whether the failure was classified as a timeout.

Logs must not contain `str(exception)`, prompts, messages, provider URLs, model
credentials, response bodies, or signed file URLs. After retries are exhausted,
the original final exception is raised so existing fallback and user-facing
error handling continue to work.

## Testing Strategy

Development follows red-green-refactor.

1. Add a failing regression test showing raw HTTPX read/connect timeouts receive
   four attempts when `LLM_MAX_RETRIES=3`.
2. Cover write/pool timeouts, provider timeout wrappers, causal-chain wrapping,
   and optional Google timeout types.
3. Verify permanent errors make one attempt and `CancelledError` is propagated
   immediately.
4. Verify each attempt has its own deadline and the final exception is retained.
5. Verify retry logs are present and secret-safe.
6. Verify agent middleware ordering keeps retry inside fallback and applies to
   both primary and fallback models.
7. Replace duplicated direct-call loops and add focused behavioral tests for
   their retry-count semantics.
8. Verify provider clients use zero SDK retries and runtime timeout changes clear
   cached clients.
9. Run focused tests, the relevant backend test groups, Ruff, Mypy, and the full
   repository check when the environment permits it.

## Success Criteria

- Every supported model timeout path performs the initial call plus the
  configured number of retries.
- With defaults, a repeatedly timing-out call makes exactly four application
  attempts, never one and never a multiplicative SDK/application count.
- Fixed errors and cancellation are never retried.
- Primary retry exhaustion still triggers configured fallback behavior.
- Retry diagnostics are visible and contain no sensitive request or exception
  payloads.
- All changed-path tests, lint, and type checks pass; broader failures, if any,
  are independently isolated and reported.

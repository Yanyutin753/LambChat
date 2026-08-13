# Remove LambChat-Owned Prompt Caching Design

## Goal

Remove every LambChat-owned request mutation whose purpose is to increase LLM
prompt/KV cache hit rates. Let the installed DeepAgents release and model
providers own prompt caching, while preserving cache-usage telemetry and its
user-facing reporting.

## Current State

LambChat currently has two active prompt-cache policy layers:

1. `LLMClient` adds OpenAI cache routing, retention, and explicit breakpoint
   options when constructing `ChatOpenAI` models.
2. `PromptCachingMiddleware` rewrites system-message blocks, tool definitions,
   and selected conversation messages for OpenAI, Anthropic, and MiniMax. It is
   explicitly mounted in the main-agent and subagent stacks for Fast, Search,
   and Team agents.

The shared persona harness profile excludes DeepAgents'
`AnthropicPromptCachingMiddleware`, making the LambChat middleware the current
cache-policy owner. Deferred tools also carry a LambChat-only volatility marker
used by that middleware, and two settings control its breakpoint behavior.

DeepAgents 0.7.5 already appends its official provider prompt-caching tail. It
always installs the Anthropic middleware in safe no-op mode for unsupported
models, and conditionally installs official Bedrock and Fireworks middleware
when those integrations are present. OpenAI's provider performs automatic
exact-prefix prompt caching for supported models without LambChat rewriting the
request.

## Chosen Approach

Use the existing DeepAgents 0.7.5 defaults without upgrading dependencies.

- Stop excluding DeepAgents' official Anthropic cache middleware from the
  LambChat harness profile.
- Delete the LambChat `PromptCachingMiddleware` implementation and remove it
  from every main-agent and subagent middleware stack.
- Stop adding `prompt_cache_key`, `prompt_cache_retention`,
  `prompt_cache_options`, or prompt-cache breakpoints in `LLMClient`.
- Remove the LambChat-only deferred-tool volatility marker.
- Remove settings and live environment documentation that only configure the
  deleted middleware.
- Leave prompt construction and tool ordering to their functional owners. Do
  not add replacement cache-aware ordering or provider capability tables.

This approach deliberately does not copy DeepAgents middleware into LambChat,
add a second caching service, or upgrade DeepAgents to chase newer caching
features.

## Code and Configuration Scope

### Delete

- `src/infra/agent/middleware/prompt_caching.py`.
- The middleware package export and all imports/registrations in Fast, Search,
  and Team agent builders.
- OpenAI cache-policy helpers, model-family allowlists, and constructor kwargs
  used only for prompt caching.
- The `_lambchat_prompt_cache_volatile` tool extra and the logic that attaches
  it.
- `PROMPT_CACHE_MAX_SYSTEM_BLOCKS` and `PROMPT_CACHE_MAX_TOOLS` from backend
  settings, admin setting definitions, live environment docs, and frontend
  setting-description locales.
- Tests dedicated to the deleted implementation and stale assertions that
  require it to be last in LambChat middleware stacks.

### Preserve

- Cache creation/read token extraction in agent events.
- Usage persistence, aggregation, API schemas, frontend types, and cache-hit
  reporting.
- The `LLMClient` model-instance LRU cache and all non-LLM-prompt caches.
- Existing prompt, schema-compaction, tool-discovery, retry, timeout, and
  fallback behavior except where a test only encoded cache ownership/order.
- Historical design and plan documents as records of earlier decisions. Live
  documentation must not advertise removed settings or active LambChat-owned
  caching.

## Runtime Data Flow

1. LambChat constructs the selected LangChain chat model without prompt-cache
   kwargs.
2. Fast, Search, or Team passes that model plus LambChat business middleware to
   `create_deep_agent`.
3. DeepAgents resolves its normal harness profile and appends its official
   provider caching tail.
4. The provider applies its supported automatic or official middleware-driven
   caching behavior.
5. Returned usage metadata continues through LambChat's existing event and
   usage-storage paths unchanged.

LambChat no longer chooses cache breakpoints, cache keys, retention periods,
provider/model cache capabilities, or cache-sensitive tool order.

## Compatibility and Failure Behavior

- Anthropic models use DeepAgents' official middleware. Unsupported model types
  are ignored by that middleware instead of receiving speculative fields.
- OpenAI and compatible providers receive no LambChat-specific cache kwargs.
  Supported OpenAI models may still use provider-side automatic caching.
- MiniMax, Kimi, ZAI, Gemini, DeepSeek, and other compatible providers receive
  no LambChat-authored cache-control fields.
- Existing deployments that still set the two removed environment variables
  receive no cache behavior from them; the variables disappear from the admin
  settings catalog and live environment reference.
- No new runtime fallback is added. Provider or official middleware failures
  follow the existing DeepAgents/LangChain error path.

## Testing Strategy

Follow TDD for the ownership change:

1. Add or update a harness-profile test that fails while LambChat still excludes
   `AnthropicPromptCachingMiddleware`, then make it pass by removing the
   exclusion.
2. Add source/assembly assertions that fail while any Fast, Search, or Team
   stack still imports or mounts `PromptCachingMiddleware`, then remove all six
   registrations.
3. Replace the OpenAI cache-configuration tests with assertions that model
   construction emits none of the removed prompt-cache kwargs; verify the test
   fails before changing `LLMClient`.
4. Add configuration-surface assertions for removal of the two obsolete
   settings, then remove backend definitions, docs, and translations.
5. Run focused agent, middleware, LLM-client, settings, usage-metric, and
   documentation tests. Then run the relevant backend quality checks and the
   full backend test suite if feasible.

Tests validate policy ownership and serialized model configuration. They do not
claim a live provider cache hit without an authorized repeated-prefix API call.

## Success Criteria

- No production source imports, exports, instantiates, or references LambChat's
  `PromptCachingMiddleware` or its volatility marker.
- No LambChat model-construction path injects prompt-cache request options.
- The LambChat harness profile allows DeepAgents' default official prompt-cache
  middleware.
- Removed cache-tuning settings no longer appear in live backend/frontend/docs
  surfaces.
- Cache usage statistics remain available and their existing tests pass.
- Focused tests and repository searches provide evidence for the complete
  removal boundary.

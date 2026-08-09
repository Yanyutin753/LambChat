# Provider Prompt Cache Optimization Design

## Goal

Increase reusable prompt-prefix cache reads across LambChat's supported model
providers without deleting prompt contracts, preloading low-frequency tools, or
misreporting provider usage. Make cache performance diagnosable per model.

## Current Evidence

The configured usage store shows that `deepseek-v4-flash` already receives
substantial native cache reuse, while the single `MiniMax-M2.7` sample has no
recorded cache reuse. The current implementation also has four structural gaps:

1. LambChat's custom middleware skips MiniMax, but DeepAgents 0.7.5 subsequently
   applies its own Anthropic middleware to every `ChatAnthropic` instance. Cache
   ownership is therefore split and the final wire behavior is not controlled by
   the MiniMax-specific branch.
2. OpenAI-specific routing and retention fields are sent to every
   OpenAI-compatible provider.
3. volatile goal/auto/tool sections can appear before later stable sections,
   shortening the reusable prefix.
4. raw provider usage aliases and model-level cache aggregates are incomplete.

The existing prompt compression, complete names-only inventories, deferred tool
discovery, and semantic prompt budgets remain valid and must be preserved.

## Chosen Approach

Use one LambChat-owned provider-aware caching layer with deterministic prompt
construction and provider-neutral usage normalization. Exclude DeepAgents' tail
`AnthropicPromptCachingMiddleware` through the registered harness profile so it
cannot add an automatic message breakpoint and new system/tool breakpoints after
LambChat has already spent the provider's four-breakpoint budget. Keep the existing
LangChain clients; do not add a second cache service or manually persist provider
cache objects.

Two alternatives were rejected:

- More prompt deletion would reduce tokens but would not improve exact-prefix
  identity and risks removing required behavior.
- A provider cache object service would add lifecycle, billing, and invalidation
  complexity; it is unnecessary for the current conversational workload and does
  not cover every provider uniformly.

## Provider Policies

### OpenAI

- Send OpenAI cache parameters only when the configured provider is `openai`.
- For models before the GPT-5.6 family, retain the stable `prompt_cache_key`.
  Send `prompt_cache_retention="24h"` only for the documented extended-retention
  families (`gpt-5.5`, `gpt-5.4`, `gpt-5.2`, `gpt-5.1`, `gpt-5`, and `gpt-4.1`,
  including their documented variants); unknown older models use automatic
  in-memory caching without a speculative retention value.
- For GPT-5.6 and later families, use `prompt_cache_options.mode="explicit"`,
  keep the stable routing key, and mark the final stable system block with an
  explicit prompt cache breakpoint.
- Do not send OpenAI cache extensions to DeepSeek, Qwen, Moonshot, or other
  OpenAI-compatible providers.

### Anthropic and MiniMax

- Preserve the runtime provider slug on the model instance so direct Anthropic and
  MiniMax can use different wire policies even though both are `ChatAnthropic`.
- Direct Anthropic uses top-level automatic `cache_control` for the growing
  conversation plus explicit stable tool/system breakpoints. The automatic point
  consumes one of the four available write slots.
- MiniMax M2-series Anthropic-compatible requests use explicit block-level
  `cache_control`. The stable tool prefix, final stable system prefix, and latest
  eligible message receive breakpoints; this matches MiniMax's documented explicit
  interface without assuming that a proxy supports Anthropic's newer top-level
  automatic field.
- MiniMax M3 uses its documented passive cache with no request changes. Unknown
  future MiniMax families also default to passive/native caching until MiniMax
  documents explicit support, preventing M2-only fields from breaking a new model.
- Use at most four total automatic plus explicit breakpoints.
- Reserve a breakpoint at the end of the stable core-tool prefix. When dynamically
  discovered tools exist, use a second tool breakpoint for the deterministically
  sorted current session tail. Use the remaining explicit slot for the final stable
  system block; direct Anthropic uses its fourth slot for top-level automatic
  conversation caching, while MiniMax uses it on the latest eligible message.
- Replace, rather than layer on top of, DeepAgents' unconditional Anthropic cache
  middleware.

### DeepSeek

- Rely on DeepSeek's native automatic disk cache.
- Do not send OpenAI-specific cache fields.
- Improve hit rate through deterministic tools and stable-prefix ordering only.

### Gemini

- Keep Gemini 2.5+ implicit caching as the default path.
- Do not create explicit cached-content objects for ordinary conversations.
- Preserve stable large common content at the beginning so prompts can meet the
  provider's model-specific minimum token threshold.
- Read cache usage from LangChain's normalized `input_token_details.cache_read` and
  retain raw `cached_content_token_count` / `total_cached_tokens` fallbacks.

### Other compatible providers

- Default to provider-native implicit behavior and exact-prefix stability.
- Add explicit provider parameters only when the provider implementation and
  usage fields are documented and covered by tests.
- Selecting an Anthropic-compatible transport does not by itself grant Anthropic
  cache capabilities. Kimi, ZAI, and future compatible transports receive no
  speculative `cache_control` fields merely because LangChain represents them as
  `ChatAnthropic`.

## Prompt and Tool Ordering

System blocks will be assembled in this order:

1. base agent prompt and canonical policy;
2. persona, enabled Skills, and memory guide;
3. session-stable sandbox runtime and environment-variable name inventory;
4. active goal and auto-mode instructions;
5. memory index, deferred-tool state, and other turn-dynamic context;
6. conversation messages.

Active goal and auto mode will move into a dedicated volatile-section middleware
so they can be appended after stable session sections without creating duplicate
instances of `SectionPromptMiddleware`.

Tool definitions will be deterministic. Stable core tools stay first. Tools
discovered during the session are marked volatile, sorted deterministically, and
appended after the stable tools. Anthropic breakpoints are cumulative, so a stable
tool breakpoint must precede the volatile suffix.

No tool or Skill is removed. Deferred discovery and the existing names-only large
inventory behavior remain unchanged.

## Usage Normalization and Diagnostics

The event processor will inspect LangChain-standard usage first and then raw
response metadata only for still-missing values. It will normalize these aliases:

- cache read: `cache_read`, `cached_tokens`, `cache_read_input_tokens`,
  `prompt_cache_hit_tokens`, `cached_content_token_count`, and
  `total_cached_tokens`;
- cache creation: `cache_creation`, `cache_creation_input_tokens`, and
  `cache_write_tokens`.

Only the first available equivalent field is counted, preventing duplicate totals.
No prompts, tool arguments, API hosts, keys, user identifiers, or provider response
bodies will be logged.

Usage dashboard ranking rows will add input tokens, cache-read tokens,
cache-creation tokens, cache-read share, and zero-cache request count. The model
ranking card will display cache hit percentage and read tokens using existing i18n
copy. Other ranking cards retain their current presentation.

## Failure Handling

- Provider-specific parameters are selected before client construction; unknown
  compatible providers receive no speculative cache extensions.
- Prompts below a provider's minimum threshold remain valid requests and simply
  report zero cache reads.
- Missing or malformed usage detail fields normalize to zero without failing the
  stream.
- Cache-write cost and cache-read success remain separately visible; a write is not
  treated as a hit.
- Existing retry and fallback behavior remains unchanged.
- The configured `gpt-5.4` currently uses a non-OpenAI proxy. Official OpenAI
  documentation cannot establish whether that proxy forwards OpenAI cache fields;
  provider slug `openai` remains the explicit opt-in boundary, and verification must
  use a low-cost repeated-prefix request before rollout claims are made.

## Test Strategy

Follow red-green-refactor for each behavior:

1. model client tests prove OpenAI-only cache parameters, GPT-5.6 explicit mode,
   and no proprietary fields for DeepSeek/Qwen;
2. prompt middleware tests prove exactly one Anthropic cache owner, direct Anthropic
   automatic-plus-explicit budgeting, MiniMax M2 explicit behavior, MiniMax M3 and
   future-family passive behavior, stable tools before volatile tools,
   four-breakpoint budgeting, and OpenAI stable system breakpoints;
3. agent source/behavior tests prove goal and auto-mode sections follow stable
   sandbox/environment sections in Fast, Search, Team, and subagents;
4. event processor tests prove every raw usage alias is counted once;
5. storage tests prove model ranking cache aggregates and division-by-zero behavior;
6. frontend tests prove only model rankings display cache metrics;
7. focused backend tests, Ruff, frontend Vitest, and frontend build run before
   completion. Existing unrelated dirty frontend files remain untouched unless a
   listed usage-dashboard file is required.

## Files in Scope

- `src/infra/llm/client.py`
- `src/agents/core/persona.py`
- `src/infra/agent/middleware/prompt_caching.py`
- `src/infra/agent/middleware/prompt_injection.py`
- `src/infra/agent/middleware/tool_interception.py`
- `src/infra/agent/events/stream.py`
- `src/infra/usage/storage.py`
- `src/kernel/schemas/usage.py`
- `src/agents/{fast_agent,search_agent,team_agent}/nodes.py`
- corresponding backend tests
- `frontend/src/types/usage.ts`
- `frontend/src/components/panels/UsagePanel.tsx`
- `frontend/src/components/panels/UsagePanel/RankingCards.tsx`
- corresponding frontend tests

Locale files are not required because the needed cache labels already exist.

## Documentation Baseline

- OpenAI Prompt Caching: exact-prefix matching, GPT-5.6 explicit breakpoints,
  `prompt_cache_key`, write/read usage fields, and legacy retention policy.
- Anthropic Prompt Caching: `tools → system → messages`, four breakpoints,
  20-block lookback, 5-minute/1-hour TTLs, and automatic plus explicit caching.
- MiniMax Prompt Caching: passive caching for M3 and the documented M2-series
  explicit Anthropic-compatible `cache_control`, cumulative prefixes, four
  breakpoints, 20-block lookback, and cache creation/read usage fields.
- DeepSeek Context Caching: automatic disk cache, complete prefix-unit matching,
  best-effort retention, and `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`.
- Gemini Context Caching: implicit caching for Gemini 2.5+, model-specific minimum
  input sizes, common-prefix placement, and cached-token usage metadata.
- Installed `deepagents==0.7.5`, `langchain-anthropic==1.5.2`,
  `langchain-openai==1.4.1`, and `langchain-google-genai==4.3.1` source and payload
  serialization.

## Acceptance Criteria

- DeepAgents' built-in Anthropic cache middleware is excluded for LambChat's runtime
  providers, leaving exactly one cache owner.
- MiniMax M2-series Anthropic-compatible requests contain valid explicit cache
  breakpoints and no undocumented top-level automatic cache field; M3 and unknown
  future families use passive caching without M2-only fields.
- DeepSeek and other non-OpenAI compatible providers receive no OpenAI-only cache
  parameters.
- GPT-5.4 retains compatible legacy hints; GPT-5.6 uses explicit cache policy and a
  stable breakpoint.
- Stable system/tool prefixes precede volatile sections deterministically.
- Provider cache read/write fields are stored without double counting.
- The usage dashboard exposes a cache rate for each model.
- Prompt semantic/budget tests, focused backend tests, Ruff, frontend tests, and
  frontend build pass, or unrelated baseline failures are reproduced and reported.
- Current unrelated user changes are preserved.

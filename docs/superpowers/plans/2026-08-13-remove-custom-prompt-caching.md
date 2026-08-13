# Remove Custom Prompt Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove LambChat-owned prompt/KV cache optimization and restore the installed DeepAgents prompt-caching defaults without removing cache-usage telemetry.

**Architecture:** LambChat will construct provider models without prompt-cache hints and will pass only business middleware to `create_deep_agent`. DeepAgents 0.7.5 remains responsible for its provider-specific prompt-caching tail, while LambChat continues to normalize, persist, aggregate, and display returned cache usage.

**Tech Stack:** Python 3.12, DeepAgents 0.7.5, LangChain chat models and middleware, pytest, React i18n JSON, Vitest.

---

## File Map

- Delete `src/infra/agent/middleware/prompt_caching.py`: remove the LambChat-owned provider cache-policy implementation.
- Modify `src/infra/agent/middleware/__init__.py`: stop exporting the deleted middleware.
- Modify `src/agents/core/persona.py`: allow DeepAgents' official Anthropic cache middleware and remove the cache-routing compatibility import.
- Modify `src/agents/{fast_agent,search_agent,team_agent}/nodes.py`: remove all main-agent and subagent registrations plus cache-specific comments.
- Modify `src/infra/agent/middleware/tool_interception.py`: stop adding LambChat-only volatility metadata to deferred tools.
- Create `tests/infra/agent/test_prompt_cache_ownership.py`: encode the official-ownership and complete-removal contract.
- Replace `tests/infra/agent/test_prompt_caching_middleware.py` with `tests/infra/agent/test_tool_search_middleware.py`: preserve non-cache deferred-tool/prompt tests while deleting obsolete cache-policy tests.
- Modify neighboring agent/source tests that currently patch or order the deleted middleware.
- Modify `src/infra/llm/client.py`: remove OpenAI prompt-cache hints and cache-only provider metadata while preserving caller kwargs and caller metadata.
- Modify `tests/infra/llm/test_prompt_cache_config.py` and `tests/infra/llm/test_model_access.py`: assert delegation to official/provider behavior.
- Modify backend settings, live docs, and five frontend locale files to remove obsolete cache-tuning controls.
- Create backend and frontend removal tests for those configuration surfaces.
- Preserve `tests/infra/agent/test_token_usage_cache_metrics.py`, `src/infra/usage/storage.py`, usage schemas/types, and frontend cache-rate presentation unchanged.

### Task 1: Restore DeepAgents Cache Ownership and Remove LambChat Middleware

**Files:**
- Create: `tests/infra/agent/test_prompt_cache_ownership.py`
- Delete: `src/infra/agent/middleware/prompt_caching.py`
- Delete: `tests/infra/agent/test_prompt_caching_middleware.py`
- Create: `tests/infra/agent/test_tool_search_middleware.py`
- Modify: `src/infra/agent/middleware/__init__.py`
- Modify: `src/agents/core/persona.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `src/infra/agent/middleware/tool_interception.py`
- Modify: `tests/agents/core/test_persona_harness_profile.py`
- Modify: `tests/agents/core/test_subagent_prompts.py`
- Modify: `tests/agents/test_disabled_skills_config_propagation.py`
- Modify: `tests/agents/test_team_agent_sandbox_support.py`
- Modify: `tests/infra/tool/test_sandbox_mcp_removal_source.py`

- [ ] **Step 1: Write failing ownership tests**

Create `tests/infra/agent/test_prompt_cache_ownership.py` with tests equivalent to:

```python
from pathlib import Path

from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from src.agents.core import persona

ROOT = Path(__file__).resolve().parents[3]
AGENT_PATHS = (
    "src/agents/fast_agent/nodes.py",
    "src/agents/search_agent/nodes.py",
    "src/agents/team_agent/nodes.py",
    "src/infra/agent/middleware/__init__.py",
)


def test_harness_profile_keeps_deepagents_prompt_cache_middleware() -> None:
    profile = persona._build_harness_profile()
    assert AnthropicPromptCachingMiddleware not in profile.excluded_middleware


def test_lambchat_prompt_cache_middleware_is_removed() -> None:
    assert not (ROOT / "src/infra/agent/middleware/prompt_caching.py").exists()
    for relative_path in AGENT_PATHS:
        assert "PromptCachingMiddleware" not in (ROOT / relative_path).read_text()


def test_deferred_tools_have_no_lambchat_cache_metadata() -> None:
    source = (ROOT / "src/infra/agent/middleware/tool_interception.py").read_text()
    assert "_lambchat_prompt_cache_volatile" not in source
```

Update `tests/agents/core/test_persona_harness_profile.py` to express the same positive official-ownership contract instead of expecting the official middleware to be excluded.

Also change the existing
`test_tool_search_middleware_injects_discovered_tools_as_volatile` before any
production edit. Rename it to
`test_tool_search_middleware_preserves_discovered_tool_extras` and assert the
injected tool retains only its original `extras` (or `{}` when none were
provided) and does not gain `_lambchat_prompt_cache_volatile`.

- [ ] **Step 2: Run the ownership tests and verify RED**

Run:

```bash
uv run pytest \
  tests/infra/agent/test_prompt_cache_ownership.py \
  tests/infra/agent/test_prompt_caching_middleware.py::test_tool_search_middleware_preserves_discovered_tool_extras \
  tests/agents/core/test_persona_harness_profile.py -q
```

Expected: FAIL because the custom middleware file, six registrations, volatility marker, and DeepAgents exclusion still exist.

- [ ] **Step 3: Remove the production cache middleware and registrations**

- Delete `src/infra/agent/middleware/prompt_caching.py`.
- Remove its import and `__all__` entry from the middleware package.
- Remove `PromptCachingMiddleware` imports and both registrations from each of Fast, Search, and Team nodes.
- Rewrite cache-specific stack comments so they describe only functional middleware order.
- Remove the `langchain_anthropic.middleware` compatibility import and `excluded_middleware` construction from `persona.py`; construct the profile with only `base_system_prompt=_BEHAVIOR_GUIDE`.
- Remove `_PROMPT_CACHE_VOLATILE_TOOL_EXTRA` and clone-free cache metadata injection from `ToolSearchMiddleware`. Continue sorting discovered tools with `_tool_sort_key` and preserve their existing `extras` objects naturally.

- [ ] **Step 4: Preserve non-cache test coverage and remove stale test dependencies**

Move the deferred-manager, `ToolSearchMiddleware`, prompt injection, and prompt-budget tests currently beginning with `test_deferred_manager_returns_discovered_tools_in_sorted_order` into `tests/infra/agent/test_tool_search_middleware.py`, including the already-failing extras-preservation contract from Step 1. Delete the old cache-only test file.

Then:

- Remove `PromptCachingMiddleware` monkeypatches and last-item assertions from Fast, Search, and Team assembly tests while retaining assertions for the remaining middleware.
- Change `test_dynamic_prompt_middleware_order_is_canonical` to validate `EnvVarPromptMiddleware < MemoryIndexMiddleware < ToolSearchMiddleware` and assert the custom cache middleware name is absent.
- Remove the deleted file from the `mcporter` source-path tuple while retaining `tool_interception.py` and other runtime files.

- [ ] **Step 5: Run focused ownership and agent assembly tests and verify GREEN**

Run:

```bash
uv run pytest \
  tests/infra/agent/test_prompt_cache_ownership.py \
  tests/infra/agent/test_tool_search_middleware.py \
  tests/infra/tool/test_sandbox_mcp_removal_source.py \
  tests/agents/core/test_persona_harness_profile.py \
  tests/agents/core/test_subagent_prompts.py \
  tests/agents/test_disabled_skills_config_propagation.py \
  tests/agents/test_team_agent_sandbox_support.py -q
```

Expected: PASS with no imports or construction of the LambChat cache middleware.

- [ ] **Step 6: Commit the middleware ownership change**

```bash
git add src/agents src/infra/agent tests/agents tests/infra/agent tests/infra/tool/test_sandbox_mcp_removal_source.py
git commit -m "refactor(agent): use DeepAgents prompt caching"
```

### Task 2: Remove Model-Construction Cache Hints and Cache-Only Metadata

**Files:**
- Modify: `tests/infra/llm/test_prompt_cache_config.py`
- Modify: `tests/infra/llm/test_model_access.py`
- Modify: `src/infra/llm/client.py`

- [ ] **Step 1: Replace cache-hint expectations with delegation expectations**

Rewrite `tests/infra/llm/test_prompt_cache_config.py` around these behaviors:

```python
@pytest.mark.parametrize(
    ("provider", "model_name"),
    [
        ("openai", "gpt-5.4"),
        ("openai", "gpt-5.6"),
        ("openai", "o4-mini"),
        ("deepseek", "deepseek-chat"),
    ],
)
def test_model_construction_does_not_own_prompt_cache_policy(
    provider: str, model_name: str
) -> None:
    model = LLMClient._create_model(
        provider,
        model_name,
        temperature=0.7,
        api_key="sk-test",
    )
    assert "prompt_cache_key" not in model.model_kwargs
    assert "prompt_cache_retention" not in model.model_kwargs
    assert model.prompt_cache_options is None
    assert not model.metadata or "lambchat_provider" not in model.metadata


def test_model_construction_preserves_caller_metadata_without_cache_routing() -> None:
    model = LLMClient._create_model(
        "openai",
        "gpt-5.4",
        temperature=0.7,
        api_key="sk-test",
        metadata={"request_scope": "test"},
    )
    assert model.metadata == {"request_scope": "test"}
```

Update the fallback-path assertion in `tests/infra/llm/test_model_access.py` to require no generated `lambchat_provider` metadata while retaining timeout, retry, and cache-hint absence assertions.

- [ ] **Step 2: Run the model tests and verify RED**

Run:

```bash
uv run pytest tests/infra/llm/test_prompt_cache_config.py tests/infra/llm/test_model_access.py -q
```

Expected: FAIL for official OpenAI models and generated provider metadata.

- [ ] **Step 3: Remove only cache-policy code from `LLMClient`**

In `src/infra/llm/client.py`:

- Remove the `re` import and `_OPENAI_EXTENDED_CACHE_FAMILIES`.
- Remove `_prompt_cache_key`, `_is_gpt_56_or_later`, `_supports_openai_extended_cache`, and `_merge_runtime_metadata`.
- Remove the `_merge_runtime_metadata(kwargs, provider)` call.
- Remove the `provider == "openai"` block that injects `model_kwargs` and `prompt_cache_options`.
- Leave caller-provided `metadata`, `model_kwargs`, and all unrelated `kwargs` in the normal `ChatOpenAI(**openai_kwargs, **kwargs)` path.
- Do not alter the model-instance LRU `_make_cache_key`, timeouts, retries, profiles, thinking configuration, or provider protocol selection.

- [ ] **Step 4: Run the model tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/llm/test_prompt_cache_config.py tests/infra/llm/test_model_access.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the model-construction cleanup**

```bash
git add src/infra/llm/client.py tests/infra/llm/test_prompt_cache_config.py tests/infra/llm/test_model_access.py
git commit -m "refactor(llm): delegate prompt caching to official layers"
```

### Task 3: Remove Obsolete Cache-Tuning Settings and Live Documentation

**Files:**
- Create: `tests/kernel/config/test_prompt_cache_settings_removed.py`
- Create: `frontend/src/i18n/__tests__/promptCacheSettingsRemoval.test.ts`
- Modify: `src/kernel/config/base.py`
- Modify: `src/kernel/config/_definitions_core.py`
- Modify: `docs/en/env/llm.md`
- Modify: `docs/zh/env/llm.md`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`

- [ ] **Step 1: Write failing configuration-surface tests**

Create the backend test:

```python
from pathlib import Path

from src.kernel.config import settings
from src.kernel.config.definitions import SETTING_DEFINITIONS

REMOVED = ("PROMPT_CACHE_MAX_SYSTEM_BLOCKS", "PROMPT_CACHE_MAX_TOOLS")


def test_lambchat_prompt_cache_settings_are_removed() -> None:
    for name in REMOVED:
        assert not hasattr(settings, name)
        assert name not in SETTING_DEFINITIONS
        assert name not in Path("docs/en/env/llm.md").read_text()
        assert name not in Path("docs/zh/env/llm.md").read_text()
```

Create a Vitest source test that loads all five locale JSON files and asserts neither key exists under `settingDesc`.

- [ ] **Step 2: Run both tests and verify RED**

Run:

```bash
uv run pytest tests/kernel/config/test_prompt_cache_settings_removed.py -q
cd frontend && pnpm test src/i18n/__tests__/promptCacheSettingsRemoval.test.ts
```

Expected: both commands FAIL because the settings and translations still exist.

- [ ] **Step 3: Remove the obsolete live settings**

- Remove both fields from `Settings` in `src/kernel/config/base.py`.
- Remove both entries from `SETTING_DEFINITIONS` in `_definitions_core.py`.
- Remove the two rows from the English and Chinese live environment references without removing `LLM_MODEL_CACHE_SIZE` or DeepAgents summarization controls. Rename the now-inaccurate `Prompt Cache Settings` / `提示缓存设置` section to `DeepAgent Context Settings` / `DeepAgent 上下文设置`, because its remaining setting controls context size rather than prompt caching.
- Remove both `settingDesc` keys from all five locale files, preserving valid JSON and locale key parity.

- [ ] **Step 4: Run configuration and locale tests and verify GREEN**

Run:

```bash
uv run pytest tests/kernel/config/test_prompt_cache_settings_removed.py tests/kernel/config/test_llm_retry_settings.py -q
cd frontend && pnpm test \
  src/i18n/__tests__/promptCacheSettingsRemoval.test.ts \
  src/i18n/__tests__/localeKeyCompleteness.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the settings cleanup**

```bash
git add src/kernel/config docs/en/env/llm.md docs/zh/env/llm.md frontend/src/i18n tests/kernel/config
git commit -m "refactor(config): remove custom prompt cache controls"
```

### Task 4: Verify the Removal Boundary and Preserved Telemetry

**Files:**
- No production changes expected.
- Modify only directly related files if fresh verification exposes a missed reference or regression; add a failing regression test before each fix.

- [ ] **Step 1: Run negative source searches**

Run:

```bash
rg -n \
  "\\bPromptCachingMiddleware\\b|src\\.infra\\.agent\\.middleware\\.prompt_caching|_lambchat_prompt_cache_volatile|lambchat_provider|_prompt_cache_key|_is_gpt_56_or_later|_supports_openai_extended_cache|_OPENAI_EXTENDED_CACHE_FAMILIES|PROMPT_CACHE_MAX_(SYSTEM_BLOCKS|TOOLS)" \
  src tests docs/en docs/zh frontend/src \
  --glob '!tests/infra/agent/test_prompt_cache_ownership.py' \
  --glob '!tests/agents/core/test_persona_harness_profile.py' \
  --glob '!tests/infra/llm/test_prompt_cache_config.py' \
  --glob '!tests/infra/llm/test_model_access.py' \
  --glob '!tests/kernel/config/test_prompt_cache_settings_removed.py' \
  --glob '!frontend/src/i18n/__tests__/promptCacheSettingsRemoval.test.ts'
```

Expected: no matches. Historical files under `docs/superpowers/` are intentionally outside the search.

- [ ] **Step 2: Verify cache telemetry remains intact**

Run:

```bash
uv run pytest \
  tests/infra/agent/test_token_usage_cache_metrics.py \
  tests/infra/agent/test_events_processor.py \
  tests/infra/usage/test_usage_storage.py -q
cd frontend && pnpm test src/components/chat/ChatMessage/__tests__/tokenCacheRateSource.test.ts
```

Expected: PASS; cache creation/read normalization, persistence, aggregation, and user-facing cache-rate rendering remain covered.

Run focused preservation checks for unrelated caches as well:

```bash
uv run pytest \
  tests/infra/tool/test_env_var_tool.py \
  tests/infra/tool/test_cache_pubsub.py \
  tests/infra/envvar/test_sync.py -q
cd frontend && pnpm test src/__tests__/pwaNginxCache.test.ts
```

Expected: PASS; environment-prompt memoization/invalidation and static/PWA cache
contracts remain intact.

- [ ] **Step 3: Run focused lint and type checks**

Run:

```bash
uv run ruff check \
  src/agents/core/persona.py \
  src/agents/fast_agent/nodes.py \
  src/agents/search_agent/nodes.py \
  src/agents/team_agent/nodes.py \
  src/infra/agent/middleware \
  src/infra/llm/client.py \
  src/kernel/config \
  tests/agents \
  tests/infra/agent \
  tests/infra/llm \
  tests/kernel/config
make typecheck
cd frontend && pnpm run lint
```

Expected: all commands exit 0.

- [ ] **Step 4: Run the repository-level cross-stack gate**

Run:

```bash
make check-all
```

Expected: exit 0. If an unrelated or environment-dependent failure occurs, isolate it with the narrowest relevant command and report it separately rather than weakening this change's tests.

- [ ] **Step 5: Review the final diff and commits**

Run:

```bash
git status --short
git diff HEAD~3 --check
git diff HEAD~3 --stat
git log -5 --oneline
```

Confirm that no usage telemetry file was changed, no dependency was upgraded, and no unrelated user changes were included.

### Task 5: Remove Cache-Oriented Prompt Segmentation Found by Final Review

**Files:**
- Modify: `tests/infra/agent/test_prompt_cache_ownership.py`
- Modify: `tests/infra/agent/test_tool_search_middleware.py`
- Modify: `tests/agents/core/test_subagent_prompts.py`
- Modify: `src/infra/agent/middleware/prompt_injection.py`
- Modify: `src/infra/agent/middleware/__init__.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `src/agents/fast_agent/prompt.py`
- Modify: `src/agents/search_agent/prompt.py`

Final code review found that the original removal inventory was incomplete:
`VolatileSectionPromptMiddleware` was introduced specifically to move changing
goal/mode content behind a stable prefix, while `SectionPromptMiddleware`
creates one content block per section explicitly for fine-grained KV cache
breakpoints. Preserve every prompt's text but remove this cache-oriented request
shape and ordering.

- [ ] **Step 1: Write failing semantic ownership tests**

Extend `test_prompt_cache_ownership.py` so production sources contain neither
`VolatileSectionPromptMiddleware` nor cache-specific prompt-shaping language
such as `KV cache`, `cache breakpoint`, `stable → semi-stable → dynamic`, or
`session-static`.

Before production edits:

- Change the `SectionPromptMiddleware` behavior test to require all supplied
  sections to be normalized and joined with `"\n\n"` into one appended system
  text block, preserving their order and content.
- Replace the volatile-order source test with assertions that Fast, Search, and
  Team add active-goal/auto-mode content to their ordinary `_prompt_sections`
  and never import or instantiate `VolatileSectionPromptMiddleware`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest \
  tests/infra/agent/test_prompt_cache_ownership.py \
  tests/infra/agent/test_tool_search_middleware.py \
  tests/agents/core/test_subagent_prompts.py -q
```

Expected: FAIL because the volatile class/registrations and multi-block section
behavior still exist.

- [ ] **Step 3: Remove cache-oriented prompt shaping while preserving content**

- Make `SectionPromptMiddleware` normalize its non-empty sections, join them
  with a blank line, and append the result as one ordinary system text block.
- Delete `VolatileSectionPromptMiddleware` and its package import/export.
- In all three main-agent builders, calculate active goal and auto-mode before
  installing `SectionPromptMiddleware`, add those strings to the existing
  `_prompt_sections`, and install one ordinary section middleware when any
  content exists.
- Remove the three volatile imports/registrations and cache-order comments.
- Rewrite prompt-module/node comments that claim independent blocks or stable
  bases optimize KV caching; retain accurate functional descriptions.
- Do not remove persona, workflow, skill, memory-guide, sandbox-runtime, active
  goal, or auto-mode content. Do not alter dynamic environment, native-memory
  index, or deferred-tool functionality.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the exact Step 2 command, then:

```bash
uv run ruff check \
  src/infra/agent/middleware/prompt_injection.py \
  src/infra/agent/middleware/__init__.py \
  src/agents/fast_agent \
  src/agents/search_agent \
  src/agents/team_agent \
  tests/infra/agent/test_prompt_cache_ownership.py \
  tests/infra/agent/test_tool_search_middleware.py \
  tests/agents/core/test_subagent_prompts.py
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Commit and repeat the final verification/review gates**

```bash
git add \
  src/infra/agent/middleware/prompt_injection.py \
  src/infra/agent/middleware/__init__.py \
  src/agents/fast_agent \
  src/agents/search_agent \
  src/agents/team_agent \
  tests/infra/agent/test_prompt_cache_ownership.py \
  tests/infra/agent/test_tool_search_middleware.py \
  tests/agents/core/test_subagent_prompts.py
git commit -m "refactor(agent): remove cache-oriented prompt shaping"
```

Repeat Task 4's negative searches, telemetry/cache-preservation tests, static
checks, and full repository gate. The semantic negative search must now cover
the deleted volatile class and cache-specific prompt-shaping language.

### Task 6: Remove Dynamic Prompt Splitting and Cache-Derived Tool Ordering

**Files:**
- Modify: `tests/infra/agent/test_prompt_cache_ownership.py`
- Modify: `tests/infra/agent/test_tool_search_middleware.py`
- Modify: `tests/infra/tool/test_env_var_tool.py`
- Modify: `src/infra/tool/env_var_prompt.py`
- Modify: `src/infra/tool/deferred_manager.py`
- Modify: `src/infra/agent/middleware/prompt_injection.py`
- Modify: `src/infra/agent/middleware/tool_interception.py`
- Modify: `src/infra/agent/middleware/_helpers.py`

Final whole-feature review found two older request-shaping paths that predate
the deleted provider middleware. Environment and deferred-tool prompts still
split stable guidance from changing inventories, and tool search still keeps a
separate `search_tools` prefix before a re-sorted discovered tail. Preserve the
data/query caches and all text, but remove these LLM request-shape policies.

- [ ] **Step 1: Write failing behavior and semantic tests**

- Change the environment prompt tests to require one complete cached string,
  and require `EnvVarPromptMiddleware` to append exactly one block containing
  both guidance and key names.
- Change deferred prompt tests to use one complete dirty-cached prompt string;
  delete assertions about stable/dynamic block splitting while retaining name,
  description, discovery invalidation, sorting, duplicate-guide, and compact
  content contracts.
- Add a ToolSearchMiddleware request test where manager-returned discovered
  tools have a known order. Require the middleware to preserve that order and
  append `search_tools` as an ordinary auxiliary tool rather than constructing
  a cache-oriented prefix/tail or sorting the discovered tools again.
- Extend semantic ownership tests to reject production uses of
  `_append_system_text_blocks`, `build_env_var_prompt_sections`,
  `get_deferred_prompt_blocks`, prompt `tail` wording, and middleware-owned
  `_tool_sort_key`.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
uv run pytest \
  tests/infra/agent/test_prompt_cache_ownership.py \
  tests/infra/agent/test_tool_search_middleware.py \
  tests/infra/tool/test_env_var_tool.py -q
```

Expected: FAIL on the current two-block APIs, multi-block middleware output,
and cache-derived tool placement/order.

- [ ] **Step 3: Collapse prompt APIs without removing data caches**

- In `env_var_prompt.py`, cache one complete prompt string per user instead of
  a tuple of sections. Keep `_CACHE_TTL`, maximum-entry eviction, storage error
  handling, secret-safe content, `force_refresh`, and invalidation unchanged.
- Make `EnvVarPromptMiddleware` call `build_env_var_prompt` and append the full
  prompt via `_append_system_text_block` once.
- In `DeferredToolManager`, replace the cached prompt-block tuple with one
  cached prompt string assembled from the same guide, MCP names, and system
  descriptions. Keep stub sorting, dirty flags, parent/fork synchronization,
  and discovery invalidation unchanged.
- Make `ToolSearchMiddleware` consume `get_deferred_stubs_string`, remove the
  guide prefix from that complete string only when it already exists, and
  append the remaining full prompt once.

- [ ] **Step 4: Restore functional tool ordering**

- Use `DeferredToolManager.get_discovered_tools()` as the sole ordering source
  for discovered tools.
- Append only missing discovered tools in that order, and append the missing
  `search_tools` helper as an ordinary auxiliary tool. Do not establish a
  dedicated stable prefix or re-sort discovered tools in the middleware.
- Remove the now-unused middleware `_tool_sort_key` helper/import. Keep the
  manager's internal sort helper because it provides deterministic functional
  inventory/discovery behavior.

- [ ] **Step 5: Verify GREEN and commit**

Run the exact Step 2 command, the environment cache invalidation tests, Ruff on
the changed sources/tests, semantic negative searches, and `git diff --check`.
Then commit only these files:

```bash
git commit -m "refactor(agent): remove cache-derived prompt and tool shaping"
```

Repeat Task 4 verification and whole-feature review. A completion claim requires
the final reviewer to find no remaining active LambChat-owned request mutation
whose purpose is increasing LLM prompt/KV cache hits.

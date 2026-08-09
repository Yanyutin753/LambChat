# Provider Prompt Cache Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve and expose per-model prompt-cache reuse for every LambChat provider without changing prompt semantics, eager-loading deferred tools, or sending one provider's private cache fields to another.

**Architecture:** `LLMClient` selects only documented provider wire options and records the configured provider slug as runtime metadata. A single LambChat-owned `PromptCachingMiddleware` then lays out deterministic system/tool/message breakpoints for OpenAI, Anthropic, and MiniMax while DeepSeek, Gemini, and other compatible providers use their native implicit caches over the same stable prefix. Provider usage is normalized once, aggregated per model, and shown only on the model ranking card.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, LangChain 1.5, DeepAgents 0.7.5, `langchain-openai` 1.4.1, `langchain-anthropic` 1.5.2, `langchain-google-genai` 4.3.1, MongoDB aggregation, pytest, React 19, TypeScript, Vitest, Tailwind CSS.

## Global Constraints

- Follow strict red-green-refactor: every production change begins with a focused failing test and the failure must be observed.
- Keep installed LangChain and DeepAgents versions; add no cache service and no new dependency.
- Preserve all canonical prompt policy, persona, Skills, memory-guide, complete names-only inventories, deferred discovery, retry, fallback, and visible behavior.
- Keep at most four Anthropic/MiniMax cache breakpoints, counting Anthropic's top-level automatic breakpoint.
- Send OpenAI cache extensions only when the configured provider slug is exactly `openai`.
- Treat `provider="openai"` as the explicit opt-in boundary even when its configured endpoint is a proxy; do not claim proxy cache support without a separately authorized repeated-prefix request.
- Do not log prompts, tool arguments, API hosts, keys, user identifiers, signed URLs, base64 data, or raw provider response bodies.
- Do not modify locale files: `usage.cacheHitRate`, `usage.cacheRead`, and `usage.cacheWrite` already exist.
- Preserve all unrelated dirty frontend work and stage only files listed by the current task.
- Use `uv` for Python and `pnpm` for frontend commands.

## File Structure

- `src/infra/llm/client.py`: provider capability selection, OpenAI family detection, stable routing keys, and runtime provider metadata.
- `src/agents/core/persona.py`: DeepAgents harness registration and exclusion of its unconditional Anthropic caching middleware.
- `src/infra/agent/middleware/prompt_caching.py`: sole cache-breakpoint owner and provider-specific request policy.
- `src/infra/agent/middleware/prompt_injection.py`: dedicated volatile-section injector used after stable session sections.
- `src/infra/agent/middleware/tool_interception.py`: deterministic stable/volatile tool construction and volatile marking.
- `src/agents/{fast_agent,search_agent,team_agent}/nodes.py`: consistent stable-before-volatile middleware ordering for main agents and subagents.
- `src/infra/agent/events/stream.py`: provider-neutral cache usage normalization.
- `src/infra/usage/storage.py` and `src/kernel/schemas/usage.py`: model-level cache aggregation and API schema.
- `frontend/src/types/usage.ts`, `frontend/src/components/panels/UsagePanel.tsx`, and `frontend/src/components/panels/UsagePanel/RankingCards.tsx`: typed model cache diagnostics.
- Existing focused test modules remain the primary test homes; one small persona profile test module is added because registration behavior has no isolated test today.

## Provider Policy Matrix

| Configured provider | Client-level options | LambChat block policy | Usage aliases covered |
|---|---|---|---|
| `openai`, GPT-5.6+ | stable key + dedicated explicit mode | final stable system `prompt_cache_breakpoint` | `cached_tokens`, `cache_write_tokens` |
| `openai`, documented older families | stable key + documented 24h retention | none | `cached_tokens` |
| `openai`, other older families | stable key only | none | normalized OpenAI fields when present |
| `anthropic` | runtime identity only | automatic conversation + stable system/core-tool/dynamic-tool breakpoints | cache creation/read fields |
| `minimax` | runtime identity only | explicit stable system/core-tool/dynamic-tool/latest-message breakpoints | cache creation/read fields |
| `deepseek` | no OpenAI private fields | implicit cache over deterministic prefix | `prompt_cache_hit_tokens` |
| `google` / `gemini` | no manual cached-content object | implicit cache over deterministic prefix | `cache_read`, `cached_content_token_count`, `total_cached_tokens` |
| every other compatible provider | no speculative cache extension | deterministic prefix only | standard fields plus documented aliases already normalized |

---

### Task 1: Provider Capability Selection and Runtime Identity

**Files:**
- Modify: `tests/infra/llm/test_prompt_cache_config.py`
- Modify: `tests/infra/llm/test_model_access.py`
- Modify: `src/infra/llm/client.py`

**Interfaces:**
- Consumes: configured `provider: str`, `model_name: str`, and optional caller `metadata`/`model_kwargs` passed to `LLMClient._create_model`.
- Produces: `_is_gpt_56_or_later(model_name: str) -> bool`, `_supports_openai_extended_cache(model_name: str) -> bool`, and model metadata key `lambchat_provider: str` consumed by Task 3.

- [ ] **Step 1: Replace the broad compatible-provider expectations with failing capability tests**

```python
def test_openai_gpt_54_uses_legacy_cache_hints_and_provider_metadata() -> None:
    model = LLMClient._create_model("openai", "gpt-5.4", temperature=0.7, api_key="sk-test")
    assert model.model_kwargs == {
        "prompt_cache_key": "lambchat:openai:gpt-5.4",
        "prompt_cache_retention": "24h",
    }
    assert model.metadata["lambchat_provider"] == "openai"


def test_openai_gpt_56_uses_explicit_cache_mode() -> None:
    model = LLMClient._create_model("openai", "gpt-5.6", temperature=0.7, api_key="sk-test")
    assert model.model_kwargs["prompt_cache_key"] == "lambchat:openai:gpt-5.6"
    assert model.prompt_cache_options == {"mode": "explicit"}
    assert "prompt_cache_retention" not in model.model_kwargs


@pytest.mark.parametrize("provider,model_name", [
    ("deepseek", "deepseek-chat"),
    ("qwen", "qwen-max"),
    ("moonshot", "moonshot-v1"),
])
def test_openai_compatible_providers_do_not_receive_openai_cache_extensions(
    provider: str, model_name: str
) -> None:
    model = LLMClient._create_model(provider, model_name, temperature=0.7, api_key="sk-test")
    assert "prompt_cache_key" not in model.model_kwargs
    assert "prompt_cache_retention" not in model.model_kwargs
    assert model.prompt_cache_options is None
    assert model.metadata["lambchat_provider"] == provider


def test_unknown_openai_model_uses_key_without_speculative_retention() -> None:
    model = LLMClient._create_model("openai", "o4-mini", temperature=0.7, api_key="sk-test")
    assert model.model_kwargs["prompt_cache_key"] == "lambchat:openai:o4-mini"
    assert "prompt_cache_retention" not in model.model_kwargs
```

Add `import pytest` to the test module. In `test_model_access.py`, change the fallback-model capture assertion to prove that a DeepSeek model has `captured["metadata"]["lambchat_provider"] == "deepseek"` and no `model_kwargs` cache extensions.

- [ ] **Step 2: Run the focused tests and observe the old cross-provider behavior fail**

Run: `uv run pytest tests/infra/llm/test_prompt_cache_config.py tests/infra/llm/test_model_access.py -q`

Expected: FAIL because DeepSeek/Qwen still receive `prompt_cache_key` and `prompt_cache_retention`, GPT-5.6 has no explicit options, and runtime provider metadata is absent.

- [ ] **Step 3: Implement explicit OpenAI family policies and metadata merging**

Add family helpers near `_prompt_cache_key`:

```python
import re

_OPENAI_EXTENDED_CACHE_FAMILIES = (
    "gpt-5.5", "gpt-5.4", "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4.1"
)


def _is_gpt_56_or_later(model_name: str) -> bool:
    match = re.match(r"^(?:chatgpt-)?gpt-(\d+)(?:\.(\d+))?", model_name.lower())
    if match is None:
        return False
    return (int(match.group(1)), int(match.group(2) or 0)) >= (5, 6)


def _supports_openai_extended_cache(model_name: str) -> bool:
    name = model_name.lower()
    return any(name == family or name.startswith(f"{family}-") for family in _OPENAI_EXTENDED_CACHE_FAMILIES)


def _merge_runtime_metadata(kwargs: dict[str, Any], provider: str) -> None:
    metadata = dict(kwargs.pop("metadata", {}) or {})
    metadata["lambchat_provider"] = provider
    kwargs["metadata"] = metadata
```

Call `_merge_runtime_metadata(kwargs, provider)` before protocol branches. Replace the current `if protocol == "openai"` cache block with:

```python
if provider == "openai":
    model_kwargs = dict(openai_kwargs.get("model_kwargs") or kwargs.pop("model_kwargs", {}))
    model_kwargs.setdefault("prompt_cache_key", _prompt_cache_key(provider, model_name))
    if _is_gpt_56_or_later(model_name):
        openai_kwargs.setdefault("prompt_cache_options", {"mode": "explicit"})
    elif _supports_openai_extended_cache(model_name):
        model_kwargs.setdefault("prompt_cache_retention", "24h")
    openai_kwargs["model_kwargs"] = model_kwargs
```

For non-OpenAI providers, preserve caller-supplied `model_kwargs` without adding fields. Keep `prompt_cache_options` as a dedicated `ChatOpenAI` constructor field, not inside `model_kwargs`.

- [ ] **Step 4: Run focused model tests**

Run: `uv run pytest tests/infra/llm/test_prompt_cache_config.py tests/infra/llm/test_model_access.py -q`

Expected: PASS with OpenAI-only extensions, explicit GPT-5.6 mode, legacy GPT-5.4 retention, and provider metadata on all model classes.

- [ ] **Step 5: Commit the provider policy boundary**

```bash
git add src/infra/llm/client.py tests/infra/llm/test_prompt_cache_config.py tests/infra/llm/test_model_access.py
git commit -m "fix(llm): scope prompt cache options by provider"
```

### Task 2: One Anthropic Cache Owner

**Files:**
- Create: `tests/agents/core/test_persona_harness_profile.py`
- Modify: `src/agents/core/persona.py`

**Interfaces:**
- Consumes: DeepAgents `HarnessProfile.excluded_middleware` and `langchain_anthropic.middleware.AnthropicPromptCachingMiddleware`.
- Produces: `_build_harness_profile() -> HarnessProfile` with the current behavior guide and the built-in caching middleware excluded for `anthropic`, `openai`, and `google_genai` runtime profiles.

- [ ] **Step 1: Write a failing isolated harness-profile test**

```python
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from src.agents.core import persona


def test_harness_profile_excludes_deepagents_anthropic_cache_owner() -> None:
    profile = persona._build_harness_profile()
    assert profile.base_system_prompt == persona._BEHAVIOR_GUIDE
    assert AnthropicPromptCachingMiddleware in profile.excluded_middleware
```

- [ ] **Step 2: Run the test and verify the helper is missing**

Run: `uv run pytest tests/agents/core/test_persona_harness_profile.py -q`

Expected: FAIL with `AttributeError: module ... has no attribute '_build_harness_profile'`.

- [ ] **Step 3: Build and register the exclusion profile**

```python
try:
    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
except ImportError:  # pragma: no cover - optional compatibility
    AnthropicPromptCachingMiddleware = None  # type: ignore[assignment,misc]


def _build_harness_profile() -> Any:
    excluded = (
        frozenset({AnthropicPromptCachingMiddleware})
        if AnthropicPromptCachingMiddleware is not None
        else frozenset()
    )
    return _HarnessProfile(
        base_system_prompt=_BEHAVIOR_GUIDE,
        excluded_middleware=excluded,
    )
```

Replace `_HarnessProfile(base_system_prompt=_BEHAVIOR_GUIDE)` in the import-time registration block with `_build_harness_profile()`. Keep the existing three runtime profile keys because all `LLMClient` concrete classes resolve through them.

- [ ] **Step 4: Run profile and agent construction regressions**

Run: `uv run pytest tests/agents/core/test_persona_harness_profile.py tests/agents/test_team_agent_sandbox_support.py tests/agents/test_disabled_skills_config_propagation.py -q`

Expected: PASS and existing harness shims continue accepting `excluded_middleware`.

- [ ] **Step 5: Commit the single-owner rule**

```bash
git add src/agents/core/persona.py tests/agents/core/test_persona_harness_profile.py
git commit -m "fix(agent): keep one prompt cache middleware owner"
```

### Task 3: Provider-Aware Breakpoints and Stable Tool Prefixes

**Files:**
- Modify: `tests/infra/agent/test_prompt_caching_middleware.py`
- Modify: `src/infra/agent/middleware/prompt_caching.py`
- Modify: `src/infra/agent/middleware/tool_interception.py`

**Interfaces:**
- Consumes: model metadata `lambchat_provider` from Task 1 and volatile tool extra `_lambchat_prompt_cache_volatile`.
- Produces: `_runtime_provider(model: Any) -> str | None`, deterministic `stable_tools + volatile_tools`, Anthropic automatic-plus-explicit policy, MiniMax explicit-only policy, and GPT-5.6 stable system breakpoint.

- [ ] **Step 1: Replace outdated tool-order and MiniMax-skip assertions with failing provider-policy tests**

Use a helper whose fake model exposes `metadata={"lambchat_provider": provider}` through a LangChain-style wrapper, then add these behaviors:

```python
def test_retag_tools_keeps_stable_prefix_before_sorted_volatile_tail() -> None:
    tools = [
        _FakeTool(name="write_file", description="stable"),
        _FakeTool(name="zeta:list", description="dynamic", extras={"_lambchat_prompt_cache_volatile": True}),
        _FakeTool(name="read_file", description="stable"),
        _FakeTool(name="alpha:get", description="dynamic", extras={"_lambchat_prompt_cache_volatile": True}),
    ]
    retagged = PromptCachingMiddleware._retag_tools(tools, {"type": "ephemeral"})
    assert [tool.name for tool in retagged] == ["write_file", "read_file", "alpha:get", "zeta:list"]
    assert retagged[1].extras["cache_control"] == {"type": "ephemeral"}
    assert retagged[3].extras["cache_control"] == {"type": "ephemeral"}


async def test_direct_anthropic_uses_automatic_and_three_explicit_breakpoints() -> None:
    result = await _run_cache_middleware(provider="anthropic", with_volatile_tool=True)
    assert result.model_settings["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert _explicit_breakpoint_count(result) == 3


async def test_minimax_uses_four_explicit_breakpoints_without_top_level_automatic() -> None:
    result = await _run_cache_middleware(provider="minimax", with_volatile_tool=True, with_message=True)
    assert "cache_control" not in result.model_settings
    assert _explicit_breakpoint_count(result) == 4
    assert _latest_message_has_cache_control(result.messages)


async def test_gpt_56_marks_only_final_stable_system_block() -> None:
    result = await _run_cache_middleware(provider="openai", model_name="gpt-5.6")
    assert _system_breakpoint_indices(result.system_message, key="prompt_cache_breakpoint") == [3]


async def test_implicit_cache_providers_receive_no_explicit_breakpoints() -> None:
    for provider in ("deepseek", "google", "qwen"):
        result = await _run_cache_middleware(provider=provider)
        assert _explicit_breakpoint_count(result) == 0
        assert result.model_settings == {}
```

Change `test_tool_search_middleware_injects_discovered_tools_as_cacheable` to `...as_volatile` and assert its extra is `True`. Include `search_tools` in the stable prefix assertion.

Replace every old assertion that expects multiple system-block cache tags with the new single final-stable-system breakpoint. Update the settings test so `PROMPT_CACHE_MAX_SYSTEM_BLOCKS=0` and `PROMPT_CACHE_MAX_TOOLS=0` disable those breakpoint classes, while nonzero values enable the fixed one-system and one-per-tool-segment policy; settings no longer multiply tags within one stable segment.

- [ ] **Step 2: Run the middleware tests and observe policy failures**

Run: `uv run pytest tests/infra/agent/test_prompt_caching_middleware.py -q`

Expected: FAIL because MiniMax is skipped, Anthropic has no top-level setting under LambChat ownership, volatile tools are ordered first and unmarked discovered tools remain cacheable.

- [ ] **Step 3: Resolve provider identity through wrapped models**

Implement one wrapper traversal and reuse it for class, metadata, and model-name checks:

```python
@staticmethod
def _model_chain(model: Any) -> list[Any]:
    chain: list[Any] = []
    seen: set[int] = set()
    current = model
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = getattr(current, "bound", None) or getattr(current, "_bound", None)
        if current is None:
            candidate = getattr(chain[-1], "model", None)
            current = candidate if not isinstance(candidate, str) else None
    return chain


@classmethod
def _runtime_provider(cls, model: Any) -> str | None:
    for current in cls._model_chain(model):
        metadata = getattr(current, "metadata", None)
        if isinstance(metadata, dict) and metadata.get("lambchat_provider"):
            return str(metadata["lambchat_provider"])
    return None
```

Keep class-module detection only as a defensive fallback for older manually constructed Anthropic models; provider-specific MiniMax behavior must use metadata, not host-string guessing.

- [ ] **Step 4: Mark discovered tools and construct stable-first deterministic order**

In `ToolSearchMiddleware.awrap_model_call`, leave `search_tools` stable, clone every discovered tool with the volatile marker, sort only the volatile list, and append it after core tools and `search_tools`:

```python
discovered_tools = [
    tool.model_copy(update={
        "extras": {**(tool.extras or {}), _PROMPT_CACHE_VOLATILE_TOOL_EXTRA: True}
    })
    for tool in discovered
    if tool.name not in existing_names
]
new_tools = []
if search_tool.name not in existing_names:
    new_tools.append(search_tool)
new_tools.extend(sorted(discovered_tools, key=_tool_sort_key))
request = request.override(tools=[*request.tools, *new_tools])
```

In `_retag_tools`, strip old cache tags, keep stable tools in original order, sort volatile tools by name, tag exactly the last stable tool and (when present) the last volatile tool, and return `stable_tools + volatile_tools`. A tool breakpoint is cumulative, so this preserves the reusable core prefix while allowing a second cacheable session tail.

- [ ] **Step 5: Implement the provider breakpoint budget**

Refactor `awrap_model_call` around explicit slot allocation:

```python
provider = self._runtime_provider(request.model)
model_name = self._runtime_model_name(request.model)

if provider == "openai" and _is_gpt_56_or_later(model_name):
    new_system = self._retag_openai_system_message(request.system_message)
    return await handler(request.override(system_message=new_system))

if provider not in {"anthropic", "minimax"} and not self._is_anthropic_model(request.model):
    return await handler(request)

automatic_slots = 1 if provider == "anthropic" else 0
message_slots = 1 if provider == "minimax" and request.messages else 0
tool_slots = int(bool(stable_tools)) + int(bool(volatile_tools))
system_slots = int(self._cacheable_system_block_count(request.system_message) > 0)
assert automatic_slots + message_slots + tool_slots + system_slots <= 4
```

For direct Anthropic, set `overrides["model_settings"]` to the existing settings plus `cache_control={"type": "ephemeral", "ttl": "5m"}`. For both Anthropic paths, tag only the final stable system block. For MiniMax, tag the last eligible text/content block in the latest message using `message.model_copy(update={"content": blocks})`; never set top-level `model_settings.cache_control`. Strip stale `cache_control`/`prompt_cache_breakpoint` tags before applying the selected policy.

For GPT-5.6+, put this LangChain OpenAI content extra only on the final stable system block:

```python
{
    "type": "text",
    "text": stable_text,
    "extras": {"prompt_cache_breakpoint": {"mode": "explicit"}},
}
```

For OpenAI pre-5.6, DeepSeek, Gemini, and other providers, do not add block-level fields.

- [ ] **Step 6: Run prompt-cache middleware tests**

Run: `uv run pytest tests/infra/agent/test_prompt_caching_middleware.py -q`

Expected: PASS; all test fixtures show stable tools first, deterministic volatile tails, no more than four breakpoints, direct Anthropic automatic mode, MiniMax explicit-only mode, and no private fields for implicit-cache providers.

- [ ] **Step 7: Commit provider-aware middleware behavior**

```bash
git add src/infra/agent/middleware/prompt_caching.py src/infra/agent/middleware/tool_interception.py tests/infra/agent/test_prompt_caching_middleware.py
git commit -m "feat(agent): optimize cache breakpoints by provider"
```

### Task 4: Stable-Before-Volatile System Prompt Ordering

**Files:**
- Modify: `src/infra/agent/middleware/prompt_injection.py`
- Modify: `src/infra/agent/middleware/__init__.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `tests/infra/agent/test_prompt_caching_middleware.py`
- Modify: `tests/agents/core/test_subagent_prompts.py`
- Modify: `tests/agents/test_disabled_skills_config_propagation.py`
- Modify: `tests/agents/test_team_agent_sandbox_support.py`

**Interfaces:**
- Consumes: stable `SectionPromptMiddleware`, async `EnvVarPromptMiddleware`, `build_goal_prompt_section`, and `AUTO_MODE_PROMPT_SECTION`.
- Produces: `VolatileSectionPromptMiddleware(sections: list[str] | tuple[str, ...])`, inserted after stable sandbox/env sections and before memory index/deferred tools.

- [ ] **Step 1: Write failing ordering tests**

Add a behavior test beside the existing section middleware test:

```python
async def test_volatile_section_middleware_appends_goal_and_auto_after_stable_sections() -> None:
    middleware = VolatileSectionPromptMiddleware(
        sections=["## Active Goal\nObjective: ship", "### Auto Mode (Autonomous Execution)"]
    )
    request = _PromptRequest(SystemMessage(content=[
        {"type": "text", "text": "base"},
        {"type": "text", "text": "## Sandbox Runtime\nwork_dir: /workspace"},
        {"type": "text", "text": "## Available Environment Variables\n- TOKEN"},
    ]))
    result = await middleware.awrap_model_call(request, _return_system_message)
    assert [block["text"].splitlines()[0] for block in result.content] == [
        "base", "## Sandbox Runtime", "## Available Environment Variables",
        "## Active Goal", "### Auto Mode (Autonomous Execution)",
    ]
```

In agent source/constructor tests, assert the effective middleware order for main agents and subagents is:

```python
assert index(SectionPromptMiddleware) < index(EnvVarPromptMiddleware)
assert index(EnvVarPromptMiddleware) < index(VolatileSectionPromptMiddleware)
assert index(VolatileSectionPromptMiddleware) < index(MemoryIndexMiddleware)
assert index(MemoryIndexMiddleware) < index(ToolSearchMiddleware)
assert index(ToolSearchMiddleware) < index(PromptCachingMiddleware)
```

Allow absent optional entries by asserting the relative order only when both are enabled in the fixture. Specifically prove Search and Team put sandbox runtime in the stable section list before env names, and all three main agents move goal/auto out of `_prompt_sections`.

- [ ] **Step 2: Run ordering tests and verify the current interleaving fails**

Run: `uv run pytest tests/infra/agent/test_prompt_caching_middleware.py tests/agents/core/test_subagent_prompts.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py -q`

Expected: FAIL because `VolatileSectionPromptMiddleware` does not exist and goal/auto currently precede later stable runtime/env sections.

- [ ] **Step 3: Add the dedicated volatile injector**

Use the same normalization and block append behavior without subclassing `SectionPromptMiddleware` (LangChain rejects duplicate middleware classes):

```python
class VolatileSectionPromptMiddleware(AgentMiddleware):
    """Append run/turn-varying sections after every session-stable section."""

    def __init__(self, *, sections: list[str] | tuple[str, ...]) -> None:
        super().__init__()
        self._sections = tuple(
            _normalize_prompt_text(section) for section in sections if section.strip()
        )

    async def awrap_model_call(self, request, handler):
        if not self._sections:
            return await handler(request)
        blocks = _system_message_to_blocks(request.system_message)
        blocks.extend({"type": "text", "text": section} for section in self._sections)
        return await handler(request.override(system_message=SystemMessage(content=blocks)))
```

Export it from `src/infra/agent/middleware/__init__.py`.

- [ ] **Step 4: Reassemble every agent and subagent middleware list**

For each Fast/Search/Team builder:

1. Build `_prompt_sections` only from canonical sections, persona, Skills, memory guide, and stable sandbox runtime.
2. Append `SectionPromptMiddleware(_prompt_sections)`.
3. Append `EnvVarPromptMiddleware` when applicable.
4. Build `_volatile_sections` from `goal_section` and `AUTO_MODE_PROMPT_SECTION`, then append one `VolatileSectionPromptMiddleware`.
5. Append `MemoryIndexMiddleware`, `ToolSearchMiddleware`, other execution middleware, and finally `PromptCachingMiddleware`.

Use this exact construction pattern in each builder rather than sharing mutable lists:

```python
_volatile_sections = [section for section in (goal_section, auto_section) if section]
if _volatile_sections:
    user_middleware.append(VolatileSectionPromptMiddleware(sections=_volatile_sections))
```

Do not remove any section, tool, or subagent behavior while moving the two volatile sections.

- [ ] **Step 5: Run ordering and prompt semantic tests**

Run: `uv run pytest tests/infra/agent/test_prompt_caching_middleware.py tests/agents/core/test_subagent_prompts.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py -q`

Expected: PASS and the captured middleware chains preserve all existing entries with stable sections before volatile sections.

- [ ] **Step 6: Commit deterministic prompt ordering**

```bash
git add src/infra/agent/middleware/prompt_injection.py src/infra/agent/middleware/__init__.py src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py tests/infra/agent/test_prompt_caching_middleware.py tests/agents/core/test_subagent_prompts.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py
git commit -m "refactor(agent): place volatile prompt sections last"
```

### Task 5: Complete Provider Cache Usage Normalization

**Files:**
- Modify: `tests/infra/agent/test_token_usage_cache_metrics.py`
- Modify: `src/infra/agent/events/stream.py`

**Interfaces:**
- Consumes: LangChain `usage_metadata`, `response_metadata.token_usage|usage`, and optional `metadata.token_usage|usage`.
- Produces: normalized, non-duplicated `total_cache_creation_tokens` and `total_cache_read_tokens` covering OpenAI, Anthropic/MiniMax, DeepSeek, and Gemini aliases.

- [ ] **Step 1: Add failing raw-alias and precedence tests**

Extend `_Response` to accept `metadata`, then add:

```python
@pytest.mark.parametrize("field", [
    "prompt_cache_hit_tokens", "cached_content_token_count", "total_cached_tokens"
])
def test_token_usage_reads_provider_cache_hit_aliases(field: str) -> None:
    processor = _processor()
    response = _Response(usage_metadata={"input_tokens": 2000}, response_metadata={
        "usage": {field: 1536}
    })
    processor._handle_token_usage({"data": {"output": response}})
    assert processor.total_input_tokens == 2000
    assert processor.total_cache_read_tokens == 1536


def test_token_usage_reads_openai_cache_write_tokens() -> None:
    processor = _processor()
    response = _Response(usage_metadata={"input_tokens": 2000}, response_metadata={
        "usage": {"cache_write_tokens": 1024}
    })
    processor._handle_token_usage({"data": {"output": response}})
    assert processor.total_cache_creation_tokens == 1024


def test_standard_usage_wins_without_double_counting_raw_alias() -> None:
    processor = _processor()
    response = _Response(
        usage_metadata={"input_tokens": 2000, "input_token_details": {"cache_read": 1536}},
        response_metadata={"usage": {"prompt_cache_hit_tokens": 1536}},
    )
    processor._handle_token_usage({"data": {"output": response}})
    assert processor.total_cache_read_tokens == 1536
```

Add `import pytest` and a local `_processor()` helper to remove repeated presenter setup.

- [ ] **Step 2: Run the normalization tests and observe missing raw fallbacks**

Run: `uv run pytest tests/infra/agent/test_token_usage_cache_metrics.py -q`

Expected: FAIL when `usage_metadata` exists but its cache detail is missing, and for the new DeepSeek/Gemini/OpenAI aliases.

- [ ] **Step 3: Merge usage sources field-by-field**

Collect ordered sources rather than choosing only one object:

```python
usage_sources: list[Any] = []
if response.usage_metadata is not None:
    usage_sources.append(response.usage_metadata)
for container in (response.response_metadata, getattr(response, "metadata", None)):
    if container:
        raw = container.get("token_usage") or container.get("usage")
        if raw is not None:
            usage_sources.append(raw)
```

Add a helper that returns the first valid integer across nested and root aliases, preserving source order. Use these exact alias orders:

```python
cache_read_aliases = (
    "cache_read", "cached_tokens", "cache_read_input_tokens",
    "prompt_cache_hit_tokens", "cached_content_token_count", "total_cached_tokens",
)
cache_creation_aliases = (
    "cache_creation", "cache_creation_input_tokens", "cache_write_tokens",
)
```

Read `input_token_details` and `prompt_tokens_details` before root fields for each source. Count one value per semantic metric, never sum aliases from the same response. Preserve the current first-source logic for input/output/total tokens.

- [ ] **Step 4: Run all event-processor cache tests**

Run: `uv run pytest tests/infra/agent/test_token_usage_cache_metrics.py tests/infra/agent/test_events_processor.py -q`

Expected: PASS; duplicate normalized/raw fields count once and malformed/missing cache fields leave totals unchanged.

- [ ] **Step 5: Commit usage normalization**

```bash
git add src/infra/agent/events/stream.py tests/infra/agent/test_token_usage_cache_metrics.py
git commit -m "fix(usage): normalize provider cache token fields"
```

### Task 6: Per-Model Cache Aggregation and API Schema

**Files:**
- Modify: `tests/infra/usage/test_usage_storage.py`
- Modify: `tests/api/routes/test_usage_routes.py`
- Modify: `src/infra/usage/storage.py`
- Modify: `src/kernel/schemas/usage.py`

**Interfaces:**
- Consumes: stored `input_tokens`, `cache_creation_tokens`, and `cache_read_tokens` per request.
- Produces: optional/defaulted `UsageRankingItem.input_tokens`, `cache_creation_tokens`, `cache_read_tokens`, `cache_read_share`, and `zero_cache_requests`; every `top_models` item is populated.

- [ ] **Step 1: Add failing model-ranking aggregation tests**

In the storage fake result, include a model facet document and assert exact formatting:

```python
"models": [{
    "_id": "deepseek-v4-flash",
    "requests": 3,
    "tokens": 2400,
    "duration": 9.5,
    "input_tokens": 2000,
    "cache_creation_tokens": 100,
    "cache_read_tokens": 1500,
    "zero_cache_requests": 1,
}],
```

```python
model = dashboard["top_models"][0]
assert model == {
    "id": "deepseek-v4-flash",
    "name": "deepseek-v4-flash",
    "requests": 3,
    "tokens": 2400,
    "duration": 9.5,
    "input_tokens": 2000,
    "cache_creation_tokens": 100,
    "cache_read_tokens": 1500,
    "cache_read_share": 0.75,
    "zero_cache_requests": 1,
}
```

Add a zero-input model case asserting `cache_read_share == 0.0`. Update the route fixture/assertion to prove these fields survive Pydantic response serialization while non-model ranking items default them to zero.

- [ ] **Step 2: Run storage and route tests and observe missing fields**

Run: `uv run pytest tests/infra/usage/test_usage_storage.py tests/api/routes/test_usage_routes.py -q`

Expected: FAIL because model facets currently aggregate only request/token/duration and the schema drops cache fields.

- [ ] **Step 3: Add cache-aware ranking aggregation only for models**

Extend `_ranking_pipeline` with `include_cache_metrics: bool = False`. When true, update its group:

```python
group.update({
    "input_tokens": {"$sum": "$input_tokens"},
    "cache_creation_tokens": {"$sum": "$cache_creation_tokens"},
    "cache_read_tokens": {"$sum": "$cache_read_tokens"},
    "zero_cache_requests": {
        "$sum": {"$cond": [{"$lte": [{"$ifNull": ["$cache_read_tokens", 0]}, 0]}, 1, 0]}
    },
})
```

Call `self._ranking_pipeline("model", include_cache_metrics=True)` only for the models facet. Do not expand other Mongo facets.

- [ ] **Step 4: Format and type ranking cache metrics**

Extend `_format_ranking_item`:

```python
input_tokens = _as_int(doc.get("input_tokens"))
cache_read_tokens = _as_int(doc.get("cache_read_tokens"))
return {
    # existing fields
    "input_tokens": input_tokens,
    "cache_creation_tokens": _as_int(doc.get("cache_creation_tokens")),
    "cache_read_tokens": cache_read_tokens,
    "cache_read_share": cache_read_tokens / input_tokens if input_tokens else 0.0,
    "zero_cache_requests": _as_int(doc.get("zero_cache_requests")),
}
```

Add matching fields with zero defaults to `UsageRankingItem`. Defaults preserve compatibility for agent/team/user/source rankings and old fixtures.

- [ ] **Step 5: Run aggregation and API tests**

Run: `uv run pytest tests/infra/usage/test_usage_storage.py tests/api/routes/test_usage_routes.py -q`

Expected: PASS, including the zero-denominator case and default compatibility for non-model rankings.

- [ ] **Step 6: Commit model cache diagnostics**

```bash
git add src/infra/usage/storage.py src/kernel/schemas/usage.py tests/infra/usage/test_usage_storage.py tests/api/routes/test_usage_routes.py
git commit -m "feat(usage): aggregate cache metrics by model"
```

### Task 7: Model Ranking Cache UI

**Files:**
- Modify: `frontend/src/types/usage.ts`
- Modify: `frontend/src/components/panels/UsagePanel/RankingCards.tsx`
- Modify: `frontend/src/components/panels/UsagePanel.tsx`
- Modify: `frontend/src/components/panels/__tests__/usagePanelPresentationSource.test.ts`

**Interfaces:**
- Consumes: Task 6 `UsageRankingItem` cache fields and existing i18n keys `usage.cacheHitRate`, `usage.cacheRead`, and `usage.cacheWrite`.
- Produces: `RankingList` prop `showCacheMetrics?: boolean`; only the model ranking passes `true`.

- [ ] **Step 1: Add a failing presentation test that scopes cache diagnostics to models**

Read `RankingCards.tsx` as `rankingSource` in the existing source test, then add:

```typescript
test("model ranking alone exposes per-model cache diagnostics", () => {
  expect(rankingSource).toMatch(/showCacheMetrics\?: boolean/);
  expect(rankingSource).toMatch(/usage\.cacheHitRate/);
  expect(rankingSource).toMatch(/pct\(item\.cache_read_share\)/);
  expect(rankingSource).toMatch(/usage\.cacheRead/);
  expect(rankingSource).toMatch(/fmt\(item\.cache_read_tokens\)/);
  expect(usagePanelSource.match(/showCacheMetrics/g)).toHaveLength(1);
  expect(usagePanelSource).toMatch(
    /title=\{modelRankingTitle\}[\s\S]*?showCacheMetrics/,
  );
});
```

- [ ] **Step 2: Run the focused Vitest and observe missing UI support**

Run: `cd frontend && pnpm vitest run src/components/panels/__tests__/usagePanelPresentationSource.test.ts`

Expected: FAIL because ranking cards have no cache-metric prop or rendering.

- [ ] **Step 3: Extend the shared TypeScript ranking type**

```typescript
export interface UsageRankingItem {
  id: string;
  name: string;
  requests: number;
  tokens: number;
  duration: number;
  input_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cache_read_share: number;
  zero_cache_requests: number;
}
```

- [ ] **Step 4: Render compact cache details behind one explicit prop**

Add `showCacheMetrics = false` to `RankingList`. Under the existing request/duration row, render only when enabled:

```tsx
{showCacheMetrics && (
  <div className="mt-1 flex flex-wrap justify-between gap-x-2 text-[10px] text-theme-text-tertiary">
    <span>
      {t("usage.cacheHitRate")}: {pct(item.cache_read_share)}
    </span>
    <span>
      {t("usage.cacheRead")}: {fmt(item.cache_read_tokens)}
    </span>
  </div>
)}
```

Pass `showCacheMetrics` on the `dashboard.top_models` `RankingList` only. Do not touch locales or change other ranking cards.

- [ ] **Step 5: Run focused test, frontend type/build validation**

Run: `cd frontend && pnpm vitest run src/components/panels/__tests__/usagePanelPresentationSource.test.ts`

Expected: PASS.

Run: `cd frontend && pnpm run build`

Expected: PASS with the extended API type and no missing props in existing fixtures. If a typed fixture constructs `UsageRankingItem` directly, add the five zero-valued fields to that fixture rather than making production fields optional.

- [ ] **Step 6: Commit the model-only cache display**

```bash
git add frontend/src/types/usage.ts frontend/src/components/panels/UsagePanel.tsx frontend/src/components/panels/UsagePanel/RankingCards.tsx frontend/src/components/panels/__tests__/usagePanelPresentationSource.test.ts
git commit -m "feat(usage): show cache rate per model"
```

### Task 8: Cross-Provider Regression and Completion Evidence

**Files:**
- Verify only; modify a scoped file only if its own newly introduced failure requires a TDD fix.

**Interfaces:**
- Consumes: all deliverables from Tasks 1-7.
- Produces: local automated evidence for request construction, prompt ordering, usage normalization, storage/API behavior, and frontend build. It does not produce a live provider cache-hit claim.

- [ ] **Step 1: Run the complete focused backend regression set**

```bash
uv run pytest \
  tests/infra/llm/test_prompt_cache_config.py \
  tests/infra/llm/test_model_access.py \
  tests/agents/core/test_persona_harness_profile.py \
  tests/infra/agent/test_prompt_caching_middleware.py \
  tests/infra/agent/test_token_usage_cache_metrics.py \
  tests/infra/agent/test_events_processor.py \
  tests/infra/usage/test_usage_storage.py \
  tests/api/routes/test_usage_routes.py \
  tests/agents/core/test_subagent_prompts.py \
  tests/agents/test_disabled_skills_config_propagation.py \
  tests/agents/test_team_agent_sandbox_support.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Python lint and type checking on the repository**

Run: `make lint`

Expected: PASS with no Ruff violations.

Run: `make typecheck`

Expected: PASS. If an unrelated baseline failure occurs, rerun its exact command against the unchanged baseline or isolate it by file before attribution.

- [ ] **Step 3: Run frontend tests and build**

Run: `cd frontend && pnpm test`

Expected: PASS.

Run: `cd frontend && pnpm run build`

Expected: PASS.

- [ ] **Step 4: Inspect the final diff and breakpoint invariants**

Run: `git diff --check`

Expected: no output.

Run: `git status --short`

Expected: only the user's pre-existing unrelated frontend changes remain unstaged; implementation files from this plan are committed.

Run: `rg -n "prompt_cache_key|prompt_cache_retention|prompt_cache_options|cache_control|prompt_cache_breakpoint" src/infra/llm/client.py src/infra/agent/middleware/prompt_caching.py src/agents/core/persona.py`

Expected: OpenAI-only constructor fields are guarded by `provider == "openai"`; Anthropic/MiniMax block fields live in the LambChat middleware; DeepAgents' built-in middleware appears only in the exclusion profile.

- [ ] **Step 5: Record the rollout boundary in the handoff**

Report automated validation separately from live provider validation. State that DeepSeek/Gemini use implicit caching, MiniMax is now explicit-only at the block level, and the configured `gpt-5.4` proxy still requires a user-authorized low-cost repeated-prefix request before claiming an external cache hit.

- [ ] **Step 6: Confirm the verification phase created no uncommitted cache work**

Run: `git status --short src tests frontend/src/types/usage.ts frontend/src/components/panels/UsagePanel.tsx frontend/src/components/panels/UsagePanel frontend/src/components/panels/__tests__/usagePanelPresentationSource.test.ts`

Expected: no plan-scoped file remains modified. If a newly introduced failure required a change, return to that task's red-green steps, rerun its focused checks, and amend that task with a normal scoped commit before repeating Task 8. Never stage the user's unrelated dirty frontend files.

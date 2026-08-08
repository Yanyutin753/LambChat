# Harness Profile Runtime Providers Design

## Goal

Ensure every chat-model class constructed by LambChat resolves the LambChat harness profile under `deepagents` 0.7.5. This removes the repeated `No harness profile matched pre-built model` warnings and ensures LambChat's behavior guide is applied consistently to Anthropic, Google, OpenAI, and OpenAI-compatible models.

## Root Cause

`src/agents/core/persona.py` currently registers `_BEHAVIOR_GUIDE` only under the provider key `anthropic`. LambChat passes pre-built LangChain model instances to `create_deep_agent`, so `deepagents` derives the harness provider from the concrete model class rather than from LambChat's configured provider slug.

The runtime mappings are:

- `ChatAnthropic` resolves to `anthropic`;
- `ChatOpenAI` resolves to `openai`, including DeepSeek and other OpenAI-compatible providers;
- `ChatGoogleGenerativeAI` resolves to `google_genai`.

For a fast, search, or team graph with five configured subagents, `deepagents` resolves the main model once and each subagent model once. An unmatched OpenAI-compatible model therefore produces six identical warnings during graph construction.

## Design

Keep a single `HarnessProfile(base_system_prompt=_BEHAVIOR_GUIDE)` definition and register it for the three runtime provider keys:

- `anthropic`;
- `openai`;
- `google_genai`.

Registration remains import-time behavior in `src/agents/core/persona.py`. Deepagents registration is additive, so provider-level LambChat settings continue to merge with any exact model profile supplied by deepagents. No model-specific registrations are needed because the concrete LangChain classes collapse LambChat's configured provider slugs into these three runtime providers.

The implementation will use a small immutable provider-key collection and register the same profile for each key. Compatibility guards for deepagents builds without `HarnessProfile` or `register_harness_profile` remain unchanged.

## Scope

The change is limited to harness-profile registration and its regression coverage. It will not:

- change model selection or provider inference in `LLMClient`;
- suppress or downgrade deepagents logging;
- add model-specific exceptions;
- change the behavior-guide text;
- update dependency versions.

## Testing Strategy

Implementation follows red-green-refactor:

1. Add a focused regression test that creates the runtime model classes used by LambChat and resolves their deepagents harness profiles.
2. Verify the test fails for `ChatOpenAI` and `ChatGoogleGenerativeAI` before the production change because their resolved profile has no LambChat base system prompt.
3. Register all three runtime provider keys and verify each resolved profile contains `_BEHAVIOR_GUIDE`.
4. Run the focused persona test module and Ruff on the changed Python files.

The functional assertion verifies profile application rather than merely checking that a warning was hidden. Because the warning is emitted only when no profile matches, successful profile resolution also removes the repeated warning at its source.

## Compatibility and Risk

The provider-level `openai` registration will also apply to exact OpenAI model profiles through deepagents' additive merge semantics. Exact model settings retain their model-level precedence while inheriting LambChat's base system prompt. The same behavior already exists for the current `anthropic` registration.

The risk is low and confined to restoring the behavior already intended by the persona module for providers that previously missed it. Regression coverage will include all three concrete runtime provider identifiers to catch future LangChain or deepagents identifier changes.

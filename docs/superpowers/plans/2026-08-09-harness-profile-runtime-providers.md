# Harness Profile Runtime Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every concrete chat-model provider used by LambChat resolve `_BEHAVIOR_GUIDE` through deepagents without unmatched-profile warnings.

**Architecture:** Keep persona-owned harness registration at module import time and expand it from the single Anthropic runtime provider to the three provider identifiers emitted by LambChat's concrete LangChain model classes. Verify the functional profile resolution contract for Anthropic, OpenAI-compatible, and Google models before checking the original six-warning reproduction.

**Tech Stack:** Python 3.12+, deepagents 0.7.5, LangChain chat-model integrations, pytest, Ruff

## Global Constraints

- Register exactly the runtime provider keys `anthropic`, `openai`, and `google_genai`.
- Keep the `_BEHAVIOR_GUIDE` text unchanged.
- Preserve compatibility when deepagents does not expose `HarnessProfile` or `register_harness_profile`.
- Do not change model selection, provider inference, logging levels, or dependency versions.
- Follow red-green-refactor and keep the production change within `src/agents/core/persona.py`.

---

### Task 1: Cover all runtime harness providers

**Files:**
- Modify: `src/agents/core/persona.py:37-75`
- Test: `tests/agents/test_persona_preset_runtime.py`

**Interfaces:**
- Consumes: `LLMClient._create_model(provider: str, model_name: str, *, temperature: float, api_key: str) -> BaseChatModel` and deepagents' `_harness_profile_for_model(model, spec)` integration contract.
- Produces: import-time harness registrations under `anthropic`, `openai`, and `google_genai`, each with `base_system_prompt == _BEHAVIOR_GUIDE`.

- [x] **Step 1: Write the failing provider-resolution test**

Add the deepagents resolver and `LLMClient` imports, extend the existing persona import with `_BEHAVIOR_GUIDE`, and add the focused parameterized test to `tests/agents/test_persona_preset_runtime.py`:

```python
from deepagents.profiles.harness.harness_profiles import _harness_profile_for_model

from src.agents.core.persona import (
    _BEHAVIOR_GUIDE,
    build_persona_prompt_section,
    build_persona_prompt_sections,
)
from src.infra.llm.client import LLMClient


@pytest.mark.parametrize(
    ("provider", "model_name"),
    [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "deepseek-v4-flash"),
        ("google", "gemini-2.5-flash"),
    ],
)
def test_lambchat_harness_profile_covers_runtime_model_providers(
    provider: str,
    model_name: str,
) -> None:
    model = LLMClient._create_model(
        provider,
        model_name,
        temperature=0.7,
        api_key="sk-test",
    )

    profile = _harness_profile_for_model(model, None)

    assert profile.base_system_prompt == _BEHAVIOR_GUIDE
```

- [x] **Step 2: Run the new test and verify RED**

Run:

```bash
uv run pytest tests/agents/test_persona_preset_runtime.py::test_lambchat_harness_profile_covers_runtime_model_providers -v
```

Expected: Anthropic passes, while the OpenAI and Google cases fail because `profile.base_system_prompt` is `None`. The run may also capture unmatched-profile warnings for those two cases.

- [x] **Step 3: Implement the minimal provider registrations**

In `src/agents/core/persona.py`, replace the single-provider registration with:

```python
_HARNESS_PROFILE_PROVIDERS = ("anthropic", "openai", "google_genai")

if _HarnessProfile is not None and _register_harness_profile is not None:
    profile = _HarnessProfile(base_system_prompt=_BEHAVIOR_GUIDE)
    for provider in _HARNESS_PROFILE_PROVIDERS:
        _register_harness_profile(provider, profile)
```

Keep registration after `_BEHAVIOR_GUIDE` is built and retain the existing compatibility guard.

- [x] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
uv run pytest tests/agents/test_persona_preset_runtime.py::test_lambchat_harness_profile_covers_runtime_model_providers -v
```

Expected: all three parameter cases pass without `No harness profile matched pre-built model` warnings.

- [x] **Step 5: Verify the original six-warning reproduction is eliminated**

Run:

```bash
uv run python - <<'PY'
import logging
from io import StringIO

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from src.agents.core import persona  # noqa: F401

stream = StringIO()
handler = logging.StreamHandler(stream)
logger = logging.getLogger("deepagents.profiles.harness.harness_profiles")
logger.addHandler(handler)
logger.setLevel(logging.WARNING)
try:
    model = ChatOpenAI(model="deepseek-v4-flash", api_key="sk-test")
    subagents = [
        {"name": f"worker-{index}", "description": "test", "system_prompt": "test"}
        for index in range(5)
    ]
    create_deep_agent(model=model, subagents=subagents)
finally:
    logger.removeHandler(handler)

warnings = [
    line
    for line in stream.getvalue().splitlines()
    if "No harness profile matched" in line
]
assert warnings == []
print({"warning_count": len(warnings)})
PY
```

Expected: `{'warning_count': 0}`.

- [x] **Step 6: Run focused regression tests and lint**

Run:

```bash
uv run pytest tests/agents/test_persona_preset_runtime.py tests/agents/test_team_agent_sandbox_support.py -v
uv run ruff check src/agents/core/persona.py tests/agents/test_persona_preset_runtime.py
git diff --check
```

Expected: all tests pass, Ruff reports no errors, and `git diff --check` emits no output.

- [x] **Step 7: Commit the repair**

```bash
git add src/agents/core/persona.py tests/agents/test_persona_preset_runtime.py docs/superpowers/plans/2026-08-09-harness-profile-runtime-providers.md
git commit -m "fix: register runtime harness providers"
```

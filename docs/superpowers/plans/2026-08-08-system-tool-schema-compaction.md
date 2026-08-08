# System Tool Schema Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the 21 system-embedded tool definitions from a measured 6,981-token baseline to at most 4,188 tokens while preserving execution objects, open-ended arguments, dynamic team subagent types, and all ordinary MCP schemas.

**Architecture:** Add an innermost model-call middleware that recognizes system tools by exact name, trusted Python provenance, and input-property signature. It clones only recognized `BaseTool` objects with compact model-facing descriptions and JSON schemas; the graph continues executing the original tools. A shared agent-stack tail factory guarantees that compaction runs after deferred injection and immediately before prompt-cache tagging in fast, search, team, and subagent stacks.

**Tech Stack:** Python 3.12, LangChain `AgentMiddleware`/`BaseTool`, deepagents 0.7.5, Pydantic/JSON Schema, pytest, tiktoken `o200k_base`, Ruff, Mypy.

---

## File Structure

- Create `src/infra/agent/middleware/tool_schema_compaction.py`: trusted system-tool registry, pure schema compaction, provenance checks, `BaseTool` cloning, and model-call middleware.
- Modify `src/infra/agent/middleware/__init__.py`: export `SystemToolSchemaCompactionMiddleware`.
- Create `src/agents/core/tool_schema_middleware.py`: return the ordered `[SystemToolSchemaCompactionMiddleware(), PromptCachingMiddleware()]` tail shared by every agent stack.
- Modify `src/agents/fast_agent/nodes.py`: use the shared tail for main and subagent middleware.
- Modify `src/agents/search_agent/nodes.py`: use the shared tail for main and subagent middleware.
- Modify `src/agents/team_agent/nodes.py`: use the shared tail for main and subagent middleware.
- Create `tests/fixtures/system_tool_schemas.json`: exact 21-tool subset of the supplied schema snapshot.
- Create `tests/infra/agent/test_tool_schema_compaction.py`: pure compaction, provenance, invariants, semantic coverage, middleware, and token-budget tests.
- Create `tests/agents/test_tool_schema_compaction_registration.py`: source-level registration and ordering regression tests for all agent variants.
- Create `scripts/report_system_tool_schema_tokens.py`: deterministic before/after report for a captured tool-schema JSON file.
- Create `tests/scripts/test_report_system_tool_schema_tokens.py`: report-helper contract test.

## Required Registry Contract

`tool_schema_compaction.py` owns an immutable registry for exactly this set:

```python
SYSTEM_TOOL_NAMES = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "task",
        "write_todos",
        "ask_human",
        "reveal_file",
        "reveal_project",
        "transfer_file",
        "transfer_path",
        "memory_retain",
        "memory_recall",
        "memory_delete",
        "upload_url_to_sandbox",
        "search_skills",
        "search_tools",
    }
)
```

Each registry entry must contain:

- Allowed defining modules for the tool class, `func`, or `coroutine`.
- The exact top-level input-property set expected for that tool.
- A compact description, or for `task`, a formatter that preserves the dynamically generated available-agent block.
- Optional compact parameter descriptions addressed by a tuple path into the JSON schema.

Minimum provenance groups:

```python
FILESYSTEM_MODULES = frozenset({"deepagents.middleware.filesystem"})
TASK_MODULES = frozenset({"deepagents.middleware.subagents"})
TODO_MODULES = frozenset({"langchain.agents.middleware.todo"})
LAMBCHAT_MODULE_PREFIXES = (
    "src.infra.memory.tools",
    "src.infra.skill.skill_search_tool",
    "src.infra.tool.",
)
```

Matching a name and property set without trusted provenance must return the original object unchanged. Dictionary tool definitions also pass through unchanged because their provenance cannot be established.

## Baseline Snapshot Source

The supplied snapshot is available at:

```text
/home/yangyang/.codex/attachments/985a047a-3698-4a7a-9c7e-6781d9ee4725/pasted-text.txt
```

Its SHA-256 is `fd7b8088649d15e7bfb6149a4236bb64dc80a742e567bbbcf331acebb71d44ef`. After excluding only `web_search_prime`, `search_doc`, and `get_repo_structure`, compact JSON serialization of the 21-entry array has SHA-256 `609dccbe1bc1f06b03d3884c02c92abc114cf322a11d5cb2c88632e847e12ec3`. Token accounting sums the independently encoded compact JSON for each tool; that per-tool sum is 6,981 tokens. Encoding the surrounding array as one payload produces a different boundary count and must not be used for the acceptance baseline.

## Compact Description Requirements

Exact wording may be refined to meet the budget, but tests must require the concepts in the right column:

| Tool | Required model-facing concepts |
|------|--------------------------------|
| `ls` | list directory; use when path is unknown |
| `read_file` | 100-line default; offset/limit paging; line prefixes; read before edit |
| `write_file` | create or replace whole file; prefer edit for existing file |
| `edit_file` | exact replacement; read first; uniqueness/replace-all; preserve indentation |
| `delete` | permanent; recursive directory deletion; irreversible/confirmed target |
| `glob` | glob matching; absolute-path results |
| `grep` | literal rather than regex; output modes; offloaded large results |
| `execute` | sandbox command; absolute paths; prefer file tools for search/read |
| `task` | stateless delegation; full context; dynamically available agent types retained |
| `write_todos` | complex tasks only; immediate state updates; complete only when done; final answer after update |
| `ask_human` | blocking clarification/confirmation; choices or fields; timeout/refusal result |
| `reveal_file` | expose one file/URL to user; not directories |
| `reveal_project` | expose multi-file project/folder; project versus folder preview |
| `transfer_file` | one text file; `/skills/` routing; no binary files |
| `transfer_path` | directory of text files; routing; size/depth/file-count safety bounds |
| `memory_retain` | durable high-signal cross-session facts; reject temporary/duplicate content |
| `memory_recall` | semantic cross-session retrieval |
| `memory_delete` | delete by ID obtained from recall |
| `upload_url_to_sandbox` | download URL into sandbox target path |
| `search_skills` | find Skills; returns `SKILL.md` path |
| `search_tools` | load deferred callable schemas; keyword, `+required`, and `select:exact` query forms |

Do not add an enum to `task.subagent_type`; configured team agents generate valid `team-*` strings at runtime.

### Task 1: Lock the Pure Compaction Contract

**Files:**
- Create: `tests/infra/agent/test_tool_schema_compaction.py`
- Create: `src/infra/agent/middleware/tool_schema_compaction.py`

- [ ] **Step 1: Write failing tests for trusted matching and pass-through**

Create a real filesystem tool with `deepagents.middleware.filesystem.FilesystemMiddleware`, a real `write_todos` tool with `create_todo_middleware()`, and local fake tools with colliding names. Cover these cases:

```python
def test_compacts_trusted_system_tool_without_mutating_original() -> None:
    original = next(tool for tool in FilesystemMiddleware().tools if tool.name == "read_file")
    original_schema = convert_to_openai_tool(original)

    compacted = compact_system_tool(original)

    assert compacted is not original
    assert compacted.name == original.name
    assert compacted.func is original.func
    assert compacted.coroutine is original.coroutine
    assert convert_to_openai_tool(original) == original_schema
    assert len(compacted.description) < len(original.description)


def test_same_name_and_signature_without_trusted_provenance_passes_through() -> None:
    fake = StructuredTool.from_function(
        name="read_file",
        description="ordinary MCP-like tool",
        func=lambda file_path, offset=0, limit=100: "ok",
    )
    assert compact_system_tool(fake) is fake


def test_dictionary_tool_definition_passes_through_by_identity() -> None:
    fake = {"type": "function", "function": {"name": "read_file", "parameters": {}}}
    assert compact_system_tool(fake) is fake
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_tool_schema_compaction.py -q
```

Expected: FAIL during collection because `tool_schema_compaction` does not exist.

- [ ] **Step 3: Implement the registry, provenance matcher, and safe clone skeleton**

Implement these boundaries:

```python
@dataclass(frozen=True)
class SystemToolSchemaSpec:
    modules: frozenset[str]
    properties: frozenset[str]
    description: str | Callable[[str], str]
    parameter_descriptions: Mapping[tuple[str, ...], str | None] = field(default_factory=dict)


def _tool_provenance_modules(tool: BaseTool) -> frozenset[str]:
    values = {type(tool).__module__}
    for attribute in ("func", "coroutine"):
        callback = getattr(tool, attribute, None)
        module = getattr(callback, "__module__", None)
        if module:
            values.add(module)
    return frozenset(values)


def _is_trusted_system_tool(tool: BaseTool, spec: SystemToolSchemaSpec) -> bool:
    modules = _tool_provenance_modules(tool)
    properties = frozenset(
        convert_to_openai_tool(tool)["function"]["parameters"].get("properties", {})
    )
    return bool(modules & spec.modules) and properties == spec.properties


def compact_system_tool(tool: Any) -> Any:
    if not isinstance(tool, BaseTool):
        return tool
    spec = SYSTEM_TOOL_SCHEMA_SPECS.get(tool.name)
    if spec is None or not _is_trusted_system_tool(tool, spec):
        return tool
    definition = convert_to_openai_tool(tool)["function"]
    compact = _compact_registered_definition(definition, spec)
    return tool.model_copy(
        update={
            "description": compact["description"],
            "args_schema": compact["parameters"],
        }
    )
```

Use `copy.deepcopy` before recursive schema edits. Strip `title` only inside a trusted compact copy. Preserve `extras`, unknown keys, defaults, required lists, nullability, bounds, formats, and `additionalProperties`.

- [ ] **Step 4: Add and run invariant tests**

Parameterize trusted tools available without external services. Compare pre/post OpenAI definitions after recursively removing only allowed metadata (`description`, `title`, and `examples`). Assert identical names, property sets, `required`, types, defaults, enums, bounds, and unknown keys. Explicitly assert `write_todos.todos[].status` remains the existing three-value enum and `task.subagent_type` remains `{"type": "string"}` when a task fixture is compacted.

Run:

```bash
uv run pytest tests/infra/agent/test_tool_schema_compaction.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the pure contract**

```bash
git add src/infra/agent/middleware/tool_schema_compaction.py tests/infra/agent/test_tool_schema_compaction.py
git commit -m "feat: compact trusted system tool schemas"
```

### Task 2: Add All 21 Curated Definitions and the Token Budget

**Files:**
- Create: `tests/fixtures/system_tool_schemas.json`
- Modify: `tests/infra/agent/test_tool_schema_compaction.py`
- Modify: `src/infra/agent/middleware/tool_schema_compaction.py`

- [ ] **Step 1: Create the exact 21-tool baseline fixture**

Verify and filter the supplied JSON snapshot with these exact commands:

```bash
sha256sum /home/yangyang/.codex/attachments/985a047a-3698-4a7a-9c7e-6781d9ee4725/pasted-text.txt
jq '[.[] | select(.name != "web_search_prime" and .name != "search_doc" and .name != "get_repo_structure")]' \
  /home/yangyang/.codex/attachments/985a047a-3698-4a7a-9c7e-6781d9ee4725/pasted-text.txt \
  > tests/fixtures/system_tool_schemas.json
```

Expected source SHA-256: `fd7b8088649d15e7bfb6149a4236bb64dc80a742e567bbbcf331acebb71d44ef`. Keep descriptions and parameter schemas byte-for-byte semantically equivalent; whitespace formatting is allowed to differ because measurement reserializes each object as compact JSON.

Add a fixture guard:

```python
EXPECTED_SYSTEM_TOOL_NAMES = {
    "ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute",
    "task", "write_todos", "ask_human", "reveal_file", "reveal_project", "transfer_file",
    "transfer_path", "memory_retain", "memory_recall", "memory_delete",
    "upload_url_to_sandbox", "search_skills", "search_tools",
}


def _token_count(definitions: list[dict[str, Any]]) -> int:
    encoding = tiktoken.get_encoding("o200k_base")
    return sum(
        len(
            encoding.encode(
                json.dumps(definition, ensure_ascii=False, separators=(",", ":"))
            )
        )
        for definition in definitions
    )


def test_fixture_matches_approved_system_tool_baseline() -> None:
    source = _load_schema_fixture()
    assert {item["name"] for item in source} == EXPECTED_SYSTEM_TOOL_NAMES
    assert _token_count(source) == 6981
```

Also compact-serialize the entire filtered array and assert its SHA-256 is `609dccbe1bc1f06b03d3884c02c92abc114cf322a11d5cb2c88632e847e12ec3`; this detects accidental edits independently of the name and token guards.

- [ ] **Step 2: Add failing token-budget and semantic-marker tests**

Use a pure snapshot helper that assumes entries have already been selected by the trusted registry; this helper is for deterministic reporting/tests and is not the runtime provenance gate.

```python
def test_compacted_system_tool_fixture_stays_within_token_budget() -> None:
    source = _load_schema_fixture()
    compact = compact_registered_system_tool_snapshot(source)
    assert _token_count(compact) <= 4188


@pytest.mark.parametrize(
    ("tool_name", "required_markers"),
    SEMANTIC_MARKERS.items(),
)
def test_compact_descriptions_keep_agent_decision_markers(
    tool_name: str,
    required_markers: tuple[str, ...],
) -> None:
    compact = _compact_fixture_by_name(tool_name)
    text = json.dumps(compact, ensure_ascii=False).lower()
    assert all(marker.lower() in text for marker in required_markers)
```

Add a dedicated dynamic-task fixture with `team-reviewer-backend` and `team-builder-ui` lines. Assert both names and their role descriptions survive `_compact_task_description`, and assert the parameter remains an open string.

- [ ] **Step 3: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_tool_schema_compaction.py \
  -k 'baseline or budget or marker or dynamic_task' -q
```

Expected: baseline PASS; compact budget/semantic tests FAIL until all curated rules exist.

- [ ] **Step 4: Implement all curated descriptions and parameter-description patches**

Populate all 21 specs from the Required Registry Contract. For `task`, retain the generated block between `Available agent types` and `Specify subagent_type`, while replacing only the fixed template around it:

```python
def _compact_task_description(description: str) -> str:
    match = _TASK_AVAILABLE_AGENTS_RE.search(description)
    if match is None:
        return description  # unknown upstream shape: preserve it
    available_agents = match.group("agents").strip()
    return (
        "Delegate a complex task to one stateless subagent.\n"
        f"Available types:\n{available_agents}\n"
        "Provide full context and desired output; relay its report to the user."
    )
```

Patch parameter descriptions only at explicit paths. Remove `examples` only for the known `ask_human.fields.items` block after its field names, field-type enum, defaults, and option schema have been asserted unchanged. Do not alter enum arrays.

- [ ] **Step 5: Run the full compaction test and inspect per-tool counts**

Run:

```bash
uv run pytest tests/infra/agent/test_tool_schema_compaction.py -q
```

Expected: PASS, total compact fixture at or below 4,188 tokens. If over budget, shorten duplicated curated prose or parameter descriptions; do not remove required markers or relax invariants.

- [ ] **Step 6: Commit the complete curated dataset**

```bash
git add src/infra/agent/middleware/tool_schema_compaction.py \
  tests/infra/agent/test_tool_schema_compaction.py \
  tests/fixtures/system_tool_schemas.json
git commit -m "test: enforce system tool token budget"
```

### Task 3: Add Model-Call Middleware With Per-Tool Fallback

**Files:**
- Modify: `src/infra/agent/middleware/tool_schema_compaction.py`
- Modify: `src/infra/agent/middleware/__init__.py`
- Modify: `tests/infra/agent/test_tool_schema_compaction.py`

- [ ] **Step 1: Write failing middleware tests**

Use a small request double with `tools` and an `override(**updates)` method. The handler captures the request it receives.

Cover:

1. Trusted tools are cloned before the handler.
2. Ordinary MCP tools retain object identity and full schema.
3. A same-name/same-signature untrusted tool retains identity.
4. One conversion failure logs the tool name and falls back only that tool.
5. The original `request.tools` list and every original tool remain unchanged.
6. Existing `extras`, including `_lambchat_prompt_cache_volatile`, survive on compact clones.
7. Untrusted tools explicitly named `web_search_prime`, `search_doc`, and `get_repo_structure` pass through by identity with identical OpenAI definitions.

- [ ] **Step 2: Run the middleware tests and verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_tool_schema_compaction.py -k middleware -q
```

Expected: FAIL because the middleware class/export is missing.

- [ ] **Step 3: Implement the middleware**

```python
class SystemToolSchemaCompactionMiddleware(AgentMiddleware):
    """Compact only trusted system tools in the model-facing request."""

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        compacted: list[Any] = []
        changed = False
        for tool in request.tools:
            try:
                model_tool = compact_system_tool(tool)
            except Exception:
                logger.warning(
                    "[ToolSchemaCompaction] Falling back to original schema for '%s'",
                    getattr(tool, "name", "<unknown>"),
                    exc_info=True,
                )
                model_tool = tool
            compacted.append(model_tool)
            changed = changed or model_tool is not tool

        model_request = request.override(tools=compacted) if changed else request
        return await handler(model_request)
```

Export it from `src.infra.agent.middleware.__init__`.

- [ ] **Step 4: Run the tests and verify GREEN**

```bash
uv run pytest tests/infra/agent/test_tool_schema_compaction.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the middleware**

```bash
git add src/infra/agent/middleware/tool_schema_compaction.py \
  src/infra/agent/middleware/__init__.py \
  tests/infra/agent/test_tool_schema_compaction.py
git commit -m "feat: compact model-facing system tool schemas"
```

### Task 4: Register the Ordered Middleware Tail Everywhere

**Files:**
- Create: `src/agents/core/tool_schema_middleware.py`
- Create: `tests/agents/test_tool_schema_compaction_registration.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`

- [ ] **Step 1: Write failing shared-tail and registration tests**

```python
def test_schema_tail_orders_compaction_before_prompt_cache() -> None:
    middleware = create_tool_schema_middleware_tail()
    assert [type(item) for item in middleware] == [
        SystemToolSchemaCompactionMiddleware,
        PromptCachingMiddleware,
    ]


@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_agent_uses_schema_tail_for_main_and_subagent_stacks(agent_name: str) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()
    assert source.count("create_tool_schema_middleware_tail()") == 2
    assert "SystemToolSchemaCompactionMiddleware()" not in source
    assert "PromptCachingMiddleware()" not in source
```

Also assert the subagent occurrence follows any `ToolSearchMiddleware` construction, and the main occurrence is after the main `ToolSearchMiddleware` block. The factory itself fixes compaction-before-cache order.

Add an async composition test that executes the same nested order as the registered stack. Use a real `DeferredToolManager` with pre-discovered untrusted `BaseTool` objects named `web_search_prime`, `search_doc`, and `get_repo_structure`, plus a real dynamically injected `ToolSearchTool`. Capture the request at the boundary between compaction and prompt caching:

```python
async def test_tool_search_compaction_and_cache_execute_in_order() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[web_tool, search_doc_tool, repo_structure_tool],
        session_id="session-1",
        pre_discovered_names=[
            "web_search_prime",
            "search_doc",
            "get_repo_structure",
        ],
    )
    search = ToolSearchMiddleware(deferred_manager=manager)
    compact = SystemToolSchemaCompactionMiddleware()
    cache = PromptCachingMiddleware()
    after_compaction: list[Any] = []

    async def final_handler(request):
        return request

    async def cache_layer(request):
        after_compaction.extend(request.tools)
        return await cache.awrap_model_call(request, final_handler)

    async def compact_layer(request):
        return await compact.awrap_model_call(request, cache_layer)

    result = await search.awrap_model_call(_AnthropicRequest(), compact_layer)

    search_tool = next(tool for tool in after_compaction if tool.name == "search_tools")
    assert len(search_tool.description) < len(search._get_search_tool().description)
    assert next(tool for tool in after_compaction if tool.name == "web_search_prime") is web_tool
    assert next(tool for tool in after_compaction if tool.name == "search_doc") is search_doc_tool
    assert next(tool for tool in after_compaction if tool.name == "get_repo_structure") is repo_structure_tool
    assert any((tool.extras or {}).get("cache_control") for tool in result.tools)
```

The final identity assertion is intentionally made at the post-compaction/pre-cache boundary because prompt caching may clone stable tools solely to add `cache_control`. At the final boundary, compare external tool names, descriptions, and parameter schemas rather than object identity.

- [ ] **Step 2: Run and verify RED**

```bash
uv run pytest tests/agents/test_tool_schema_compaction_registration.py -q
```

Expected: FAIL because the factory and registrations do not exist.

- [ ] **Step 3: Implement the shared tail**

```python
from langchain.agents.middleware.types import AgentMiddleware

from src.infra.agent.middleware import (
    PromptCachingMiddleware,
    SystemToolSchemaCompactionMiddleware,
)


def create_tool_schema_middleware_tail() -> list[AgentMiddleware]:
    """Run after tool injection: compact schemas, then apply cache tags."""
    return [SystemToolSchemaCompactionMiddleware(), PromptCachingMiddleware()]
```

In each of the three node modules:

- Import `create_tool_schema_middleware_tail` from `src.agents.core.tool_schema_middleware`.
- Remove the direct `PromptCachingMiddleware` import if unused.
- Replace the subagent `mw.append(PromptCachingMiddleware())` with `mw.extend(create_tool_schema_middleware_tail())`.
- Replace the main `user_middleware.append(PromptCachingMiddleware())` with `user_middleware.extend(create_tool_schema_middleware_tail())`.

- [ ] **Step 4: Run registration and neighboring middleware tests**

```bash
uv run pytest \
  tests/agents/test_tool_schema_compaction_registration.py \
  tests/agents/test_todo_middleware_registration.py \
  tests/infra/agent/test_prompt_caching_middleware.py \
  tests/infra/tool/test_tool_search_tool.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit registration**

```bash
git add src/agents/core/tool_schema_middleware.py \
  src/agents/fast_agent/nodes.py \
  src/agents/search_agent/nodes.py \
  src/agents/team_agent/nodes.py \
  tests/agents/test_tool_schema_compaction_registration.py
git commit -m "feat: enable system tool schema compaction"
```

### Task 5: Add a Reproducible Token Report

**Files:**
- Create: `scripts/report_system_tool_schema_tokens.py`
- Create: `tests/scripts/test_report_system_tool_schema_tokens.py`

- [ ] **Step 1: Write the failing CLI contract test**

Invoke the script against `tests/fixtures/system_tool_schemas.json` and assert exit code 0 plus machine-readable summary fields:

```python
assert report["tool_names"] == sorted(EXPECTED_SYSTEM_TOOL_NAMES)
assert report["before_tokens"] == 6981
assert report["after_tokens"] <= 4188
assert report["saved_tokens"] == report["before_tokens"] - report["after_tokens"]
assert report["saved_percent"] >= 40.0
```

Include per-tool `before_tokens`, `after_tokens`, and `saved_tokens`. Reject snapshots whose name set is not exactly the approved 21 tools so the report cannot silently include external MCP tools.

- [ ] **Step 2: Run and verify RED**

```bash
uv run pytest tests/scripts/test_report_system_tool_schema_tokens.py -q
```

Expected: FAIL because the script is absent.

- [ ] **Step 3: Implement the report script**

Use `argparse`, `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`, `tiktoken.get_encoding("o200k_base")`, and `compact_registered_system_tool_snapshot`. Print JSON to stdout and send errors to stderr. Do not import or initialize agent services.

Manual command:

```bash
uv run python scripts/report_system_tool_schema_tokens.py \
  tests/fixtures/system_tool_schemas.json
```

- [ ] **Step 4: Run and verify GREEN**

```bash
uv run pytest tests/scripts/test_report_system_tool_schema_tokens.py -q
uv run python scripts/report_system_tool_schema_tokens.py \
  tests/fixtures/system_tool_schemas.json
```

Expected: test PASS; report states 6,981 before, no more than 4,188 after, and at least 40 percent saved.

- [ ] **Step 5: Commit the report helper**

```bash
git add scripts/report_system_tool_schema_tokens.py \
  tests/scripts/test_report_system_tool_schema_tokens.py
git commit -m "chore: report system tool schema tokens"
```

### Task 6: Focused and Full Verification

**Files:**
- Verify only; modify production files only if a failing check exposes a defect covered by this plan.

- [ ] **Step 1: Run focused behavioral regressions**

```bash
uv run pytest \
  tests/infra/agent/test_tool_schema_compaction.py \
  tests/agents/test_tool_schema_compaction_registration.py \
  tests/scripts/test_report_system_tool_schema_tokens.py \
  tests/agents/test_todo_middleware_registration.py \
  tests/agents/core/test_subagent_prompts.py \
  tests/infra/agent/test_prompt_caching_middleware.py \
  tests/infra/tool/test_tool_search_tool.py \
  tests/infra/tool/test_internal_registry_exposure.py -q
```

Expected: PASS.

- [ ] **Step 2: Run formatting, lint, and type checks**

```bash
uv run ruff format --check \
  src/infra/agent/middleware/tool_schema_compaction.py \
  src/agents/core/tool_schema_middleware.py \
  tests/infra/agent/test_tool_schema_compaction.py \
  tests/agents/test_tool_schema_compaction_registration.py \
  scripts/report_system_tool_schema_tokens.py \
  tests/scripts/test_report_system_tool_schema_tokens.py
uv run ruff check \
  src/infra/agent/middleware/tool_schema_compaction.py \
  src/infra/agent/middleware/__init__.py \
  src/agents/core/tool_schema_middleware.py \
  src/agents/fast_agent/nodes.py \
  src/agents/search_agent/nodes.py \
  src/agents/team_agent/nodes.py \
  tests/infra/agent/test_tool_schema_compaction.py \
  tests/agents/test_tool_schema_compaction_registration.py \
  scripts/report_system_tool_schema_tokens.py \
  tests/scripts/test_report_system_tool_schema_tokens.py
make typecheck
```

Expected: all checks pass.

- [ ] **Step 3: Run the complete backend test suite**

```bash
uv run pytest -q
```

Expected: PASS. If infrastructure or external-service prerequisites prevent completion, retain the focused green results and record the exact blocker rather than weakening tests.

- [ ] **Step 4: Generate and retain final measurement evidence**

```bash
uv run python scripts/report_system_tool_schema_tokens.py \
  tests/fixtures/system_tool_schemas.json
git status --short
git diff --check HEAD~5..HEAD
```

Record before/after tokens, percentage saved, focused-test count, full-suite result, Ruff result, and Mypy result in the handoff. Confirm that `web_search_prime`, `search_doc`, and `get_repo_structure` are absent from the compacted fixture and unchanged by pass-through tests.

- [ ] **Step 5: Request final code review**

Use `superpowers:requesting-code-review` with the spec, this plan, commit range, token report, and verification output. Address only actionable findings within scope, rerun affected checks, and then use `superpowers:verification-before-completion` before claiming success.

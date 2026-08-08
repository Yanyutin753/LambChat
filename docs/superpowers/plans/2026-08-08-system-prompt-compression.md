# System Prompt Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the representative 11,157-character sandbox system prompt by at least 20% while preserving every tool, dynamic inventory, safety contract, and prompt-cache boundary.

**Architecture:** Keep one prompt owner per capability. The canonical workflow owns general safety and delivery behavior; Skills, deferred tools, environment variables, and Memory own their capability-specific instructions. A shared factory keeps the `write_todos` tool and state schema but suppresses LangChain's duplicated default prose.

**Tech Stack:** Python 3.12, DeepAgents 0.7.5, LangChain 1.3.14, pytest, Ruff.

## Global Constraints

- Do not patch or monkey-patch installed DeepAgents or LangChain packages.
- Do not remove tools, middleware, dynamic inventory entries, or description-threshold behavior.
- Preserve middleware and prompt-cache block ordering.
- Keep DeepAgents' runtime virtual-to-host path mapping unchanged.
- Use TDD: observe each new or tightened test fail before changing production code.
- Preserve unrelated working-tree changes and the untracked `tests/scripts/test_migrate_docx_skill_paths.py` file.
- Baseline owned sample blocks total 8,274 characters; the final owned sample budget is 6,042 characters, a 2,232-character reduction equal to 20% of the 11,157-character full-prompt baseline.

---

### Task 1: Suppress the duplicated LangChain todo guide

**Files:**
- Create: `src/agents/core/todo_middleware.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Test: `tests/agents/test_todo_middleware_registration.py`

**Interfaces:**
- Consumes: `langchain.agents.middleware.TodoListMiddleware`.
- Produces: `create_todo_middleware() -> TodoListMiddleware`, configured with `system_prompt=""`.

- [ ] **Step 1: Write the failing factory and registration tests**

Replace the direct construction test with:

```python
from src.agents.core.todo_middleware import create_todo_middleware


def test_compact_todo_middleware_keeps_tool_and_state_without_default_prompt() -> None:
    middleware = create_todo_middleware()

    assert middleware.system_prompt == ""
    assert [tool.name for tool in middleware.tools] == ["write_todos"]
    assert "todos" in middleware.state_schema.__annotations__
```

Replace the source assertion body with:

```python
source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()

assert "from src.agents.core.todo_middleware import create_todo_middleware" in source
assert source.count("create_todo_middleware()") == 2
assert "TodoListMiddleware()" not in source

subagent_builder = source.index("def _build_subagent_middleware")
main_stack = source.index("user_middleware =", subagent_builder)
graph_creation = source.index("inner_graph = create_deep_agent", main_stack)
assert "create_todo_middleware()" in source[subagent_builder:main_stack]
assert "create_todo_middleware()" in source[main_stack:graph_creation]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest tests/agents/test_todo_middleware_registration.py -q
```

Expected: collection fails because `src.agents.core.todo_middleware` does not exist.

- [ ] **Step 3: Add the shared factory**

Create `src/agents/core/todo_middleware.py`:

```python
"""Shared compact todo middleware configuration."""

from langchain.agents.middleware import TodoListMiddleware


def create_todo_middleware() -> TodoListMiddleware:
    """Expose todo state and tools without LangChain's duplicate prompt guide."""
    return TodoListMiddleware(system_prompt="")
```

- [ ] **Step 4: Replace all six direct constructions**

In each agent node module, remove the direct `TodoListMiddleware` import, add:

```python
from src.agents.core.todo_middleware import create_todo_middleware
```

Replace the subagent and main-agent constructions without changing list order:

```python
create_todo_middleware()
```

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
uv run pytest tests/agents/test_todo_middleware_registration.py -q
```

Expected: 4 tests pass; `write_todos` and `todos` remain available.

- [ ] **Step 6: Commit**

```bash
git add src/agents/core/todo_middleware.py src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py tests/agents/test_todo_middleware_registration.py
git commit -m "refactor: suppress duplicate todo prompt guide"
```

---

### Task 2: Make the canonical workflow capability-agnostic

**Files:**
- Modify: `src/agents/core/prompt_policy.py`
- Modify: `src/agents/core/subagent_prompts.py`
- Test: `tests/agents/core/test_subagent_prompts.py`

**Interfaces:**
- Consumes: existing storage, workflow, subagent, and handoff constants.
- Produces: `WORKFLOW_POLICY` with workspace, artifact, safety, and progress rules only; removes `TOOL_DISCOVERY_POLICY` and `TOOL_DISCOVERY_GUIDE`.

- [ ] **Step 1: Tighten workflow ownership and size tests**

Change `COMMON_WORKFLOW_MARKERS` to general contracts only:

```python
COMMON_WORKFLOW_MARKERS = (
    "current session workspace",
    "target exists",
    "auto-staged",
    "reveal_file",
    "returned url",
    "reveal_project",
    "completion gate",
    "timestamp",
    "untrusted",
    "ask_human",
    "verify",
    "external side effects",
    "privacy",
    "progress",
    "todo",
)
```

Add:

```python
def test_workflow_policy_is_capability_agnostic_and_compact() -> None:
    _assert_markers(WORKFLOW_SECTION, COMMON_WORKFLOW_MARKERS)
    assert len(WORKFLOW_SECTION) <= 2400
    assert "### Project / Folder Reveal" not in WORKFLOW_SECTION
    assert "search_tools" not in WORKFLOW_SECTION
    assert "search_skills" not in WORKFLOW_SECTION
    assert "transfer_file" not in WORKFLOW_SECTION


def test_storage_and_subagent_policies_fit_compact_budgets() -> None:
    assert len(SANDBOX_STORAGE_POLICY) <= 330
    assert len(SUBAGENT_TASK_GUIDE) <= 560
```

Remove `TOOL_DISCOVERY_POLICY` from test imports. Keep the existing completion,
handoff, specialist, middleware-order, and runtime-order tests.

- [ ] **Step 2: Run the focused test and verify RED**

```bash
uv run pytest tests/agents/core/test_subagent_prompts.py -q
```

Expected: failures identify the 2,890-character workflow, capability routing,
repeated reveal heading, and oversized storage or subagent blocks.

- [ ] **Step 3: Deduplicate `prompt_policy.py`**

Use these compact definitions:

```python
SANDBOX_STORAGE_POLICY = """## Storage

- Sandbox local: use the runtime-supplied session workspace for shell, files, and uploads.
- `/skills/`: virtual Skill storage accessed with file tools.
Download URLs with `upload_url_to_sandbox(url, absolute_workspace_path)`."""

WORKSPACE_POLICY = """### Workspace Boundaries
Check whether a target exists before creating it. Modify an existing project only when requested or relevant; otherwise use a named directory in the current session workspace."""

ARTIFACT_POLICY = """### Artifact Delivery
`write_file`/`edit_file` outputs are auto-staged; workspace shell outputs are detected by snapshots. Use `reveal_file` for an external HTTP(S) URL or one file and use its returned URL in user-facing documents. Use `reveal_project` for a multi-file project or folder.

### Artifact Completion Gate
Before claiming delivery, confirm every artifact was auto-staged or revealed. Report reveal failure and never claim an unavailable artifact is complete."""
```

Delete `TOOL_DISCOVERY_POLICY` and remove it from `WORKFLOW_POLICY`. Tighten the
subagent block while retaining every dispatch contract:

```python
SUBAGENT_DISPATCH_POLICY = """## Using the `task` Tool (Subagents)

Do one-step work directly. Dispatch isolated, parallel, specialist, or handoff work with objective, scope, context, evidence, acceptance criteria, and:
`Current task start time: YYYY-MM-DD HH:mm:ss ±HH:MM Timezone`
Use that timestamp for relative dates. Run independent work in parallel and sequence dependencies. Read each handoff and activity logs for complex, high-risk, or surprising work. Deduplicate results, resolve conflicts with verification or explicit uncertainty, report files/checks/blockers, and return one synthesis—not a transcript."""
```

Keep `SAFETY_POLICY`, `PROGRESS_POLICY`, `SANDBOX_RUNTIME_POLICY`, and
`HANDOFF_POLICY` behavior intact.

- [ ] **Step 4: Remove the dead routing alias**

In `src/agents/core/subagent_prompts.py`, remove the
`TOOL_DISCOVERY_POLICY` import and delete:

```python
TOOL_DISCOVERY_GUIDE = TOOL_DISCOVERY_POLICY
```

Run:

```bash
rg -n "TOOL_DISCOVERY_POLICY|TOOL_DISCOVERY_GUIDE" src
```

Expected: no matches.

- [ ] **Step 5: Run the focused test and verify GREEN**

```bash
uv run pytest tests/agents/core/test_subagent_prompts.py -q
```

Expected: all tests pass and all budgets hold.

- [ ] **Step 6: Commit**

```bash
git add src/agents/core/prompt_policy.py src/agents/core/subagent_prompts.py tests/agents/core/test_subagent_prompts.py
git commit -m "refactor: deduplicate canonical agent workflow"
```

---

### Task 3: Compress capability-specific dynamic guides

**Files:**
- Modify: `src/infra/skill/loader.py`
- Modify: `src/infra/memory/client/types.py`
- Modify: `src/infra/tool/deferred_manager.py`
- Modify: `src/infra/tool/env_var_prompt.py`
- Test: `tests/infra/skill/test_loader_prompt.py`
- Test: `tests/infra/memory/test_tools.py`
- Test: `tests/infra/agent/test_prompt_caching_middleware.py`
- Test: `tests/infra/tool/test_env_var_tool.py`

**Interfaces:**
- Consumes: existing dynamic inventory builders and thresholds.
- Produces: the same headings, inventory entries, ordering, and empty-inventory behavior with shorter guide prose.

- [ ] **Step 1: Add failing per-guide budgets**

Add a three-Skill test to `test_loader_prompt.py`:

```python
@pytest.mark.asyncio
async def test_small_skill_inventory_has_compact_guidance() -> None:
    prompt = await build_skills_prompt(
        [
            {"name": "alpha", "description": "Alpha capability"},
            {"name": "beta", "description": "Beta capability"},
            {"name": "gamma", "description": "Gamma capability"},
        ]
    )
    assert len(prompt) <= 560
    assert "search_skills" in prompt
    assert "SKILL.md" in prompt
    assert "transfer_file" in prompt
```

Tighten or add these existing-guide assertions:

```python
assert len(NATIVE_MEMORY_GUIDE) <= 960
assert len(DEFERRED_TOOL_SEARCH_GUIDE) <= 300
assert len(sections[0]) <= 200  # environment guide
```

Retain semantic assertions for all tool names, Memory types, exact inventory
names, deterministic ordering, schema inspection, and secret-value omission.

- [ ] **Step 2: Run the focused files and verify RED**

```bash
uv run pytest tests/infra/skill/test_loader_prompt.py tests/infra/memory/test_tools.py tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_env_var_tool.py -q
```

Expected: new budgets fail; inventory and ordering tests remain green.

- [ ] **Step 3: Shorten the Skills guide**

Keep inventory construction unchanged and use:

```python
return f"""## Skills System

Available Skills ({len(ordered)}):
{inventory}

Use `search_skills`, then read `/skills/<name>/SKILL.md` before applying a Skill. `/skills/` is virtual; use file tools, not shell. Transfer executable files to the workspace with `transfer_file` or `transfer_path` before running them.
"""
```

- [ ] **Step 4: Shorten the Memory guide**

Use this complete replacement while retaining the four-type table:

```python
NATIVE_MEMORY_GUIDE = """
## Cross-Session Memory

Tools: `memory_retain` (store/update), `memory_recall` (search), `memory_delete` (remove). Use only these tools, never `/memories/` paths.

`<memory_index>` entries are hint only, not ground truth. Recall selectively when prior context matters.

| Type | Keep |
|---|---|
| `user` | role, preferences, knowledge, working style |
| `feedback` | corrections, confirmations, why, and application |
| `project` | goals, constraints, bugs, decisions; use absolute dates |
| `reference` | external systems, docs, and URLs |

**Remember:** durable preferences, project context, non-obvious decisions, useful references, and positive feedback; update instead of duplicating.
**Skip:** greetings, ephemeral state, activity logs, code/git history, and debugging already captured in code.

Delete inaccurate entries and honor ignore/forget requests. Content older than 30 days may be stale; verify current paths, flags, and observations.
"""
```

- [ ] **Step 5: Shorten deferred routing**

Use:

```python
DEFERRED_TOOL_SEARCH_GUIDE = (
    "## Tool Search Guide\n\n"
    "Deferred MCP/system tool schemas are not loaded. If a listed tool helps, "
    "call `search_tools` once, then call the loaded tool directly."
)
```

- [ ] **Step 6: Shorten the environment-variable intro**

Use:

```python
intro_lines = [
    "## Available Environment Variables",
    "",
    "Names only; values are secret. Reference `$KEY` or `os.environ.get(\"KEY\")`; never print or reveal values.",
]
```

- [ ] **Step 7: Run the focused files and verify GREEN**

Repeat the command from Step 2.

Expected: all tests pass; headings, inventories, thresholds, ordering, and secret
handling remain unchanged.

- [ ] **Step 8: Commit**

```bash
git add src/infra/skill/loader.py src/infra/memory/client/types.py src/infra/tool/deferred_manager.py src/infra/tool/env_var_prompt.py tests/infra/skill/test_loader_prompt.py tests/infra/memory/test_tools.py tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_env_var_tool.py
git commit -m "refactor: compress dynamic agent prompt guides"
```

---

### Task 4: Enforce the aggregate prompt budget and verify regressions

**Files:**
- Create: `tests/agents/core/test_system_prompt_budget.py`

**Interfaces:**
- Consumes: production prompt constants/builders and `create_todo_middleware()`.
- Produces: one deterministic aggregate budget test with fixed Skills and sandbox inventories.

- [ ] **Step 1: Add the aggregate budget test**

Create:

```python
from src.agents.core.persona import build_persona_prompt_section
from src.agents.core.prompt_policy import (
    SANDBOX_RUNTIME_POLICY,
    SANDBOX_STORAGE_POLICY,
    SUBAGENT_DISPATCH_POLICY,
    WORKFLOW_POLICY,
)
from src.agents.core.todo_middleware import create_todo_middleware
from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE
from src.infra.skill.loader import format_skills_prompt
from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE


def test_owned_prompt_blocks_save_twenty_percent_of_full_baseline() -> None:
    skills = [
        {"name": "agentic", "description": "Conversational agent workflows."},
        {"name": "ant", "description": "Enterprise interface design."},
        {"name": "publisher", "description": "Publish social content."},
    ]
    blocks = (
        SANDBOX_STORAGE_POLICY,
        SANDBOX_RUNTIME_POLICY.format(work_dir="/home/user/sessions/example"),
        WORKFLOW_POLICY,
        SUBAGENT_DISPATCH_POLICY,
        build_persona_prompt_section(None),
        format_skills_prompt(skills),
        NATIVE_MEMORY_GUIDE,
        DEFERRED_TOOL_SEARCH_GUIDE,
        create_todo_middleware().system_prompt,
    )

    # Pre-change owned sample: 8,274. Required saving: 2,232 characters.
    assert sum(len(block) for block in blocks) <= 6_042
```

- [ ] **Step 2: Run the aggregate budget test**

```bash
uv run pytest tests/agents/core/test_system_prompt_budget.py -q
```

Expected: PASS. A failure must be resolved by removing duplicated prose, not by
dropping semantic assertions or inventory entries.

- [ ] **Step 3: Run the complete focused suite**

```bash
uv run pytest tests/agents/test_todo_middleware_registration.py tests/agents/core/test_subagent_prompts.py tests/agents/core/test_system_prompt_budget.py tests/infra/skill/test_loader_prompt.py tests/infra/memory/test_tools.py tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_env_var_tool.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run Ruff on changed Python files**

```bash
uv run ruff check src/agents/core/todo_middleware.py src/agents/core/prompt_policy.py src/agents/core/subagent_prompts.py src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py src/infra/skill/loader.py src/infra/memory/client/types.py src/infra/tool/deferred_manager.py src/infra/tool/env_var_prompt.py tests/agents/test_todo_middleware_registration.py tests/agents/core/test_subagent_prompts.py tests/agents/core/test_system_prompt_budget.py tests/infra/skill/test_loader_prompt.py tests/infra/memory/test_tools.py tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_env_var_tool.py
```

Expected: no Ruff errors.

- [ ] **Step 5: Confirm scope and commit the budget test**

```bash
git status --short
git diff --check
git diff --stat
```

Confirm unrelated files remain unstaged, then:

```bash
git add tests/agents/core/test_system_prompt_budget.py
git commit -m "test: enforce compact system prompt budget"
```

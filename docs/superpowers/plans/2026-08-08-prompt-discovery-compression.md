# Prompt and Discovery Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compress LambChat's agent-controlled system prompts while preserving every behavioral contract, exposing every available tool name, deferring non-inline internal-system schemas, and adding deterministic pinyin-aware discovery for tools and Skills.

**Architecture:** Move normalization, pinyin aliasing, required-term filtering, and fuzzy ranking into a shared lexical search module. Use one deferred manager for MCP tools and non-inline LambChat system tools, add a metadata-only `search_skills` tool, and generate deterministic progressive-disclosure inventories. Consolidate repeated agent instructions into canonical prompt sections and verify both semantic coverage and character budgets.

**Tech Stack:** Python 3.12, LangChain `BaseTool`, Pydantic 2, `pypinyin`, `difflib.SequenceMatcher`, pytest, Ruff, tiktoken/character-budget diagnostics.

**Design spec:** `docs/superpowers/specs/2026-08-08-prompt-discovery-compression-design.md`

---

## File Map

**Create**

- `src/infra/search/__init__.py` — public exports for shared discovery search.
- `src/infra/search/discovery.py` — normalized aliases, pinyin indexes, required terms, exact selection, typo matching, and deterministic ranking.
- `src/infra/skill/skill_search_tool.py` — metadata-only `search_skills` LangChain tool.
- `src/agents/core/prompt_policy.py` — canonical storage, artifact, safety, discovery, progress, and subagent contracts.
- `tests/infra/search/test_discovery.py` — shared search behavior.
- `tests/infra/skill/test_skill_search_tool.py` — `search_skills` output and limits.
- `tests/infra/tool/test_internal_registry_exposure.py` — internal inline/deferred policy splitting.
- `tests/agents/test_deferred_system_tools.py` — cross-category collision, MCP threshold, disabled-deferral, and context registration behavior.
- `tests/agents/core/test_prompt_budgets.py` — prompt length ceilings and duplicate-rule regression checks.

**Modify**

- `pyproject.toml`, `uv.lock` — add `pypinyin`.
- `src/infra/tool/tool_search.py` — adapt tool records to the shared ranking module while preserving weak-reference caching.
- `src/infra/tool/tool_search_tool.py` — compact callable schema and deterministic result formatting.
- `src/infra/tool/deferred_manager.py` — deduplicate canonical names and render complete MCP and internal-system inventories by kind.
- `src/infra/tool/internal_registry.py` — split authorized internal tools according to the existing `inline_exposure` policy.
- `src/infra/skill/loader.py`, `src/infra/skill/middleware.py` — one shared Skill inventory builder and 20/21 threshold behavior.
- `src/kernel/config/base.py`, `src/kernel/config/_definitions_tools.py` — add the Skill description threshold to runtime settings and remove the deferred prompt limit.
- `src/agents/fast_agent/context.py`, `src/agents/search_agent/context.py` — register `search_skills`; stop passing deferred prompt limits.
- `src/agents/fast_agent/nodes.py`, `src/agents/search_agent/nodes.py`, `src/agents/team_agent/nodes.py` — preserve scoped Skills prompt/tool availability in main and custom-subagent graphs.
- `src/agents/search_agent/prompt.py`, `src/agents/team_agent/prompt.py`, `src/agents/fast_agent/prompt.py` — consume canonical storage/base sections.
- `src/agents/core/subagent_prompts.py`, `src/agents/core/persona.py` — compose compact canonical rules and remove behavioral duplication.
- `src/infra/memory/client/types.py`, `src/infra/tool/env_var_prompt.py` — compact stable dynamic guides without changing behavior.
- `docs/en/env/mcp.md`, `docs/zh/env/mcp.md` — remove the obsolete deferred prompt limit and document the Skill inventory threshold.
- `tests/kernel/config/test_tool_setting_definitions.py` — verify new/removed tool-setting definitions.
- Existing tests under `tests/infra/tool/`, `tests/infra/skill/`, `tests/agents/core/`, and `tests/agents/` — migrate literal legacy assertions to semantic invariants.

## Task 1: Shared Pinyin-Aware Discovery Engine

**Files:**

- Create: `src/infra/search/__init__.py`
- Create: `src/infra/search/discovery.py`
- Create: `tests/infra/search/test_discovery.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Add failing normalization and ranking tests**

Cover exact names, `_`/`-`/`:`/space equivalence, Chinese source text, contiguous and spaced pinyin, initials, stable tie sorting, `select:`, and `+term`.

```python
def test_search_matches_full_pinyin_and_initials():
    records = [DiscoveryRecord(name="小红书发布", text="发布图文内容")]
    assert [r.name for r in search_records("xiaohongshufabu", records)] == ["小红书发布"]
    assert [r.name for r in search_records("xhsfb", records)] == ["小红书发布"]


def test_required_term_matches_pinyin_alias():
    records = [DiscoveryRecord(name="小红书发布", text="publish content")]
    assert [r.name for r in search_records("+xiaohongshu publish", records)] == ["小红书发布"]
```

- [ ] **Step 2: Add failing typo-boundary tests**

```python
def test_typo_matching_is_conservative():
    records = [DiscoveryRecord(name="小红书", text="")]
    assert [r.name for r in search_records("xiaohognshu", records)] == ["小红书"]
    assert search_records("xhb", records) == []
    assert search_records("xiaolanshu", records) == []
```

Monkeypatch the pinyin conversion helper to raise and assert record construction plus normalized non-pinyin search still work. This locks the required transliteration-failure fallback before implementation.

- [ ] **Step 3: Run the new test module and confirm RED**

Run: `uv run pytest tests/infra/search/test_discovery.py -q`

Expected: collection/import failure because `src.infra.search.discovery` does not exist.

- [ ] **Step 4: Add the dependency and shared data types**

Add `pypinyin>=0.53.0` to application dependencies and run `uv lock`. Implement immutable `DiscoveryRecord`, parsed aliases, and `DiscoveryMatch` types. The public call accepts records plus `max_results` and returns stable ranked matches.

- [ ] **Step 5: Implement exact, normalized, pinyin, required-term, and typo tiers**

Call `lazy_pinyin` behind an exception-safe helper; on any transliteration failure, return no pinyin aliases and retain raw/normalized aliases. Build contiguous full pinyin and first-letter aliases when conversion succeeds. Apply `SequenceMatcher` only when both strings have length at least four and ratio is at least `0.82`. Do not apply typo similarity to descriptions. Sort by descending score and canonical name.

- [ ] **Step 6: Run tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/infra/search/test_discovery.py -q
uv run ruff check src/infra/search tests/infra/search
```

Expected: all discovery tests pass; Ruff reports no errors.

- [ ] **Step 7: Commit the shared engine**

```bash
git add pyproject.toml uv.lock src/infra/search tests/infra/search
git commit -m "feat: add pinyin-aware discovery search"
```

## Task 2: Migrate and Compact `search_tools`

**Files:**

- Modify: `src/infra/tool/tool_search.py`
- Modify: `src/infra/tool/tool_search_tool.py`
- Modify: `tests/infra/test_tool_search_cache.py`
- Modify: `tests/infra/tool/test_tool_search_tool.py`

- [ ] **Step 1: Write failing adapter tests for pinyin and cache lifetime**

Create fake MCP and system tools whose Chinese name or description is discoverable by full pinyin and initials. Assert one query can rank both kinds. Retain the existing weak-reference cleanup assertion after results and tools are released.

- [ ] **Step 2: Write failing compact-schema tests**

Assert that the output retains `type`, `properties`, `required`, `additionalProperties`, `$defs`, `oneOf`, `anyOf`, and `allOf`; omits annotation-only top-level fields; uses compact JSON; omits score text; and preserves explicit array/string truncation markers.

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```bash
uv run pytest tests/infra/test_tool_search_cache.py tests/infra/tool/test_tool_search_tool.py -q
```

Expected: pinyin tests fail and legacy formatted schema does not satisfy the compact-output assertions.

- [ ] **Step 4: Adapt cached tools into shared discovery records**

Keep `_parse_cache` keyed by weak tool references. Store the reusable `DiscoveryRecord` and tool metadata in `_ParsedTool`; delegate query parsing and ranking to `search_records`. Preserve the public `search_tools_with_keywords()` signature and `ToolSearchResult` for callers.

- [ ] **Step 5: Implement deterministic compact result formatting**

Project the allowed top-level schema keys, recursively apply current caps, serialize with `json.dumps(..., separators=(",", ":"), ensure_ascii=False)`, and return one concise load-count header plus matched definitions. Keep the instruction that a returned schema makes the tool directly callable.

- [ ] **Step 6: Run focused tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/infra/test_tool_search_cache.py tests/infra/tool/test_tool_search_tool.py -q
uv run ruff check src/infra/tool/tool_search.py src/infra/tool/tool_search_tool.py tests/infra/tool tests/infra/test_tool_search_cache.py
```

- [ ] **Step 7: Commit tool search migration**

```bash
git add src/infra/tool/tool_search.py src/infra/tool/tool_search_tool.py tests/infra/test_tool_search_cache.py tests/infra/tool/test_tool_search_tool.py
git commit -m "feat: improve deferred tool search"
```

## Task 3: Complete Deferred MCP and System-Tool Inventories

**Files:**

- Modify: `src/infra/tool/deferred_manager.py`
- Modify: `src/infra/tool/internal_registry.py`
- Modify: `src/kernel/config/base.py`
- Modify: `src/agents/fast_agent/context.py`
- Modify: `src/agents/search_agent/context.py`
- Modify: `tests/infra/agent/test_prompt_caching_middleware.py`
- Create: `tests/infra/tool/test_internal_registry_exposure.py`
- Create: `tests/agents/test_deferred_system_tools.py`

- [ ] **Step 1: Replace the MCP truncation test with a complete-set failing test**

Construct at least 101 fake deferred tools and assert:

```python
prompt_names = parse_bullet_names(manager.get_deferred_stubs_string())
assert prompt_names == {tool.name for tool in manager.get_undiscovered_tools()}
assert all(tool.description not in prompt for tool in tools)
assert "not shown" not in prompt
```

Also add duplicate-name input with different descriptions and assert one deterministic first-wins tool plus a warning.

- [ ] **Step 2: Add failing internal-system exposure tests**

Configure authorized internal tools with and without `inline_exposure`. Assert inline tools are returned for direct registration, while non-inline tools are returned as deferred kind `system`. In a mixed manager, assert the prompt has separate sections: MCP names only, system names plus capped first-line descriptions. Add a same-name MCP/system collision and assert the system tool wins.

Add a regression where an environment-variable tool is returned by the internal registry and the context's compatibility registration path. Assert the deferred name is not appended again as a direct tool.

Add a collision matrix covering core direct, system direct/deferred, and MCP direct/deferred candidates. Assert priority `core > system > MCP`, then `direct > deferred` within a category, with exactly one surviving callable name. Add `ENABLE_DEFERRED_TOOL_LOADING=false` and assert every authorized internal and MCP tool is direct, with no deferred inventory.

- [ ] **Step 3: Run tests and confirm RED**

Run: `uv run pytest tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_internal_registry_exposure.py tests/agents/test_deferred_system_tools.py -q`

Expected: the legacy prompt omits names above its configured limit and includes descriptions.

- [ ] **Step 4: Split authorized internal tools by exposure policy**

Add a backward-compatible internal-registry API that returns direct and deferred tools after the existing authorization, role, business-permission, and quota wrapping steps. Treat missing policy as non-inline. Keep `get_internal_tools_for_user()` available for callers that still require the aggregate list, but migrate agent contexts to the split API.

When `ENABLE_DEFERRED_TOOL_LOADING=false`, bypass the exposure split for model registration and return all authorized tools as direct while retaining policy metadata for the administration UI.

- [ ] **Step 5: Deduplicate and format complete typed inventories**

Carry `mcp` versus `system` kind in deferred entries. Resolve cross-kind collisions with system-first priority, then `(server, name)`, warn on duplicates, and derive `_all_tools` from the canonical map. Format every MCP stub as `- {name}` and every system stub as `- {name}: {first_line[:120]}`. Retain one stable generic search guide plus separate dynamic inventory blocks.

Before final direct-tool and manager construction, resolve duplicate callable names across core, system, and MCP candidates with priority `core > system > MCP`, then `direct > deferred` within a category. Feed only surviving deferred candidates to the manager.

- [ ] **Step 6: Make the shared manager independent of MCP thresholds**

Store deferred internal tools during agent setup. During lazy MCP setup, first apply the existing MCP count threshold: MCP tools below the threshold remain direct, while only MCP tools that independently qualify for deferral join the deferred collection. Create the shared manager whenever deferred system tools or threshold-qualified deferred MCP tools exist. A deferred system collection must create the manager even when MCP is disabled, but it must never cause below-threshold MCP tools to become deferred.

When legacy compatibility blocks register internal tool families separately, deduplicate against the union of direct and deferred internal names so a deferred schema cannot leak back into the initial model tool list.

- [ ] **Step 7: Remove prompt-limit configuration and call sites**

Delete `DEFERRED_TOOL_PROMPT_LIMIT`, the manager constructor argument/property, overflow notes, and context arguments. Keep `DEFERRED_TOOL_THRESHOLD` and `DEFERRED_TOOL_SEARCH_LIMIT`.

- [ ] **Step 8: Run focused tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_internal_registry_exposure.py tests/agents/test_deferred_system_tools.py -q
uv run ruff check src/infra/tool/deferred_manager.py src/infra/tool/internal_registry.py src/agents/fast_agent/context.py src/agents/search_agent/context.py src/kernel/config/base.py
```

- [ ] **Step 9: Commit inventory changes**

```bash
git add src/infra/tool/deferred_manager.py src/infra/tool/internal_registry.py src/kernel/config/base.py src/agents/fast_agent/context.py src/agents/search_agent/context.py tests/infra/agent/test_prompt_caching_middleware.py tests/infra/tool/test_internal_registry_exposure.py tests/agents/test_deferred_system_tools.py
git commit -m "feat: defer internal system tools"
```

## Task 4: Add Progressive Skill Inventory and `search_skills`

**Files:**

- Create: `src/infra/skill/skill_search_tool.py`
- Create: `tests/infra/skill/test_skill_search_tool.py`
- Modify: `src/infra/skill/loader.py`
- Modify: `src/infra/skill/middleware.py`
- Modify: `src/kernel/config/base.py`
- Modify: `src/kernel/config/_definitions_tools.py`
- Modify: `docs/en/env/mcp.md`
- Modify: `docs/zh/env/mcp.md`
- Modify: `tests/infra/skill/test_loader_prompt.py`
- Create: `tests/kernel/config/test_tool_setting_definitions.py`

- [ ] **Step 1: Write failing 20/21 Skill inventory tests**

Assert that 20 Skills include all names and descriptions, while 21 Skills include all names, no descriptions, no repeated per-Skill paths, and a concise instruction to use `search_skills` then read the returned `SKILL.md`.

- [ ] **Step 2: Write failing `search_skills` tests**

Cover `select:`, Chinese/full-pinyin/initial matching, tags, stable ordering, no result beyond ten, and output fields:

```python
assert "Name: RedBookSkills" in result
assert "Path: /skills/RedBookSkills/SKILL.md" in result
assert "read" in result.lower()
assert full_skill_body not in result
```

Also assert concise actionable responses for an empty registry, a blank query, and a non-empty query with no matches. These cases must not throw or return fabricated Skills.

- [ ] **Step 3: Run tests and confirm RED**

Run: `uv run pytest tests/infra/skill/test_loader_prompt.py tests/infra/skill/test_skill_search_tool.py -q`

Expected: missing tool module and legacy Skill prompt always includes descriptions and paths.

- [ ] **Step 4: Unify Skill inventory formatting**

Create one synchronous formatting helper used by both `loader.build_skills_prompt()` and `SkillsMiddleware._build_skills_prompt()`. Add `SKILL_PROMPT_DESCRIPTION_THRESHOLD = 20` to `base.py` and `_definitions_tools.py` with a settings-definition regression test. Sort and deduplicate names; do not introduce a prompt-level count limit. Remove `DEFERRED_TOOL_PROMPT_LIMIT` from both code and the English/Chinese MCP setting tables, and document the Skill threshold.

- [ ] **Step 5: Implement metadata-only `SkillSearchTool`**

Construct immutable discovery records from filtered Skill dictionaries. Use name, description, and normalized tags as searchable metadata. Set `name="search_skills"`, a concise query schema, and a fixed result limit of ten. Return explicit short messages for blank query, empty registry, and no match. Do not read files or mutate Skill state.

- [ ] **Step 6: Run focused tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/infra/skill/test_loader_prompt.py tests/infra/skill/test_skill_search_tool.py tests/kernel/config/test_tool_setting_definitions.py -q
uv run ruff check src/infra/skill tests/infra/skill
```

- [ ] **Step 7: Commit Skill discovery**

```bash
git add src/infra/skill/loader.py src/infra/skill/middleware.py src/infra/skill/skill_search_tool.py src/kernel/config/base.py src/kernel/config/_definitions_tools.py docs/en/env/mcp.md docs/zh/env/mcp.md tests/infra/skill tests/kernel/config/test_tool_setting_definitions.py
git commit -m "feat: add progressive skill discovery"
```

## Task 5: Register `search_skills` Across Agent Graphs

**Files:**

- Modify: `src/agents/fast_agent/context.py`
- Modify: `src/agents/search_agent/context.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `tests/agents/test_disabled_skills_config_propagation.py`
- Modify: `tests/unit/agents/test_team_router.py`

- [ ] **Step 1: Add failing construction tests**

For Fast, Search, non-explicit Team, explicit Team members, and custom subagents, assert that `search_skills` is present exactly once when filtered Skills are non-empty and absent when Skills are disabled or empty. Assert that disabled Skills cannot be returned. Also assert `search_tools` is registered when only deferred system tools exist and MCP is disabled.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
uv run pytest tests/agents/test_disabled_skills_config_propagation.py tests/unit/agents/test_team_router.py -q
```

Expected: no graph currently exposes `search_skills`.

- [ ] **Step 3: Register the tool after Skill filtering**

Build the tool from `context.skills` only after whitelist/blacklist filters. Append it once to the context tool registry. When a Team member has a role-specific Skill subset, construct that member's search tool from the same subset used for its Skill prompt; do not let role-specific discovery widen the member's advertised inventory.

- [ ] **Step 4: Preserve main/subagent tool routing**

Ensure the registered tool reaches `create_deep_agent` and custom subagents through the same tool path as other local tools. Avoid a second middleware interception path unless construction tests prove the inherited tool path cannot work.

- [ ] **Step 5: Run tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/agents/test_disabled_skills_config_propagation.py tests/unit/agents/test_team_router.py -q
uv run ruff check src/agents tests/agents tests/unit/agents
```

- [ ] **Step 6: Commit agent integration**

```bash
git add src/agents/fast_agent src/agents/search_agent src/agents/team_agent tests/agents/test_disabled_skills_config_propagation.py tests/unit/agents/test_team_router.py
git commit -m "feat: expose skill search to agents"
```

## Task 6: Canonicalize and Compress Static Agent Guidance

**Files:**

- Create: `src/agents/core/prompt_policy.py`
- Modify: `src/agents/core/subagent_prompts.py`
- Modify: `src/agents/core/persona.py`
- Modify: `src/agents/fast_agent/prompt.py`
- Modify: `src/agents/search_agent/prompt.py`
- Modify: `src/agents/team_agent/prompt.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `tests/agents/core/test_subagent_prompts.py`
- Modify: `tests/unit/agents/test_team_prompt_builder.py`

- [ ] **Step 1: Convert literal prose tests into a failing semantic coverage matrix**

Define compact markers or predicates for storage, workspace boundaries, transfer-before-execute, artifact staging/reveal/resources/completion, time, untrusted input, clarification, verification, external actions, privacy, direct/deferred MCP/deferred system-tool routing, progress, todos, subagent timestamp/dispatch/handoff/synthesis, and canonical `SKILL.md` naming. Run each required matrix against the relevant main and subagent effective prompts. Add middleware/source assertions for the exact dynamic order defined below.

- [ ] **Step 2: Add failing duplicate-source tests**

Assert Search and Team sandbox base prompts consume the same canonical storage block; `/skills/` shell prohibition and artifact completion guidance each originate once in the effective static prompt; and runtime `{work_dir}` stays outside durable base prompts.

- [ ] **Step 3: Run prompt tests and confirm RED where new budgets/uniqueness apply**

Run:

```bash
uv run pytest tests/agents/core/test_subagent_prompts.py tests/unit/agents/test_team_prompt_builder.py -q
```

- [ ] **Step 4: Create canonical prompt-policy sections**

Write concise direct rules in `prompt_policy.py`, one semantic source per contract. Provide a sandbox and persistent storage base builder plus reusable artifact, safety, discovery/progress, and subagent sections. Keep compatibility exports in `subagent_prompts.py` composed from these constants.

- [ ] **Step 5: Remove persona/workflow overlap**

Keep persona behavior limited to response style and task persistence. Remove duplicate clarification, progress, verification, and tool-operation prose already provided by canonical workflow sections.

- [ ] **Step 6: Update every agent base prompt to import canonical blocks**

Fast, Search, and Team must retain their distinct roles and filesystem mode while sharing identical operational contracts. Build the static `SectionPromptMiddleware` content in this order when each block exists: canonical workflow, persona, Skills inventory, memory guide, goal/mode, sandbox runtime. Order later dynamic middleware as: environment-variable names, memory index, deferred tool inventories (`ToolSearchMiddleware`), and finally `PromptCachingMiddleware`. Fast Agent omits unavailable sandbox/env blocks but preserves the relative order. Apply the corresponding subset to custom subagents. Update tests to assert this order rather than preserving the current differing order.

- [ ] **Step 7: Run prompt tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/agents/core/test_subagent_prompts.py tests/unit/agents/test_team_prompt_builder.py -q
uv run ruff check src/agents/core src/agents/fast_agent/prompt.py src/agents/search_agent/prompt.py src/agents/team_agent/prompt.py tests/agents/core
```

- [ ] **Step 8: Commit canonical prompt policy**

```bash
git add src/agents/core src/agents/fast_agent/prompt.py src/agents/search_agent/prompt.py src/agents/team_agent/prompt.py src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py tests/agents/core/test_subagent_prompts.py tests/unit/agents/test_team_prompt_builder.py
git commit -m "refactor: compress shared agent prompts"
```

## Task 7: Compact Memory and Environment Guides; Enforce Budgets

**Files:**

- Create: `tests/agents/core/test_prompt_budgets.py`
- Modify: `src/infra/memory/client/types.py`
- Modify: `src/infra/tool/env_var_prompt.py`
- Modify: `tests/infra/memory/test_tools.py`
- Modify: `tests/infra/tool/test_env_var_prompt.py` if present, otherwise create it.
- Modify: `tests/agents/core/test_subagent_prompts.py`

- [ ] **Step 1: Add failing behavior and budget tests**

Preserve memory tools, index-is-hint semantics, four memory types, remember/skip behavior, selective recall, deletion, staleness, and `/memories/` prohibition. Preserve environment names-only and secret-value prohibition. Add the approved ceilings:

```python
assert len(main_sandbox_static_prompt) <= 6000
assert len(WORKFLOW_SECTION) <= 3800
assert len(SUBAGENT_PROMPT) <= 4800
assert len(skills_prompt_for_25) <= 1200
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
uv run pytest tests/infra/memory/test_tools.py tests/infra/tool/test_env_var_prompt.py tests/agents/core/test_prompt_budgets.py -q
```

Expected: current prompt lengths exceed the approved ceilings.

- [ ] **Step 3: Compact memory and environment prose**

Express each memory rule once in a dense table/bullet structure. Reduce the environment guide to one sentence about configured names and secrecy plus the complete sorted key list. Do not expose values or weaken retention/deletion rules.

- [ ] **Step 4: Tune canonical text without deleting semantic coverage**

If a ceiling still fails, remove formatting overhead, repeated examples, and schema-redundant explanation. Do not delete a semantic marker merely to pass the length test; revise the design explicitly if correctness cannot fit.

- [ ] **Step 5: Run focused tests and Ruff until GREEN**

Run:

```bash
uv run pytest tests/infra/memory/test_tools.py tests/infra/tool/test_env_var_prompt.py tests/agents/core/test_prompt_budgets.py tests/agents/core/test_subagent_prompts.py -q
uv run ruff check src/infra/memory/client/types.py src/infra/tool/env_var_prompt.py tests/infra/memory tests/infra/tool/test_env_var_prompt.py tests/agents/core
```

- [ ] **Step 6: Commit dynamic guide compression**

```bash
git add src/infra/memory/client/types.py src/infra/tool/env_var_prompt.py tests/infra/memory tests/infra/tool/test_env_var_prompt.py tests/agents/core
git commit -m "refactor: enforce compact prompt budgets"
```

## Task 8: Cross-Agent Regression Verification

**Files:**

- Modify only tests or implementation files needed to correct discovered regressions; do not broaden feature scope.

- [ ] **Step 1: Run the complete focused suite**

```bash
uv run pytest \
  tests/infra/search \
  tests/infra/tool \
  tests/infra/skill \
  tests/infra/memory \
  tests/infra/agent/test_prompt_caching_middleware.py \
  tests/agents/core \
  tests/agents/test_disabled_skills_config_propagation.py \
  tests/unit/agents/test_team_router.py \
  tests/unit/agents/test_team_prompt_builder.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run prompt measurements and inspect output**

Print the four measured character counts alongside the original baselines from the spec. Confirm every ceiling passes and the complete dynamic name sets are unchanged except for filtered/discovered items.

- [ ] **Step 3: Run project lint and type checks for changed backend code**

```bash
uv run ruff check src tests
make typecheck
```

Expected: Ruff reports no errors; Mypy completes without new errors.

- [ ] **Step 4: Run the full backend test suite if the environment permits**

Run: `uv run pytest -q`

If infrastructure or external-service requirements prevent completion, record the exact failing command and distinguish environment failures from code failures.

- [ ] **Step 5: Review the final diff for scope and generated files**

Run:

```bash
git status --short
git diff --check
git diff --stat HEAD~8..HEAD
```

Confirm no secrets, runtime paths, build artifacts, or unrelated refactors were introduced.

- [ ] **Step 6: Commit any final regression-only corrections**

If Step 1–5 required corrections:

```bash
git add <only-corrected-files>
git commit -m "test: verify prompt discovery compression"
```

If no corrections were needed, do not create an empty commit.

# Prompt and Discovery Compression Design

**Date:** 2026-08-08
**Status:** Approved direction; pending spec review
**Scope:** LambChat Fast, Search, Team, and subagent system prompts; deferred MCP discovery; sandbox tool inventories; Skills discovery.

## Context

LambChat currently builds its effective system prompt from agent base prompts, shared workflow guidance, persona, Skills, memory guidance and index, sandbox runtime data, environment-variable names, deferred MCP tools, and sandbox tool metadata. The resulting prompt repeats several contracts across agents and can grow sharply when tools or Skills are numerous.

Measured baselines on 2026-08-08:

| Prompt material | Characters |
|---|---:|
| Main sandbox static prompt | 11,952 |
| Shared workflow section | 7,461 |
| Search subagent prompt | 8,772 |
| Skills prompt with 25 sample Skills | 3,579 |

Deferred MCP prompts currently truncate the visible list at `DEFERRED_TOOL_PROMPT_LIMIT`, while sandbox tool prompts show at most 20 tools. This means a tool can be available but absent from the model-visible inventory. Skills have no dedicated `search_skills` tool and inject every description directly.

## Goals

1. Reduce agent-controlled static system-prompt text by 50–65% without removing any operational contract.
2. Make every filtered, undiscovered MCP tool name visible in the deferred inventory, with no prompt-level truncation.
3. Make every sandbox tool name returned by `mcporter list --json` visible; large inventories must contain names only.
4. Add `search_skills` and apply progressive disclosure to Skill metadata.
5. Support Chinese, full pinyin, spaced pinyin, pinyin initials, separator normalization, and light typo tolerance in both tool and Skill search.
6. Keep prompt blocks deterministic and ordered from stable to dynamic for prompt-cache efficiency.
7. Preserve authorization, disabled-item filtering, storage limits, and existing tool execution boundaries.

## Non-goals

- Changing user-authored persona text, Skill instructions, memory entries, or user messages.
- Making `search_tools` search sandbox tools. Sandbox tools remain discoverable and callable only through `execute` and `mcporter`.
- Returning complete `SKILL.md` content from `search_skills`; the model must read the selected file through the Skills backend.
- Replacing MongoDB or the Skills virtual filesystem.
- Introducing embeddings, a vector database, or a remote search service for discovery.

## Chosen Approach

Use a canonical prompt-policy module plus a shared lexical search engine.

Two alternatives were rejected:

- **Local text cleanup only:** low implementation cost, but leaves duplicated sources, divergent agent behavior, missing search_skills, and truncated inventories.
- **Embedding-based discovery:** supports semantic matching but adds latency, persistence, model dependencies, and operational complexity that are unnecessary for at most hundreds of metadata records.

The chosen approach keeps exact behavior local, deterministic, testable, and inexpensive.

## Prompt Architecture

### Canonical static sections

Create one canonical source for these semantic contracts:

1. **Storage and paths:** workspace ownership, `/skills/` virtual routing, shell restrictions, URL upload, and transfer-before-execute.
2. **Artifact delivery:** automatic staging, explicit reveal cases, document resource URLs, single-file versus project reveal, and the completion gate.
3. **Safety and verification:** untrusted content, clarification boundary, time handling, destructive/external actions, secrets/privacy, and verification before completion.
4. **Discovery and progress:** loaded-tool preference, deferred MCP search, sandbox `mcporter` routing, concise progress updates, and synchronized todos.
5. **Subagent contract:** dispatch threshold, timestamp propagation, complete work order, report inspection, synthesis, specialist routing, and structured handoff.

Fast, Search, Team, and subagent prompts will import these sections rather than maintaining copies. Compatibility exports such as `WORKFLOW_SECTION` and `MAIN_AGENT_PROMPT_SECTIONS` may remain, but their content must be composed from the canonical definitions.

Rules will be expressed once with direct MUST/MUST NOT language. Repeated examples, repeated warnings, redundant headings, and statements already guaranteed by tool schemas will be removed.

### Dynamic sections

Dynamic data remains in separate prompt blocks after stable guidance:

1. Persona
2. Skills inventory
3. Memory guide
4. Goal and mode state
5. Sandbox runtime path
6. Environment-variable names
7. Memory index
8. Deferred MCP names
9. Sandbox tool inventory

Each list must have deterministic sorting. Dynamic blocks must not repeat stable operating instructions.

### Prompt coverage invariant

Compression is semantic, not deletion. Tests will maintain a coverage matrix for every contract present in the current prompt:

- workspace creation and project-boundary checks;
- virtual `/skills/` access and transfer rules;
- URL upload path rules;
- artifact staging, reveal, resource URL, and completion rules;
- timestamp and time-sensitive verification;
- untrusted-content handling;
- clarification and irreversible-action boundaries;
- code/config/document verification;
- secrets and privacy-safe output;
- direct, deferred MCP, and sandbox tool routing;
- user progress and todo state;
- subagent dispatch, timestamp, handoff, report inspection, and synthesis;
- Skill selection and canonical `SKILL.md` naming;
- memory recall, retention, deletion, staleness, and virtual-path rules.

Exact legacy sentences are not compatibility requirements; observable model guidance is.

## Tool Inventory Design

### Deferred MCP tools

Deferred mode already activates only for a large tool set. Its prompt inventory therefore always contains names only:

```text
## Deferred MCP Tools
- github:create_issue
- github:list_issues
- slack:send_message
```

The list is the complete, sorted set returned by `DeferredToolManager.get_undiscovered_tools()` after disabled-tool and server filters. Descriptions, scores, schemas, hidden-count notes, and prompt limits are excluded. Discovered tools disappear from the list because their schemas are injected directly.

`DEFERRED_TOOL_PROMPT_LIMIT` becomes obsolete and will be removed from runtime construction and configuration. `DEFERRED_TOOL_SEARCH_LIMIT` remains as the maximum number of schemas loaded by one fuzzy query.

### Sandbox tools

Sandbox tools remain separate from deferred MCP tools:

- The stable guide says to use `execute`, then `mcporter list <service> --schema`, then `mcporter call`.
- With at most 20 sandbox tools, the inventory includes each name and one cleaned single-line description. It omits parameter summaries and repeated per-tool commands because the stable guide already requires schema inspection.
- Above 20 tools, the inventory contains every `server.tool` name and no descriptions, parameter summaries, or repeated per-tool commands.
- No sandbox tool is hidden, and no overflow note claims that tools were omitted.

The first-use schema-inspection requirement remains because the prompt inventory is not an invocation schema.

## Skill Inventory and `search_skills`

The Skills prompt uses a configurable description threshold with a default of 20:

- At or below 20 filtered Skills: name plus one-line description.
- Above 20 filtered Skills: every name, with no descriptions or repeated paths.

The inventory is built from the complete filtered `context.skills` collection supplied to the agent. Existing authorization and upstream storage safety limits remain unchanged; prompt formatting must not add another truncation layer.

Whenever at least one Skill is available, register a `search_skills` tool for the main agent and its custom subagents. The tool accepts the same query forms as `search_tools`:

- `select:RedBookSkills` for exact selection;
- `xiaohongshu`, `xiao hong shu`, or `xhs` for pinyin matching;
- ordinary capability keywords;
- `+term` for required terms.

Each result contains only:

- canonical Skill name;
- one-line description;
- `/skills/{name}/SKILL.md` path;
- a short instruction to read the file before applying the Skill.

It does not mutate discovery state or return complete Skill instructions.

`search_skills` returns at most 10 results. This is a constructor-level constant, not a model-controlled argument or deployment setting. Exact `select:` queries still return only the requested existing names. Ten results are sufficient for routing while bounding tool-result context.

## Shared Search Engine

Introduce a small shared discovery-ranking module used by `search_tools` and `search_skills`. Each record indexes:

- raw lowercase name and searchable metadata;
- separator-normalized tokens (`_`, `-`, `:`, and whitespace are equivalent);
- contiguous full pinyin;
- spaced pinyin tokens;
- pinyin initials;
- normalized description and Skill tags.

Use `pypinyin` for Chinese transliteration. Use the standard library `SequenceMatcher` for light typo tolerance; do not add a second fuzzy-search dependency. Typo matching applies only when both normalized strings contain at least four characters and their similarity ratio is at least `0.82`. Short aliases must match through exact, prefix, substring, or pinyin-initial rules instead of typo similarity. For example, `xiaohognshu` must match the `xiaohongshu` alias, while `xhb` must not fuzzy-match the `xhs` initials and `xiaolanshu` must not match `xiaohongshu` through the typo tier.

Ranking priority:

1. exact canonical name;
2. exact normalized name;
3. exact token, prefix, and name substring;
4. contiguous or tokenized full pinyin;
5. pinyin initials;
6. description or tags;
7. typo similarity on names and pinyin aliases.

Description typo similarity is intentionally excluded to reduce noisy matches. Required `+term` filters match across the same normalized and pinyin aliases. `select:` bypasses fuzzy ranking and performs case-insensitive exact-name selection. Equal scores sort by canonical name.

Tool-object parsing keeps the existing weak-reference cache. Skill indexes are immutable for the lifetime of the constructed `search_skills` tool.

## Search Result Context Control

`search_tools` remains the schema-loading boundary:

- Exact `select:` queries normally load one named tool.
- Fuzzy queries return only the highest-ranked results up to `DEFERRED_TOOL_SEARCH_LIMIT`.
- Each result includes the callable name, concise description, and compact callable parameter schema.
- The compact schema preserves top-level `type`, `properties`, `required`, `additionalProperties`, `$defs`, `oneOf`, `anyOf`, and `allOf` when present. Nested values under those fields are preserved recursively subject to the existing array-item and string-length safety caps. Other annotation-only top-level fields are omitted.
- A capped array receives the existing explicit `... schema truncated, N more item(s) omitted` sentinel entry; a capped string receives the corresponding omitted-character suffix. These markers are prompt metadata and are not treated as executable JSON Schema.
- Output uses compact JSON rather than indentation. It omits ranking scores and repeated per-result call guidance. One concise header identifies newly loaded versus already available counts, followed by the matched definitions.
- Schema safety caps remain to prevent unbounded third-party schemas.

`search_skills` returns at most 10 results because results are routing hints rather than callable schemas.

## Error Handling

- Empty query or empty registry returns a concise actionable message.
- No-match responses tell the model to use another keyword or an exact visible name.
- Pinyin generation failures fall back to normalized text search and never break tool construction.
- Malformed third-party tool schemas retain the current empty-schema fallback.
- Duplicate canonical tool names are resolved before prompt or search construction. After sorting by `(server, canonical name)`, the first tool wins and later duplicates are ignored with a warning. This makes prompt, search, and invocation use the same object deterministically. Duplicate Skill names are resolved by the already-effective Skill mapping before the list reaches the prompt builder.
- Disabled or unauthorized items are never reintroduced by search.
- Prompt builders return an empty section when the corresponding capability is unavailable.

## Configuration

- Add `SKILL_PROMPT_DESCRIPTION_THRESHOLD`, default `20`.
- Keep `DEFERRED_TOOL_THRESHOLD` and `DEFERRED_TOOL_SEARCH_LIMIT`.
- Remove `DEFERRED_TOOL_PROMPT_LIMIT` after all call sites and tests migrate.
- Add `pypinyin` to application dependencies and refresh `uv.lock`.

## Verification and Acceptance Criteria

Implementation follows red-green-refactor TDD.

### Discovery tests

- A deferred registry containing more than 100 tools exposes every undiscovered name exactly once and no description.
- The prompt name set exactly equals the manager's filtered, undiscovered name set.
- Discovered and disabled tools are absent; ordering is stable.
- Sandbox inventories above 20 expose every `server.tool` name and no metadata.
- Skill inventories exercise the 20/21 boundary and never add prompt-level truncation.
- `search_skills` returns canonical name, description, path, and read-next instruction.
- Both searches match Chinese, full pinyin, spaced pinyin, initials, separator variants, and one light typo.
- `select:` and `+term` retain deterministic semantics.

### Prompt tests

- The semantic coverage matrix passes for Fast, Search, Team, and every subagent prompt.
- `/skills/` shell prohibition and transfer-before-execute instructions have one canonical source.
- Artifact, safety, privacy, verification, time, discovery, and handoff rules remain present.
- Stable and dynamic sections remain separate and deterministic.
- Baseline budgets after refactoring:
  - main sandbox static prompt: at most 6,000 characters;
  - shared workflow material: at most 3,800 characters;
  - Search subagent prompt: at most 4,800 characters;
  - 25-Skill names-only inventory plus guide: at most 1,200 characters.

Budgets are regression ceilings, not targets to fill. If a necessary rule cannot fit a ceiling, correctness wins and the design must be revisited explicitly rather than silently deleting the rule.

### Focused verification

```bash
uv run pytest \
  tests/infra/tool \
  tests/infra/skill \
  tests/agents/core \
  tests/test_sandbox_mcp_prompt_guidance.py -q

uv run ruff check src/infra/tool src/infra/skill src/agents tests
```

Agent construction tests must additionally confirm that `search_skills` is available in Fast, Search, Team, and custom-subagent tool paths when Skills exist.

## Rollout Risk

The largest risk is preserving literal-string tests while improving wording. Tests should migrate from long sentence matching to behavioral assertions and compact semantic markers. The second risk is fuzzy-search noise; exact and name matches must dominate, typo matching must use a conservative threshold, and deterministic tie-breaking is required. The third risk is accidentally conflating deferred MCP tools with sandbox tools; separate headings, tools, and invocation rules remain mandatory.

No deployment data migration is required. The change affects prompt construction, local ranking, dependency packaging, and tests.

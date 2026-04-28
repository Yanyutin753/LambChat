# Assistant System Prompt Marketplace Design

## Summary

Add a first-class `assistant` entity that powers a public assistant marketplace and a user's private assistant library. In phase 1, each assistant only carries presentation metadata and a `system_prompt`, which is injected into the agent at runtime. The design reserves fields for future assistant-bound skills, model defaults, and tool preferences without implementing those behaviors yet.

## Problem

The current system has `skills`, which tell the agent what capabilities and workflows are available, but it does not have a stable assistant layer that defines how the agent should behave for a specific use case. Users want something closer to an assistant plaza:

- Admins can publish shared assistants.
- Users can browse and use those assistants.
- Users can create and save their own assistants.
- Users can copy a public assistant into their own library and customize it.

At the same time, phase 1 should stay lightweight. We do not want to build a full bundled assistant runtime yet. We only need an assistant record that can inject a system prompt into the existing agent prompt chain.

## Goals

- Create a durable `assistant` data model in the database.
- Support both public marketplace assistants and user-private assistants.
- Allow users to clone a public assistant into their own library.
- Inject the selected assistant's `system_prompt` into the agent prompt chain.
- Store a session-level prompt snapshot so old conversations stay stable even if the source assistant changes later.
- Reuse the existing chat, session, and prompt middleware architecture.

## Non-Goals

- No assistant-bound skill installation or activation in phase 1.
- No assistant-specific model enforcement in phase 1.
- No automatic sync from a public assistant to user clones.
- No assistant recommendation engine.
- No version diff or historical rollback UI.

## Data Model

Use a dedicated MongoDB collection, `assistants`.

### Document Shape

```python
{
    "_id": ObjectId,
    "assistant_id": str,                # stable external id
    "name": str,
    "description": str,
    "system_prompt": str,

    "scope": str,                      # "public" | "private"
    "created_by": str | None,          # admin id for public, user id for private
    "is_active": bool,

    "tags": list[str],
    "avatar_url": str | None,

    "cloned_from_assistant_id": str | None,
    "version": str,                    # default "1.0.0"

    # Reserved for future phases
    "bound_skill_names": list[str],
    "default_model": str | None,
    "default_agent_options": dict,
    "default_disabled_tools": list[str],
    "default_disabled_skills": list[str],

    "created_at": datetime,
    "updated_at": datetime,
}
```

### Phase 1 Required Fields

Phase 1 logic only depends on:

- `assistant_id`
- `name`
- `description`
- `system_prompt`
- `scope`
- `created_by`
- `is_active`
- `tags`
- `cloned_from_assistant_id`
- `created_at`
- `updated_at`

The reserved fields should still be stored so the schema grows forward cleanly.

### Indexes

- Unique: `assistant_id`
- Query: `(scope, is_active, updated_at DESC)`
- Query: `(created_by, updated_at DESC)`
- Query: `tags`
- Query: `cloned_from_assistant_id`

If search remains regex-based in phase 1, no extra text index is required yet.

## Ownership Model

Use one collection with two scopes:

- `public`: marketplace assistants managed by admins
- `private`: user-owned assistants

This keeps storage simple while still supporting both use cases.

### Public Assistants

- Created and updated by admins.
- Visible in the marketplace.
- Can be used directly in a session.
- Can be cloned by users.

### Private Assistants

- Created by a user or cloned from a public assistant.
- Visible only to the owner.
- Fully editable by the owner.

### Cloning

Cloning creates a new `private` assistant document with:

- copied `name`, `description`, `system_prompt`, and `tags`
- `created_by = current_user`
- `scope = "private"`
- `cloned_from_assistant_id = source.assistant_id`

There is no automatic downstream sync after cloning.

## Session Integration

The session should store both assistant identity and the exact prompt snapshot used by the conversation.

### Session Metadata Fields

Store these under `session.metadata`:

```python
{
    "assistant_id": str | None,
    "assistant_name": str | None,
    "assistant_prompt_snapshot": str | None,
}
```

### Why Snapshot the Prompt

The source assistant can change over time, especially for public assistants maintained by admins. Without a snapshot, an old session could behave differently after an assistant edit. The snapshot makes each conversation stable.

### Runtime Resolution Rule

When a run starts:

1. If `session.metadata.assistant_prompt_snapshot` exists, use it.
2. Otherwise, if an `assistant_id` is provided, load the assistant and snapshot its current `system_prompt` into the session.
3. If neither exists, no assistant prompt is injected.

This rule supports both stable existing sessions and newly selected assistants.

## Prompt Injection Architecture

Phase 1 should reuse the existing prompt middleware pattern in `search_agent`.

### Injection Order

Recommended order:

1. Base system prompt
2. Workflow and subagent guide
3. Assistant system prompt
4. Skills prompt
5. Memory guide

This preserves platform guardrails while allowing the assistant to shape task style and persona before skills and memory add capabilities and context.

### Backend Changes

Add assistant loading into the request/session path, then append a new assistant prompt section during graph construction.

Expected touch points:

- session/chat request handling: resolve selected assistant and update session metadata
- `src/agents/search_agent/nodes.py`: append `assistant_prompt` to `_prompt_sections`
- matching fast agent path if it shares the same prompt architecture

The assistant prompt should be injected with the same middleware style already used for skills and memory so it stays cache-friendly and easy to reason about.

## Backend Architecture

### Storage Layer

Add a dedicated storage module, for example:

- `src/infra/assistant/storage.py`

Responsibilities:

- create assistant
- update assistant
- soft-validate ownership and scope rules
- list marketplace assistants
- list a user's assistants
- clone assistant
- get assistant by id
- optional activate/deactivate for admin moderation

### Manager Layer

Add a thin service layer if needed:

- `src/infra/assistant/manager.py`

This layer should handle:

- marketplace visibility rules
- clone semantics
- runtime assistant lookup for chat requests
- snapshot preparation

### API Surface

Phase 1 API should stay small:

- `GET /api/assistants`
  - supports `scope=public|mine|all`, `search`, `tags`
- `GET /api/assistants/{assistant_id}`
- `POST /api/assistants`
  - create private assistant
- `PATCH /api/assistants/{assistant_id}`
  - owner edits private assistant, admin edits public assistant
- `DELETE /api/assistants/{assistant_id}`
- `POST /api/assistants/{assistant_id}/clone`
  - create a private copy from a public assistant
- `POST /api/assistants/{assistant_id}/select`
  - attach assistant to a session and write the snapshot

`/select` can accept `session_id` and update:

- `assistant_id`
- `assistant_name`
- `assistant_prompt_snapshot`

An alternative is to pass `assistant_id` through the existing chat request and let the chat route perform the snapshot write. Either is valid. The simpler implementation is whichever reuses existing session update code with the fewest moving parts.

## Frontend Shape

Phase 1 frontend does not need a heavy standalone experience yet.

### Minimum UX

- A marketplace view for public assistants
- A "My Assistants" view for private assistants
- A selector in chat to choose the current session assistant
- A lightweight create/edit form with:
  - name
  - description
  - tags
  - system prompt

### Marketplace Behavior

- Browse public assistants
- Search and filter by tags
- Use directly in a chat session
- Clone to personal library

### My Assistants Behavior

- Create private assistants
- Edit private assistants
- Delete private assistants
- Start chat with a selected assistant

This is enough to support the YubbChat-inspired assistant plaza flow without building a complex detail page in phase 1.

## Permissions

Suggested permission split:

- `assistant:read`
- `assistant:write`
- `assistant:marketplace_read`
- `assistant:marketplace_admin`

If the project prefers to avoid new permission types in phase 1, marketplace read can reuse ordinary authenticated access and admin mutation can follow existing admin checks.

## Migration and Rollout

### Initial Rollout

1. Add assistant collection and indexes.
2. Add storage and API.
3. Add session metadata fields and selection flow.
4. Inject assistant prompt into the agent prompt chain.
5. Add minimal marketplace and personal assistant UI.

### Backward Compatibility

Existing sessions without assistant metadata continue to work unchanged.

Existing chat flows without an assistant selection behave exactly as they do now.

## Testing

Add focused tests for:

- storage CRUD and visibility filtering
- clone behavior preserves source link and copies prompt fields
- chat/session selection writes `assistant_prompt_snapshot`
- runtime resolution prefers snapshot over live assistant lookup
- prompt injection order includes assistant prompt before skills and memory
- permissions for public vs private mutations

Frontend coverage can stay focused on selector and create/edit flows.

## Future Phases

Once phase 1 is stable, the same assistant model can expand to:

- bind selected skills to an assistant
- bind default model and tool preferences
- richer marketplace detail pages
- assistant import/export
- usage stats and recommendations

Because the collection already reserves these fields, those upgrades should not require a schema reset.

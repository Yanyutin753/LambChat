# Session Pin-to-Top & Task Status Indicator Design

**Date**: 2026-08-16
**Status**: Approved

## Overview

Two related sidebar enhancements:

1. **Pin to top**: Pinned sessions appear first within each project's session list. Triggered via right-click context menu, reusing the existing `SessionMenu` component.
2. **Task running indicator**: Sessions with active tasks (`task_status: "running"` or `"pending"`) show an animated indicator in the sidebar.

## Requirements

### Pin to Top
1. Users can pin/unpin sessions via right-click context menu
2. Pinned sessions sort to the top within each project list (uncategorized, per-project, favorites)
3. No separate "Pinned" group — pinned sessions lead within their existing list context
4. No quantity limit on pinned sessions
5. Mobile: no right-click available; existing "..." menu gets the pin option as well

### Task Running Indicator
6. Sessions with `task_status === "running"` or `"pending"` show a spinning/animated indicator
7. Indicator appears on the `SessionItem` row in the sidebar
8. `BackendSession` type must include `task_status` field (backend already returns it)

## Architecture

### Data Flow

```
User right-clicks SessionItem
  -> onContextMenu sets cursorPosition, opens SessionMenu
  -> User clicks "Pin to top"
  -> sessionApi.togglePin(sessionId)
  -> POST /api/sessions/{id}/pin
  -> Backend toggles metadata.is_pinned, returns updated session
  -> Frontend reconciles session across all lists
  -> Backend sort automatically places pinned sessions first
```

### Key Files to Modify

| Layer | File | Change |
|-------|------|--------|
| Backend API | `src/api/routes/session.py` | Add `POST /{id}/pin` route |
| Backend Storage | `src/infra/session/storage.py` | Add `toggle_pin()` method; modify sort in `list_sessions()` |
| Frontend API | `frontend/src/services/api/session.ts` | Add `togglePin()` method; add `task_status` to `BackendSession` |
| Frontend Menu | `frontend/src/components/sidebar/SessionMenu.tsx` | Add cursor positioning mode + pin menu item |
| Frontend Item | `frontend/src/components/sidebar/SessionItem.tsx` | Wire onContextMenu to open SessionMenu; add task running indicator |
| Frontend Actions | `frontend/src/hooks/useSessionSidebarActions.ts` | Add `handleTogglePin` handler |
| Frontend List | `frontend/src/components/panels/SidebarParts/SessionListContent.tsx` | Pass `isPinned`/`onTogglePin` to SessionItem |
| Frontend Project | `frontend/src/components/sidebar/ProjectItem.tsx` | Pass `isPinned`/`onTogglePin` to SessionItem |
| Frontend Helper | `frontend/src/components/sidebar/sessionPin.ts` | New file: `isSessionPinned()` |
| i18n | `frontend/src/i18n/locales/*.json` (5 files) | Add `sidebar.pinToTop` / `sidebar.unpinFromTop` |

## Backend Design

### Toggle API Route

`POST /api/sessions/{session_id}/pin`

Mirrors the existing `toggle_favorite` route (`src/api/routes/session.py:693-725`):

1. Verify session ownership
2. Read current `metadata.is_pinned` (default `false`)
3. Toggle to opposite value
4. `find_one_and_update` with `$set: {"metadata.is_pinned": new_value}` and bump `updated_at`
5. Return `{ status: "pinned" | "unpinned", is_pinned: bool, session: BackendSession }`

### Storage: `toggle_pin()` method

New method on `SessionStorage` at `src/infra/session/storage.py`, mirroring `toggle_favorite()` (lines 881-934):

```python
async def toggle_pin(self, session_id: str, user_id: str) -> dict:
    doc = await self.collection.find_one({"_id": ObjectId(session_id), "user_id": user_id})
    current = bool(doc.get("metadata", {}).get("is_pinned", False))
    new_value = not current
    updated = await self.collection.find_one_and_update(
        {"_id": ObjectId(session_id)},
        {"$set": {"metadata.is_pinned": new_value, "updated_at": datetime.utcnow()}},
        return_document=ReturnDocument.AFTER,
    )
    return {
        "status": "pinned" if new_value else "unpinned",
        "is_pinned": new_value,
        "session": self._to_model_dict(updated),
    }
```

### Sort Change

`src/infra/session/storage.py` line 435, change from:

```python
.sort({"updated_at": -1})
```

To:

```python
.sort([("metadata.is_pinned", -1), ("updated_at", -1)])
```

MongoDB sort order: `true (1) > false (0) > missing (None)`. Pinned sessions sort first; unpinned sessions maintain `updated_at` ordering. No index change needed initially.

## Frontend Design

### API Client

`frontend/src/services/api/session.ts` — new method:

```typescript
togglePin: async (sessionId: string) => {
  return apiClient.post<{ status: string; is_pinned: boolean; session: BackendSession }>(
    `/sessions/${sessionId}/pin`
  );
}
```

### SessionMenu Changes

**Cursor positioning mode:**
- New prop: `cursorPosition?: { x: number; y: number }`
- When `cursorPosition` is set, compute `menuStyle` as `position: fixed; left: x; top: y`
- Boundary detection: if menu would overflow viewport bottom, flip upward; if overflow right, flip left
- Mobile branch unchanged (still renders as bottom sheet)

**Pin menu item:**
- New props: `onTogglePin?: () => void`, `isPinned?: boolean`
- Placed after the Favorite button (line 183), before Share (line 186)
- Uses lucide-react `Pin` icon (already used in persona components)
- Highlighted style when pinned (amber accent, same pattern as favorite)

### SessionItem Right-Click

`SessionItem.tsx` — modify `onContextMenu` handler (currently lines 200-204):

1. `e.preventDefault()` — suppress browser default menu
2. If `isDragging`, return early (existing guard)
3. Set `cursorPosition` state to `{ x: e.clientX, y: e.clientY }`
4. Set `isMenuOpen = true`

New props: `onTogglePin`, `isPinned`, passed through to `SessionMenu`.

### Action Handler

`useSessionSidebarActions.ts` — new `handleTogglePin(sessionId: string)`:

1. Call `sessionApi.togglePin(sessionId)`
2. On success: reconcile updated session across uncategorized list, project refs, and favorites ref
3. Show toast: `t("sidebar.pinned")` or `t("sidebar.unpinned")`

### Pin State Helper

New file `frontend/src/components/sidebar/sessionPin.ts`:

```typescript
import type { BackendSession } from "../../services/api/session";

export function isSessionPinned(session: BackendSession): boolean {
  return session.metadata?.is_pinned === true;
}
```

### i18n Keys

| Key | en | zh | ja | ko | ru |
|-----|----|----|----|----|-----|
| `sidebar.pinToTop` | Pin to top | 置顶 | ピン留め | 고정 | Закрепить |
| `sidebar.unpinFromTop` | Unpin | 取消置顶 | ピン留めを外す | 고정 해제 | Открепить |
| `sidebar.pinned` | Pinned | 已置顶 | ピン留めしました | 고정됨 | Закреплено |
| `sidebar.unpinned` | Unpinned | 已取消置顶 | ピン留めを外しました | 고정 해제됨 | Откреплено |

## Task Running Indicator Design

### Backend

No backend changes needed. The `Session` model already has `task_status: Optional[str]` (`pending`, `running`, `completed`, `failed`) and it's returned in API responses.

### Frontend Type

Add `task_status` to `BackendSession` interface in `frontend/src/services/api/session.ts`:

```typescript
export interface BackendSession {
  // ... existing fields
  task_status?: string | null;  // "pending" | "running" | "completed" | "failed"
}
```

### SessionItem Indicator

In `SessionItem.tsx`, when `session.task_status === "running"` or `session.task_status === "pending"`:

- Show a small spinning indicator (CSS `@keyframes spin` or Tailwind `animate-spin`) to the left of the session title
- Use a small dot or circle (matching the existing unread badge size ~10px) with a spinning animation
- Color: use the primary/accent color (e.g., `blue-500`) to differentiate from the red unread badge
- The indicator replaces no existing element — it's inserted between the selection checkbox (if in selection mode) and the title text

### Visual Design

```
[checkbox] [🔄 spinner] Session Title          ... [unread badge]
                       ^-- small animated blue dot when task is running
```

- Spinner: 10px blue circle with `animate-spin`, `opacity-70` to be subtle
- Positioned before the title text, aligned vertically
- Only shown when task is actively running/pending; hidden when `completed`, `failed`, or `null`

## Testing

| Type | File | Covers |
|------|------|--------|
| Backend unit | `tests/unit/test_session_pin.py` | `toggle_pin`: initial pin, unpin, concurrent toggle, missing session |
| Backend route | `tests/unit/test_session_routes_pin.py` | API: ownership check, response format, unauthorized rejection |
| Frontend unit | `components/sidebar/__tests__/sessionPin.test.ts` | `isSessionPinned` helper |
| Frontend component | `components/sidebar/__tests__/SessionMenu.test.tsx` | Right-click menu rendering, cursor positioning, pin item visibility |
| Frontend component | `components/sidebar/__tests__/SessionItem.test.tsx` (extend) | Task running indicator visibility for running/pending/completed/null |

## Edge Cases

- **Missing `is_pinned` field**: Treated as `false` via `metadata?.is_pinned === true` check
- **Concurrent toggle**: Backend `find_one_and_update` is atomic
- **Right-click during drag**: Guarded by existing `isDragging` check — menu won't open
- **Mobile**: No right-click; pin option also added to the existing "..." hover menu
- **Search results**: Search queries use the same `list_sessions` sort, so pinned results appear first in search. This is acceptable behavior.

## Out of Scope

- No new database index (data volume doesn't warrant it initially)
- No drag-to-reorder within pinned sessions
- No separate "Pinned" section/group in sidebar
- No search result sort exemption

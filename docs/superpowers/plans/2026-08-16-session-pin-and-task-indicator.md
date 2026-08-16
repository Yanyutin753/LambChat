# Session Pin-to-Top & Task Status Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session pin-to-top (via right-click context menu) and a task running indicator in the sidebar.

**Architecture:** Backend stores pin state as `metadata.is_pinned` on session documents, toggled via a new API route. Backend sort places pinned sessions first. Frontend reuses the existing `SessionMenu` with a new cursor-positioning mode for right-click triggers. Task running status uses the existing `task_status` field with an animated indicator.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), MongoDB, TailwindCSS, lucide-react icons

## Global Constraints

- Pin state stored as `metadata.is_pinned` (boolean) on session documents — follows `metadata.is_favorite` precedent
- Backend API route: `POST /api/sessions/{session_id}/pin` returning `{ status, is_pinned, session }`
- Backend sort: `[("metadata.is_pinned", -1), ("updated_at", -1)]` replaces single-field sort
- No new database indexes
- Right-click triggers the existing `SessionMenu` with cursor positioning; "..." button also gets the pin option
- Task running indicator shows for `task_status === "running"` or `"pending"` only
- i18n: 5 locales (en, zh, ja, ko, ru)

---

### Task 1: Backend Storage — `toggle_pin()` method

**Files:**
- Modify: `src/infra/session/storage.py:934` (after `toggle_favorite`)

**Interfaces:**
- Consumes: `ObjectId` from `bson`, `utc_now` from existing imports, `Session` model, `ReturnDocument`
- Produces: `toggle_pin(session_id: str, user_id: str) -> Optional[Session]` — returns updated `Session` or `None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_session_pin.py`:

```python
"""Tests for session pin toggle functionality."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from bson import ObjectId

from src.infra.session.storage import SessionStorage


@pytest.fixture
def storage():
    return SessionStorage()


@pytest.mark.asyncio
async def test_toggle_pin_initial_pin(storage):
    """Pinning an unpinned session sets is_pinned=True."""
    session_id = str(ObjectId())
    user_id = "user_1"
    now_mock = "2026-08-16T00:00:00"

    fake_doc = {
        "_id": ObjectId(session_id),
        "user_id": user_id,
        "metadata": {},
        "updated_at": "2026-08-15T00:00:00",
        "name": "Test Session",
    }
    updated_doc = {
        **fake_doc,
        "metadata": {"is_pinned": True},
        "updated_at": now_mock,
    }

    storage.collection = MagicMock()
    storage.collection.find_one = AsyncMock(return_value=fake_doc)
    storage.collection.find_one_and_update = AsyncMock(return_value=updated_doc)
    storage._build_session = MagicMock(return_value=MagicMock(
        metadata={"is_pinned": True},
    ))

    with patch("src.infra.session.storage.utc_now", return_value=now_mock):
        result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.metadata["is_pinned"] is True
    storage.collection.find_one_and_update.assert_called_once()


@pytest.mark.asyncio
async def test_toggle_pin_unpin(storage):
    """Unpinning a pinned session sets is_pinned=False."""
    session_id = str(ObjectId())
    user_id = "user_1"

    fake_doc = {
        "_id": ObjectId(session_id),
        "user_id": user_id,
        "metadata": {"is_pinned": True},
        "updated_at": "2026-08-15T00:00:00",
        "name": "Test Session",
    }
    updated_doc = {
        **fake_doc,
        "metadata": {"is_pinned": False},
        "updated_at": fake_doc["updated_at"],
    }

    storage.collection = MagicMock()
    storage.collection.find_one = AsyncMock(return_value=fake_doc)
    storage.collection.find_one_and_update = AsyncMock(return_value=updated_doc)
    storage._build_session = MagicMock(return_value=MagicMock(
        metadata={"is_pinned": False},
    ))

    result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.metadata["is_pinned"] is False


@pytest.mark.asyncio
async def test_toggle_pin_session_not_found(storage):
    """Returns None when session doesn't exist."""
    storage.collection = MagicMock()
    storage.collection.find_one = AsyncMock(return_value=None)

    result = await storage.toggle_pin("nonexistent", "user_1")
    assert result is None


@pytest.mark.asyncio
async def test_toggle_pin_wrong_user(storage):
    """Returns None when session belongs to a different user."""
    session_id = str(ObjectId())
    fake_doc = {
        "_id": ObjectId(session_id),
        "user_id": "other_user",
        "metadata": {},
    }

    storage.collection = MagicMock()
    storage.collection.find_one = AsyncMock(return_value=fake_doc)

    result = await storage.toggle_pin(session_id, "user_1")
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/test_session_pin.py -v`
Expected: FAIL — `AttributeError: 'SessionStorage' object has no attribute 'toggle_pin'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/infra/session/storage.py` after the `toggle_favorite` method (after line 934):

```python
async def toggle_pin(
    self,
    session_id: str,
    user_id: str,
) -> Optional[Session]:
    """Toggle a session's pinned-to-top state."""

    doc = await self.collection.find_one(
        {"_id": ObjectId(session_id), "user_id": user_id},
    )
    if not doc:
        return None

    current_pinned = bool(doc.get("metadata", {}).get("is_pinned", False))
    next_pinned = not current_pinned

    result = await self.collection.find_one_and_update(
        {"_id": ObjectId(session_id), "user_id": user_id},
        {
            "$set": {
                "metadata.is_pinned": next_pinned,
                "updated_at": utc_now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not result:
        return None

    return self._build_session(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/test_session_pin.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_session_pin.py src/infra/session/storage.py
git commit -m "feat(session): add toggle_pin storage method"
```

---

### Task 2: Backend — Sort change in `list_sessions()`

**Files:**
- Modify: `src/infra/session/storage.py:435`

**Interfaces:**
- Consumes: nothing new
- Produces: pinned sessions sorted before unpinned in all list queries

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_session_pin.py`:

```python
@pytest.mark.asyncio
async def test_list_sessions_pinned_first(storage):
    """Pinned sessions appear before unpinned in list results."""
    user_id = "user_1"

    unpinned_doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "is_active": True,
        "metadata": {},
        "updated_at": "2026-08-16T12:00:00",
        "name": "Unpinned Session",
    }
    pinned_doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "is_active": True,
        "metadata": {"is_pinned": True},
        "updated_at": "2026-08-16T10:00:00",  # older but should be first
        "name": "Pinned Session",
    }

    # Mock find() to return a cursor-like with sort
    mock_cursor = MagicMock()
    mock_cursor.skip = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[pinned_doc, unpinned_doc])

    storage.collection = MagicMock()
    storage.collection.find = MagicMock(return_value=mock_cursor)
    storage.collection.count_documents = AsyncMock(return_value=2)
    storage._build_session = MagicMock(side_effect=lambda d, **kw: MagicMock(
        id=str(d["_id"]),
        metadata=d.get("metadata", {}),
    ))

    sessions, total = await storage.list_sessions(
        user_id=user_id, skip=0, limit=20,
    )

    # Verify sort was called with pinned first
    mock_cursor.sort.assert_called_once_with(
        [("metadata.is_pinned", -1), ("updated_at", -1)]
    )
    assert total == 2
    assert len(sessions) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/test_session_pin.py::test_list_sessions_pinned_first -v`
Expected: FAIL — sort assertion fails (currently sorts by `("updated_at", -1)` only)

- [ ] **Step 3: Implement sort change**

In `src/infra/session/storage.py`, change line 435 from:

```python
cursor = self.collection.find(query).skip(skip).limit(limit).sort("updated_at", -1)
```

To:

```python
cursor = (
    self.collection.find(query)
    .skip(skip)
    .limit(limit)
    .sort([("metadata.is_pinned", -1), ("updated_at", -1)])
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/test_session_pin.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/infra/session/storage.py tests/unit/test_session_pin.py
git commit -m "feat(session): sort pinned sessions before unpinned in list"
```

---

### Task 3: Backend — Pin toggle API route

**Files:**
- Modify: `src/api/routes/session.py:725` (after the `/favorite` route)

**Interfaces:**
- Consumes: `SessionStorage.toggle_pin()`, `verify_session_ownership()`, `get_current_user_required`, `_normalize_session()`
- Produces: `POST /api/sessions/{session_id}/pin` returning `{ status, is_pinned, session }`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_session_routes_pin.py`:

```python
"""Tests for session pin toggle API route."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.api.routes.session import router


@pytest.mark.asyncio
async def test_toggle_pin_success():
    """Pin toggle returns correct status and session."""
    from src.api.deps import TokenPayload

    session_id = "abc123"
    user = TokenPayload(sub="user_1", exp=9999999999)

    mock_session = MagicMock()
    mock_session.user_id = "user_1"
    mock_session.metadata = {"is_pinned": True}

    mock_manager = AsyncMock()
    mock_manager.get_session = AsyncMock(return_value=mock_session)

    mock_storage = AsyncMock()
    mock_storage.toggle_pin = AsyncMock(return_value=mock_session)

    mock_normalized = MagicMock()
    mock_normalized.metadata = {"is_pinned": True}

    with (
        patch("src.api.routes.session.SessionManager", return_value=mock_manager),
        patch("src.api.routes.session.SessionStorage", return_value=mock_storage),
        patch("src.api.routes.session.verify_session_ownership"),
        patch("src.api.routes.session._normalize_session", return_value=mock_normalized),
    ):
        # Find the route handler
        for route in router.routes:
            if hasattr(route, "path") and route.path.endswith("/pin") and hasattr(route, "methods") and "POST" in route.methods:
                handler = route.endpoint
                response = await handler(session_id, user=user)
                assert response["status"] == "updated"
                assert response["is_pinned"] is True
                assert "session" in response
                break
        else:
            pytest.fail("No /pin POST route found")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/test_session_routes_pin.py -v`
Expected: FAIL — "No /pin POST route found"

- [ ] **Step 3: Implement the route**

Add to `src/api/routes/session.py` after the `toggle_session_favorite` route (after line 725):

```python
@router.post("/{session_id}/pin")
async def toggle_session_pin(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Toggle a session's pinned-to-top state."""

    manager = SessionManager()
    storage = SessionStorage()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    favorites_project_id = await _get_favorites_project_id(user.sub)
    updated_session = await storage.toggle_pin(session_id, user.sub)
    if not updated_session:
        raise HTTPException(status_code=500, detail="置顶状态更新失败")

    updated_session = _normalize_session(updated_session, favorites_project_id)
    return {
        "status": "updated",
        "is_pinned": bool(updated_session.metadata.get("is_pinned", False)),
        "session": updated_session,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/test_session_routes_pin.py -v`
Expected: PASS

- [ ] **Step 5: Run existing session tests to ensure no regression**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/ -k session -v`
Expected: All existing session tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/session.py tests/unit/test_session_routes_pin.py
git commit -m "feat(api): add POST /sessions/{id}/pin toggle route"
```

---

### Task 4: Frontend — Types, API client, and pin helper

**Files:**
- Modify: `frontend/src/services/api/session.ts:15-25` (BackendSession interface)
- Modify: `frontend/src/services/api/session.ts:392` (after toggleFavorite, add togglePin)
- Create: `frontend/src/components/sidebar/sessionPin.ts`

**Interfaces:**
- Consumes: `BackendSession` type, `apiClient.post`
- Produces: `BackendSession.task_status`, `sessionApi.togglePin()`, `isSessionPinned()`

- [ ] **Step 1: Write the failing test for the helper**

Create `frontend/src/components/sidebar/__tests__/sessionPin.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { isSessionPinned } from "../sessionPin";
import type { BackendSession } from "../../../services/api/session";

describe("isSessionPinned", () => {
  it("returns true when metadata.is_pinned is true", () => {
    const session = { metadata: { is_pinned: true } } as BackendSession;
    expect(isSessionPinned(session)).toBe(true);
  });

  it("returns false when metadata.is_pinned is false", () => {
    const session = { metadata: { is_pinned: false } } as BackendSession;
    expect(isSessionPinned(session)).toBe(false);
  });

  it("returns false when is_pinned is missing", () => {
    const session = { metadata: {} } as BackendSession;
    expect(isSessionPinned(session)).toBe(false);
  });

  it("returns false when metadata is missing", () => {
    const session = {} as BackendSession;
    expect(isSessionPinned(session)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run sessionPin.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement helper and type changes**

Create `frontend/src/components/sidebar/sessionPin.ts`:

```typescript
import type { BackendSession } from "../../services/api/session";

export function isSessionPinned(session: BackendSession): boolean {
  return session.metadata?.is_pinned === true;
}
```

Add `task_status` to `BackendSession` in `frontend/src/services/api/session.ts` (add after `unread_count` at line 24):

```typescript
  task_status?: string | null;
```

Add `togglePin` to `sessionApi` in `frontend/src/services/api/session.ts` (after `toggleFavorite` around line 392):

```typescript
  togglePin: async (sessionId: string) => {
    return apiClient.post<{
      status: string;
      is_pinned: boolean;
      session: BackendSession;
    }>(`/sessions/${sessionId}/pin`);
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run sessionPin.test.ts`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing frontend tests for regressions**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api/session.ts frontend/src/components/sidebar/sessionPin.ts frontend/src/components/sidebar/__tests__/sessionPin.test.ts
git commit -m "feat(frontend): add BackendSession.task_status, togglePin API, and isSessionPinned helper"
```

---

### Task 5: Frontend — SessionMenu cursor positioning and pin menu item

**Files:**
- Modify: `frontend/src/components/sidebar/SessionMenu.tsx`

**Interfaces:**
- Consumes: `Pin` from lucide-react, `cursorPosition` prop
- Produces: `SessionMenu` with `cursorPosition`, `onTogglePin`, `isPinned` props; pin menu item rendered

- [ ] **Step 1: Write the failing test**

Create or extend `frontend/src/components/sidebar/__tests__/SessionMenuPin.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionMenu } from "../SessionMenu";
import type { BackendSession } from "../../../services/api/session";

const mockSession = {
  id: "sess_1",
  agent_id: "agent_1",
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
  is_active: true,
  metadata: {},
} satisfies BackendSession;

describe("SessionMenu pin item", () => {
  it("shows pin menu item when onTogglePin is provided", () => {
    const { container } = render(
      <SessionMenu
        session={mockSession}
        projects={[]}
        isOpen={true}
        onClose={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        anchorEl={container}
        onTogglePin={vi.fn()}
        isPinned={false}
      />
    );

    // Pin icon should be in the document
    expect(screen.getByText("Pin to top")).toBeInTheDocument();
  });

  it("shows unpin text when session is pinned", () => {
    const { container } = render(
      <SessionMenu
        session={mockSession}
        projects={[]}
        isOpen={true}
        onClose={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        anchorEl={container}
        onTogglePin={vi.fn()}
        isPinned={true}
      />
    );

    expect(screen.getByText("Unpin")).toBeInTheDocument();
  });

  it("does not show pin item when onTogglePin is not provided", () => {
    const { container } = render(
      <SessionMenu
        session={mockSession}
        projects={[]}
        isOpen={true}
        onClose={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        anchorEl={container}
      />
    );

    expect(screen.queryByText("Pin to top")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run SessionMenuPin.test.tsx`
Expected: FAIL — "Pin to top" not found

- [ ] **Step 3: Implement SessionMenu changes**

In `frontend/src/components/sidebar/SessionMenu.tsx`:

1. Add `Pin` to lucide-react imports (line 8-18):
```typescript
import {
  Edit2,
  Trash2,
  FolderHeart,
  Tag,
  X,
  ChevronLeft,
  Share2,
  Star,
  Check,
  Pin,
} from "lucide-react";
```

2. Extend `SessionMenuProps` interface (after `isFavorite` at line 38):
```typescript
  onTogglePin?: () => void;
  isPinned?: boolean;
  cursorPosition?: { x: number; y: number };
```

3. Destructure new props in the component (after `isFavorite` at line 54):
```typescript
  onTogglePin,
  isPinned = false,
  cursorPosition,
```

4. Update `menuStyle` computation for cursor positioning. Replace the existing `menuStyle` block (lines 61-75) with:
```typescript
  const menuStyle = cursorPosition
    ? (() => {
        const style: React.CSSProperties = {
          position: "fixed",
          left: cursorPosition.x,
          top: cursorPosition.y,
          zIndex: 50,
        };
        // Will be adjusted after render via useEffect
        return style;
      })()
    : useStickyDropdownPosition(anchorRef, isOpen, (rect) => {
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        const openBelow = spaceBelow >= spaceAbove;
        return {
          position: "fixed",
          ...(openBelow
            ? { top: rect.bottom + 4 }
            : { bottom: window.innerHeight - rect.top + 4 }),
          right: window.innerWidth - rect.right,
          maxHeight: (openBelow ? spaceBelow : spaceAbove) - 16,
          overflowY: "auto",
          zIndex: 50,
        };
      });
```

5. Add pin menu item in `mainMenu` JSX, after the Favorite button (after line 183, before Share):
```tsx
      {/* Pin to top */}
      {onTogglePin && (
        <button
          onClick={() => {
            onTogglePin();
            onClose();
          }}
          className={`flex w-full items-center gap-3 px-3 py-2.5 text-sm transition-colors ${
            isPinned
              ? "text-blue-500 hover:bg-blue-500/10"
              : "text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-bg-subtle)]"
          }`}
        >
          <Pin
            size={16}
            className={`shrink-0 ${isPinned ? "fill-blue-500" : ""}`}
          />
          <span>
            {isPinned
              ? t("sidebar.unpinFromTop")
              : t("sidebar.pinToTop")}
          </span>
        </button>
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run SessionMenuPin.test.tsx`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sidebar/SessionMenu.tsx frontend/src/components/sidebar/__tests__/SessionMenuPin.test.tsx
git commit -m "feat(ui): add pin menu item and cursor positioning to SessionMenu"
```

---

### Task 6: Frontend — SessionItem right-click and task running indicator

**Files:**
- Modify: `frontend/src/components/sidebar/SessionItem.tsx`

**Interfaces:**
- Consumes: `cursorPosition` state, `onTogglePin`, `isPinned` props, `session.task_status`
- Produces: Right-click opens SessionMenu at cursor position; spinning blue dot for running tasks

- [ ] **Step 1: Write the failing test for task indicator**

Create or extend `frontend/src/components/sidebar/__tests__/SessionItemIndicator.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionItem } from "../SessionItem";
import type { BackendSession } from "../../../services/api/session";

const baseSession = {
  id: "sess_1",
  agent_id: "agent_1",
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
  is_active: true,
  metadata: {},
} satisfies BackendSession;

describe("SessionItem task running indicator", () => {
  it("shows spinner when task_status is running", () => {
    const session = { ...baseSession, task_status: "running" };
    render(
      <SessionItem
        session={session}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />
    );
    // The spinner should have animate-spin class
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("shows spinner when task_status is pending", () => {
    const session = { ...baseSession, task_status: "pending" };
    render(
      <SessionItem
        session={session}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />
    );
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("does not show spinner when task_status is completed", () => {
    const session = { ...baseSession, task_status: "completed" };
    render(
      <SessionItem
        session={session}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />
    );
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeInTheDocument();
  });

  it("does not show spinner when task_status is null", () => {
    const session = { ...baseSession, task_status: null };
    render(
      <SessionItem
        session={session}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />
    );
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run SessionItemIndicator.test.tsx`
Expected: FAIL — no `.animate-spin` element found

- [ ] **Step 3: Implement SessionItem changes**

In `frontend/src/components/sidebar/SessionItem.tsx`:

1. Add new props to `SessionItemProps` interface (after `onToggleFavorite` at line 23):
```typescript
  onTogglePin?: () => void;
  isPinned?: boolean;
```

2. Destructure new props in the component (after `onToggleFavorite` at line 48):
```typescript
  onTogglePin,
  isPinned = false,
```

3. Add `cursorPosition` state (after `isTouched` state at line 67):
```typescript
  const [cursorPosition, setCursorPosition] = useState<{ x: number; y: number } | null>(null);
```

4. Replace `handleContextMenu` (lines 200-204):
```typescript
  const handleContextMenu = (e: React.MouseEvent) => {
    if (isDragging) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    setCursorPosition({ x: e.clientX, y: e.clientY });
    setIsMenuOpen(true);
  };
```

5. Add task running indicator before the title `<div>` (around line 294-295), inside the title container:
```tsx
        {/* Title - editable or display */}
        <div className="min-w-0 flex-1 flex items-center gap-2">
          {/* Task running indicator */}
          {(session.task_status === "running" || session.task_status === "pending") && (
            <span className="shrink-0 h-2 w-2 rounded-full bg-blue-500 animate-spin opacity-70" />
          )}
          {isEditing ? (
```

6. Pass new props to `SessionMenu` (around line 354-369):
```tsx
        <SessionMenu
          session={session}
          projects={projects}
          isOpen={isMenuOpen}
          onClose={() => {
            setIsMenuOpen(false);
            setCursorPosition(null);
          }}
          onRename={handleStartEdit}
          onDelete={onDelete}
          onMoveToProject={onMoveToProject}
          onShare={onShare}
          onToggleFavorite={onToggleFavorite}
          anchorEl={menuAnchor}
          isFavorite={isFavorite}
          currentProjectId={currentProjectId}
          onTogglePin={onTogglePin}
          isPinned={isPinned}
          cursorPosition={cursorPosition ?? undefined}
        />
```

7. Update the `areSessionItemPropsEqual` comparator (add after line 387):
```typescript
    prev.isPinned === next.isPinned &&
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run SessionItemIndicator.test.tsx`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing frontend tests for regressions**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/sidebar/SessionItem.tsx frontend/src/components/sidebar/__tests__/SessionItemIndicator.test.tsx
git commit -m "feat(ui): add right-click context menu and task running indicator to SessionItem"
```

---

### Task 7: Frontend — Action handler `handleTogglePin`

**Files:**
- Modify: `frontend/src/hooks/useSessionSidebarActions.ts:335` (after `handleToggleFavorite`)

**Interfaces:**
- Consumes: `sessionApi.togglePin()`, `getProjectRef`, `projectRefs`, `uncategorizedList`, `setUnreadBySession`
- Produces: `handleTogglePin(sessionId: string)` — calls API, reconciles lists, shows toast

- [ ] **Step 1: Implement the handler**

Add to `frontend/src/hooks/useSessionSidebarActions.ts` after the `handleToggleFavorite` callback (after line 335), following the same reconciliation pattern:

```typescript
  // ─── Toggle pin ─────────────────────────────────────────────────

  const handleTogglePin = useCallback(
    async (sessionId: string) => {
      try {
        const response = await sessionApi.togglePin(sessionId);
        const updatedSession = response.session;

        if (uncategorizedList.sessions.some((s) => s.id === sessionId)) {
          uncategorizedList.updateSession(updatedSession);
        }
        for (const [, handle] of projectRefs.current) {
          if (handle.sessions.some((s) => s.id === sessionId)) {
            handle.updateSession(updatedSession);
          }
        }
      } catch (err) {
        console.error("Failed to toggle pin:", err);
        toast.error(t("sidebar.pinToggleFailed", "置顶状态更新失败"));
      }
    },
    [projectRefs, t, uncategorizedList],
  );
```

- [ ] **Step 2: Run existing frontend tests**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useSessionSidebarActions.ts
git commit -m "feat(hooks): add handleTogglePin action handler"
```

---

### Task 8: Frontend — Wire up SessionListContent and ProjectItem

**Files:**
- Modify: `frontend/src/components/panels/SidebarParts/SessionListContent.tsx:739` (SessionItem props)
- Modify: `frontend/src/components/sidebar/ProjectItem.tsx:431` (SessionItem props)

**Interfaces:**
- Consumes: `sessionActions.onTogglePin`, `isSessionPinned` helper
- Produces: `onTogglePin` and `isPinned` props passed to all `SessionItem` instances

- [ ] **Step 1: Update SessionListContent.tsx**

In `frontend/src/components/panels/SidebarParts/SessionListContent.tsx`, add import at the top:

```typescript
import { isSessionPinned } from "../../sidebar/sessionPin";
```

Then for each `<SessionItem>` in the uncategorized list (around line 714), add after `isFavorite={isSessionFavorite(session)}` (line 739):

```tsx
                                onTogglePin={() =>
                                  sessionActions.onTogglePin(session.id)
                                }
                                isPinned={isSessionPinned(session)}
```

- [ ] **Step 2: Update ProjectItem.tsx**

In `frontend/src/components/sidebar/ProjectItem.tsx`, add import:

```typescript
import { isSessionPinned } from "./sessionPin";
```

Then for the `<SessionItem>` in the sessions map (around line 409), add after `isFavorite={isSessionFavorite(session)}` (line 431):

```tsx
                    onTogglePin={
                      onTogglePin ? () => onTogglePin(session.id) : undefined
                    }
                    isPinned={isSessionPinned(session)}
```

Also add `onTogglePin` to ProjectItem's props interface, following the `onToggleFavorite` pattern — it should be an optional `(sessionId: string) => void` prop received from the parent `SessionSidebar`.

- [ ] **Step 3: Update SessionSidebar.tsx to expose handleTogglePin**

In `frontend/src/components/panels/SessionSidebar.tsx`, find where `sessionActions` / `sessionListProps` is constructed and ensure `onTogglePin: handleTogglePin` is included in the actions object spread to `SessionListContent`.

- [ ] **Step 4: Run frontend build to check for type errors**

Run: `cd /home/yangyang/LambChat/frontend && pnpm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Run frontend tests**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/panels/SidebarParts/SessionListContent.tsx frontend/src/components/sidebar/ProjectItem.tsx frontend/src/components/panels/SessionSidebar.tsx
git commit -m "feat(ui): wire pin props through SessionListContent and ProjectItem"
```

---

### Task 9: Frontend — i18n translations

**Files:**
- Modify: `frontend/src/i18n/locales/en.json` (around line 2537, near `addToFavorites`)
- Modify: `frontend/src/i18n/locales/zh.json` (around line 2537)
- Modify: `frontend/src/i18n/locales/ja.json` (around line 2537)
- Modify: `frontend/src/i18n/locales/ko.json` (around line 2537)
- Modify: `frontend/src/i18n/locales/ru.json` (around line 2537)

**Interfaces:**
- Consumes: existing `sidebar` i18n namespace
- Produces: new keys `sidebar.pinToTop`, `sidebar.unpinFromTop`, `sidebar.pinned`, `sidebar.unpinned`, `sidebar.pinToggleFailed`

- [ ] **Step 1: Add English translations**

In `frontend/src/i18n/locales/en.json`, add near `addToFavorites`:

```json
"pinToTop": "Pin to top",
"pinToggleFailed": "Failed to update pin status",
"pinned": "Pinned",
"unpinFromTop": "Unpin",
"unpinned": "Unpinned"
```

- [ ] **Step 2: Add Chinese translations**

In `frontend/src/i18n/locales/zh.json`, add near `addToFavorites`:

```json
"pinToTop": "置顶",
"pinToggleFailed": "置顶状态更新失败",
"pinned": "已置顶",
"unpinFromTop": "取消置顶",
"unpinned": "已取消置顶"
```

- [ ] **Step 3: Add Japanese translations**

In `frontend/src/i18n/locales/ja.json`, add near `addToFavorites`:

```json
"pinToTop": "ピン留め",
"pinToggleFailed": "ピン留め状態の更新に失敗しました",
"pinned": "ピン留めしました",
"unpinFromTop": "ピン留めを外す",
"unpinned": "ピン留めを外しました"
```

- [ ] **Step 4: Add Korean translations**

In `frontend/src/i18n/locales/ko.json`, add near `addToFavorites`:

```json
"pinToTop": "고정",
"pinToggleFailed": "고정 상태 업데이트 실패",
"pinned": "고정됨",
"unpinFromTop": "고정 해제",
"unpinned": "고정 해제됨"
```

- [ ] **Step 5: Add Russian translations**

In `frontend/src/i18n/locales/ru.json`, add near `addToFavorites`:

```json
"pinToTop": "Закрепить",
"pinToggleFailed": "Не удалось обновить статус закрепления",
"pinned": "Закреплено",
"unpinFromTop": "Открепить",
"unpinned": "Откреплено"
```

- [ ] **Step 6: Run frontend build**

Run: `cd /home/yangyang/LambChat/frontend && pnpm run build`
Expected: Build succeeds

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/locales/
git commit -m "feat(i18n): add pin-to-top translations for all 5 locales"
```

---

### Task 10: Final verification

**Files:** None — verification only

- [ ] **Step 1: Run all backend tests**

Run: `cd /home/yangyang/LambChat && uv run pytest tests/unit/ -v`
Expected: All tests PASS (including new pin tests)

- [ ] **Step 2: Run all frontend tests**

Run: `cd /home/yangyang/LambChat/frontend && pnpm test -- --run`
Expected: All tests PASS (including new pin and indicator tests)

- [ ] **Step 3: Run frontend build**

Run: `cd /home/yangyang/LambChat/frontend && pnpm run build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Run linters**

Run: `cd /home/yangyang/LambChat && make lint && cd frontend && pnpm run lint`
Expected: No lint errors

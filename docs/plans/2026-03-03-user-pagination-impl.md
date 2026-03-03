# User Pagination & Avatar Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add server-side pagination, search, and avatar display to user management.

**Architecture:** Backend returns paginated `UserListResponse` with total count, frontend implements page-number navigation and debounced search. Avatar display shows user image or initial letter fallback.

**Tech Stack:** FastAPI (Pydantic), MongoDB, React, TypeScript, Tailwind CSS

---

## Task 1: Backend - Add UserListResponse Schema

**Files:**
- Modify: `src/kernel/schemas/user.py`

**Step 1: Add UserListResponse schema**

Add after the `User` class definition (around line 48):

```python
class UserListResponse(BaseModel):
    """Paginated user list response."""

    users: List[User]
    total: int
    skip: int
    limit: int
    has_more: bool
```

**Step 2: Commit**

```bash
git add src/kernel/schemas/user.py
git commit -m "feat(schema): add UserListResponse for pagination"
```

---

## Task 2: Backend - Add count_users to Storage

**Files:**
- Modify: `src/infra/user/storage.py`

**Step 1: Add count_users method**

Add after the `list_users` method (around line 236):

```python
async def count_users(
    self,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> int:
    """
    Count users with optional search filter.

    Args:
        search: Search string for username/email fuzzy match
        is_active: Filter by active status

    Returns:
        Total count of matching users
    """
    query: dict = {}
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    return await self.collection.count_documents(query)
```

**Step 2: Modify list_users to support search**

Update the `list_users` method signature and query (around line 208-229):

```python
async def list_users(
    self,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
) -> list[User]:
    """
    List users with pagination and search.

    Args:
        skip: Skip count
        limit: Return count
        is_active: Filter by active status
        search: Search string for username/email fuzzy match

    Returns:
        List of users
    """
    query: dict = {}
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    cursor = self.collection.find(query).skip(skip).limit(limit)
    users = []

    async for user_dict in cursor:
        user_dict["id"] = str(user_dict.pop("_id"))
        users.append(User(**user_dict))

    return users
```

**Step 3: Commit**

```bash
git add src/infra/user/storage.py
git commit -m "feat(storage): add count_users and search support to list_users"
```

---

## Task 3: Backend - Update Manager Layer

**Files:**
- Modify: `src/infra/user/manager.py`

**Step 1: Update imports**

Add `UserListResponse` to imports (around line 14):

```python
from src.kernel.schemas.user import Token, User, UserCreate, UserUpdate, UserListResponse
```

**Step 2: Update list_users method**

Replace the `list_users` method (around line 156-173):

```python
async def list_users(
    self,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> UserListResponse:
    """
    List users with pagination.

    Args:
        skip: Skip count
        limit: Return count (default 20)
        search: Search string for username/email fuzzy match
        is_active: Filter by active status

    Returns:
        Paginated user list response
    """
    users = await self.storage.list_users(skip, limit, is_active, search)
    total = await self.storage.count_users(search, is_active)
    return UserListResponse(
        users=users,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )
```

**Step 3: Commit**

```bash
git add src/infra/user/manager.py
git commit -m "feat(manager): update list_users to return UserListResponse"
```

---

## Task 4: Backend - Update API Route

**Files:**
- Modify: `src/api/routes/user.py`

**Step 1: Update imports**

Add `Optional` and `UserListResponse` to imports (around line 5, 12):

```python
from typing import List, Optional

from src.kernel.schemas.user import TokenPayload, User, UserCreate, UserUpdate, UserListResponse
```

**Step 2: Update list_users endpoint**

Replace the `list_users` endpoint (around line 17-25):

```python
@router.get("/", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    _: None = Depends(require_permissions("user:read")),
):
    """List users with pagination and search."""
    manager = UserManager()
    return await manager.list_users(skip, limit, search)
```

**Step 3: Commit**

```bash
git add src/api/routes/user.py
git commit -m "feat(api): update list_users endpoint with pagination and search"
```

---

## Task 5: Frontend - Add Types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add UserListResponse type**

Add after `UserUpdate` interface (around line 492):

```typescript
// User list response (paginated)
export interface UserListResponse {
  users: User[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add UserListResponse type"
```

---

## Task 6: Frontend - Update User API

**Files:**
- Modify: `frontend/src/services/api/user.ts`

**Step 1: Update imports and add types**

Add at top of file (around line 5):

```typescript
import type { User, UserCreate, UserUpdate, UserListResponse } from "../../types";
```

**Step 2: Update list method**

Replace the `list` method (around line 13-17):

```typescript
  /**
   * List users with pagination and search
   */
  async list(params?: {
    skip?: number;
    limit?: number;
    search?: string;
  }): Promise<UserListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.skip !== undefined) {
      searchParams.set("skip", params.skip.toString());
    }
    if (params?.limit !== undefined) {
      searchParams.set("limit", params.limit.toString());
    }
    if (params?.search) {
      searchParams.set("search", params.search);
    }

    const query = searchParams.toString() ? `?${searchParams}` : "";
    return authFetch<UserListResponse>(`${API_BASE}/api/users/${query}`);
  },
```

**Step 3: Commit**

```bash
git add frontend/src/services/api/user.ts
git commit -m "feat(api): update userApi.list to support pagination"
```

---

## Task 7: Frontend - Create Pagination Component

**Files:**
- Create: `frontend/src/components/common/Pagination.tsx`

**Step 1: Create Pagination component**

```tsx
/**
 * Pagination Component - Page number navigation
 */

import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);

  if (totalPages <= 1) return null;

  const pages = getPageNumbers(page, totalPages);

  return (
    <div className="flex items-center justify-center gap-1">
      {/* Previous button */}
      <button
        onClick={() => onChange(page - 1)}
        disabled={page === 1}
        className="btn-icon disabled:opacity-40"
        aria-label="Previous page"
      >
        <ChevronLeft size={18} />
      </button>

      {/* Page numbers */}
      {pages.map((p, idx) =>
        p === "..." ? (
          <span key={`ellipsis-${idx}`} className="px-2 text-stone-400">
            ...
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onChange(p as number)}
            className={`min-w-[32px] rounded-lg px-2 py-1 text-sm font-medium transition-colors ${
              p === page
                ? "bg-amber-500 text-white"
                : "text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
            }`}
          >
            {p}
          </button>
        )
      )}

      {/* Next button */}
      <button
        onClick={() => onChange(page + 1)}
        disabled={page === totalPages}
        className="btn-icon disabled:opacity-40"
        aria-label="Next page"
      >
        <ChevronRight size={18} />
      </button>
    </div>
  );
}

/**
 * Generate page numbers with ellipsis for large page counts
 */
function getPageNumbers(current: number, total: number): (number | string)[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | string)[] = [];

  // Always show first page
  pages.push(1);

  if (current > 3) {
    pages.push("...");
  }

  // Show pages around current
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (current < total - 2) {
    pages.push("...");
  }

  // Always show last page
  if (total > 1) {
    pages.push(total);
  }

  return pages;
}

export default Pagination;
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/Pagination.tsx
git commit -m "feat(ui): add Pagination component"
```

---

## Task 8: Frontend - Update UsersPanel with Pagination and Avatar

**Files:**
- Modify: `frontend/src/components/panels/UsersPanel.tsx`

**Step 1: Add imports**

Update imports at top of file (around line 1-30):

```tsx
import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Users,
  Plus,
  Search,
  Edit,
  Trash2,
  X,
  AlertCircle,
  Check,
  User,
  Mail,
  Lock,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { Pagination } from "../common/Pagination";
import { userApi, roleApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  User as UserType,
  UserCreate,
  UserUpdate,
  Role,
} from "../../types";
```

**Step 2: Add UserAvatar component**

Add before `UserFormModal` component (around line 33):

```tsx
// User avatar display component
interface UserAvatarProps {
  user: UserType;
  size?: "sm" | "md";
}

function UserAvatar({ user, size = "sm" }: UserAvatarProps) {
  const sizeClasses = size === "sm" ? "h-8 w-8 text-sm" : "h-10 w-10 text-base";

  if (user.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.username}
        className={`rounded-full object-cover ${sizeClasses}`}
      />
    );
  }

  // Fallback to initial letter
  const initial = user.username.charAt(0).toUpperCase();
  return (
    <div
      className={`flex items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 font-medium ${sizeClasses}`}
    >
      {initial}
    </div>
  );
}
```

**Step 3: Add useDebounce hook**

Add after UserAvatar component:

```tsx
// Debounce hook for search
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
```

**Step 4: Update UsersPanel state**

Replace the state declarations in `UsersPanel` (around line 351-361):

```tsx
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [users, setUsers] = useState<UserType[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination state
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // Debounced search
  const debouncedSearch = useDebounce(searchQuery, 300);

  // Modal state
  const [showFormModal, setShowFormModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserType | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserType | null>(null);
  const [isSaving, setIsSaving] = useState(false);
```

**Step 5: Update loadData function**

Replace the `loadData` function (around line 369-392):

```tsx
  // Load data
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const skip = (page - 1) * pageSize;
      const response = await userApi.list({
        skip,
        limit: pageSize,
        search: debouncedSearch || undefined,
      });
      setUsers(response.users);
      setTotal(response.total);
    } catch (err) {
      const errorMsg = (err as Error).message || t("users.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    }

    // Load roles separately (unchanged)
    try {
      const rolesData = await roleApi.list();
      setRoles(rolesData);
    } catch (err) {
      console.error("Failed to load roles:", err);
    }

    setIsLoading(false);
  }, [page, debouncedSearch, t]);
```

**Step 6: Update useEffect**

Replace the useEffect (around line 394-396):

```tsx
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Reset to page 1 when search changes
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);
```

**Step 7: Update handleSaveUser**

Replace `handleSaveUser` function (around line 399-423):

```tsx
  // Save user
  const handleSaveUser = async (data: UserCreate | UserUpdate) => {
    setIsSaving(true);
    try {
      if (editingUser) {
        await userApi.update(editingUser.id, data as UserUpdate);
        toast.success(t("users.updateSuccess"));
      } else {
        await userApi.create(data as UserCreate);
        toast.success(t("users.createSuccess"));
      }
      // Reload data to reflect changes
      await loadData();
      setShowFormModal(false);
      setEditingUser(null);
    } catch (error) {
      toast.error((error as Error).message || t("users.operationFailed"));
    } finally {
      setIsSaving(false);
    }
  };
```

**Step 8: Update handleDeleteUser**

Replace `handleDeleteUser` function (around line 426-439):

```tsx
  // Delete user
  const handleDeleteUser = async () => {
    if (!deleteUser) return;
    setIsSaving(true);
    try {
      await userApi.delete(deleteUser.id);
      toast.success(t("users.deleteSuccess"));
      // Reload data to reflect changes
      await loadData();
      setDeleteUser(null);
    } catch (error) {
      toast.error((error as Error).message || t("users.deleteFailed"));
    } finally {
      setIsSaving(false);
    }
  };
```

**Step 9: Remove filteredUsers and update table/cell rendering**

Remove `filteredUsers` variable and update the user list rendering.

Replace the table body section (around line 567-642) - change `<User />` icon to `<UserAvatar user={user} />`:

```tsx
                      <td className="whitespace-nowrap px-6 py-4">
                        <div className="flex items-center gap-3">
                          <UserAvatar user={user} />
                          <span className="font-medium text-stone-900 dark:text-stone-100">
                            {user.username}
                          </span>
                        </div>
                      </td>
```

Also update mobile card view (around line 652-667):

```tsx
                  <div className="flex items-start gap-3">
                    <UserAvatar user={user} size="md" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-stone-900 dark:text-stone-100">
                        {user.username}
                      </p>
                      <p className="truncate text-sm text-stone-500 dark:text-stone-400">
                        {user.email}
                      </p>
                    </div>
                  </div>
```

**Step 10: Replace filteredUsers with users in list rendering**

Replace all occurrences of `filteredUsers` with `users` in the component (around line 528, 568, 649).

**Step 11: Add pagination component and info**

Add before the modal section (around line 727, after the user list `</div>`):

```tsx
      {/* Pagination */}
      {total > pageSize && (
        <div className="border-t border-stone-200 px-3 py-3 dark:border-stone-800 sm:px-6">
          <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-between">
            <p className="text-sm text-stone-500 dark:text-stone-400">
              {t("users.paginationInfo", {
                start: (page - 1) * pageSize + 1,
                end: Math.min(page * pageSize, total),
                total,
              })}
            </p>
            <Pagination
              page={page}
              pageSize={pageSize}
              total={total}
              onChange={setPage}
            />
          </div>
        </div>
      )}
```

**Step 12: Update empty state condition**

Replace the empty state condition (around line 528-537):

```tsx
        {users.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Users
              size={48}
              className="mb-4 text-stone-300 dark:text-stone-600"
            />
            <p className="text-stone-500 dark:text-stone-400">
              {debouncedSearch ? t("users.noMatchingUsers") : t("users.noUsers")}
            </p>
          </div>
```

**Step 13: Commit**

```bash
git add frontend/src/components/panels/UsersPanel.tsx
git commit -m "feat(ui): add pagination and avatar display to UsersPanel"
```

---

## Task 9: Frontend - Add i18n translations

**Files:**
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Step 1: Add Chinese translations**

Add to `users` section in `zh.json`:

```json
  "users": {
    "paginationInfo": "显示 {{start}}-{{end}} 条，共 {{total}} 条"
  }
```

**Step 2: Add English translations**

Add to `users` section in `en.json`:

```json
  "users": {
    "paginationInfo": "Showing {{start}}-{{end}} of {{total}}"
  }
```

**Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh.json frontend/src/i18n/locales/en.json
git commit -m "feat(i18n): add pagination translations"
```

---

## Task 10: Final verification

**Step 1: Run backend tests**

```bash
cd /home/yangyang/LambChat
python -m pytest tests/ -v -k user
```

Expected: All tests pass

**Step 2: Run frontend type check**

```bash
cd /home/yangyang/LambChat/frontend
npm run typecheck
```

Expected: No type errors

**Step 3: Manual testing**

1. Start backend: `python main.py`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to Users panel
4. Verify:
   - Avatars display correctly (or show initial letter)
   - Pagination shows when > 20 users
   - Search triggers API calls with debounce
   - Page navigation works

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address any issues found during testing"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add UserListResponse schema | `src/kernel/schemas/user.py` |
| 2 | Add count_users + search to storage | `src/infra/user/storage.py` |
| 3 | Update manager layer | `src/infra/user/manager.py` |
| 4 | Update API route | `src/api/routes/user.py` |
| 5 | Add frontend types | `frontend/src/types/index.ts` |
| 6 | Update user API | `frontend/src/services/api/user.ts` |
| 7 | Create Pagination component | `frontend/src/components/common/Pagination.tsx` |
| 8 | Update UsersPanel | `frontend/src/components/panels/UsersPanel.tsx` |
| 9 | Add i18n translations | `frontend/src/i18n/locales/*.json` |
| 10 | Final verification | Tests + manual |

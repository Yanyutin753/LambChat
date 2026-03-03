# User Pagination & Avatar Display Design

## Overview

Add server-side pagination and search to user management, plus display user avatars in the user list.

## Requirements

1. Support 1000+ users with traditional page-number pagination
2. Server-side search (fuzzy match on username/email)
3. Display user avatars in the user list (fallback to initial letter if no avatar)

## Design Details

### 1. Backend - Schema

**File**: `src/kernel/schemas/user.py`

Add pagination response schema:

```python
class UserListResponse(BaseModel):
    """Paginated user list response."""
    users: List[User]
    total: int
    skip: int
    limit: int
    has_more: bool
```

### 2. Backend - Storage Layer

**File**: `src/infra/user/storage.py`

Add `count_users` method and modify `list_users` to support search:

```python
async def count_users(self, search: Optional[str] = None) -> int:
    """Count users with optional search filter."""
    query = {}
    if search:
        query["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    return await self.collection.count_documents(query)

async def list_users(
    self,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,  # New parameter
) -> list[User]:
    """List users with pagination and search."""
    query = {}
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    cursor = self.collection.find(query).skip(skip).limit(limit)
    # ... rest unchanged
```

### 3. Backend - Manager Layer

**File**: `src/infra/user/manager.py`

Update `list_users` to return paginated response:

```python
async def list_users(
    self,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
) -> UserListResponse:
    """List users with pagination."""
    users = await self.storage.list_users(skip, limit, search=search)
    total = await self.storage.count_users(search=search)
    return UserListResponse(
        users=users,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )
```

### 4. Backend - API Route

**File**: `src/api/routes/user.py`

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

### 5. Frontend - Types

**File**: `frontend/src/types/index.ts`

Add pagination response type:

```typescript
export interface UserListResponse {
  users: User[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}
```

### 6. Frontend - API Service

**File**: `frontend/src/services/api/user.ts`

```typescript
export interface UserListParams {
  skip?: number;
  limit?: number;
  search?: string;
}

export interface UserListResponse {
  users: User[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

export const userApi = {
  async list(params?: UserListParams): Promise<UserListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.skip) searchParams.set("skip", params.skip.toString());
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.search) searchParams.set("search", params.search);

    return authFetch<UserListResponse>(
      `${API_BASE}/api/users/?${searchParams}`
    );
  },
  // ... other methods unchanged
};
```

### 7. Frontend - UsersPanel Component

**File**: `frontend/src/components/panels/UsersPanel.tsx`

**Changes**:

1. **State management**:
```typescript
const [page, setPage] = useState(1);
const [pageSize] = useState(20);
const [total, setTotal] = useState(0);
const [searchQuery, setSearchQuery] = useState("");
const [debouncedSearch, setDebouncedSearch] = useState("");
```

2. **Avatar display component**:
```tsx
function UserAvatar({ user }: { user: User }) {
  if (user.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.username}
        className="h-8 w-8 rounded-full object-cover"
      />
    );
  }
  // Fallback to initial letter
  const initial = user.username.charAt(0).toUpperCase();
  return (
    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 font-medium text-sm">
      {initial}
    </div>
  );
}
```

3. **Pagination component** (reuse existing pagination patterns)

4. **Search with debounce** (300ms delay)

## Files to Modify

### Backend
1. `src/kernel/schemas/user.py` - Add `UserListResponse` schema
2. `src/infra/user/storage.py` - Add `count_users`, modify `list_users`
3. `src/infra/user/manager.py` - Update `list_users` return type
4. `src/api/routes/user.py` - Update endpoint signature

### Frontend
1. `frontend/src/types/index.ts` - Add `UserListResponse` type
2. `frontend/src/services/api/user.ts` - Update `list` method
3. `frontend/src/components/panels/UsersPanel.tsx` - Add pagination, avatar display, search integration

## Migration Notes

- API response format changes from `User[]` to `UserListResponse`
- Frontend needs to handle new response structure
- Default page size: 20 users per page

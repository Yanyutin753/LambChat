# Session Share Feature Design

## Overview

Add a session sharing feature similar to ChatGPT, allowing users to share conversations via public links with permission-based access control.

## Requirements

| Requirement | Decision |
|-------------|----------|
| Share granularity | Full session or partial content (user selects) |
| Access control | Public link or authenticated only (user selects) |
| Permission model | `session:admin` + `session:share` (replace hardcoded ADMIN_ROLES) |
| Additional features | Basic: create, view, delete share |

## Architecture

### Approach: Independent Share Table

Create a dedicated `shared_sessions` collection to manage share records.

**Benefits**:
- Share records decoupled from sessions
- Support multiple shares per session with different settings
- Easy to extend (e.g., expiry time, view count)
- Cascade delete when session is deleted

## Database Design

### New Collection: `shared_sessions`

```python
# SharedSession Schema
{
    "id": str,                    # Share record ID (ObjectId)
    "share_id": str,              # Share identifier (for URL, random string)
    "session_id": str,            # Original session ID
    "owner_id": str,              # Owner user ID

    # Share scope
    "share_type": "full" | "partial",   # Full session / Partial
    "run_ids": list[str] | None,        # Run IDs for partial share

    # Access control
    "visibility": "public" | "authenticated",  # Public / Login required

    # Timestamps
    "created_at": datetime,
    "updated_at": datetime,
}
```

### Indexes

- `share_id` (unique) - Fast share lookup
- `session_id` - Query all shares for a session
- `owner_id` - Query all shares by user

## Permission Design

### New Permissions

Add to `src/kernel/types.py`:

```python
class Permission(str, Enum):
    # Session (new)
    SESSION_ADMIN = "session:admin"   # Manage all sessions (replaces ADMIN_ROLES)
    SESSION_SHARE = "session:share"   # Share sessions
```

Add to `src/kernel/schemas/permission.py`:

```python
# Permission metadata
Permission.SESSION_ADMIN.value: {
    "label": "管理所有会话",
    "description": "查看和管理所有用户的会话（管理员权限）",
},
Permission.SESSION_SHARE.value: {
    "label": "分享会话",
    "description": "创建和管理会话分享链接",
},

# Permission group config - update session group
{
    "name": "会话",
    "permissions": [
        Permission.SESSION_READ.value,
        Permission.SESSION_WRITE.value,
        Permission.SESSION_DELETE.value,
        Permission.SESSION_ADMIN.value,
        Permission.SESSION_SHARE.value,
    ],
},
```

### Permission Logic

- `session:admin` - Can view/manage all users' sessions (admin backend)
- `session:share` - Can share own sessions
- Users without `session:share` permission won't see share button

### Refactor ADMIN_ROLES

Replace hardcoded `ADMIN_ROLES = {"admin", "administrator"}` in `src/api/routes/session.py` with `session:admin` permission check.

## API Design

### New Routes: `src/api/routes/share.py`

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/share` | Create share | Required + `session:share` |
| GET | `/api/share` | List my shares | Required |
| GET | `/api/share/{share_id}` | Get share detail | Required + owner |
| DELETE | `/api/share/{share_id}` | Delete share | Required + owner |
| GET | `/api/shared/{share_id}` | View shared content | Depends on visibility |

### API Details

#### Create Share

```typescript
POST /api/share
Request:
{
    "session_id": "xxx",
    "share_type": "full" | "partial",
    "run_ids": ["run1", "run2"],     // Required when share_type=partial
    "visibility": "public" | "authenticated"
}
Response:
{
    "id": "...",
    "share_id": "abc123",
    "url": "/shared/abc123",
    "session_id": "xxx",
    "share_type": "full",
    "visibility": "public",
    "created_at": "..."
}
```

#### List My Shares

```typescript
GET /api/share
Response:
{
    "shares": [
        {
            "id": "...",
            "share_id": "abc123",
            "session_id": "xxx",
            "session_name": "Chat about Python",
            "share_type": "full",
            "visibility": "public",
            "created_at": "...",
            "view_count": 0  // Future extension
        }
    ],
    "total": 5
}
```

#### View Shared Content

```typescript
GET /api/shared/{share_id}
Response (visibility=public):
{
    "session": {
        "id": "xxx",
        "name": "Chat about Python",
        "created_at": "...",
        ...
    },
    "events": [...],
    "owner": {
        "username": "john",
        "avatar_url": "..."
    },
    "share_type": "full",
    "run_ids": null
}
```

## Frontend Design

### 1. Types (`frontend/src/types/index.ts`)

```typescript
export enum Permission {
  // ... existing ...
  SESSION_ADMIN = "session:admin",
  SESSION_SHARE = "session:share",
}

export type ShareType = "full" | "partial";
export type ShareVisibility = "public" | "authenticated";

export interface SharedSession {
  id: string;
  share_id: string;
  session_id: string;
  session_name?: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
  created_at: string;
  updated_at: string;
}

export interface ShareCreate {
  session_id: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
}

export interface SharedContent {
  session: Session;
  events: SSEEventRecord[];
  owner: {
    username: string;
    avatar_url?: string;
  };
  share_type: ShareType;
  run_ids?: string[];
}
```

### 2. API Service (`frontend/src/services/api/share.ts`)

```typescript
export const shareApi = {
  create: async (data: ShareCreate): Promise<SharedSession> => {...},
  list: async (): Promise<{ shares: SharedSession[]; total: number }> => {...},
  delete: async (shareId: string): Promise<void> => {...},
  getShared: async (shareId: string): Promise<SharedContent> => {...},
}
```

### 3. UI Components

#### SessionSidebar Modification

- Add share button (icon: `Share2`) to each session item
- Only show when user has `session:share` permission
- Click opens ShareDialog

#### New ShareDialog Component

```typescript
interface ShareDialogProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  sessionName: string;
}
```

Features:
- Select share scope (full session / partial)
- If partial, show run list to select
- Select visibility (public / authenticated)
- Generate share link
- Copy link button
- Show existing shares for this session

#### New SharedPage Component

Route: `/shared/:shareId`

- Read-only view of shared conversation
- Display session name, messages
- Show owner info (username, avatar)
- Handle auth requirement based on visibility
- Redirect to login if auth required and not logged in

### 4. Routes

```typescript
// Add to App.tsx
<Route path="/shared/:shareId" element={<SharedPage />} />
```

### 5. i18n Keys

```json
{
  "share": {
    "title": "分享会话",
    "createShare": "创建分享",
    "shareType": "分享范围",
    "fullSession": "整个会话",
    "partialSession": "部分内容",
    "visibility": "可见性",
    "public": "公开链接",
    "publicDesc": "任何人都可以查看",
    "authenticated": "需要登录",
    "authenticatedDesc": "只有登录用户可以查看",
    "linkCopied": "链接已复制",
    "copyLink": "复制链接",
    "deleteShare": "取消分享",
    "deleteConfirm": "确定要取消分享吗？",
    "noPermission": "你没有分享会话的权限",
    "sharedBy": "分享者"
  }
}
```

## Files to Modify/Create

### Backend

| File | Action | Description |
|------|--------|-------------|
| `src/kernel/types.py` | Modify | Add `SESSION_ADMIN`, `SESSION_SHARE` permissions |
| `src/kernel/schemas/permission.py` | Modify | Add permission metadata and group |
| `src/kernel/schemas/share.py` | Create | SharedSession schema |
| `src/infra/share/storage.py` | Create | Share storage (MongoDB) |
| `src/api/routes/share.py` | Create | Share API routes |
| `src/api/routes/session.py` | Modify | Replace ADMIN_ROLES with permission check |
| `src/api/main.py` | Modify | Register share router |

### Frontend

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/types/index.ts` | Modify | Add share types and permissions |
| `frontend/src/services/api/share.ts` | Create | Share API service |
| `frontend/src/services/api/index.ts` | Modify | Export shareApi |
| `frontend/src/components/panels/SessionSidebar.tsx` | Modify | Add share button |
| `frontend/src/components/share/ShareDialog.tsx` | Create | Share dialog component |
| `frontend/src/components/share/SharedPage.tsx` | Create | Public share view page |
| `frontend/src/App.tsx` | Modify | Add /shared/:shareId route |
| `frontend/src/i18n/locales/en.json` | Modify | Add share translations |
| `frontend/src/i18n/locales/zh.json` | Modify | Add share translations |

## Implementation Order

1. **Backend - Permissions**
   - Add `SESSION_ADMIN`, `SESSION_SHARE` to `types.py`
   - Add metadata to `permission.py`
   - Update role management to assign new permissions

2. **Backend - Schema & Storage**
   - Create `schemas/share.py`
   - Create `infra/share/storage.py`

3. **Backend - API Routes**
   - Create `routes/share.py`
   - Modify `routes/session.py` to use `session:admin` permission

4. **Frontend - Types & API**
   - Add types to `types/index.ts`
   - Create `services/api/share.ts`

5. **Frontend - UI Components**
   - Create `ShareDialog.tsx`
   - Modify `SessionSidebar.tsx`
   - Create `SharedPage.tsx`

6. **Frontend - Routing & i18n**
   - Add route to `App.tsx`
   - Add translation keys

## Security Considerations

1. **Share ID Generation**: Use cryptographically secure random strings (min 12 chars)
2. **Owner Verification**: Always verify ownership before delete/update
3. **Session Events**: Only return events for shared runs (not full session)
4. **Rate Limiting**: Consider rate limiting share creation
5. **Content Sanitization**: Ensure no sensitive data in shared content

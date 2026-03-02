# Avatar Upload Permission Design

## Overview

Add independent `avatar:upload` permission for avatar operations and implement avatar deletion functionality.

## Background

Current implementation:
- Backend has `/api/upload/avatar` endpoint using `file:upload` permission
- Avatar stored as base64 in `users.avatar_url` field
- Frontend has upload UI in Profile modal but no delete functionality

## Requirements

1. Create independent `avatar:upload` permission (separate from `file:upload`)
2. Add avatar deletion functionality (frontend + backend)
3. Permission-based control for avatar operations

## Design Details

### 1. Backend - Permission Definition

**File**: `src/kernel/types.py`

Add new permission to enum:
```python
class Permission(str, Enum):
    # ... existing permissions ...

    # Avatar
    AVATAR_UPLOAD = "avatar:upload"
```

**File**: `src/kernel/schemas/permission.py`

Add permission metadata:
```python
Permission.AVATAR_UPLOAD.value: {
    "label": "上传头像",
    "description": "允许上传和删除头像",
},
```

Add to permission groups:
```python
{
    "name": "头像",
    "permissions": [Permission.AVATAR_UPLOAD.value],
},
```

### 2. Backend - API Changes

**File**: `src/api/routes/upload.py`

**Modify upload endpoint permission**:
```python
@router.post("/avatar", dependencies=[Depends(require_permissions("avatar:upload"))])
async def upload_avatar(...):
    # Existing logic unchanged
```

**Add delete endpoint**:
```python
@router.delete("/avatar", dependencies=[Depends(require_permissions("avatar:upload"))])
async def delete_avatar(current_user: TokenPayload = Depends(get_current_user_required)):
    """Delete user avatar"""
    storage = UserStorage()
    await storage.update(current_user.sub, UserUpdate(avatar_url=None))
    return {"deleted": True}
```

### 3. Frontend - Permission Definition

**File**: `frontend/src/types/index.ts`

```typescript
export enum Permission {
  // ... existing permissions ...

  // Avatar
  AVATAR_UPLOAD = "avatar:upload",
}
```

### 4. Frontend - API Service

**File**: `frontend/src/services/api/upload.ts`

```typescript
async deleteAvatar(): Promise<{ deleted: boolean }> {
  const response = await fetch(`${API_BASE}/api/upload/avatar`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${getAccessToken()}` },
    credentials: "include",
  });
  if (!response.ok) throw new Error("Delete failed");
  return response.json();
}
```

### 5. Frontend - UI Changes

**File**: `frontend/src/App.tsx` (ProfileModal component)

- Add permission check using `hasPermission(Permission.AVATAR_UPLOAD)`
- Only show upload/delete buttons when user has permission
- Add delete button next to avatar with trash icon
- On delete: call API, clear avatar_url in state, refresh auth context

## Files to Modify

### Backend
1. `src/kernel/types.py` - Add `AVATAR_UPLOAD` permission
2. `src/kernel/schemas/permission.py` - Add metadata and group config
3. `src/api/routes/upload.py` - Change permission, add delete endpoint

### Frontend
1. `frontend/src/types/index.ts` - Add `AVATAR_UPLOAD` permission
2. `frontend/src/services/api/upload.ts` - Add `deleteAvatar` method
3. `frontend/src/App.tsx` - Add permission check and delete button in ProfileModal
4. `frontend/src/i18n/locales/*.json` - Add translation keys (optional)

## Migration Notes

- Existing users with `file:upload` permission will need to be granted `avatar:upload` separately
- Default roles should be updated to include `avatar:upload` if they had `file:upload`

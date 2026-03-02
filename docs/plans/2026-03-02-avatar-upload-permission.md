# Avatar Upload Permission Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add independent `avatar:upload` permission and avatar deletion functionality.

**Architecture:** Create a new permission `avatar:upload` separate from `file:upload`, add backend delete endpoint, and update frontend ProfileModal with permission check and delete button.

**Tech Stack:** Python/FastAPI (backend), TypeScript/React (frontend), Pydantic for schemas.

---

## Task 1: Add Backend Permission Enum

**Files:**
- Modify: `src/kernel/types.py:56-61`

**Step 1: Add AVATAR_UPLOAD permission to enum**

Add the new permission after the FILE permissions:

```python
    # File
    FILE_UPLOAD = "file:upload"
    FILE_UPLOAD_IMAGE = "file:upload:image"
    FILE_UPLOAD_VIDEO = "file:upload:video"
    FILE_UPLOAD_AUDIO = "file:upload:audio"
    FILE_UPLOAD_DOCUMENT = "file:upload:document"

    # Avatar
    AVATAR_UPLOAD = "avatar:upload"
```

**Step 2: Commit**

```bash
git add src/kernel/types.py
git commit -m "feat(permission): add AVATAR_UPLOAD permission enum"
```

---

## Task 2: Add Permission Metadata and Group

**Files:**
- Modify: `src/kernel/schemas/permission.py:130-151` (metadata)
- Modify: `src/kernel/schemas/permission.py:210-219` (groups)

**Step 1: Add permission metadata**

Add after the FILE_UPLOAD_DOCUMENT entry (around line 151):

```python
    # Avatar
    Permission.AVATAR_UPLOAD.value: {
        "label": "上传头像",
        "description": "允许上传和删除用户头像",
    },
```

**Step 2: Add permission group**

Add after the "文件上传" group (around line 219):

```python
    {
        "name": "头像",
        "permissions": [
            Permission.AVATAR_UPLOAD.value,
        ],
    },
```

**Step 3: Commit**

```bash
git add src/kernel/schemas/permission.py
git commit -m "feat(permission): add avatar:upload metadata and group"
```

---

## Task 3: Update Upload Endpoint Permission

**Files:**
- Modify: `src/api/routes/upload.py:262`

**Step 1: Change avatar upload endpoint permission**

Change line 262 from:
```python
@router.post("/avatar", dependencies=[Depends(require_permissions("file:upload"))])
```

To:
```python
@router.post("/avatar", dependencies=[Depends(require_permissions("avatar:upload"))])
```

**Step 2: Commit**

```bash
git add src/api/routes/upload.py
git commit -m "feat(upload): use avatar:upload permission for avatar endpoint"
```

---

## Task 4: Add Avatar Delete Endpoint

**Files:**
- Modify: `src/api/routes/upload.py` (add after upload_avatar function, around line 335)

**Step 1: Add delete endpoint**

Add after the `upload_avatar` function:

```python
@router.delete("/avatar", dependencies=[Depends(require_permissions("avatar:upload"))])
async def delete_avatar(
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Delete user avatar

    Removes the avatar_url from the user's profile.
    Requires: avatar:upload permission

    Args:
        current_user: Current authenticated user

    Returns:
        Deletion status
    """
    try:
        from src.infra.user.storage import UserStorage
        from src.kernel.schemas.user import UserUpdate

        logger.info(f"Deleting avatar for user: {current_user.sub}")
        storage = UserStorage()
        await storage.update(
            current_user.sub,
            UserUpdate(avatar_url=None),
        )
        logger.info(f"Avatar deleted successfully for user: {current_user.sub}")

        return {"deleted": True}
    except Exception as e:
        logger.exception("Avatar deletion failed")
        raise HTTPException(status_code=500, detail=f"Avatar deletion failed: {str(e)}")
```

**Step 2: Commit**

```bash
git add src/api/routes/upload.py
git commit -m "feat(upload): add avatar delete endpoint"
```

---

## Task 5: Add Frontend Permission Enum

**Files:**
- Modify: `frontend/src/types/index.ts:454-460`

**Step 1: Add AVATAR_UPLOAD permission**

Add after the FILE permissions:

```typescript
  // File
  FILE_UPLOAD = "file:upload",
  FILE_UPLOAD_IMAGE = "file:upload:image",
  FILE_UPLOAD_VIDEO = "file:upload:video",
  FILE_UPLOAD_AUDIO = "file:upload:audio",
  FILE_UPLOAD_DOCUMENT = "file:upload:document",
  // Avatar
  AVATAR_UPLOAD = "avatar:upload",
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): add AVATAR_UPLOAD permission enum"
```

---

## Task 6: Add Frontend Delete Avatar API

**Files:**
- Modify: `frontend/src/services/api/upload.ts`

**Step 1: Add deleteAvatar method**

Add after the `uploadAvatar` method (around line 79):

```typescript
  /**
   * 删除头像
   */
  async deleteAvatar(): Promise<{ deleted: boolean }> {
    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/api/upload/avatar`, {
      method: "DELETE",
      headers: token
        ? {
            Authorization: `Bearer ${token}`,
          }
        : {},
      credentials: "include",
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Delete failed: ${response.statusText}`,
      );
    }

    return response.json();
  },
```

**Step 2: Commit**

```bash
git add frontend/src/services/api/upload.ts
git commit -m "feat(frontend): add deleteAvatar API method"
```

---

## Task 7: Update ProfileModal with Permission Check and Delete Button

**Files:**
- Modify: `frontend/src/App.tsx` (ProfileModal component)

**Step 1: Import Permission enum and useAuth hook**

The imports should already exist. Verify `Permission` is imported from `"./types"` and `useAuth` provides `hasPermission`.

**Step 2: Add avatar permission check in ProfileModal**

Inside ProfileModal component, add permission check after the state declarations (around line 88):

```typescript
  const { user, refreshUser, hasPermission } = useAuth();
  const canUploadAvatar = hasPermission(Permission.AVATAR_UPLOAD);
```

Note: The `useAuth` hook already has `hasPermission`. Update the destructuring to include it.

**Step 3: Add delete handler**

Add after `handleAvatarUpload` function (around line 218):

```typescript
  // Handle avatar delete
  const handleAvatarDelete = async () => {
    setIsUploading(true);
    try {
      await uploadApi.deleteAvatar();
      // Refresh user data in both local state and global auth context
      const user = await authApi.getProfile();
      setUserData(user);
      // Update global auth context to refresh avatar in header/sidebar
      refreshUser();
      toast.success(t("profile.avatarDeleted"));
    } catch (error) {
      console.error("Failed to delete avatar:", error);
      const message = error instanceof Error ? error.message : "Delete failed";
      toast.error(message);
    } finally {
      setIsUploading(false);
    }
  };
```

**Step 4: Update avatar UI section**

Replace the avatar section (around lines 343-388) with:

```tsx
              {/* Avatar */}
              <div className="flex flex-col items-center mb-6">
                <div className="relative">
                  {userData?.avatar_url ? (
                    <img
                      src={userData.avatar_url}
                      alt="Avatar"
                      className="w-20 h-20 rounded-full object-cover border-4 border-white dark:border-stone-700 shadow-md"
                    />
                  ) : (
                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center border-4 border-white dark:border-stone-700 shadow-md">
                      <span className="text-2xl font-bold text-white">
                        {userData?.username?.charAt(0).toUpperCase() || "U"}
                      </span>
                    </div>
                  )}
                  {isUploading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-full">
                      <Loader2 size={24} className="animate-spin text-white" />
                    </div>
                  )}
                </div>
                {canUploadAvatar && (
                  <div className="mt-3 flex items-center gap-2">
                    <label className="cursor-pointer rounded-lg bg-stone-100 dark:bg-stone-700 px-3 py-1.5 text-xs font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-600 transition-colors">
                      {t("profile.changeAvatar")}
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        disabled={isUploading}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) handleAvatarUpload(file);
                        }}
                      />
                    </label>
                    {userData?.avatar_url && (
                      <button
                        onClick={handleAvatarDelete}
                        disabled={isUploading}
                        className="rounded-lg bg-red-50 dark:bg-red-900/30 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors disabled:opacity-50"
                      >
                        {t("profile.deleteAvatar")}
                      </button>
                    )}
                  </div>
                )}
              </div>
```

**Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): add avatar permission check and delete button in ProfileModal"
```

---

## Task 8: Add Translation Keys (Optional)

**Files:**
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Step 1: Add Chinese translations**

Add to `profile` section:

```json
    "avatarDeleted": "头像已删除",
    "deleteAvatar": "删除头像"
```

**Step 2: Add English translations**

Add to `profile` section:

```json
    "avatarDeleted": "Avatar deleted",
    "deleteAvatar": "Delete Avatar"
```

**Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh.json frontend/src/i18n/locales/en.json
git commit -m "feat(i18n): add avatar deletion translations"
```

---

## Task 9: Final Verification

**Step 1: Run backend tests**

```bash
cd /home/yangyang/LambChat && python -m pytest tests/ -v --tb=short
```

**Step 2: Run frontend type check**

```bash
cd /home/yangyang/LambChat/frontend && npm run typecheck
```

**Step 3: Manual testing checklist**

1. Login as admin user
2. Go to Role Management
3. Verify `avatar:upload` permission appears in permission list
4. Create a test role without `avatar:upload` permission
5. Assign test role to a user
6. Login as that user
7. Open Profile modal - upload/delete buttons should be hidden
8. Grant `avatar:upload` permission
9. Refresh and verify buttons appear
10. Test avatar upload and delete functionality

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add backend permission enum | `src/kernel/types.py` |
| 2 | Add permission metadata/group | `src/kernel/schemas/permission.py` |
| 3 | Update upload endpoint permission | `src/api/routes/upload.py` |
| 4 | Add delete endpoint | `src/api/routes/upload.py` |
| 5 | Add frontend permission enum | `frontend/src/types/index.ts` |
| 6 | Add delete API method | `frontend/src/services/api/upload.ts` |
| 7 | Update ProfileModal UI | `frontend/src/App.tsx` |
| 8 | Add translations | `frontend/src/i18n/locales/*.json` |
| 9 | Verification | Tests + Manual |

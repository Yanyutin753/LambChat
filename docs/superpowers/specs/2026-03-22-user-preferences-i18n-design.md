# User Preferences & Multi-language Suggestions Design

**Date**: 2026-03-22
**Status**: Approved

## Goal

Store user language and theme preferences in backend metadata, sync across devices, and support multi-language welcome suggestions.

## Approach

Add an optional `metadata` JSON field to the User model. Store language and theme preferences there. On login, restore preferences from backend. On preference change, write to both localStorage and backend. Change WELCOME_SUGGESTIONS to a multi-language JSON structure.

## Data Model

### User metadata

```json
{
  "language": "zh",
  "theme": "dark"
}
```

- `language`: i18next language code — `en`, `zh`, `ja`, `ko`, `ru`
- `theme`: `"light"` | `"dark"`

### Schema change

File: `src/kernel/schemas/user.py`

```python
class UserBase(BaseModel):
    username: str
    email: EmailStr
    avatar_url: Optional[str]
    oauth_provider: Optional[OAuthProvider]
    oauth_id: Optional[str]
    metadata: Optional[dict] = None  # NEW
```

Backward compatible: existing users have `metadata: null`, written on first preference update.

### WELCOME_SUGGESTIONS change

File: `src/kernel/config/definitions.py`

Current default (flat array):
```json
[
  {"icon": "🐍", "text": "Create a Python hello world script"},
  {"icon": "📁", "text": "List files in the workspace directory"},
  {"icon": "📄", "text": "Read the README.md file"},
  {"icon": "🔧", "text": "Help me write a shell script"}
]
```

New default (multi-language object):
```json
{
  "en": [
    {"icon": "🐍", "text": "Create a Python hello world script"},
    {"icon": "📁", "text": "List files in the workspace directory"},
    {"icon": "📄", "text": "Read the README.md file"},
    {"icon": "🔧", "text": "Help me write a shell script"}
  ],
  "zh": [
    {"icon": "🐍", "text": "创建一个 Python Hello World 脚本"},
    {"icon": "📁", "text": "列出工作区目录中的文件"},
    {"icon": "📄", "text": "读取 README.md 文件"},
    {"icon": "🔧", "text": "帮我写一个 Shell 脚本"}
  ],
  "ja": [
    {"icon": "🐍", "text": "PythonのHello Worldスクリプトを作成"},
    {"icon": "📁", "text": "ワークスペースディレクトリのファイルを一覧表示"},
    {"icon": "📄", "text": "README.mdファイルを読む"},
    {"icon": "🔧", "text": "シェルスクリプトを書くのを手伝って"}
  ],
  "ko": [
    {"icon": "🐍", "text": "Python Hello World 스크립트 만들기"},
    {"icon": "📁", "text": "작업 공간 디렉토리의 파일 목록 보기"},
    {"icon": "📄", "text": "README.md 파일 읽기"},
    {"icon": "🔧", "text": "쉘 스크립트 작성 도와줘"}
  ],
  "ru": [
    {"icon": "🐍", "text": "Создайте скрипт Python Hello World"},
    {"icon": "📁", "text": "Покажите файлы в рабочей директории"},
    {"icon": "📄", "text": "Прочитайте файл README.md"},
    {"icon": "🔧", "text": "Помогите написать скрипт оболочки"}
  ]
}
```

## Backend API

### New endpoint

```
PUT /api/auth/profile/metadata
Authorization: Bearer <JWT>
Content-Type: application/json

Body: { "metadata": { "language": "zh" } }
Response: { "metadata": { "language": "zh", "theme": "dark" } }
```

- Partial update: merges provided keys into existing metadata
- Requires authentication

### Modified endpoints

- `GET /api/auth/profile` — response includes `metadata` field
- Login/OAuth responses — include user metadata (or frontend fetches profile separately)

### Storage layer

File: `src/infra/user/storage.py`

New method: `update_metadata(user_id: str, metadata: dict)` — merges metadata into user document using `$set` on the `metadata` key.

## Frontend Changes

### Type update

File: `frontend/src/types/auth.ts`

```typescript
interface User {
  // ...existing fields
  metadata?: {
    language?: string;
    theme?: string;
  };
}
```

### Login sync

In `useAuth.tsx`, after successful login/profile fetch:

```
if user.metadata?.language → localStorage.setItem("language", lang) + i18n.changeLanguage(lang)
if user.metadata?.theme → localStorage.setItem("lamb-agent-theme", theme) + apply theme
```

### Preference toggle sync

- `LanguageToggle.tsx`: on language change, call `PUT /api/auth/profile/metadata` in background (non-blocking)
- `ThemeToggle.tsx` / `ThemeContext.tsx`: on theme change, call `PUT /api/auth/profile/metadata` in background
- API failures are silent — localStorage remains the source of truth for the session

### Welcome suggestions

File: `frontend/src/components/layout/AppContent.tsx`

```typescript
const currentLang = i18n.language?.split('-')[0] || 'en'
const suggestions = welcomeSuggestions?.[currentLang] || welcomeSuggestions?.en || []
```

Fallback chain: current language → English → empty array.

### ProfileModal Preferences Tab

New file: `frontend/src/components/profile/tabs/ProfilePreferencesTab.tsx`

Tab list becomes: Profile | Change Password | Notifications | Default Agent | **Preferences**

Tab contents:
- Language selector: dropdown with supported languages (en, zh, ja, ko, ru) showing native names
- Theme selector: light/dark toggle (synced with ThemeContext)
- Changes apply immediately + write to backend

## Files Changed

| Layer | File | Change |
|-------|------|--------|
| Backend Schema | `src/kernel/schemas/user.py` | Add `metadata: Optional[dict]` |
| Backend Storage | `src/infra/user/storage.py` | Add `update_metadata()` |
| Backend Manager | `src/infra/user/manager.py` | Add `update_metadata()` |
| Backend API | `src/api/routes/auth/profile.py` | Add PUT metadata endpoint, include metadata in GET |
| Backend Config | `src/kernel/config/definitions.py` | WELCOME_SUGGESTIONS multi-language default |
| Frontend Type | `frontend/src/types/auth.ts` | Add `metadata` to User |
| Frontend API | `frontend/src/services/api/auth.ts` | Add `updateMetadata()` |
| Frontend Auth | `frontend/src/hooks/useAuth.tsx` | Sync metadata on login |
| Frontend Context | `frontend/src/contexts/ThemeContext.tsx` | Sync theme to backend on change |
| Frontend Component | `frontend/src/components/common/LanguageToggle.tsx` | Sync language to backend on change |
| Frontend Component | `frontend/src/components/layout/AppContent.tsx` | Multi-language suggestion lookup |
| Frontend Component | `frontend/src/components/profile/ProfileModal.tsx` | Add Preferences tab |
| Frontend Component | `frontend/src/components/profile/tabs/ProfilePreferencesTab.tsx` | New file |

## Error Handling

- Backend API failure on metadata update: silent — localStorage is the session source of truth
- Invalid metadata values: backend validates language code against supported list, theme against `["light", "dark"]`
- Missing metadata on existing users: frontend falls back to localStorage → browser language → "en"

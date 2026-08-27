# App Auto-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one-click auto-update to LambChat for Desktop (Tauri) and Mobile (Capacitor Android/iOS) platforms.

**Architecture:** Desktop uses `tauri-plugin-updater` to check GitHub Releases, download signed packages, install, and relaunch. Mobile uses the existing backend `/api/version` endpoint to detect updates, then downloads APK directly (Android) or opens the release page (iOS). Both platforms share a `UpdateDialog` component and `useAutoUpdate` hook.

**Tech Stack:** Tauri v2 plugin-updater/process, Capacitor v7, React 19, react-hot-toast, i18next, TailwindCSS

---

### Task 1: Backend — Extend GitHubRelease and VersionResponse

Add `ReleaseAsset` model and `body` (release notes) to `GitHubRelease`. Extend `VersionResponse` to include `release_notes` and `release_assets`.

**Files:**
- Modify: `src/infra/github_client.py`
- Modify: `src/kernel/schemas/agent.py`
- Modify: `src/api/routes/version.py`
- Test: `tests/test_version_route.py`

- [ ] **Step 1: Add `ReleaseAsset` model to schemas**

In `src/kernel/schemas/agent.py`, add the new model right before the `VersionResponse` class (before line 164):

```python
class ReleaseAsset(BaseModel):
    """GitHub release asset for mobile download."""

    name: str = Field(..., description="Asset filename")
    url: str = Field(..., description="Asset download URL")
    size: Optional[int] = Field(None, description="File size in bytes")
    content_type: str = Field("application/octet-stream", description="MIME type")
```

- [ ] **Step 2: Extend `VersionResponse` with new fields**

In `src/kernel/schemas/agent.py`, add two new fields to `VersionResponse` (after line 175):

```python
    release_notes: Optional[str] = Field(None, description="Release body/notes")
    release_assets: Optional[list[ReleaseAsset]] = Field(None, description="Release assets for mobile")
```

- [ ] **Step 3: Extend `GitHubRelease` dataclass with `body` and `assets`**

In `src/infra/github_client.py`, update the `GitHubRelease` dataclass (replace lines 14-20):

```python
@dataclass
class GitHubRelease:
    """GitHub release information"""

    tag_name: str
    html_url: str
    published_at: str
    body: str = ""
    assets: list[dict] = None

    def __post_init__(self):
        if self.assets is None:
            self.assets = []
```

- [ ] **Step 4: Update `_parse_release` to extract body and assets**

In `src/infra/github_client.py`, update `_parse_release` (replace lines 62-68):

```python
def _parse_release(self, data: dict) -> GitHubRelease:
    """Parse GitHub API response"""
    assets = []
    for asset in data.get("assets", []):
        assets.append(
            {
                "name": asset.get("name", ""),
                "url": asset.get("browser_download_url", ""),
                "size": asset.get("size"),
                "content_type": asset.get("content_type", "application/octet-stream"),
            }
        )
    return GitHubRelease(
        tag_name=data.get("tag_name", ""),
        html_url=data.get("html_url", ""),
        published_at=data.get("published_at", ""),
        body=data.get("body", ""),
        assets=assets,
    )
```

- [ ] **Step 5: Update version route to return new fields**

In `src/api/routes/version.py`, update the route to include `release_notes` and `release_assets` in the response (replace lines 26-36):

```python
release_assets = None
if latest_release:
    release_assets = [ReleaseAsset(**asset) for asset in latest_release.assets]

return VersionResponse(
    app_version=settings.APP_VERSION,
    git_tag=settings.GIT_TAG,
    commit_hash=settings.COMMIT_HASH,
    build_time=settings.BUILD_TIME,
    latest_version=normalize_version(latest_release.tag_name) if latest_release else None,
    release_url=latest_release.html_url if latest_release else None,
    github_url=settings.GITHUB_URL,
    has_update=has_update,
    published_at=latest_release.published_at if latest_release else None,
    release_notes=latest_release.body if latest_release else None,
    release_assets=release_assets,
)
```

Add the import at the top of `version.py`:

```python
from src.kernel.schemas.agent import ReleaseAsset, VersionResponse
```

- [ ] **Step 6: Verify the backend starts without errors**

Run: `cd /home/yangyang/LambChat && python -c "from src.api.routes.version import router; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add src/infra/github_client.py src/kernel/schemas/agent.py src/api/routes/version.py
git commit -m "feat: extend version API with release notes and assets for auto-update"
```

---

### Task 2: Backend — Write Tests for Version API Enhancement

**Files:**
- Create: `tests/test_version_route.py`

- [ ] **Step 1: Write tests for the extended version API**

Create `tests/test_version_route.py`:

```python
"""Tests for version route with release assets."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.infra.github_client import GitHubClient, GitHubRelease


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def make_mock_release(**overrides) -> GitHubRelease:
    defaults = dict(
        tag_name="v2.6.0",
        html_url="https://github.com/Yanyutin753/LambChat/releases/tag/v2.6.0",
        published_at="2026-06-11T00:00:00Z",
        body="## What's New\n- Fixed bugs\n- Added features",
        assets=[
            {
                "name": "LambChat-v2.6.0-android-signed.apk",
                "url": "https://github.com/Yanyutin753/LambChat/releases/download/v2.6.0/LambChat-v2.6.0-android-signed.apk",
                "size": 50_000_000,
                "content_type": "application/vnd.android.package-archive",
            }
        ],
    )
    defaults.update(overrides)
    return GitHubRelease(**defaults)


def test_version_response_has_release_notes(client):
    release = make_mock_release()
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=release
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_notes"] == "## What's New\n- Fixed bugs\n- Added features"


def test_version_response_has_release_assets(client):
    release = make_mock_release()
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=release
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_assets"] is not None
        assert len(data["release_assets"]) == 1
        asset = data["release_assets"][0]
        assert asset["name"] == "LambChat-v2.6.0-android-signed.apk"
        assert "android-signed.apk" in asset["url"]
        assert asset["size"] == 50_000_000


def test_version_response_no_release(client):
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=None
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_notes"] is None
        assert data["release_assets"] is None
```

- [ ] **Step 2: Run the tests**

Run: `cd /home/yangyang/LambChat && python -m pytest tests/test_version_route.py -v`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_version_route.py
git commit -m "test: add tests for version API release notes and assets"
```

---

### Task 3: Tauri — Configure Updater Plugin

**Files:**
- Modify: `frontend/src-tauri/tauri.conf.json`
- Modify: `frontend/src-tauri/Cargo.toml`
- Modify: `frontend/src-tauri/src/lib.rs`
- Modify: `frontend/src-tauri/capabilities/default.json`

- [ ] **Step 1: Add updater config to tauri.conf.json**

Replace the full content of `frontend/src-tauri/tauri.conf.json` with:

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "LambChat",
  "version": "2.5.0",
  "identifier": "com.lambchat.app",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "pnpm dev",
    "beforeBuildCommand": "pnpm packaged:build"
  },
  "app": {
    "windows": [
      {
        "title": "LambChat",
        "width": 1280,
        "height": 860,
        "minWidth": 960,
        "minHeight": 640
      }
    ],
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "createUpdaterArtifacts": true,
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  },
  "plugins": {
    "updater": {
      "endpoints": [
        "https://github.com/Yanyutin753/LambChat/releases/latest/download/latest.json"
      ]
    }
  }
}
```

Note: `pubkey` will be added after generating signing keys (Task 8). The version is bumped from `2.4.1` to `2.5.0` to match `pyproject.toml`.

- [ ] **Step 2: Add Rust dependencies to Cargo.toml**

In `frontend/src-tauri/Cargo.toml`, add two new dependencies (after line 18):

```toml
tauri-plugin-updater = "2"
tauri-plugin-process = "2"
```

And update the `version` field on line 3 from `"2.4.1"` to `"2.5.0"`.

- [ ] **Step 3: Register plugins in lib.rs**

Replace the content of `frontend/src-tauri/src/lib.rs` with:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .run(tauri::generate_context!())
        .expect("error while running LambChat desktop app");
}
```

- [ ] **Step 4: Add updater permission to capabilities**

Replace the content of `frontend/src-tauri/capabilities/default.json` with:

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default desktop capability",
  "windows": ["main"],
  "permissions": ["core:default", "notification:default", "updater:default"]
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src-tauri/
git commit -m "feat(tauri): configure updater and process plugins for auto-update"
```

---

### Task 4: Frontend — Add Tauri Updater/Process JS Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Add JS packages**

Run:
```bash
cd /home/yangyang/LambChat/frontend && pnpm add @tauri-apps/plugin-updater @tauri-apps/plugin-process
```

This installs the JavaScript/TypeScript bindings for the Tauri updater and process plugins.

- [ ] **Step 2: Verify packages are in package.json**

Check that `frontend/package.json` now contains:
```json
"@tauri-apps/plugin-updater": "^2",
"@tauri-apps/plugin-process": "^2"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: add tauri updater and process JS packages"
```

---

### Task 5: Frontend — Add Types and i18n Keys

**Files:**
- Modify: `frontend/src/types/common.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`

- [ ] **Step 1: Add `UpdateState` type and extend `VersionInfo`**

In `frontend/src/types/common.ts`, add the `UpdateState` interface and the `ReleaseAsset` interface after the existing `VersionInfo` (after line 16):

```typescript
export interface ReleaseAsset {
  name: string;
  url: string;
  size?: number;
  content_type: string;
}

export interface UpdateState {
  available: boolean;
  version: string | null;
  releaseNotes: string | null;
  releaseUrl: string | null;
  releaseAssets: ReleaseAsset[];
  publishedAt: string | null;
  downloading: boolean;
  progress: number;
  contentLength: number;
  downloaded: number;
  error: string | null;
}
```

- [ ] **Step 2: Add i18n keys to en.json**

In `frontend/src/i18n/locales/en.json`, find the `"about"` section (around line 2) and add these keys after the existing ones:

```json
"updateAvailable": "New version available!",
"updateChecking": "Checking for updates...",
"updateDownload": "Update Now",
"updateDownloading": "Downloading...",
"updateDownloadProgress": "{{percent}}% downloaded",
"updateSkip": "Later",
"updateError": "Update failed",
"updateRetry": "Retry",
"updateSuccess": "Update ready! Restarting...",
"updateInstall": "Install Now",
"updateGoToDownload": "Go to Download",
"updateNewVersion": "New version {{version}} available",
"updateReleaseNotes": "Release Notes",
"updatePublishedAt": "Published {{date}}"
```

Note: `updateAvailable` already exists. Only add the keys that are not already present. Check the existing `about` section first, then add the missing ones.

- [ ] **Step 3: Add i18n keys to zh.json**

In `frontend/src/i18n/locales/zh.json`, find the `"about"` section and add the same keys with Chinese translations:

```json
"updateAvailable": "发现新版本！",
"updateChecking": "正在检查更新...",
"updateDownload": "立即升级",
"updateDownloading": "正在下载...",
"updateDownloadProgress": "已下载 {{percent}}%",
"updateSkip": "稍后提醒",
"updateError": "更新失败",
"updateRetry": "重试",
"updateSuccess": "更新就绪！正在重启...",
"updateInstall": "立即安装",
"updateGoToDownload": "前往下载",
"updateNewVersion": "发现新版本 {{version}}",
"updateReleaseNotes": "更新内容",
"updatePublishedAt": "发布于 {{date}}"
```

Again, only add keys that don't already exist.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/common.ts frontend/src/i18n/locales/
git commit -m "feat: add update state types and i18n keys for auto-update"
```

---

### Task 6: Frontend — Create `UpdateProgressBar` Component

**Files:**
- Create: `frontend/src/components/update/UpdateProgressBar.tsx`

- [ ] **Step 1: Create the progress bar component**

Create `frontend/src/components/update/UpdateProgressBar.tsx`:

```tsx
import { useTranslation } from "react-i18next";

interface UpdateProgressBarProps {
  progress: number;
  downloaded: number;
  contentLength: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UpdateProgressBar({
  progress,
  downloaded,
  contentLength,
}: UpdateProgressBarProps) {
  const { t } = useTranslation();

  const percent = Math.min(Math.round(progress), 100);
  const downloadedStr = formatBytes(downloaded);
  const totalStr = contentLength > 0 ? formatBytes(contentLength) : "?";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-stone-500 dark:text-stone-400">
        <span>
          {t("updateDownloading", "正在下载...")}
        </span>
        <span>
          {downloadedStr} / {totalStr} — {percent}%
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
        <div
          className="h-full rounded-full bg-[var(--theme-primary)] transition-all duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/update/UpdateProgressBar.tsx
git commit -m "feat: add UpdateProgressBar component for download progress"
```

---

### Task 7: Frontend — Create `UpdateDialog` Component

**Files:**
- Create: `frontend/src/components/update/UpdateDialog.tsx`

- [ ] **Step 1: Create the update dialog component**

Create `frontend/src/components/update/UpdateDialog.tsx`:

```tsx
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Download, ExternalLink, RefreshCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { UpdateProgressBar } from "./UpdateProgressBar";
import type { UpdateState } from "../../types";

interface UpdateDialogProps {
  state: UpdateState;
  isOpen: boolean;
  onUpgrade: () => void;
  onSkip: () => void;
  onDismiss: () => void;
  /** Platform: "tauri" uses native updater, "android" downloads APK, "ios" opens browser */
  platform: "tauri" | "android" | "ios";
}

export function UpdateDialog({
  state,
  isOpen,
  onUpgrade,
  onSkip,
  onDismiss,
  platform,
}: UpdateDialogProps) {
  const { t } = useTranslation();
  useBodyScrollLock(isOpen);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape" && !state.downloading) {
        onDismiss();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onDismiss, state.downloading]);

  if (!isOpen) return null;

  return createPortal(
    <div className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={state.downloading ? undefined : onDismiss}
      />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-md mx-4 bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <div className="flex items-center gap-2">
            <Download
              size={20}
              className="text-[var(--theme-primary)]"
            />
            <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">
              {t("updateNewVersion", {
                version: state.version ?? "",
              })}
            </h3>
          </div>
          {!state.downloading && (
            <button
              onClick={onDismiss}
              className="inline-flex size-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
              aria-label={t("common.dismiss", "关闭")}
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-5 pb-4 space-y-3">
          {state.publishedAt && (
            <p className="text-xs text-stone-500 dark:text-stone-400">
              {t("updatePublishedAt", {
                date: new Date(state.publishedAt).toLocaleDateString(),
              })}
            </p>
          )}

          {state.releaseNotes && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-stone-600 dark:text-stone-300">
                {t("updateReleaseNotes", "更新内容")}
              </p>
              <div
                className="max-h-40 overflow-y-auto rounded-lg bg-stone-50 dark:bg-stone-900/50 p-3 text-sm text-stone-600 dark:text-stone-400 leading-relaxed prose prose-sm prose-stone dark:prose-invert max-w-none"
              >
                {state.releaseNotes}
              </div>
            </div>
          )}

          {/* Download progress */}
          {state.downloading && (
            <UpdateProgressBar
              progress={state.progress}
              downloaded={state.downloaded}
              contentLength={state.contentLength}
            />
          )}

          {/* Error */}
          {state.error && (
            <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-600 dark:text-red-400">
              {state.error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 bg-stone-50 dark:bg-stone-900/50 border-t border-stone-100 dark:border-stone-700">
          {!state.downloading && (
            <button
              onClick={onSkip}
              className="px-4 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors"
            >
              {t("updateSkip", "稍后提醒")}
            </button>
          )}

          {platform === "ios" ? (
            <button
              onClick={onUpgrade}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--theme-primary)] rounded-lg hover:opacity-90 transition-opacity inline-flex items-center gap-2"
            >
              <ExternalLink size={16} />
              {t("updateGoToDownload", "前往下载")}
            </button>
          ) : (
            <button
              onClick={onUpgrade}
              disabled={state.downloading}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--theme-primary)] rounded-lg hover:opacity-90 transition-opacity inline-flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {state.downloading ? (
                <span className="inline-flex h-4 w-4 items-center justify-center">
                  <LoadingSpinner size="sm" color="text-current" />
                </span>
              ) : (
                <RefreshCw size={16} />
              )}
              {state.downloading
                ? t("updateDownloading", "正在下载...")
                : t("updateDownload", "立即升级")}
            </button>
          )}

          {state.error && !state.downloading && (
            <button
              onClick={onUpgrade}
              className="px-4 py-2 text-sm font-medium text-stone-600 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 transition-colors"
            >
              {t("updateRetry", "重试")}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
```

Note: `publishedAt` is not currently in `UpdateState`. We'll add it in the `useAutoUpdate` hook (Task 8). The component accesses it via `state.publishedAt` which TypeScript will flag — that's intentional, the type will be extended in the next task.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/update/UpdateDialog.tsx
git commit -m "feat: add UpdateDialog component for auto-update prompt"
```

---

### Task 8: Frontend — Create `useAutoUpdate` Hook

**Files:**
- Create: `frontend/src/hooks/useAutoUpdate.ts`

- [ ] **Step 1: Create the auto-update hook**

Create `frontend/src/hooks/useAutoUpdate.ts`:

```typescript
import { useState, useEffect, useCallback, useRef } from "react";
import i18n from "i18next";
import { versionApi } from "../services/api";
import { isNativeAppRuntime } from "../services/api/config";
import type { UpdateState, ReleaseAsset, VersionInfo } from "../types";

/** Detect current runtime platform */
function detectPlatform(): "tauri" | "android" | "ios" | "web" {
  if (typeof window === "undefined") return "web";
  if (
    (window as unknown as Record<string, unknown>).__TAURI__ ||
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__
  )
    return "tauri";
  if (typeof (window as any).Capacitor !== "undefined") {
    const platform = (window as any).Capacitor.getPlatform();
    if (platform === "android") return "android";
    if (platform === "ios") return "ios";
  }
  return "web";
}

/** Find the best APK asset from the release assets list */
function findApkAsset(assets: ReleaseAsset[]): ReleaseAsset | null {
  // Prefer signed APK, fall back to any APK
  const signed = assets.find(
    (a) => a.name.endsWith(".apk") && a.name.includes("signed"),
  );
  if (signed) return signed;
  const anyApk = assets.find((a) => a.name.endsWith(".apk"));
  return anyApk ?? null;
}

export interface UseAutoUpdateReturn {
  state: UpdateState;
  showDialog: boolean;
  setShowDialog: (v: boolean) => void;
  startUpdate: () => Promise<void>;
  skipUpdate: () => void;
}

const INITIAL_STATE: UpdateState = {
  available: false,
  version: null,
  releaseNotes: null,
  releaseUrl: null,
  releaseAssets: [],
  publishedAt: null,
  downloading: false,
  progress: 0,
  contentLength: 0,
  downloaded: 0,
  error: null,
};

/** Debounce delay (ms) before checking for updates on startup */
const CHECK_DELAY_MS = 5000;

export function useAutoUpdate(): UseAutoUpdateReturn {
  const [state, setState] = useState<UpdateState>(INITIAL_STATE);
  const [showDialog, setShowDialog] = useState(false);
  const platformRef = useRef(detectPlatform());
  const checkedRef = useRef(false);

  const platform = platformRef.current;

  /** Check for updates */
  const checkForUpdate = useCallback(async () => {
    if (platform === "tauri") {
      await checkTauriUpdate();
    } else if (platform === "android" || platform === "ios") {
      await checkBackendUpdate();
    }
    // web: no-op
  }, [platform]);

  /** Check via Tauri updater plugin */
  const checkTauriUpdate = useCallback(async () => {
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (update?.available) {
        setState({
          ...INITIAL_STATE,
          available: true,
          version: update.version,
          releaseNotes: update.body ?? null,
          releaseUrl: null,
          releaseAssets: [],
        });
        setShowDialog(true);
      }
    } catch {
      // Silently fail — updater may not be available in dev
    }
  }, []);

  /** Check via backend /api/version endpoint */
  const checkBackendUpdate = useCallback(async () => {
    try {
      const info: VersionInfo = await versionApi.checkForUpdates();
      if (info.has_update) {
        setState({
          ...INITIAL_STATE,
          available: true,
          version: info.latest_version ?? null,
          releaseNotes: (info as VersionInfo & { release_notes?: string }).release_notes ?? null,
          releaseUrl: info.release_url ?? null,
          releaseAssets: (info as VersionInfo & { release_assets?: ReleaseAsset[] }).release_assets ?? [],
        });
        setShowDialog(true);
      }
    } catch {
      // Silently fail
    }
  }, []);

  /** Start the update process */
  const startUpdate = useCallback(async () => {
    if (platform === "tauri") {
      await installTauriUpdate();
    } else if (platform === "android") {
      await installAndroidUpdate();
    } else if (platform === "ios") {
      openReleasePage();
    }
  }, [platform, state]);

  /** Install via Tauri updater (download + install + relaunch) */
  const installTauriUpdate = useCallback(async () => {
    setState((prev) => ({ ...prev, downloading: true, error: null, progress: 0 }));
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      const update = await check();
      if (!update) throw new Error("No update found");

      let downloaded = 0;
      let contentLength = 0;

      await update.downloadAndInstall((event: any) => {
        switch (event.event) {
          case "Started":
            contentLength = event.data.contentLength ?? 0;
            setState((prev) => ({ ...prev, contentLength }));
            break;
          case "Progress":
            downloaded += event.data.chunkLength;
            const pct = contentLength > 0 ? (downloaded / contentLength) * 100 : 0;
            setState((prev) => ({
              ...prev,
              downloaded,
              progress: pct,
            }));
            break;
          case "Finished":
            setState((prev) => ({ ...prev, progress: 100 }));
            break;
        }
      });

      // Download and install complete, relaunch
      await relaunch();
    } catch (err) {
      setState((prev) => ({
        ...prev,
        downloading: false,
        error:
          err instanceof Error
            ? err.message
            : i18n.t("updateError", "更新失败"),
      }));
    }
  }, []);

  /** Download APK and trigger Android install intent */
  const installAndroidUpdate = useCallback(async () => {
    setState((prev) => ({ ...prev, downloading: true, error: null, progress: 0 }));
    try {
      const apkAsset = findApkAsset(state.releaseAssets);
      if (!apkAsset) throw new Error("No APK found in release assets");

      const response = await fetch(apkAsset.url);
      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const contentLength = Number(response.headers.get("content-length") ?? 0);
      const totalChunks: number[] = [];
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        totalChunks.push(...value);
        const dl = totalChunks.length;
        const pct = contentLength > 0 ? (dl / contentLength) * 100 : 0;
        setState((prev) => ({
          ...prev,
          downloaded: dl,
          progress: pct,
          contentLength,
        }));
      }

      const blob = new Blob(totalChunks, { type: apkAsset.content_type });

      // Use Capacitor Filesystem to write the APK, then open it
      const { Filesystem, Directory } = await import("@capacitor/filesystem");
      const base64 = await blobToBase64(blob);
      const fileName = apkAsset.name || "LambChat-update.apk";
      const result = await Filesystem.writeFile({
        path: fileName,
        data: base64,
        directory: Directory.Cache,
      });

      // Use Capacitor Share to open the APK file (triggers install)
      const { Share } = await import("@capacitor/share");
      await Share.share({
        path: result.uri,
      });

      setState((prev) => ({
        ...prev,
        downloading: false,
        progress: 100,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        downloading: false,
        error:
          err instanceof Error
            ? err.message
            : i18n.t("updateError", "更新失败"),
      }));
    }
  }, [state.releaseAssets]);

  /** Open release page in browser (iOS) */
  const openReleasePage = useCallback(() => {
    if (state.releaseUrl) {
      window.open(state.releaseUrl, "_blank", "noopener");
    }
  }, [state.releaseUrl]);

  /** Skip this update */
  const skipUpdate = useCallback(() => {
    setShowDialog(false);
  }, []);

  // Auto-check on mount with delay
  useEffect(() => {
    if (platform === "web") return;
    if (checkedRef.current) return;
    checkedRef.current = true;

    const timer = setTimeout(() => {
      checkForUpdate();
    }, CHECK_DELAY_MS);

    return () => clearTimeout(timer);
  }, [platform, checkForUpdate]);

  return {
    state,
    showDialog,
    setShowDialog,
    startUpdate,
    skipUpdate,
  };
}

/** Convert a Blob to base64 string */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // Remove data URL prefix: "data:...;base64,"
      const base64 = result.split(",")[1] || "";
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useAutoUpdate.ts
git commit -m "feat: add useAutoUpdate hook for desktop and mobile auto-update"
```

---

### Task 9: Frontend — Integrate UpdateDialog in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add the auto-update hook and dialog to App.tsx**

In `frontend/src/App.tsx`:

**a)** Add import at the top (after line 26, before the lazy imports or at line 27):

```typescript
import { UpdateDialog } from "./components/update/UpdateDialog";
import { useAutoUpdate } from "./hooks/useAutoUpdate";
```

**b)** Inside the `App` function component (after line 324, the `const navigate = useNavigate();` line), add the hook call:

```typescript
  // Auto-update for desktop and mobile
  const { state: updateState, showDialog: showUpdateDialog, setShowDialog: setShowUpdateDialog, startUpdate, skipUpdate } = useAutoUpdate();
  const updatePlatform = updateState.available
    ? (typeof window !== "undefined" &&
        ((window as any).__TAURI__ || (window as any).__TAURI_INTERNALS__)
          ? "tauri"
          : typeof (window as any).Capacitor !== "undefined"
            ? (window as any).Capacitor.getPlatform() === "ios"
              ? "ios"
              : "android"
            : "web")
    : "tauri"; // default, won't render if not available
```

**c)** In the JSX, add the `UpdateDialog` right after `<PwaStatusToasts />` (line 395), before `<SelectionActionPopover />`:

```tsx
        {showUpdateDialog && (
          <UpdateDialog
            state={updateState}
            isOpen={showUpdateDialog}
            onUpgrade={startUpdate}
            onSkip={skipUpdate}
            onDismiss={() => setShowUpdateDialog(false)}
            platform={updatePlatform as "tauri" | "android" | "ios"}
          />
        )}
```

- [ ] **Step 2: Verify the frontend builds without errors**

Run: `cd /home/yangyang/LambChat/frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No TypeScript errors (or only pre-existing ones unrelated to our changes)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: integrate auto-update dialog in App component"
```

---

### Task 10: Android — Add Install Permission

**Files:**
- Modify: `frontend/android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Add REQUEST_INSTALL_PACKAGES permission**

In `frontend/android/app/src/main/AndroidManifest.xml`, add the new permission after the existing `POST_NOTIFICATIONS` permission (after line 41):

```xml
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
```

The permissions section at the bottom of the file should now look like:

```xml
    <!-- Permissions -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/android/app/src/main/AndroidManifest.xml
git commit -m "feat(android): add REQUEST_INSTALL_PACKAGES permission for auto-update"
```

---

### Task 11: Version Sync — Unify Version Numbers

**Files:**
- Modify: `frontend/package.json` (line ~4, `"version": "2.4.1"`)
- Note: `tauri.conf.json` and `Cargo.toml` were already updated in Task 3

- [ ] **Step 1: Update frontend/package.json version**

In `frontend/package.json`, change `"version": "2.4.1"` to `"version": "2.5.0"`.

- [ ] **Step 2: Verify all version files match**

Run: `grep -rn '"version".*"2\.5\.0"' /home/yangyang/LambChat/frontend/package.json /home/yangyang/LambChat/frontend/src-tauri/tauri.conf.json /home/yangyang/LambChat/frontend/src-tauri/Cargo.toml /home/yangyang/LambChat/pyproject.toml`
Expected: All 4 files show `"2.5.0"` (pyproject.toml uses `version = "2.5.0"` without quotes around the key, grep will still match).

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json
git commit -m "chore: sync frontend version to 2.5.0"
```

---

### Task 12: CI/CD — Add Signing Keys and Updater Manifest Collection

**Files:**
- Modify: `.github/workflows/app-release.yml`

- [ ] **Step 1: Add TAURI_SIGNING_PRIVATE_KEY to desktop build step**

In `.github/workflows/app-release.yml`, find the "Build desktop package with Tauri" step (around line 121) and update the `env` block to include signing keys:

```yaml
      - name: Build desktop package with Tauri
        env:
          TAURI_BUNDLES: ${{ matrix.bundles }}
          TAURI_TARGET: ${{ matrix.target || '' }}
          TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
          CARGO_BUILD_JOBS: 1
        run: pnpm package:desktop
        working-directory: frontend
```

- [ ] **Step 2: Add updater manifest collection step after artifact collection**

For each platform (Linux, Windows, macOS), add a step after the artifact collection steps. Add this after each "Collect Linux/Windows/macOS desktop artifacts" step:

```yaml
      - name: Collect updater manifest artifacts
        if: runner.os == 'Linux' || runner.os == 'Windows' || runner.os == 'macOS'
        shell: bash
        run: |
          set -euo pipefail
          # Find platform-specific updater manifests generated by Tauri
          find frontend/src-tauri/target -name "latest*.json" -exec cp {} release-assets/ \; 2>/dev/null || true
          find frontend/src-tauri/target -name "*.sig" -exec cp {} release-assets/ \; 2>/dev/null || true
          ls -la release-assets/ 2>/dev/null || true
```

Note: This step runs after the platform-specific artifact collection steps. Place it once after ALL platform collection steps, before the "Upload desktop artifacts" step. Since each matrix entry has its own steps, this single step covers each platform.

- [ ] **Step 3: Add manifest merge step in the release job**

In the release job (after the "Ensure release has useful installable artifacts" step, around line 411), add:

```yaml
      - name: Merge updater manifests
        run: |
          # Find all platform-specific latest*.json files and merge into latest.json
          python3 -c "
          import json, glob, os
          platform_files = glob.glob('release-assets/latest*.json') or glob.glob('release-assets/*-latest.json')
          if not platform_files:
              print('No updater manifests found')
              exit(0)
          merged = {}
          for f in sorted(platform_files):
              data = json.load(open(f))
              # Merge platforms dict
              if 'platforms' in data:
                  merged['platforms'] = merged.get('platforms', {})
                  merged['platforms'].update(data['platforms'])
              # Take version/notes/date from first file
              if 'version' not in merged and 'version' in data:
                  merged['version'] = data['version']
              if 'notes' not in merged and 'notes' in data:
                  merged['notes'] = data['notes']
              if 'pub_date' not in merged and 'pub_date' in data:
                  merged['pub_date'] = data['pub_date']
          if merged:
              with open('release-assets/latest.json', 'w') as out:
                  json.dump(merged, out, indent=2)
              print(f'Merged {len(platform_files)} manifests into latest.json')
          "
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/app-release.yml
git commit -m "ci: add updater signing keys and manifest merge for auto-update"
```

---

### Task 13: Generate Signing Keys (Manual Step)

This step requires manual action from the developer — it cannot be automated because the private key must be kept secret.

- [ ] **Step 1: Generate Ed25519 signing key pair**

Run:
```bash
cd /home/yangyang/LambChat/frontend && pnpm tauri signer generate -w ~/.tauri/lambchat.key
```

This generates two files:
- `~/.tauri/lambchat.key` — private key (NEVER commit this)
- `~/.tauri/lambchat.key.pub` — public key

- [ ] **Step 2: Add public key to tauri.conf.json**

Read the public key file:
```bash
cat ~/.tauri/lambchat.key.pub
```

Copy the content and paste it as the `pubkey` value in `frontend/src-tauri/tauri.conf.json` under `plugins.updater.pubkey`.

- [ ] **Step 3: Add private key to GitHub Secrets**

Go to: `https://github.com/Yanyutin753/LambChat/settings/secrets/actions`

Add two secrets:
- `TAURI_SIGNING_PRIVATE_KEY` = contents of `~/.tauri/lambchat.key`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` = the password you set during generation (if any)

- [ ] **Step 4: Commit the pubkey change**

```bash
git add frontend/src-tauri/tauri.conf.json
git commit -m "feat(tauri): add updater public key for signature verification"
```

---

### Task 14: Verify Full Frontend Build

**Files:** None (verification only)

- [ ] **Step 1: Run frontend type check**

Run: `cd /home/yangyang/LambChat/frontend && npx tsc --noEmit`
Expected: No errors (or only pre-existing errors)

- [ ] **Step 2: Run frontend build**

Run: `cd /home/yangyang/LambChat/frontend && pnpm packaged:build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Run backend lint**

Run: `cd /home/yangyang/LambChat && ruff check src/`
Expected: No errors

- [ ] **Step 4: Run frontend lint**

Run: `cd /home/yangyang/LambChat/frontend && npx eslint src/hooks/useAutoUpdate.ts src/components/update/`
Expected: No errors

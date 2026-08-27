# LambChat App Auto-Update Design

**Date**: 2026-06-11
**Status**: Approved
**Scope**: Desktop (Tauri) + Mobile (Capacitor Android/iOS)

## Summary

Add a one-click auto-update feature to LambChat. On app startup, the app checks for new versions and presents an update dialog. Users can download and install the update with a single click.

## Background

LambChat ships in 4 form factors (Web, Desktop Tauri, Mobile Capacitor, PWA). The backend already has a `/api/version` endpoint that checks GitHub Releases for the latest version and reports whether an update is available. However, there is no actual download/install mechanism — it only displays version info.

This design adds real auto-update capabilities for **Desktop (Tauri)** and **Mobile (Capacitor)** platforms.

## Approach

**Desktop**: Use `tauri-plugin-updater` — the official Tauri plugin that checks GitHub Releases, downloads signed update packages, and installs them with a single API call.

**Mobile**: Use the existing `/api/version` backend endpoint for version checking, then download APK directly from GitHub Releases and trigger Android system installer. iOS redirects to the GitHub Release page (iOS cannot install IPA directly).

## Requirements

1. App checks for updates automatically on startup
2. When a new version is available, show a dialog with version number, release notes, and download progress
3. User confirms to download; download completes and installs automatically
4. Desktop: Tauri updater handles download, signature verification, install, and relaunch
5. Android: Download APK from GitHub Releases, trigger system install intent
6. iOS: Show dialog with link to GitHub Release page (system limitation)
7. Update source is GitHub Releases (already used by CI/CD)
8. Update packages must be signed to prevent tampering

## Architecture

### Desktop (Tauri) Flow

```
App startup
  → useAutoUpdate() hook calls check() from @tauri-apps/plugin-updater
  → Tauri plugin fetches latest.json from GitHub Releases
  → New version found → UpdateDialog shown
  → User clicks "Upgrade" → downloadAndInstall() with progress callback
  → Download complete → relaunch() from @tauri-apps/plugin-process
```

### Mobile (Capacitor) Flow

```
App startup
  → useAutoUpdate() hook calls /api/version (backend endpoint)
  → Backend fetches latest release info from GitHub API
  → New version found → UpdateDialog shown
  → User clicks "Upgrade"
    → Android: Download APK from GitHub Release asset URL → trigger Intent install
    → iOS: Open GitHub Release page in browser
```

### Shared Components

Both platforms share the same `UpdateDialog` UI component. The `useAutoUpdate` hook detects the platform and dispatches to the appropriate update mechanism.

## Detailed Changes

### 1. Tauri Configuration (`frontend/src-tauri/tauri.conf.json`)

Add updater plugin configuration:

```json
{
  "bundle": {
    "createUpdaterArtifacts": true
  },
  "plugins": {
    "updater": {
      "pubkey": "<public key content>",
      "endpoints": [
        "https://github.com/Yanyutin753/LambChat/releases/latest/download/latest.json"
      ]
    }
  }
}
```

- `createUpdaterArtifacts: true` — generates `.sig` signature files and platform manifests during build
- `endpoints` — URL pointing to the combined `latest.json` manifest in GitHub Releases
- `pubkey` — Ed25519 public key for verifying update signatures

### 2. Rust Dependencies (`frontend/src-tauri/Cargo.toml`)

Add:

```toml
tauri-plugin-updater = "2"
tauri-plugin-process = "2"
```

### 3. Rust Plugin Registration (`frontend/src-tauri/src/lib.rs`)

```rust
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .run(tauri::generate_context!())
        .expect("error while running LambChat desktop app");
}
```

### 4. Tauri Capabilities (`frontend/src-tauri/capabilities/default.json`)

Add updater permission:

```json
{
  "permissions": ["core:default", "notification:default", "updater:default"]
}
```

### 5. Frontend Dependencies (`frontend/package.json`)

Add:

```json
"@tauri-apps/plugin-updater": "^2",
"@tauri-apps/plugin-process": "^2"
```

### 6. New Frontend Files

| File | Purpose |
|---|---|
| `frontend/src/hooks/useAutoUpdate.ts` | Core update logic: platform detection, version check, download, install |
| `frontend/src/components/update/UpdateDialog.tsx` | Update dialog UI: version, release notes, progress bar, action buttons |
| `frontend/src/components/update/UpdateProgressBar.tsx` | Download progress bar with percentage and speed display |

### 7. `useAutoUpdate` Hook

```typescript
interface UpdateState {
  available: boolean;
  version: string | null;
  releaseNotes: string | null;
  downloading: boolean;
  progress: number;        // 0-100
  contentLength: number;   // total bytes
  downloaded: number;      // downloaded bytes
  error: string | null;
}

function useAutoUpdate(): {
  state: UpdateState;
  showDialog: boolean;
  setShowDialog: (v: boolean) => void;
  checkForUpdate: () => Promise<void>;
  startUpdate: () => Promise<void>;
  skipUpdate: () => void;
}
```

Platform detection logic:
- Tauri: use `check()` from `@tauri-apps/plugin-updater`
- Capacitor Android: use `/api/version` backend endpoint, then download APK from `release_url` + assets
- Capacitor iOS: use `/api/version` backend endpoint, then open release URL in browser
- Web/PWA: no-op (updates are server-side)

The hook checks for updates on mount (with a debounce to avoid blocking startup).

### 8. UpdateDialog Component

Visual layout:

```
┌─────────────────────────────────────┐
│  🔔 发现新版本 v{version}            │
│                                     │
│  发布日期: {published_at}           │
│                                     │
│  更新内容:                           │
│  {release_notes}                    │
│                                     │
│  [████████████░░░░░] 65% 12MB/s    │  ← only during download
│                                     │
│  [稍后提醒]           [立即升级]     │
└─────────────────────────────────────┘
```

States:
- **Checking**: spinner, "正在检查更新..."
- **Available**: show version, notes, and upgrade button
- **Downloading**: show progress bar, disable buttons
- **Error**: show error message, retry button

The dialog uses the existing toast system (`react-hot-toast`) for success/error notifications.

### 9. App.tsx Integration

In the root component, conditionally mount the auto-update hook and dialog:

```typescript
// In App.tsx
const { state, showDialog, setShowDialog, startUpdate, skipUpdate } = useAutoUpdate();

// Render UpdateDialog when applicable
{showDialog && (
  <UpdateDialog
    state={state}
    onUpgrade={startUpdate}
    onSkip={skipUpdate}
    onDismiss={() => setShowDialog(false)}
  />
)}
```

### 10. Android Configuration

Add to `frontend/android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
```

This permission allows the app to trigger APK installation from downloaded files.

For the APK download, the hook will:
1. Fetch the GitHub Release assets list via the backend API
2. Find the APK asset matching the device architecture
3. Download the APK to the app's cache directory
4. Trigger `Intent.ACTION_VIEW` with the APK URI and `application/vnd.android.package-archive` MIME type

### 11. iOS Behavior

iOS cannot install apps directly from outside the App Store. The update dialog will show a "前往下载" (Go to Download) button that opens the GitHub Release page in Safari.

### 12. CI/CD Changes (`app-release.yml`)

#### Signing Keys

Add GitHub Secrets:
- `TAURI_SIGNING_PRIVATE_KEY` — Ed25519 private key for signing desktop updates
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — optional password for the key

Generate keys with: `pnpm tauri signer generate -w ~/.tauri/lambchat.key`

#### Build Step Changes

In the desktop build step, set the signing environment variable:

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

#### Updater Manifest Collection

After building, Tauri generates platform-specific updater manifests (e.g., `latest-linux-x86_64.json`). These need to be collected and merged into a single `latest.json`:

```yaml
- name: Collect updater artifacts
  if: runner.os == 'Linux' || runner.os == 'Windows' || runner.os == 'macOS'
  shell: bash
  run: |
    # Tauri generates updater manifests in the bundle directory
    # Find and copy them for the release step
    find frontend/src-tauri/target -name "latest*.json" -exec cp {} release-assets/ \;
```

#### Release Manifest Merge

In the release job, merge all platform manifests into a single `latest.json` and upload to the release:

```yaml
- name: Merge updater manifests into latest.json
  run: |
    # Combine all platform manifests into one latest.json
    # The Tauri updater expects a specific format
    python3 scripts/merge-updater-manifests.py release-assets/
```

### 13. Version Number Synchronization

Current state (inconsistent):
- `pyproject.toml`: 2.5.0
- `frontend/package.json`: 2.4.1
- `frontend/src-tauri/tauri.conf.json`: 2.4.1
- `frontend/src-tauri/Cargo.toml`: 2.4.1

Resolution: `pyproject.toml` is the source of truth. Update all other files to match. Consider adding a script to sync versions across files.

### 14. Backend API Enhancement

Extend the `/api/version` response to include asset download URLs for mobile:

Add to `VersionResponse` schema:
```python
release_assets: list[ReleaseAsset] | None = None
```

Where `ReleaseAsset` contains:
```python
class ReleaseAsset(BaseModel):
    name: str  # e.g., "LambChat-v2.6.0-android-signed.apk"
    url: str  # download URL
    size: int | None  # file size in bytes
    content_type: str  # MIME type
```

This lets the mobile frontend find the correct APK without directly calling the GitHub API.

## Files to Modify

| File | Change |
|---|---|
| `frontend/src-tauri/tauri.conf.json` | Add updater plugin config |
| `frontend/src-tauri/Cargo.toml` | Add updater + process dependencies |
| `frontend/src-tauri/src/lib.rs` | Register updater plugin |
| `frontend/src-tauri/capabilities/default.json` | Add updater permission |
| `frontend/package.json` | Add tauri updater + process JS packages |
| `frontend/src/App.tsx` | Integrate auto-update hook and dialog |
| `frontend/android/app/src/main/AndroidManifest.xml` | Add install permission |
| `.github/workflows/app-release.yml` | Add signing keys, updater manifest collection |
| `src/api/routes/version.py` | Add release assets to response |
| `src/kernel/schemas/agent.py` | Add ReleaseAsset model |

## Files to Create

| File | Purpose |
|---|---|
| `frontend/src/hooks/useAutoUpdate.ts` | Auto-update logic hook |
| `frontend/src/components/update/UpdateDialog.tsx` | Update dialog UI |
| `frontend/src/components/update/UpdateProgressBar.tsx` | Progress bar component |
| `scripts/merge-updater-manifests.py` | Merge platform manifests for CI |

## Out of Scope

- Force update mechanism (mandatory upgrade) — can be added later
- Differential/incremental updates — full download only
- Beta/canary update channels — single stable channel only
- Self-hosted update server — GitHub Releases only

## Testing

1. **Desktop**: Build with `createUpdaterArtifacts: true` + signing key, verify `latest.json` is generated, verify update dialog appears when newer version exists on GitHub
2. **Android**: Verify APK download and install prompt on a real device
3. **iOS**: Verify Safari opens to GitHub Release page
4. **Version sync**: Verify all version files match after update

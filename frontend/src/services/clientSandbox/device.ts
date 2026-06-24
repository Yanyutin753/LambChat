import { isNativeAppRuntime, type BrowserLocationLike } from "../api/config";

const DEVICE_ID_KEY = "lambchat.clientSandbox.deviceId";
const WORKSPACE_ROOT_KEY = "lambchat.clientSandbox.workspaceRoot";

interface RuntimeGlobalLike {
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
  isTauri?: unknown;
}

export function isTauriDesktopRuntime(
  globalLike: RuntimeGlobalLike | null = typeof globalThis !== "undefined"
    ? (globalThis as RuntimeGlobalLike)
    : null,
  locationLike?: Partial<BrowserLocationLike> | null,
): boolean {
  if (
    globalLike?.__TAURI__ ||
    globalLike?.__TAURI_INTERNALS__ ||
    globalLike?.isTauri
  ) {
    return true;
  }

  const location =
    locationLike || (typeof window !== "undefined" ? window.location : null);
  const protocol = location?.protocol?.toLowerCase() || "";
  const hostname = location?.hostname?.toLowerCase() || "";
  return protocol === "tauri:" || hostname === "tauri.localhost";
}

export function getOrCreateClientSandboxDeviceId(
  storage: Storage = window.localStorage,
): string {
  const existing = storage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const deviceId = `desktop_${random}`;
  storage.setItem(DEVICE_ID_KEY, deviceId);
  return deviceId;
}

export function getClientSandboxWorkspaceRoot(
  storage: Storage = window.localStorage,
): string {
  const existing = storage.getItem(WORKSPACE_ROOT_KEY);
  if (existing) return existing;
  return "";
}

export function setClientSandboxWorkspaceRoot(
  workspaceRoot: string,
  storage: Storage = window.localStorage,
): void {
  storage.setItem(WORKSPACE_ROOT_KEY, workspaceRoot);
}

export function shouldStartClientSandboxService(
  locationLike?: Partial<BrowserLocationLike> | null,
  globalLike?: RuntimeGlobalLike | null,
): boolean {
  return (
    isNativeAppRuntime(locationLike, globalLike) &&
    isTauriDesktopRuntime(globalLike, locationLike)
  );
}

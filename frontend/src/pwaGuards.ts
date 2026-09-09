export interface PwaRegistrationSupport {
  isProduction: boolean;
  hasServiceWorker: boolean;
  /** Tauri 桌面壳（__TAURI__ / __TAURI_INTERNALS__ 注入）内恒不注册。 */
  isTauriShell?: boolean;
}

export const PWA_UPDATE_AVAILABLE_EVENT = "lambchat:pwa-update-available";
export const PWA_SKIP_WAITING_MESSAGE = "SKIP_WAITING";

/** Tauri 桌面壳探测：与 App.tsx / services/api/config.ts 认同一组标记。 */
export function isTauriShell(
  globalObject:
    | ({ __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown } & object)
    | undefined
    | null = globalThis as object,
): boolean {
  if (!globalObject) return false;
  return Boolean(globalObject.__TAURI__ || globalObject.__TAURI_INTERNALS__);
}

export function shouldRegisterPwa({
  isProduction,
  hasServiceWorker,
  isTauriShell: tauriShell = false,
}: PwaRegistrationSupport): boolean {
  // 桌面端更新走 Tauri updater 换装；SW 在壳内只会沉淀一层陈旧缓存，
  // updater 重启后回放旧 index.html/旧 chunk——桌面端动态导入 404 的
  // 主要根因（Windows WebView2 上 tauri.localhost 可注册 SW）。
  if (tauriShell) return false;
  return isProduction && hasServiceWorker;
}

export interface TauriPwaCleanupSupport {
  isTauriShell: boolean;
  hasServiceWorker: boolean;
}

export function shouldUnregisterTauriPwa({
  isTauriShell,
  hasServiceWorker,
}: TauriPwaCleanupSupport): boolean {
  return isTauriShell && hasServiceWorker;
}

export interface PwaUpdateState {
  hasController: boolean;
  workerState: ServiceWorkerState | string | null | undefined;
}

export function isPwaUpdateReady({
  hasController,
  workerState,
}: PwaUpdateState): boolean {
  return hasController && workerState === "installed";
}

export function isPwaSkipWaitingMessage(data: unknown): boolean {
  if (data === PWA_SKIP_WAITING_MESSAGE) return true;
  if (!data || typeof data !== "object") return false;

  return (
    "type" in data &&
    (data as { type?: unknown }).type === PWA_SKIP_WAITING_MESSAGE
  );
}

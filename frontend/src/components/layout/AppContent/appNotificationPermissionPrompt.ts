/**
 * One-time native notification permission prompt.
 *
 * Android 13+ (targetSdk 35) denies POST_NOTIFICATIONS by default and runtime
 * requests only work while the app is foregrounded — requesting lazily at
 * delivery time (exactly when the app may be hidden) fails silently. Prompt
 * once right after the user's first message, when the value of "reply done"
 * notifications is obvious.
 */

import type { AppNotificationRuntime } from "../../../services/notifications/appNotificationService";

export const APP_NOTIFICATION_PERMISSION_PROMPT_STORAGE_KEY =
  "lambchat.app_notification_permission_prompted";

export interface PromptStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export function shouldPromptForAppNotificationPermission({
  appRuntime,
  storage,
}: {
  appRuntime: AppNotificationRuntime;
  storage: PromptStorage;
}): boolean {
  if (appRuntime === "unsupported") return false;
  return (
    storage.getItem(APP_NOTIFICATION_PERMISSION_PROMPT_STORAGE_KEY) !==
    "requested"
  );
}

/**
 * 请求一次原生通知权限（App 客户端）。无论用户授予与否都记录已请求，
 * 避免反复骚扰；被拒后仍可在 设置 → 通知 里重试。
 */
export async function promptAppNotificationPermissionOnce({
  appRuntime,
  storage,
  requestPermission,
}: {
  appRuntime: AppNotificationRuntime;
  storage: PromptStorage | null;
  requestPermission: () => Promise<string>;
}): Promise<boolean> {
  const safeStorage: PromptStorage =
    storage ??
    (typeof localStorage === "undefined"
      ? {
          getItem: () => null,
          setItem: () => {},
        }
      : localStorage);

  if (
    !shouldPromptForAppNotificationPermission({
      appRuntime,
      storage: safeStorage,
    })
  ) {
    return false;
  }

  safeStorage.setItem(
    APP_NOTIFICATION_PERMISSION_PROMPT_STORAGE_KEY,
    "requested",
  );
  try {
    await requestPermission();
  } catch (error) {
    console.warn("[AppNotification] Permission prompt failed:", error);
  }
  return true;
}

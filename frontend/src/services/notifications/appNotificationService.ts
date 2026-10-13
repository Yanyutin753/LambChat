export type AppNotificationRuntime =
  | "tauri"
  | "capacitor-android"
  | "unsupported";

export type AppNotificationType =
  | "task"
  | "announcement"
  | "approval"
  | "message"
  | "auth"
  | "error";

export interface AppNotificationPayload {
  type: AppNotificationType;
  title: string;
  body?: string;
  route?: string;
  ownerUserId?: string;
  dedupeKey?: string;
  importance?: "normal" | "high";
}

export type AppNotificationPermission = "granted" | "denied";

export type AppNotificationResult =
  | "delivered"
  | "deduped"
  | "unsupported"
  | "permission-denied"
  | "failed";

interface BrowserLocationLike {
  protocol?: string;
  hostname?: string;
}

interface CapacitorGlobalLike {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
}

interface AppNotificationGlobalLike {
  Capacitor?: CapacitorGlobalLike;
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
}

export interface DetectAppNotificationRuntimeOptions {
  locationLike?: BrowserLocationLike | null;
  globalLike?: AppNotificationGlobalLike | null;
}

export interface AppNotificationAdapter {
  requestPermission: () => Promise<AppNotificationPermission>;
  notify: (payload: AppNotificationPayload) => Promise<void>;
}

export interface AppNotificationServiceOptions {
  runtime?: AppNotificationRuntime;
  adapters?: {
    tauri?: AppNotificationAdapter;
    capacitorAndroid?: AppNotificationAdapter;
  };
  onNavigate?: (route: string) => void;
  onWarning?: (message: string, error?: unknown) => void;
}

export interface AppNotificationService {
  notify: (payload: AppNotificationPayload) => Promise<AppNotificationResult>;
  requestPermission: () => Promise<AppNotificationPermission | "unsupported">;
  getRuntime: () => AppNotificationRuntime;
  clearDedupe: () => void;
  setActiveUserId: (userId: string | null) => void;
  setNavigator: (navigator: ((route: string) => void) | null) => void;
  initializeNativeClickHandlers: () => void;
}

export function detectAppNotificationRuntime(
  options: DetectAppNotificationRuntimeOptions = {},
): AppNotificationRuntime {
  const globalObject =
    options.globalLike ??
    (typeof globalThis !== "undefined"
      ? (globalThis as AppNotificationGlobalLike)
      : null);

  if (globalObject?.__TAURI__ || globalObject?.__TAURI_INTERNALS__) {
    return "tauri";
  }

  const capacitor = globalObject?.Capacitor;
  if (
    capacitor?.isNativePlatform?.() &&
    capacitor?.getPlatform?.() === "android"
  ) {
    return "capacitor-android";
  }

  const location =
    options.locationLike ??
    (typeof window !== "undefined" ? window.location : null);
  const protocol = location?.protocol?.toLowerCase() || "";
  const hostname = location?.hostname?.toLowerCase() || "";

  if (protocol === "tauri:" || hostname === "tauri.localhost") {
    return "tauri";
  }
  if (protocol === "capacitor:") {
    return "capacitor-android";
  }

  return "unsupported";
}

function resolveAdapter(
  runtime: AppNotificationRuntime,
  adapters: AppNotificationServiceOptions["adapters"],
): AppNotificationAdapter | null {
  if (runtime === "tauri") return adapters?.tauri ?? createTauriAdapter();
  if (runtime === "capacitor-android") {
    return adapters?.capacitorAndroid ?? createCapacitorAndroidAdapter();
  }
  return null;
}

export function createAppNotificationService(
  options: AppNotificationServiceOptions = {},
): AppNotificationService {
  const runtime = options.runtime ?? detectAppNotificationRuntime();
  const deliveredKeys = new Set<string>();
  let navigate = options.onNavigate ?? null;
  let clickHandlersInitialized = false;
  let activeUserId: string | null = null;
  let accountGeneration = 0;
  let selectedAdapter: AppNotificationAdapter | null | undefined;
  const warn =
    options.onWarning ??
    ((message: string, error?: unknown) => {
      console.warn(message, error);
    });

  const getAdapter = () => {
    if (selectedAdapter === undefined) selectedAdapter = resolveAdapter(runtime, options.adapters);
    return selectedAdapter;
  };
  const handleNativeAction = (payload: unknown) => {
    if (!payload || typeof payload !== "object") return;
    const {route, ownerUserId} = payload as {route?:unknown; ownerUserId?:unknown};
    if (!navigate || !activeUserId || ownerUserId !== activeUserId || !isInternalNotificationRoute(route)) return;
    navigate(route);
    if (runtime === "tauri") {
      void import("@tauri-apps/api/core").then(({invoke}) => invoke("desktop_notification_focus"))
        .catch(error => warn("[AppNotification] Native focus failed", error));
    }
  };

  return {
    getRuntime() {
      return runtime;
    },
    clearDedupe() {
      deliveredKeys.clear();
    },
    setActiveUserId(userId) {
      if (activeUserId === userId) return;
      activeUserId = userId;
      accountGeneration += 1;
      deliveredKeys.clear();
    },
    setNavigator(navigator) {
      navigate = navigator;
    },
    initializeNativeClickHandlers() {
      if (clickHandlersInitialized || runtime === "unsupported") return;
      clickHandlersInitialized = true;
      const failed = (error: unknown) => {
        clickHandlersInitialized = false;
        warn("[AppNotification] Native click handler failed", error);
      };
      if (runtime === "tauri") {
        void import("@tauri-apps/api/event")
          .then(({listen}) => listen("desktop-notification-action", event => handleNativeAction(event.payload)))
          .catch(failed);
      } else {
        void import("@capacitor/local-notifications")
          .then(({LocalNotifications}) => LocalNotifications.addListener(
            "localNotificationActionPerformed", payload => handleNativeAction(payload.notification.extra),
          ))
          .catch(failed);
      }
    },
    async requestPermission() {
      const adapter = getAdapter();
      if (!adapter) return "unsupported";
      try {
        return await adapter.requestPermission();
      } catch (error) {
        warn("[AppNotification] Permission request failed", error);
        return "denied";
      }
    },
    async notify(payload) {
      const adapter = getAdapter();
      if (!adapter) return "unsupported";

      const generation = accountGeneration;
      const ownerUserId = payload.ownerUserId ?? activeUserId ?? undefined;
      const isCurrent = () => !ownerUserId || (activeUserId === ownerUserId && accountGeneration === generation);
      if (!isCurrent()) return "failed";
      this.initializeNativeClickHandlers();
      if (payload.dedupeKey && deliveredKeys.has(payload.dedupeKey)) {
        return "deduped";
      }

      const permission = await this.requestPermission();
      if (!isCurrent()) return "failed";
      if (permission !== "granted") return "permission-denied";

      try {
        await adapter.notify(ownerUserId ? {...payload, ownerUserId} : payload);
        if (!isCurrent()) return "failed";
        if (payload.dedupeKey) deliveredKeys.add(payload.dedupeKey);
        return "delivered";
      } catch (error) {
        warn("[AppNotification] Native notification failed", error);
        return "failed";
      }
    },
  };
}

export const appNotificationService = createAppNotificationService();

function isInternalNotificationRoute(route: unknown): route is string {
  if (typeof route !== "string" || route.length > 2048) return false;
  if (route === "/notifications") return true;
  if (!/^\/chat\/[^/?#\\\s]+(?:\?run_id=[^#\\\s]*)?$/.test(route)) return false;
  try {
    const session = decodeURIComponent(route.slice(6).split("?")[0]);
    return session !== "." && session !== ".." && !/[/\\\s]/.test(session);
  } catch { return false; }
}

function createTauriAdapter(): AppNotificationAdapter {
  let platform: Promise<boolean> | undefined;
  const supportsActions = () => platform ??= import("@tauri-apps/api/core")
    .then(({invoke}) => invoke<boolean>("desktop_notification_supports_actions"));
  return {
    async requestPermission() {
      if (await supportsActions()) {
        const {invoke} = await import("@tauri-apps/api/core");
        return await invoke<AppNotificationPermission>("desktop_notification_permission");
      }
      const notification = await import("@tauri-apps/plugin-notification");
      const permission = await notification.requestPermission();
      return permission === "granted" ? "granted" : "denied";
    },
    async notify(payload) {
      if (await supportsActions()) {
        const {invoke} = await import("@tauri-apps/api/core");
        await invoke("desktop_notification_send", {payload:{
          title:payload.title, body:payload.body, route:payload.route, ownerUserId:payload.ownerUserId,
        }});
        return;
      }
      const notification = await import("@tauri-apps/plugin-notification");
      notification.sendNotification({title:payload.title, body:payload.body});
    },
  };
}

function createCapacitorAndroidAdapter(): AppNotificationAdapter {
  return {
    async requestPermission() {
      const { LocalNotifications } = await import(
        "@capacitor/local-notifications"
      );
      const permission = await LocalNotifications.requestPermissions();
      return permission.display === "granted" ? "granted" : "denied";
    },
    async notify(payload) {
      const { LocalNotifications } = await import(
        "@capacitor/local-notifications"
      );
      await LocalNotifications.schedule({
        notifications: [
          {
            id: notificationIdFromPayload(payload),
            title: payload.title,
            body: payload.body || "",
            extra: {
              route: payload.route,
              ownerUserId: payload.ownerUserId,
              type: payload.type,
              dedupeKey: payload.dedupeKey,
            },
          },
        ],
      });
    },
  };
}

function notificationIdFromPayload(payload: AppNotificationPayload): number {
  const source = payload.dedupeKey || `${payload.type}:${payload.title}`;
  let hash = 0;
  for (let i = 0; i < source.length; i += 1) {
    hash = (hash * 31 + source.charCodeAt(i)) | 0;
  }
  return Math.abs(hash) || 1;
}

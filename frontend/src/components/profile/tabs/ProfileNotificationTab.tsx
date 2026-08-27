import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, AlertCircle } from "lucide-react";
import { useBrowserNotification } from "../../../hooks/useBrowserNotification";
import { useWebPush } from "../../../hooks/useWebPush";
import {
  appNotificationService,
  type AppNotificationPermission,
} from "../../../services/notifications/appNotificationService";

export function ProfileNotificationTab() {
  const { t } = useTranslation();
  const {
    requestPermission: requestBrowserPermission,
    isSupported,
    permission: browserPermission,
  } = useBrowserNotification();
  const {
    status: pushStatus,
    subscribe: subscribePush,
    unsubscribe: unsubscribePush,
  } = useWebPush();
  const isPushLoading = pushStatus === "loading";
  const appRuntime = appNotificationService.getRuntime();
  const isAppNotificationRuntime = appRuntime !== "unsupported";
  const [appPermission, setAppPermission] = useState<
    AppNotificationPermission | "default"
  >("default");
  const permission = isAppNotificationRuntime
    ? appPermission
    : browserPermission;
  const requestPermission = async () => {
    if (!isAppNotificationRuntime) {
      await requestBrowserPermission();
      return;
    }
    const result = await appNotificationService.requestPermission();
    setAppPermission(result === "granted" ? "granted" : "denied");
  };
  const handlePushSubscribe = async () => {
    if (isAppNotificationRuntime) {
      // For native apps, browser notification permission might not be needed
      await subscribePush();
      return;
    }
    // For browser/PWA, ensure notification permission is granted first
    if (browserPermission !== "granted") {
      await requestBrowserPermission();
    }
    await subscribePush();
  };

  return (
    <div className="space-y-3">
      {/* Browser Notification Setting */}
      <div className="rounded-xl bg-stone-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="font-medium font-serif text-sm text-stone-900 dark:text-stone-100">
              {t("profile.browserNotification")}
            </h4>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-1 leading-relaxed">
              {t("profile.browserNotificationDesc")}
            </p>
          </div>
          {!isSupported && !isAppNotificationRuntime ? (
            <span className="shrink-0 text-xs text-stone-400 mt-0.5">
              {t("profile.notSupported")}
            </span>
          ) : permission === "granted" ? (
            <span className="shrink-0 text-xs text-green-600 dark:text-green-400 flex items-center gap-1 mt-0.5">
              <Check size={14} />
              {t("profile.enabled")}
            </span>
          ) : (
            <button
              onClick={requestPermission}
              className="shrink-0 px-3 py-1.5 text-xs bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors font-medium"
            >
              {permission === "denied"
                ? t("profile.retry")
                : t("profile.enable")}
            </button>
          )}
        </div>

        {permission === "denied" && (
          <p className="text-xs text-red-500 mt-2.5 flex items-start gap-1.5">
            <AlertCircle size={12} className="shrink-0 mt-0.5" />
            {t("profile.notificationDeniedHint")}
          </p>
        )}
      </div>

      {/* WebSocket Connection Status */}
      <div className="rounded-xl bg-stone-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="font-medium font-serif text-sm text-stone-900 dark:text-stone-100">
              {t("profile.realtimeNotification")}
            </h4>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-1 leading-relaxed">
              {t("profile.realtimeNotificationDesc")}
            </p>
          </div>
        </div>
      </div>

      {/* Web Push Notification */}
      <div className="rounded-xl bg-stone-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="font-medium font-serif text-sm text-stone-900 dark:text-stone-100">
              {t("profile.pushNotification")}
            </h4>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-1 leading-relaxed">
              {t("profile.pushNotificationDesc")}
            </p>
          </div>
          {pushStatus === "subscribed" ? (
            <button
              onClick={unsubscribePush}
              disabled={isPushLoading}
              className="shrink-0 px-3 py-1.5 text-xs bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors font-medium disabled:opacity-50"
            >
              {t("profile.pushDisabled")}
            </button>
          ) : pushStatus === "unavailable" || pushStatus === "loading" ? (
            <span className="shrink-0 text-xs text-stone-400 mt-0.5">
              {pushStatus === "loading"
                ? t("profile.loading") || "..."
                : t("profile.notSupported")}
            </span>
          ) : (
            <button
              onClick={handlePushSubscribe}
              disabled={isPushLoading}
              className="shrink-0 px-3 py-1.5 text-xs bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors font-medium disabled:opacity-50"
            >
              {t("profile.pushEnabled")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

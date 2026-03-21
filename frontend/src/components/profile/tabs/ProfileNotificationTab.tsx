import { useTranslation } from "react-i18next";
import { Check, AlertCircle } from "lucide-react";
import { useBrowserNotification } from "../../../hooks/useBrowserNotification";

export function ProfileNotificationTab() {
  const { t } = useTranslation();
  const {
    requestPermission,
    isSupported,
    permission,
    isMobile,
    isMobileNotificationSupported,
  } = useBrowserNotification();

  return (
    <div className="space-y-3">
      {/* Browser Notification Setting */}
      <div className="rounded-xl bg-gray-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="font-medium text-sm text-gray-900 dark:text-stone-100">
              {t("profile.browserNotification")}
            </h4>
            <p className="text-xs text-gray-500 dark:text-stone-400 mt-1 leading-relaxed">
              {t("profile.browserNotificationDesc")}
            </p>
          </div>
          {!isSupported ? (
            <span className="shrink-0 text-xs text-gray-400 mt-0.5">
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

      {/* Mobile Notification Status */}
      {isMobile && (
        <div className="rounded-xl bg-gray-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h4 className="font-medium text-sm text-gray-900 dark:text-stone-100">
                {t("profile.mobileNotification")}
              </h4>
              <p className="text-xs text-gray-500 dark:text-stone-400 mt-1 leading-relaxed">
                {t("profile.mobileNotificationDesc")}
              </p>
            </div>
            <span
              className={`shrink-0 text-xs flex items-center gap-1 mt-0.5 ${
                isMobileNotificationSupported()
                  ? "text-green-600 dark:text-green-400"
                  : "text-amber-600 dark:text-amber-400"
              }`}
            >
              {isMobileNotificationSupported() ? (
                <>
                  <Check size={14} />
                  {t("profile.supported")}
                </>
              ) : (
                t("profile.limitedSupport")
              )}
            </span>
          </div>
        </div>
      )}

      {/* WebSocket Connection Status */}
      <div className="rounded-xl bg-gray-50 dark:bg-stone-700/50 p-3.5 sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="font-medium text-sm text-gray-900 dark:text-stone-100">
              {t("profile.realtimeNotification")}
            </h4>
            <p className="text-xs text-gray-500 dark:text-stone-400 mt-1 leading-relaxed">
              {t("profile.realtimeNotificationDesc")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

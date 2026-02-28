import { X, RefreshCw, ExternalLink, ArrowDownCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useVersion } from "../../hooks/useVersion";

interface AboutDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AboutDialog({ isOpen, onClose }: AboutDialogProps) {
  const { t } = useTranslation();
  const { versionInfo, isLoading, error, checkForUpdates } = useVersion();

  if (!isOpen) return null;

  const handleCheckUpdates = async () => {
    await checkForUpdates();
  };

  const handleGoToRelease = () => {
    if (versionInfo?.release_url) {
      window.open(versionInfo.release_url, "_blank");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-stone-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-stone-100">
              {t("about.title", "LambChat")}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-stone-700 dark:hover:text-stone-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="space-y-3">
          {isLoading ? (
            <div className="py-8 text-center text-gray-500 dark:text-stone-400">
              {t("common.loading", "Loading...")}
            </div>
          ) : error ? (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
              {error}
            </div>
          ) : versionInfo ? (
            <>
              {/* App Version */}
              <div className="flex items-center justify-between rounded-lg bg-gray-50 p-4 dark:bg-stone-700/50">
                <div>
                  <div className="text-xs text-gray-500 dark:text-stone-400">
                    {t("about.currentVersion", "Current Version")}
                  </div>
                  <div className="font-mono text-2xl font-bold text-gray-900 dark:text-stone-100">
                    {versionInfo.app_version}
                  </div>
                </div>
                <button
                  onClick={handleCheckUpdates}
                  disabled={isLoading}
                  className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  <RefreshCw
                    className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
                  />
                  {t("about.checkUpdate", "Check Update")}
                </button>
              </div>

              {/* Latest Version */}
              {versionInfo.latest_version && (
                <div className="rounded-lg bg-gray-50 p-4 dark:bg-stone-700/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ArrowDownCircle className="h-5 w-5 text-gray-400 dark:text-stone-500" />
                      <span className="text-sm text-gray-500 dark:text-stone-400">
                        {t("about.latestVersion", "Latest Version")}
                      </span>
                    </div>
                    <span className="font-mono text-lg font-bold text-gray-900 dark:text-stone-100">
                      {versionInfo.latest_version}
                    </span>
                  </div>
                </div>
              )}

              {/* Update Available Banner */}
              {versionInfo.has_update && (
                <div className="flex items-center justify-between rounded-lg bg-green-50 p-4 dark:bg-green-900/30">
                  <div className="flex items-center gap-2">
                    <ArrowDownCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                    <div>
                      <div className="text-sm font-medium text-green-800 dark:text-green-200">
                        {t("about.updateAvailable", "New version available!")}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleGoToRelease}
                    className="flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                  >
                    <ExternalLink className="h-4 w-4" />
                    {t("about.viewUpdate", "Update")}
                  </button>
                </div>
              )}

              {/* No Update Message */}
              {versionInfo.latest_version && !versionInfo.has_update && (
                <div className="rounded-lg bg-green-50 p-3 text-center text-sm text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  {t("about.upToDate", "You're up to date!")}
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
          >
            {t("common.close", "Close")}
          </button>
        </div>
      </div>
    </div>
  );
}

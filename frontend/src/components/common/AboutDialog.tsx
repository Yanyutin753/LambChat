import {
  X,
  RefreshCw,
  ExternalLink,
  ArrowDownCircle,
  Github,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useVersion } from "../../hooks/useVersion";
import { APP_NAME } from "../../constants";
import { SkeletonBlock, SkeletonLine } from "../skeletons";

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

  const handleGoToGitHub = () => {
    if (versionInfo?.github_url) {
      window.open(versionInfo.github_url, "_blank");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-stone-800">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-stone-900 dark:text-stone-100 font-serif">
              {t("about.title", APP_NAME)}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-700 dark:hover:text-stone-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="space-y-3">
          {isLoading ? (
            <div className="space-y-3 py-2">
              <div className="flex items-center justify-between rounded-lg bg-stone-50 p-4 dark:bg-stone-700/50">
                <div className="space-y-2">
                  <SkeletonLine width="w-24" className="!h-2" />
                  <SkeletonBlock width="w-20" height="h-7" />
                </div>
                <SkeletonBlock
                  width="w-24"
                  height="h-9"
                  className="!rounded-lg"
                />
              </div>
              <div className="rounded-lg bg-stone-50 p-4 dark:bg-stone-700/50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <SkeletonBlock
                      width="w-5"
                      height="h-5"
                      className="!rounded-full"
                    />
                    <SkeletonLine width="w-24" className="!h-2" />
                  </div>
                  <SkeletonBlock width="w-16" height="h-5" />
                </div>
              </div>
              <SkeletonBlock
                width="w-full"
                height="h-11"
                className="!rounded-lg"
              />
            </div>
          ) : error ? (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
              {error}
            </div>
          ) : versionInfo ? (
            <>
              {/* App Version */}
              <div className="flex items-center justify-between rounded-lg bg-stone-50 p-4 dark:bg-stone-700/50">
                <div>
                  <div className="text-xs text-stone-500 dark:text-stone-400">
                    {t("about.currentVersion", "Current Version")}
                  </div>
                  <div className="font-mono text-2xl font-bold text-stone-900 dark:text-stone-100">
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
                <div className="rounded-lg bg-stone-50 p-4 dark:bg-stone-700/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ArrowDownCircle className="h-5 w-5 text-stone-400 dark:text-stone-500" />
                      <span className="text-sm text-stone-500 dark:text-stone-400">
                        {t("about.latestVersion", "Latest Version")}
                      </span>
                    </div>
                    <span className="font-mono text-lg font-bold text-stone-900 dark:text-stone-100">
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

              {/* GitHub Link */}
              {versionInfo.github_url && (
                <button
                  onClick={handleGoToGitHub}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-stone-200 p-3 text-sm font-medium text-stone-600 hover:bg-stone-50 dark:border-stone-600 dark:text-stone-400 dark:hover:bg-stone-700"
                >
                  <Github className="h-4 w-4" />
                  {t("about.viewOnGitHub", "View on GitHub")}
                </button>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-stone-100 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-200 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
          >
            {t("common.close", "Close")}
          </button>
        </div>
      </div>
    </div>
  );
}

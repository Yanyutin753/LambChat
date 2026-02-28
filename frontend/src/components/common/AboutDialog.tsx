import {
  X,
  Tag,
  GitCommit,
  Info,
  Clock,
  RefreshCw,
  ExternalLink,
  ArrowDownCircle,
} from "lucide-react";
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

  const formatBuildTime = (buildTime?: string) => {
    if (!buildTime) return "-";
    try {
      return new Date(buildTime).toLocaleString();
    } catch {
      return buildTime;
    }
  };

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
            <Info className="h-5 w-5 text-blue-600 dark:text-amber-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-stone-100">
              {t("about.title", "About Lamb Agent")}
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
              <div className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-stone-700/50">
                <Info className="h-4 w-4 text-gray-400 dark:text-stone-500" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500 dark:text-stone-400">
                    {t("about.appVersion", "Version")}
                  </div>
                  <div className="font-mono text-sm font-medium text-gray-900 dark:text-stone-100">
                    {versionInfo.app_version}
                  </div>
                </div>
              </div>

              {/* Git Tag */}
              <div className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-stone-700/50">
                <Tag className="h-4 w-4 text-gray-400 dark:text-stone-500" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500 dark:text-stone-400">
                    {t("about.gitTag", "Git Tag")}
                  </div>
                  <div className="font-mono text-sm font-medium text-gray-900 dark:text-stone-100">
                    {versionInfo.git_tag || "-"}
                  </div>
                </div>
              </div>

              {/* Commit Hash */}
              <div className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-stone-700/50">
                <GitCommit className="h-4 w-4 text-gray-400 dark:text-stone-500" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500 dark:text-stone-400">
                    {t("about.commitHash", "Commit")}
                  </div>
                  <div className="font-mono text-sm font-medium text-gray-900 dark:text-stone-100">
                    {versionInfo.commit_hash || "-"}
                  </div>
                </div>
              </div>

              {/* Build Time */}
              <div className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-stone-700/50">
                <Clock className="h-4 w-4 text-gray-400 dark:text-stone-500" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500 dark:text-stone-400">
                    {t("about.buildTime", "Build Time")}
                  </div>
                  <div className="font-mono text-sm font-medium text-gray-900 dark:text-stone-100">
                    {formatBuildTime(versionInfo.build_time)}
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="my-4 border-t border-gray-200 dark:border-stone-600" />

              {/* GitHub Latest Info */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-600 dark:text-stone-400">
                    {t("about.latestFromGitHub", "Latest from GitHub")}
                  </span>
                  <button
                    onClick={handleCheckUpdates}
                    disabled={isLoading}
                    className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-50 dark:text-blue-400 dark:hover:bg-blue-900/30"
                  >
                    <RefreshCw
                      className={`h-3 w-3 ${isLoading ? "animate-spin" : ""}`}
                    />
                    {t("about.checkUpdate", "Check Update")}
                  </button>
                </div>

                {/* Latest Version */}
                <div className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-stone-700/50">
                  <ArrowDownCircle className="h-4 w-4 text-gray-400 dark:text-stone-500" />
                  <div className="flex-1">
                    <div className="text-xs text-gray-500 dark:text-stone-400">
                      {t("about.latestVersion", "Latest Version")}
                    </div>
                    <div className="font-mono text-sm font-medium text-gray-900 dark:text-stone-100">
                      {versionInfo.latest_version || "-"}
                    </div>
                  </div>
                </div>

                {/* Published At */}
                {versionInfo.published_at && (
                  <div className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-stone-700/50">
                    <Clock className="h-4 w-4 text-gray-400 dark:text-stone-500" />
                    <div className="flex-1">
                      <div className="text-xs text-gray-500 dark:text-stone-400">
                        {t("about.publishedAt", "Published")}
                      </div>
                      <div className="font-mono text-sm font-medium text-gray-900 dark:text-stone-100">
                        {formatBuildTime(versionInfo.published_at)}
                      </div>
                    </div>
                  </div>
                )}

                {/* Update Available Banner */}
                {versionInfo.has_update && (
                  <div className="flex items-center justify-between rounded-lg bg-green-50 p-3 dark:bg-green-900/30">
                    <div className="flex items-center gap-2">
                      <ArrowDownCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                      <div>
                        <div className="text-sm font-medium text-green-800 dark:text-green-200">
                          {t("about.updateAvailable", "New version available!")}
                        </div>
                        <div className="text-xs text-green-600 dark:text-green-400">
                          {versionInfo.latest_version}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={handleGoToRelease}
                      className="flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                    >
                      <ExternalLink className="h-4 w-4" />
                      {t("about.viewUpdate", "View")}
                    </button>
                  </div>
                )}

                {/* No Update Message */}
                {versionInfo.latest_version && !versionInfo.has_update && (
                  <div className="rounded-lg bg-gray-50 p-3 text-center text-sm text-gray-500 dark:bg-stone-700/50 dark:text-stone-400">
                    {t("about.upToDate", "You're up to date!")}
                  </div>
                )}
              </div>
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

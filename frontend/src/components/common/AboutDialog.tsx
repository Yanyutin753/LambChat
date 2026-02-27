import { X, Tag, GitCommit, Clock, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useVersion } from "../../hooks/useVersion";

interface AboutDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AboutDialog({ isOpen, onClose }: AboutDialogProps) {
  const { t } = useTranslation();
  const { versionInfo, isLoading, error } = useVersion();

  if (!isOpen) return null;

  const formatBuildTime = (buildTime?: string) => {
    if (!buildTime) return "-";
    try {
      return new Date(buildTime).toLocaleString();
    } catch {
      return buildTime;
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

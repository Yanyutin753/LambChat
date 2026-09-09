import { ArrowRight, Download, ExternalLink, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../common/Dialog";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ReleaseNotesMarkdown } from "./ReleaseNotesMarkdown";
import { UpdateProgressBar } from "./UpdateProgressBar";
import { APP_VERSION } from "../../utils/appVersion";
import type { UpdateState } from "../../types";

interface UpdateDialogProps {
  state: UpdateState;
  isOpen: boolean;
  onUpgrade: () => void;
  onSkip: () => void;
  onDismiss: () => void;
  /** 跳过此版本：该版本不再自动提醒（手动检查仍会显示） */
  onSkipVersion: () => void;
  platform: "tauri" | "android" | "ios";
}

const ghostButtonClass =
  "px-4 py-2 text-14 font-medium text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors";

export function UpdateDialog({
  state,
  isOpen,
  onUpgrade,
  onSkip,
  onDismiss,
  onSkipVersion,
  platform,
}: UpdateDialogProps) {
  const { t } = useTranslation();

  // Linux 安装来源分流文案：deb/rpm=下载并安装（pkexec），unknown=前往下载
  // （无法判定安装方式不盲装），appimage/非 Linux 保持 updater 语义
  const source = state.linuxInstallSource;
  const isLinuxPackage =
    platform === "tauri" && (source === "deb" || source === "rpm");
  const isUnknownSource = platform === "tauri" && source === "unknown";
  const isGoToDownload = platform === "ios" || isUnknownSource;

  const footer = (
    <>
      {!state.downloading && (
        <button onClick={onSkipVersion} className={ghostButtonClass}>
          {t("update.skipVersion", "跳过此版本")}
        </button>
      )}
      {!state.downloading && (
        <button onClick={onSkip} className={ghostButtonClass}>
          {t("updateSkip", "以后再说")}
        </button>
      )}
      <button
        onClick={onUpgrade}
        disabled={state.downloading}
        className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--theme-primary)] px-4 py-2 text-14 font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {state.downloading ? (
          <span className="inline-flex h-4 w-4 items-center justify-center">
            <LoadingSpinner size="sm" color="text-current" />
          </span>
        ) : isGoToDownload ? (
          <ExternalLink size={16} />
        ) : isLinuxPackage ? (
          <Download size={16} />
        ) : (
          <RefreshCw size={16} />
        )}
        {state.downloading
          ? t("updateDownloading", "正在下载...")
          : isGoToDownload
            ? t("updateGoToDownload", "前往下载")
            : isLinuxPackage
              ? t("updateDownloadAndInstall", "下载并安装")
              : state.readyToInstall
                ? t("updateRelaunchInstall", "重启并安装")
                : t("updateDownload", "立即升级")}
      </button>
    </>
  );

  return (
    <Dialog
      open={isOpen}
      onClose={onDismiss}
      dismissible={!state.downloading}
      size="md"
      title={t("update.availableTitle", "发现新版本")}
      icon={<Download size={18} className="shrink-0 text-[var(--theme-primary)]" />}
      footer={footer}
    >
      <div className="space-y-3">
        {/* 版本迁移行：当前 → 新版本 */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="inline-flex items-center gap-1.5 font-mono text-14 text-stone-500 dark:text-stone-400">
            v{APP_VERSION}
            <ArrowRight size={14} className="opacity-60" aria-hidden="true" />
            <span className="font-semibold text-stone-900 dark:text-stone-100">
              v{state.version ?? ""}
            </span>
          </span>
          {state.publishedAt && (
            <span className="text-12 text-stone-400 dark:text-stone-500">
              {t("updatePublishedAt", {
                date: new Date(state.publishedAt).toLocaleDateString(),
              })}
            </span>
          )}
        </div>

        {state.releaseNotes && (
          <div className="space-y-1">
            <p className="text-12 font-medium text-stone-600 dark:text-stone-300">
              {t("updateReleaseNotes", "更新日志")}
            </p>
            <div className="max-h-56 overflow-y-auto rounded-lg bg-stone-50 p-3 dark:bg-stone-900/50">
              <ReleaseNotesMarkdown content={state.releaseNotes} />
            </div>
          </div>
        )}

        {state.releaseUrl && !state.downloading && (
          <a
            href={state.releaseUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-12 text-blue-600 hover:underline dark:text-blue-400"
          >
            <ExternalLink size={12} />
            {t("update.viewFullNotes", "查看完整更新日志")}
          </a>
        )}

        {state.downloading && (
          <UpdateProgressBar
            progress={state.progress}
            downloaded={state.downloaded}
            contentLength={state.contentLength}
          />
        )}

        {state.error && (
          <div className="flex items-center justify-between gap-2 rounded-lg bg-red-50 p-3 text-14 text-red-600 dark:bg-red-900/20 dark:text-red-400">
            <span className="break-words">{state.error}</span>
            {!state.downloading && (
              <button
                onClick={onUpgrade}
                className="shrink-0 font-medium underline underline-offset-2 hover:opacity-80"
              >
                {t("updateRetry", "重试")}
              </button>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}

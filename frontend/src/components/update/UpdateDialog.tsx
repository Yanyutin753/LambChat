import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Download, ExternalLink, RefreshCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { UpdateProgressBar } from "./UpdateProgressBar";
import type { UpdateState } from "../../types";

interface UpdateDialogProps {
  state: UpdateState;
  isOpen: boolean;
  onUpgrade: () => void;
  onSkip: () => void;
  onDismiss: () => void;
  platform: "tauri" | "android" | "ios";
}

export function UpdateDialog({
  state,
  isOpen,
  onUpgrade,
  onSkip,
  onDismiss,
  platform,
}: UpdateDialogProps) {
  const { t } = useTranslation();
  useBodyScrollLock(isOpen);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape" && !state.downloading) {
        onDismiss();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onDismiss, state.downloading]);

  if (!isOpen) return null;

  return createPortal(
    <div className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={state.downloading ? undefined : onDismiss}
      />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-md mx-4 bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <div className="flex items-center gap-2">
            <Download size={20} className="text-[var(--theme-primary)]" />
            <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">
              {t("updateNewVersion", {
                version: state.version ?? "",
              })}
            </h3>
          </div>
          {!state.downloading && (
            <button
              onClick={onDismiss}
              className="inline-flex size-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
              aria-label={t("common.dismiss", "关闭")}
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-5 pb-4 space-y-3">
          {state.publishedAt && (
            <p className="text-xs text-stone-500 dark:text-stone-400">
              {t("updatePublishedAt", {
                date: new Date(state.publishedAt).toLocaleDateString(),
              })}
            </p>
          )}

          {state.releaseNotes && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-stone-600 dark:text-stone-300">
                {t("updateReleaseNotes", "更新内容")}
              </p>
              <div className="max-h-40 overflow-y-auto rounded-lg bg-stone-50 dark:bg-stone-900/50 p-3 text-sm text-stone-600 dark:text-stone-400 leading-relaxed prose prose-sm prose-stone dark:prose-invert max-w-none">
                {state.releaseNotes}
              </div>
            </div>
          )}

          {state.downloading && (
            <UpdateProgressBar
              progress={state.progress}
              downloaded={state.downloaded}
              contentLength={state.contentLength}
            />
          )}

          {state.error && (
            <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-600 dark:text-red-400">
              {state.error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 bg-stone-50 dark:bg-stone-900/50 border-t border-stone-100 dark:border-stone-700">
          {!state.downloading && (
            <button
              onClick={onSkip}
              className="px-4 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors"
            >
              {t("updateSkip", "稍后提醒")}
            </button>
          )}

          {platform === "ios" ? (
            <button
              onClick={onUpgrade}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--theme-primary)] rounded-lg hover:opacity-90 transition-opacity inline-flex items-center gap-2"
            >
              <ExternalLink size={16} />
              {t("updateGoToDownload", "前往下载")}
            </button>
          ) : (
            <button
              onClick={onUpgrade}
              disabled={state.downloading}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--theme-primary)] rounded-lg hover:opacity-90 transition-opacity inline-flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {state.downloading ? (
                <span className="inline-flex h-4 w-4 items-center justify-center">
                  <LoadingSpinner size="sm" color="text-current" />
                </span>
              ) : (
                <RefreshCw size={16} />
              )}
              {state.downloading
                ? t("updateDownloading", "正在下载...")
                : state.readyToInstall
                  ? t("updateRelaunchInstall", "重启并安装")
                  : t("updateDownload", "立即升级")}
            </button>
          )}

          {state.error && !state.downloading && (
            <button
              onClick={onUpgrade}
              className="px-4 py-2 text-sm font-medium text-stone-600 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 transition-colors"
            >
              {t("updateRetry", "重试")}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

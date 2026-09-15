import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowDownCircle,
  ArrowRight,
  ArrowUpCircle,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { ReleaseNotesMarkdown } from "../../update/ReleaseNotesMarkdown";
import { UpdateProgressBar } from "../../update/UpdateProgressBar";
import { useStickyDropdownPosition } from "../../../hooks/useStickyDropdownPosition";
import { APP_VERSION } from "../../../utils/appVersion";
import type { UpdateState } from "../../../types";
import { updateIndicatorPhase } from "./updateIndicatorPhase";

/**
 * 标题栏更新指示器：桌面端更新流程的唯一常驻入口。
 * 发现新版本即点亮；点击展开轻量 popover（非模态、不阻塞），
 * 后台下载进度与「重启并安装」都在这里完成。
 */

interface UpdateTitlebarIndicatorProps {
  state: UpdateState;
  onInstall: () => void;
  onSkipVersion: () => void;
}

function ProgressRing({ progress }: { progress: number }) {
  // 静态进度环（不旋转动画）：下载进度本身就是动态反馈
  const r = 5.5;
  const c = 2 * Math.PI * r;
  const clamped = Math.min(Math.max(progress, 0), 100);
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <circle
        cx="8"
        cy="8"
        r={r}
        fill="none"
        strokeWidth="2"
        className="stroke-[var(--color-border)]"
      />
      <circle
        cx="8"
        cy="8"
        r={r}
        fill="none"
        strokeWidth="2"
        strokeLinecap="round"
        stroke="var(--theme-primary)"
        strokeDasharray={c}
        strokeDashoffset={c - (clamped / 100) * c}
        transform="rotate(-90 8 8)"
      />
    </svg>
  );
}

export function UpdateTitlebarIndicator({
  state,
  onInstall,
  onSkipVersion,
}: UpdateTitlebarIndicatorProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const phase = updateIndicatorPhase(state);

  const menuPosition = useStickyDropdownPosition(
    buttonRef,
    open,
    (rect) => ({
      top: rect.bottom + 6,
      right: window.innerWidth - rect.right,
    }),
    phase,
  );

  // 外点关闭 + Escape 关闭
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        panelRef.current?.contains(target) ||
        buttonRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", onPointerDown);
    }, 0);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!state.available) return null;

  const iconByPhase = {
    downloading: <ProgressRing progress={state.progress} />,
    ready: <ArrowUpCircle size={16} className="text-[var(--theme-primary)]" />,
    error: <AlertCircle size={16} className="text-red-500" />,
    available: <ArrowDownCircle size={16} className="opacity-70" />,
  }[phase];

  const label =
    phase === "downloading"
      ? t("updateDownloading", "正在下载...")
      : phase === "error"
        ? t("updateError", "更新失败")
        : t("update.availableTitle", "发现新版本");

  // 主按钮文案与 UpdateDialog 的分流保持一致（deb/rpm / unknown / updater）
  const isLinuxPackage =
    state.linuxInstallSource === "deb" || state.linuxInstallSource === "rpm";
  const isGoToDownload = state.linuxInstallSource === "unknown";
  const primaryLabel = state.downloading
    ? t("updateDownloading", "正在下载...")
    : isGoToDownload
      ? t("updateGoToDownload", "前往下载")
      : isLinuxPackage
        ? t("updateDownloadAndInstall", "下载并安装")
        : state.readyToInstall
          ? t("update.updateRelaunchInstall", "重启并安装")
          : t("updateDownload", "立即升级");

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        title={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)]"
      >
        {iconByPhase}
      </button>

      {open &&
        createPortal(
          <div
            ref={panelRef}
            role="dialog"
            aria-label={t("update.availableTitle", "发现新版本")}
            className="fixed z-[302] w-80 rounded-xl border shadow-xl animate-scale-in"
            style={{
              ...menuPosition,
              backgroundColor: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
            }}
          >
            <div className="space-y-3 p-3.5">
              <div className="flex items-center gap-1.5 font-mono text-13 text-[var(--color-text-secondary)]">
                v{APP_VERSION}
                <ArrowRight size={13} className="opacity-60" aria-hidden="true" />
                <span className="font-semibold text-[var(--color-text-primary)]">
                  v{state.version ?? ""}
                </span>
                {state.publishedAt && (
                  <span className="font-sans text-11 opacity-70">
                    {t("updatePublishedAt", {
                      date: new Date(state.publishedAt).toLocaleDateString(),
                    })}
                  </span>
                )}
              </div>

              {state.releaseNotes && (
                <div className="max-h-52 overflow-y-auto rounded-lg bg-[var(--theme-bg-subtle)] p-2.5">
                  <ReleaseNotesMarkdown content={state.releaseNotes} />
                </div>
              )}

              {state.releaseUrl && (
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
                <div className="flex items-center justify-between gap-2 rounded-lg bg-red-50 p-2.5 text-13 text-red-600 dark:bg-red-900/20 dark:text-red-400">
                  <span className="break-words">{state.error}</span>
                  {!state.downloading && (
                    <button
                      type="button"
                      onClick={onInstall}
                      className="shrink-0 font-medium underline underline-offset-2 hover:opacity-80"
                    >
                      {t("updateRetry", "重试")}
                    </button>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between gap-2">
                {!state.downloading ? (
                  <button
                    type="button"
                    onClick={onSkipVersion}
                    className="rounded-md px-2.5 py-1.5 text-12 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--theme-bg-subtle)] hover:text-[var(--color-text-secondary)]"
                  >
                    {t("update.skipVersion", "跳过此版本")}
                  </button>
                ) : (
                  <span />
                )}
                <button
                  type="button"
                  onClick={onInstall}
                  disabled={state.downloading}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-[var(--theme-primary)] px-3.5 py-1.5 text-13 font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {primaryLabel}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { topmostVisibleDialog } from "../../../utils/modalDialog";
import {
  ArrowDownCircle,
  ArrowRight,
  ArrowUpCircle,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { ReleaseNotesMarkdown } from "../../update/ReleaseNotesMarkdown";
import { Button } from "../../common/ui/Button";
import { ConfigPanelErrorCallout } from "../../panels/ConfigPanelErrorCallout";
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

  useEffect(() => {
    if (!state.available) setOpen(false);
  }, [state.available]);

  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

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
      if (
        e.key === "Escape" &&
        !e.defaultPrevented &&
        !e.isComposing &&
        topmostVisibleDialog() === panelRef.current
      ) {
        e.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onFocus = (e: FocusEvent) => {
      if (
        !panelRef.current?.contains(e.target as Node) &&
        !buttonRef.current?.contains(e.target as Node)
      )
        setOpen(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", onPointerDown);
    }, 0);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocus);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocus);
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

  // 主按钮文案与 UpdateDialog 的分流保持一致（deb/rpm 已缓存待装 /
  // appimage+unknown 前往下载 / updater 重启安装）
  const source = state.linuxInstallSource;
  const isLinuxPackage = source === "deb" || source === "rpm";
  const isGoToDownload = source === "unknown" || source === "appimage";
  const primaryLabel = state.downloading
    ? t("updateDownloading", "正在下载...")
    : state.error
      ? t("updateRetry", "重试")
      : isGoToDownload
        ? t("updateGoToDownload", "前往下载")
        : state.readyToInstall
          ? t("update.updateRelaunchInstall", "重启并安装")
          : isLinuxPackage
            ? t("updateDownloadAndInstall", "下载并安装")
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
            tabIndex={-1}
            aria-label={t("update.availableTitle", "发现新版本")}
            className="fixed z-[302] w-96 max-w-[calc(100vw-1rem)] max-h-[calc(100dvh-var(--titlebar-inset,40px)-1rem)] overflow-y-auto rounded-xl border shadow-xl animate-scale-in motion-reduce:animate-none outline-none"
            style={{
              ...menuPosition,
              backgroundColor: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
            }}
          >
            <div className="space-y-4 p-4">
              <div className="space-y-1">
                <h2 className="font-serif text-16 font-semibold text-theme-text">
                  {phase === "ready"
                    ? t("update.readyTitle", "更新已下载")
                    : label}
                </h2>
                {phase === "ready" && (
                  <p className="text-12 leading-relaxed text-theme-text-secondary">
                    {t("update.readyHint", "重启后即可使用新版本。")}
                  </p>
                )}
              </div>
              <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 font-mono text-13 text-[var(--color-text-secondary)]">
                v{APP_VERSION}
                <ArrowRight
                  size={13}
                  className="opacity-60"
                  aria-hidden="true"
                />
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

              <div className="space-y-2">
                <p className="text-12 font-medium text-theme-text-secondary">
                  {t("updateReleaseNotes", "更新日志")}
                </p>
                <div className="max-h-64 overflow-y-auto overscroll-contain pr-1">
                  <ReleaseNotesMarkdown content={state.releaseNotes ?? ""} />
                </div>
              </div>

              {state.releaseUrl && (
                <a
                  href={state.releaseUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-9 [@media(pointer:coarse)]:min-h-11 items-center gap-1 text-12 text-theme-text-secondary hover:text-theme-text hover:underline"
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

              {state.error && <ConfigPanelErrorCallout message={state.error} />}

              <div className="flex items-center justify-between gap-2 border-t border-theme-border pt-3">
                {!state.downloading ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onSkipVersion}
                    className="[@media(pointer:coarse)]:!min-h-11"
                  >
                    {t("update.skipVersion", "跳过此版本")}
                  </Button>
                ) : (
                  <span />
                )}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={onInstall}
                  disabled={state.downloading}
                  className="[@media(pointer:coarse)]:!min-h-11"
                >
                  {primaryLabel}
                </Button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

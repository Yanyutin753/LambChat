import {
  ArrowDownCircle,
  BadgeCheck,
  Calendar,
  CheckCircle2,
  Download,
  ExternalLink,
  PackageCheck,
  RefreshCw,
  ScrollText,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../common/Dialog";
import { Button } from "../common/ui/Button";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
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

const actionClass =
  "!min-h-11 sm:!min-h-9 [@media(pointer:coarse)]:!min-h-11 [&>span]:!whitespace-normal min-w-0 flex-1 self-stretch sm:flex-none";

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
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isOpen || !state.error) return;
    const content = contentRef.current;
    const surface = content?.closest("[data-modal-surface]");
    if (surface?.contains(document.activeElement)) {
      content?.querySelector<HTMLElement>('[role="alert"]')?.focus();
    }
  }, [isOpen, state.error]);

  // Linux 安装来源分流文案：deb/rpm=下载并安装（pkcon/pkexec），appimage/
  // unknown=前往下载（AppImage 已停发，引导换装 deb），其余保持 updater 语义
  const source = state.linuxInstallSource;
  const isLinuxPackage =
    platform === "tauri" && (source === "deb" || source === "rpm");
  const isGoToDownload =
    platform === "ios" ||
    (platform === "tauri" && (source === "unknown" || source === "appimage"));

  const footer = (
    <>
      {state.downloading && (
        <div className="w-full min-w-0">
          <UpdateProgressBar
            progress={state.progress}
            downloaded={state.downloaded}
            contentLength={state.contentLength}
          />
        </div>
      )}
      {!state.downloading && (
        <Button onClick={onSkipVersion} variant="ghost" className={actionClass}>
          {t("update.skipVersion", "跳过此版本")}
        </Button>
      )}
      {!state.downloading && (
        <Button onClick={onSkip} className={actionClass}>
          {t("updateSkip", "以后再说")}
        </Button>
      )}
      <Button
        onClick={(event) => {
          event.currentTarget
            .closest<HTMLElement>("[data-modal-surface]")
            ?.focus();
          onUpgrade();
        }}
        loading={state.downloading}
        variant="primary"
        className={`${actionClass} basis-full sm:basis-auto`}
        leftIcon={
          isGoToDownload ? (
            <ExternalLink size={16} />
          ) : isLinuxPackage ? (
            <Download size={16} />
          ) : state.readyToInstall ? (
            platform === "android" ? (
              <PackageCheck size={16} />
            ) : (
              <RefreshCw size={16} />
            )
          ) : (
            <Download size={16} />
          )
        }
      >
        {state.downloading
          ? t("updateDownloading", "正在下载...")
          : state.error
            ? t("updateRetry", "重试")
            : isGoToDownload
              ? t("updateGoToDownload", "前往下载")
              : state.readyToInstall
                ? // 移动端已下载完整 APK：直接安装不重下；桌面语义是重启替换
                  platform === "android"
                  ? t("update.installNow", "安装")
                  : t("update.updateRelaunchInstall", "重启并安装")
                : isLinuxPackage
                  ? t("updateDownloadAndInstall", "下载并安装")
                  : t("updateDownload", "立即升级")}
      </Button>
    </>
  );

  return (
    <Dialog
      open={isOpen}
      onClose={onDismiss}
      dismissible={!state.downloading}
      size="md"
      title={t("update.availableTitle", "发现新版本")}
      icon={
        state.downloading ? (
          <ArrowDownCircle
            size={18}
            className="shrink-0 text-[var(--theme-primary)]"
          />
        ) : state.readyToInstall ? (
          <BadgeCheck
            size={18}
            className="shrink-0 text-[var(--theme-primary)]"
          />
        ) : (
          <Download size={18} className="shrink-0 text-[var(--theme-primary)]" />
        )
      }
      footer={footer}
    >
      <div ref={contentRef} className="space-y-3">
        {state.error && (
          <ConfigPanelErrorCallout message={state.error} tabIndex={-1} />
        )}
        {/* 版本信息是弹窗主体：新版本号大号居前，当前版本作小字参照 */}
        <div className="flex flex-col gap-1">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
            <span className="min-w-0 [overflow-wrap:anywhere] font-mono text-20 font-semibold text-theme-text dark:text-stone-100">
              v{state.version ?? ""}
            </span>
            <span className="min-w-0 text-12 text-theme-text-tertiary dark:text-stone-500">
              {t("update.currentVersionLabel", "当前")}
              {" v"}
              {APP_VERSION}
            </span>
          </div>
          {state.publishedAt && (
            <span className="flex items-center gap-1 text-12 text-theme-text-tertiary dark:text-stone-500">
              <Calendar size={12} className="shrink-0 opacity-70" aria-hidden="true" />
              {t("updatePublishedAt", {
                date: new Date(state.publishedAt).toLocaleDateString(),
              })}
            </span>
          )}
        </div>

        {platform === "android" &&
          state.readyToInstall &&
          !state.downloading &&
          !state.error && (
            <div className="flex items-center gap-1.5 text-12 text-theme-text-secondary dark:text-stone-300">
              <CheckCircle2
                size={13}
                className="shrink-0 text-[var(--theme-primary)]"
                aria-hidden="true"
              />
              {t("update.apkReady", {
                defaultValue: "安装包已下载完成，点击安装不会重复下载",
              })}
            </div>
          )}

        {state.releaseNotes && (
          <div className="space-y-1">
            <p className="flex items-center gap-1 text-12 font-medium text-theme-text-secondary dark:text-stone-300">
              <ScrollText
                size={12}
                className="shrink-0 opacity-70"
                aria-hidden="true"
              />
              {t("updateReleaseNotes", "更新日志")}
            </p>
            <ReleaseNotesMarkdown content={state.releaseNotes} />
          </div>
        )}

        {state.releaseUrl && !state.downloading && (
          <a
            href={state.releaseUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 sm:min-h-0 [@media(pointer:coarse)]:min-h-11 items-center gap-1 text-12 text-blue-600 hover:underline dark:text-blue-400"
          >
            <ExternalLink size={12} />
            {t("update.viewFullNotes", "查看完整更新日志")}
          </a>
        )}
      </div>
    </Dialog>
  );
}

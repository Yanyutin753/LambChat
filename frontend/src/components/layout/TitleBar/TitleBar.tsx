import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Minus,
  Square,
  X,
} from "lucide-react";
import { useNavigationHistory } from "../../../hooks/useNavigationHistory";
import {
  closeWindow,
  minimizeWindow,
  queryWindowMaximized,
  subscribeWindowResized,
  toggleMaximizeWindow,
} from "../../../services/tauri/windowControls";
import type { UpdateState } from "../../../types";
import type { DesktopOs } from "./titlebarPlatform";
import { UpdateTitlebarIndicator } from "./UpdateTitlebarIndicator";

/**
 * 桌面端自绘标题栏（Windows/Linux 全自绘；macOS Overlay 模式下只承担
 * 导航与更新指示，红绿灯为原生控件）。结构：
 *
 * [羊头 logo + LambChat] [← →] ·······拖拽区······· [更新图标] [— □ ×]
 */

interface TitleBarProps {
  os: DesktopOs;
  updateState: UpdateState;
  onInstallUpdate: () => void;
  onSkipVersion: () => void;
}

function NavButton({
  direction,
  enabled,
  onClick,
  label,
  children,
}: {
  direction: "back" | "forward";
  enabled: boolean;
  onClick: () => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!enabled}
      aria-label={label}
      title={label}
      data-nav-direction={direction}
      className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)] disabled:pointer-events-none disabled:opacity-35"
    >
      {children}
    </button>
  );
}

export function WindowControls() {
  const { t } = useTranslation();
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | null = null;
    void (async () => {
      const sync = async () => {
        const value = await queryWindowMaximized();
        if (value !== null) setMaximized(value);
      };
      void sync();
      const fn = await subscribeWindowResized(sync);
      if (disposed) {
        fn();
      } else {
        unlisten = fn;
      }
    })();
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  const controlClass =
    "flex h-full w-[46px] items-center justify-center text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)]";

  const maximizeLabel = maximized
    ? t("titlebar.restore", "还原")
    : t("titlebar.maximize", "最大化");

  return (
    <div className="flex h-full items-stretch" data-window-controls>
      <button
        type="button"
        aria-label={t("titlebar.minimize", "最小化")}
        title={t("titlebar.minimize", "最小化")}
        onClick={() => void minimizeWindow()}
        className={controlClass}
      >
        <Minus size={14} strokeWidth={1.6} aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label={maximizeLabel}
        title={maximizeLabel}
        onClick={() => void toggleMaximizeWindow()}
        className={controlClass}
      >
        {maximized ? (
          <Copy size={12} strokeWidth={1.6} aria-hidden="true" />
        ) : (
          <Square size={11} strokeWidth={1.6} aria-hidden="true" />
        )}
      </button>
      <button
        type="button"
        aria-label={t("titlebar.close", "关闭")}
        title={t("titlebar.close", "关闭")}
        onClick={() => void closeWindow()}
        className="flex h-full w-[46px] items-center justify-center text-[var(--color-text-secondary)] transition-colors hover:bg-[#e81123] hover:text-white"
      >
        <X size={15} strokeWidth={1.6} aria-hidden="true" />
      </button>
    </div>
  );
}

export function TitleBar({
  os,
  updateState,
  onInstallUpdate,
  onSkipVersion,
}: TitleBarProps) {
  const { t } = useTranslation();
  const { canBack, canForward, back, forward } = useNavigationHistory();
  // macOS Overlay：左侧给原生红绿灯让位（三个按钮 + 安全边距）
  const isMac = os === "mac";

  return (
    <div
      data-titlebar
      className={`sticky top-0 z-[300] flex h-10 select-none items-center gap-1 border-b border-[var(--theme-border)] bg-[var(--theme-bg)] ${
        isMac ? "pl-[78px] pr-2" : "px-2"
      }`}
    >
      {!isMac && (
        <div className="flex min-w-0 items-center gap-2 pl-1 pr-2">
          <img
            src="/icons/icon.svg"
            alt=""
            width={18}
            height={18}
            className="pointer-events-none"
            draggable={false}
          />
          <span className="text-13 font-semibold tracking-wide text-[var(--color-text-secondary)]">
            LambChat
          </span>
        </div>
      )}

      <NavButton
        direction="back"
        enabled={canBack}
        onClick={back}
        label={t("titlebar.back", "后退")}
      >
        <ChevronLeft size={16} strokeWidth={2} />
      </NavButton>
      <NavButton
        direction="forward"
        enabled={canForward}
        onClick={forward}
        label={t("titlebar.forward", "前进")}
      >
        <ChevronRight size={16} strokeWidth={2} />
      </NavButton>

      {/* 拖拽区：flex 弹性占位（双击最大化由 Tauri 运行时处理） */}
      <div
        data-tauri-drag-region
        className="h-full flex-1"
        aria-hidden="true"
      />

      <UpdateTitlebarIndicator
        state={updateState}
        onInstall={onInstallUpdate}
        onSkipVersion={onSkipVersion}
      />

      {!isMac && <WindowControls />}
    </div>
  );
}

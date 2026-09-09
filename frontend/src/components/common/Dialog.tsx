import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";

/**
 * 通用弹窗组件：桌面居中卡片、移动端底部弹层（同一 DOM，sm 断点切换）。
 *
 * 统一各处手搓的 createPortal 弹窗外壳（头部/正文/页脚三段式、ESC 与
 * 背景关闭、滚动锁定、安全区），专业简约；`dismissible=false` 用于下载
 * 中/表单未保存等不允许关闭的场景。
 */

const SIZE_CLASSES: Record<"sm" | "md" | "lg", string> = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-lg",
};

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  /** 标题左侧图标（可选） */
  icon?: ReactNode;
  size?: "sm" | "md" | "lg";
  /** false：隐藏关闭按钮，ESC 与背景点击不关闭 */
  dismissible?: boolean;
  /** 页脚操作区（按钮组）；无 footer 时不渲染页脚条 */
  footer?: ReactNode;
  children: ReactNode;
}

export function Dialog({
  open,
  onClose,
  title,
  icon,
  size = "sm",
  dismissible = true,
  footer,
  children,
}: DialogProps) {
  const { t } = useTranslation();
  useBodyScrollLock(open);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === "Escape" && dismissible) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose, dismissible]);

  if (!open) return null;

  return createPortal(
    <div
      data-yields-sidebar
      className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-end sm:items-center sm:justify-center"
    >
      {/* Backdrop */}
      <div
        data-dialog-backdrop
        className="absolute inset-0 bg-black/50"
        onClick={dismissible ? onClose : undefined}
      />

      {/* 移动端底部弹层 / 桌面居中卡片 */}
      <div
        role="dialog"
        aria-modal="true"
        className={`relative z-10 flex max-h-[92dvh] w-full flex-col overflow-hidden bg-white shadow-xl dark:bg-stone-800 sm:mx-4 sm:rounded-xl sm:border sm:border-stone-200 sm:dark:border-stone-700 ${SIZE_CLASSES[size]} rounded-t-2xl border-x border-t border-stone-200/80 dark:border-stone-700/60 animate-slide-up-sheet duration-200 sm:animate-in sm:fade-in sm:zoom-in-95`}
      >
        {title !== undefined && (
          <div className="flex items-center justify-between gap-2 px-5 pt-5 pb-3">
            <div className="flex min-w-0 items-center gap-2">
              {icon}
              <h3 className="truncate text-16 font-semibold font-serif text-stone-900 dark:text-stone-100">
                {title}
              </h3>
            </div>
            {dismissible && (
              <button
                onClick={onClose}
                className="inline-flex size-7 shrink-0 items-center justify-center rounded-full text-stone-400 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700"
                aria-label={t("common.dismiss", "关闭")}
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">{children}</div>

        {footer !== undefined && (
          <div className="safe-area-bottom flex items-center justify-end gap-2 border-t border-stone-100 bg-stone-50 px-5 py-3 dark:border-stone-700 dark:bg-stone-900/50">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

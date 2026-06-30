import type { ReactNode } from "react";
import { X } from "lucide-react";

export const SELECTOR_MODAL_HEADER_CLASS =
  "flex items-center justify-between gap-4 px-4 sm:px-6 py-4 sm:py-5 border-b bg-white/85 dark:bg-stone-900/70";
export const SELECTOR_MODAL_DRAG_HANDLE_CLASS =
  "absolute left-1/2 -translate-x-1/2 top-2 w-10 h-1 rounded-full bg-stone-300/80 dark:bg-stone-600 sm:hidden";
export const SELECTOR_MODAL_CLOSE_BUTTON_CLASS =
  "p-2 rounded-full border border-stone-200/80 bg-white/80 text-stone-500 shadow-sm hover:bg-stone-100 hover:text-stone-800 active:bg-stone-200 dark:border-stone-700/80 dark:bg-stone-800/80 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-100 transition-colors";
export const SELECTOR_MODAL_ICON_TILE_CLASS =
  "size-10 sm:size-11 rounded-2xl bg-white dark:bg-stone-800 flex items-center justify-center shadow-sm ring-1 ring-stone-200/80 dark:ring-stone-700/80";

interface SelectorModalHeaderProps {
  icon: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  className?: string;
  subtitleClassName?: string;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function SelectorModalHeader({
  icon,
  title,
  subtitle,
  onClose,
  className,
  subtitleClassName = "text-xs sm:text-xs text-stone-500 dark:text-stone-400",
}: SelectorModalHeaderProps) {
  return (
    <div
      className={cx(SELECTOR_MODAL_HEADER_CLASS, className)}
      style={{ borderColor: "var(--theme-border)" }}
    >
      <div className={SELECTOR_MODAL_DRAG_HANDLE_CLASS} />
      <div className="flex min-w-0 items-center gap-3 mt-2 sm:mt-0">
        <div className={SELECTOR_MODAL_ICON_TILE_CLASS}>{icon}</div>
        <div className="min-w-0">
          <h2 className="truncate text-base sm:text-lg font-semibold text-stone-950 dark:text-stone-50">
            {title}
          </h2>
          {subtitle && <p className={subtitleClassName}>{subtitle}</p>}
        </div>
      </div>
      <button onClick={onClose} className={SELECTOR_MODAL_CLOSE_BUTTON_CLASS}>
        <X size={18} />
      </button>
    </div>
  );
}

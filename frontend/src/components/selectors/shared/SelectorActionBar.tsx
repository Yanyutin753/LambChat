import type { ButtonHTMLAttributes, ReactNode } from "react";

export const SELECTOR_ACTION_BAR_CLASS =
  "sticky top-0 z-10 flex items-center gap-2 px-4 sm:px-6 py-2.5 border-b border-stone-200/80 bg-white/75 dark:border-stone-700/80 dark:bg-stone-900/60";
export const SELECTOR_ACTION_BUTTON_CLASS =
  "rounded-full border border-transparent px-3 py-2 sm:py-1.5 text-xs font-semibold text-stone-600 hover:border-stone-200 hover:bg-stone-100 hover:text-stone-950 active:bg-stone-200 dark:text-stone-300 dark:hover:border-stone-700 dark:hover:bg-stone-800 dark:hover:text-stone-50 transition-colors";
export const SELECTOR_ACTION_ACCENT_BUTTON_CLASS =
  "flex items-center gap-1 rounded-full border border-stone-200 bg-white px-3 py-2 sm:py-1.5 text-xs font-semibold text-stone-700 shadow-sm hover:bg-stone-100 hover:text-stone-950 active:bg-stone-200 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300 dark:hover:bg-amber-500/15 dark:hover:text-amber-200 transition-colors";

interface SelectorActionBarProps {
  children: ReactNode;
  className?: string;
}

interface SelectorActionButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  accent?: boolean;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function SelectorActionBar({
  children,
  className,
}: SelectorActionBarProps) {
  return (
    <div className={cx(SELECTOR_ACTION_BAR_CLASS, className)}>{children}</div>
  );
}

export function SelectorActionButton({
  accent = false,
  className,
  type = "button",
  children,
  ...props
}: SelectorActionButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        accent
          ? SELECTOR_ACTION_ACCENT_BUTTON_CLASS
          : SELECTOR_ACTION_BUTTON_CLASS,
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

import type { ButtonHTMLAttributes, ReactNode } from "react";

export const SELECTOR_ACTION_BAR_CLASS =
  "sticky top-0 z-10 flex items-center gap-2 px-4 sm:px-6 py-2.5 border-b border-theme-border/80 bg-theme-bg-card/75 dark:bg-stone-900/60";
export const SELECTOR_ACTION_BUTTON_CLASS =
  "rounded-full border border-transparent px-3 py-2 sm:py-1.5 text-12 font-semibold text-theme-text-secondary hover:border-theme-border hover:bg-theme-bg-hover hover:text-theme-text active:bg-theme-bg-hover dark:text-stone-300 dark:hover:border-stone-700 dark:hover:text-stone-50 transition-colors";
export const SELECTOR_ACTION_ACCENT_BUTTON_CLASS =
  "flex items-center gap-1 rounded-full border border-theme-border bg-theme-bg-card px-3 py-2 sm:py-1.5 text-12 font-semibold text-theme-text-secondary shadow-sm hover:bg-theme-bg-hover hover:text-theme-text active:bg-theme-bg-hover dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300 dark:hover:bg-amber-500/15 dark:hover:text-amber-200 transition-colors";

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

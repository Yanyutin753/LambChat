import type { ButtonHTMLAttributes, ReactNode } from "react";

type ToolbarIconButtonVariant = "stone" | "muted";

export interface ToolbarIconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: ReactNode;
  variant?: ToolbarIconButtonVariant;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

const variants: Record<ToolbarIconButtonVariant, string> = {
  stone:
    "rounded-lg text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60",
  muted:
    "rounded-xl text-stone-400 dark:text-stone-500 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60",
};

const shared =
  "flex shrink-0 items-center justify-center min-h-[44px] min-w-[44px] sm:size-8 sm:min-h-0 sm:min-w-0 transition-all duration-200 active:scale-95 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)]/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-bg-card)]";

export function ToolbarIconButton({
  icon,
  variant = "stone",
  className,
  onClick,
  type = "button",
  ...props
}: ToolbarIconButtonProps) {
  return (
    <button
      type={type}
      className={cx(shared, variants[variant], className)}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      {...props}
    >
      {icon}
    </button>
  );
}

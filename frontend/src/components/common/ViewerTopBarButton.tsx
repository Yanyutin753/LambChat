import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import clsx from "clsx";

export interface ViewerTopBarButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  iconOnly?: boolean;
  ref?: Ref<HTMLButtonElement>;
}

export function ViewerTopBarButton({
  icon,
  iconOnly = false,
  className,
  children,
  type = "button",
  ...props
}: ViewerTopBarButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "min-h-11 min-w-11 sm:min-h-0 sm:min-w-0",
        iconOnly
          ? "flex shrink-0 items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          : "flex shrink-0 items-center gap-1.5 rounded-lg px-3 h-10 text-14 font-medium transition-colors cursor-pointer hover:bg-white/10 text-white/70 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed",
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

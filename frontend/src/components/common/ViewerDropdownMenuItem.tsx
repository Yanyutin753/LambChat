import { InteractiveIcon } from "./InteractiveIcon";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ViewerDropdownMenuItemVariant = "stone" | "dark";

interface ViewerDropdownMenuItemProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: ViewerDropdownMenuItemVariant;
}

const variantClasses: Record<ViewerDropdownMenuItemVariant, string> = {
  stone:
    "px-3 py-2 text-12 text-stone-700 dark:text-stone-300 hover:bg-theme-bg-hover dark:hover:bg-theme-bg-hover",
  dark: "px-4 py-2.5 text-14 text-white/80 hover:bg-white/10",
};

export function ViewerDropdownMenuItem({
  children,
  className = "",
  variant = "stone",
  type = "button",
  ...props
}: ViewerDropdownMenuItemProps) {
  return (
    <button
      type={type}
      className={[
        "flex w-full items-center gap-2 whitespace-nowrap text-left",
        variantClasses[variant],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    >
      <InteractiveIcon>{children}</InteractiveIcon>
    </button>
  );
}

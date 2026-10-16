import { InteractiveIcon } from "../InteractiveIcon";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface FloatingIconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: ReactNode;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function FloatingIconButton({
  icon,
  className,
  type = "button",
  ...props
}: FloatingIconButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        "fixed right-4 z-[410] flex shrink-0 items-center justify-center w-11 h-11 rounded-xl bg-black/80 hover:bg-black text-white shadow-xl transition-all duration-200 hover:scale-105 active:scale-95 cursor-pointer",
        className,
      )}
      {...props}
    >
      <InteractiveIcon>{icon}</InteractiveIcon>
    </button>
  );
}

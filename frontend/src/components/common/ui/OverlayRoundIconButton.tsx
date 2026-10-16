import { InteractiveIcon } from "../InteractiveIcon";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface OverlayRoundIconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: ReactNode;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function OverlayRoundIconButton({
  icon,
  className,
  type = "button",
  ...props
}: OverlayRoundIconButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        "flex shrink-0 items-center justify-center w-10 h-10 rounded-full bg-black/70 hover:bg-black/90 text-white shadow-lg transition-all duration-200 cursor-pointer",
        className,
      )}
      {...props}
    >
      <InteractiveIcon>{icon}</InteractiveIcon>
    </button>
  );
}

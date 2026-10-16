import { InteractiveIcon } from "../InteractiveIcon";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { ChevronDown } from "lucide-react";

export interface PickerTriggerProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  open?: boolean;
  selected?: boolean;
  children: ReactNode;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function PickerTrigger({
  open = false,
  selected = false,
  children,
  className,
  ...props
}: PickerTriggerProps) {
  return (
    <button
      type="button"
      className={cx("ui-select-trigger ui-picker-trigger", className)}
      aria-haspopup="listbox"
      aria-expanded={open}
      {...props}
    >
      <span
        className={cx(
          "ui-picker-trigger__content",
          selected
            ? "ui-select-trigger__label"
            : "ui-select-trigger__placeholder",
        )}
      >
        {children}
      </span>
      <InteractiveIcon>
        <ChevronDown
          size={15}
          className="ui-select-trigger__icon"
          style={{ transform: open ? "rotate(180deg)" : undefined }}
        />
      </InteractiveIcon>
    </button>
  );
}

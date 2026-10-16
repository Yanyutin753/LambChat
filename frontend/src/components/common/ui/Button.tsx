import { InteractiveIcon } from "../InteractiveIcon";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { LoadingSpinner } from "../LoadingSpinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  leftIcon,
  rightIcon,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cx(
        "ui-button",
        `ui-button--${variant}`,
        `ui-button--${size}`,
        loading && "ui-button--loading",
        className,
      )}
      {...props}
    >
      {loading ? (
        <LoadingSpinner
          size="sm"
          color={
            variant === "primary"
              ? "text-white dark:text-stone-900"
              : variant === "danger"
                ? "text-red-600 dark:text-red-400"
                : ""
          }
        />
      ) : (
        <InteractiveIcon>{leftIcon}</InteractiveIcon>
      )}
      {children && (
        <span className="ui-button__label">
          <InteractiveIcon>{children}</InteractiveIcon>
        </span>
      )}
      <InteractiveIcon>{rightIcon}</InteractiveIcon>
    </button>
  );
}

import { Check, LoaderCircle } from "lucide-react";

type CheckboxProps = {
  checked: boolean;
  onChange?: () => void;
  pending?: boolean;
  disabled?: boolean;
  /** "sm" (18px), "md" (20px, default), "lg" (24px) */
  size?: "sm" | "md" | "lg";
  className?: string;
  ariaLabel?: string;
};

const sizeClasses = {
  sm: "h-[18px] w-[18px]",
  md: "h-5 w-5",
  lg: "h-6 w-6",
} as const;

const iconSizes = {
  sm: 12,
  md: 12,
  lg: 13,
} as const;

export function Checkbox({
  checked,
  onChange,
  pending,
  disabled,
  size = "md",
  className = "",
  ariaLabel,
}: CheckboxProps) {
  const cls = [
    "relative flex items-center justify-center rounded-[5px] shrink-0 transition-colors duration-150 motion-reduce:transition-none focus-within:!opacity-100 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--theme-ring)]",
    sizeClasses[size],
    pending
      ? "border-2 border-[var(--theme-primary)] bg-[var(--theme-bg-subtle)]"
      : checked
        ? "border-2 border-[var(--theme-primary)] bg-[var(--theme-primary)]"
        : "border-2 border-[var(--theme-border)] bg-[var(--theme-bg-card)]",
    disabled && "opacity-50 cursor-not-allowed",
    onChange && !disabled && "cursor-pointer",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={cls} aria-hidden={!onChange || undefined}>
      {onChange && (
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-label={ariaLabel}
          aria-busy={pending || undefined}
          className="absolute inset-0 z-10 m-0 h-full w-full cursor-inherit opacity-0"
          onClick={(event) => event.stopPropagation()}
          onChange={() => onChange()}
        />
      )}
      {pending ? (
        <LoaderCircle
          size={iconSizes[size]}
          aria-hidden="true"
          className="animate-spin text-[var(--theme-primary)] motion-reduce:animate-none"
        />
      ) : checked ? (
        <Check
          size={iconSizes[size]}
          strokeWidth={3}
          aria-hidden="true"
          className="text-white dark:text-[var(--theme-bg)]"
        />
      ) : null}
    </span>
  );
}

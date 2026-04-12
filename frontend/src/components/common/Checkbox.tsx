import { Check, LoaderCircle } from "lucide-react";

type CheckboxProps = {
  checked: boolean;
  onChange?: () => void;
  pending?: boolean;
  disabled?: boolean;
  /** "sm" (18px), "md" (20px, default), "lg" (24px) */
  size?: "sm" | "md" | "lg";
  className?: string;
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
}: CheckboxProps) {
  const cls = [
    "flex items-center justify-center rounded-[5px] border-2 shrink-0 transition-all duration-200",
    sizeClasses[size],
    pending
      ? "border-amber-500/40 bg-amber-500/[0.08]"
      : checked
        ? "border-amber-500 bg-amber-500 shadow-[0_0_8px_color-mix(in_srgb,#f59e0b_30%,transparent)]"
        : "border-[var(--theme-border)] group-hover:border-amber-500/40",
    disabled && "opacity-50 cursor-not-allowed",
    onChange && !disabled && "cursor-pointer",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!disabled) {
      onChange?.();
    }
  };

  return (
    <div
      className={cls}
      onClick={handleClick}
      role="checkbox"
      aria-checked={checked}
    >
      {pending ? (
        <LoaderCircle
          size={iconSizes[size]}
          className="animate-spin text-amber-500"
        />
      ) : checked ? (
        <Check
          size={iconSizes[size]}
          strokeWidth={3}
          className="text-white animate-[check-pop_200ms_ease-out]"
        />
      ) : null}
    </div>
  );
}

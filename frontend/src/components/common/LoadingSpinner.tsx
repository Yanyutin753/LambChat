import { twMerge } from "tailwind-merge";
import { useTranslation } from "react-i18next";

export type LoadingSize = "xs" | "sm" | "md" | "lg" | "xl";

interface LoadingSpinnerProps {
  size?: LoadingSize | number;
  className?: string;
  static?: boolean;
  color?: string;
}

const sizeMap: Record<LoadingSize, number> = {
  xs: 12,
  sm: 16,
  md: 24,
  lg: 32,
  xl: 40,
};

export function LoadingSpinner({
  size = "md",
  className = "",
  static: isStatic = false,
  color = "",
}: LoadingSpinnerProps) {
  const sizeValue = typeof size === "number" ? size : sizeMap[size];

  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={`${sizeValue / 16}rem`}
      height={`${sizeValue / 16}rem`}
      viewBox="0 0 24 24"
      fill="none"
      className={twMerge(
        color || "text-theme-text-secondary",
        isStatic ? "" : "spinner-rotate",
        "shrink-0",
        className,
      )}
    >
      {Array.from({ length: 8 }, (_, index) => (
        <line
          key={index}
          x1="12"
          y1="3"
          x2="12"
          y2="6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          transform={`rotate(${index * 45} 12 12)`}
          opacity={(index + 1) / 8}
        />
      ))}
    </svg>
  );
}

interface LoadingProps {
  text?: string;
  size?: LoadingSize;
  className?: string;
}

export function Loading({ text, size = "md", className = "" }: LoadingProps) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={text ? undefined : t("common.loading")}
      className={`flex items-center gap-2.5 ${className}`}
    >
      <LoadingSpinner size={size} />
      {text && <span className="loading-label text-14">{text}</span>}
    </div>
  );
}

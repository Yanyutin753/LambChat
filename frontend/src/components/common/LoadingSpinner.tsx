import { Loader2 } from "lucide-react";

export type LoadingSize = "xs" | "sm" | "md" | "lg" | "xl";

interface LoadingSpinnerProps {
  size?: LoadingSize;
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
  const sizeValue = sizeMap[size];

  return (
    <Loader2
      size={sizeValue}
      className={`${color || "text-stone-500 dark:text-stone-300"} ${
        isStatic ? "" : "animate-spin"
      } ${className}`}
    />
  );
}

// 带文字的加载提示组件
interface LoadingProps {
  text?: string;
  size?: LoadingSize;
  className?: string;
}

export function Loading({ text, size = "md", className = "" }: LoadingProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <LoadingSpinner size={size} />
      {text && (
        <span
          className="text-sm"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {text}
        </span>
      )}
    </div>
  );
}

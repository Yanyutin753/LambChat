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
  color = "text-amber-500",
}: LoadingSpinnerProps) {
  const sizeValue = sizeMap[size];

  return (
    <Loader2
      size={sizeValue}
      className={`${color} ${isStatic ? "" : "animate-spin"} ${className}`}
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
        <span className="text-sm text-stone-500 dark:text-stone-400">
          {text}
        </span>
      )}
    </div>
  );
}

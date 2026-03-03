import { clsx } from "clsx";
import { useState } from "react";
import { CheckCircle, XCircle, ChevronRight } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";

export type CollapsibleStatus = "idle" | "loading" | "success" | "error";
export type CollapsibleVariant = "default" | "tool" | "thinking";

export interface CollapsiblePillProps {
  status?: CollapsibleStatus;
  icon: React.ReactNode;
  label: string;
  suffix?: React.ReactNode;
  defaultExpanded?: boolean;
  onExpandChange?: (expanded: boolean) => void;
  variant?: CollapsibleVariant;
  children?: React.ReactNode;
  expandable?: boolean;
}

// Get spinner color based on variant
function getSpinnerColor(variant: CollapsibleVariant): string {
  if (variant === "tool") {
    return "text-amber-500 dark:text-amber-400";
  }
  if (variant === "thinking") {
    return "text-stone-500 dark:text-stone-400";
  }
  // default (sandbox) - use emerald
  return "text-emerald-500 dark:text-emerald-400";
}

// StatusIndicator component
function StatusIndicator({
  status,
  variant,
}: {
  status: CollapsibleStatus;
  variant: CollapsibleVariant;
}) {
  if (status === "loading") {
    return (
      <LoadingSpinner
        size="xs"
        className="shrink-0"
        color={getSpinnerColor(variant)}
      />
    );
  }
  if (status === "success") {
    return <CheckCircle size={12} className="shrink-0" />;
  }
  if (status === "error") {
    return <XCircle size={12} className="shrink-0" />;
  }
  // idle - no indicator
  return null;
}

// Get button styles based on status and variant
function getButtonStyles(
  status: CollapsibleStatus,
  variant: CollapsibleVariant,
): string {
  if (variant === "thinking") {
    return clsx(
      "bg-stone-200 dark:bg-stone-700",
      "text-stone-600 dark:text-stone-300",
      "hover:bg-stone-300 dark:hover:bg-stone-600",
    );
  }

  if (variant === "tool") {
    if (status === "loading") {
      return clsx(
        "bg-amber-100/80 dark:bg-amber-900/30",
        "text-amber-700 dark:text-amber-300",
      );
    }
    if (status === "success") {
      return clsx(
        "bg-emerald-100/80 dark:bg-emerald-900/30",
        "text-emerald-700 dark:text-emerald-300",
      );
    }
    if (status === "error") {
      return clsx(
        "bg-red-100/80 dark:bg-red-900/30",
        "text-red-700 dark:text-red-300",
      );
    }
    return clsx(
      "bg-stone-100 dark:bg-stone-800",
      "text-stone-600 dark:text-stone-400",
    );
  }

  // default variant (for Sandbox)
  if (status === "error") {
    return clsx(
      "bg-red-100/80 dark:bg-red-900/30",
      "text-red-700 dark:text-red-300",
    );
  }
  return clsx(
    "bg-emerald-100/80 dark:bg-emerald-900/30",
    "text-emerald-700 dark:text-emerald-300",
  );
}

export function CollapsiblePill({
  status = "idle",
  icon,
  label,
  suffix,
  defaultExpanded = false,
  onExpandChange,
  variant = "default",
  children,
  expandable = true,
}: CollapsiblePillProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const hasChildren = children !== undefined;

  const handleToggle = () => {
    if (!expandable && !hasChildren) return;
    const newState = !isExpanded;
    setIsExpanded(newState);
    onExpandChange?.(newState);
  };

  const canExpand = expandable || hasChildren;

  return (
    <div className="my-1">
      <button
        onClick={handleToggle}
        className={clsx(
          "inline-flex items-center gap-1 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-all",
          getButtonStyles(status, variant),
          canExpand && "cursor-pointer",
          !canExpand && "cursor-default",
        )}
      >
        <StatusIndicator status={status} variant={variant} />
        {icon}
        <span className="font-mono">{label}</span>
        {suffix}
        {canExpand && (
          <ChevronRight
            size={12}
            className={clsx(
              "shrink-0 transition-transform duration-200",
              "text-stone-500 dark:text-stone-400",
              isExpanded && "rotate-90",
            )}
          />
        )}
      </button>

      <div
        className={clsx(
          "grid transition-all duration-200 ease-out",
          isExpanded && hasChildren
            ? "grid-rows-[1fr] opacity-100 mt-1"
            : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </div>
  );
}

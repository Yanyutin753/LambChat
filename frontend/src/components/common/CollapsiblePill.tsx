import { clsx } from "clsx";
import { useState } from "react";
import { Ban, CheckCircle, XCircle, ChevronRight } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";

export type CollapsibleStatus =
  | "idle"
  | "loading"
  | "success"
  | "error"
  | "cancelled";
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
  /** On mobile, call this instead of toggling inline expansion */
  onPanelOpen?: () => void;
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
  if (status === "cancelled") {
    return <Ban size={12} className="shrink-0" />;
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
    if (status === "cancelled") {
      return clsx(
        "bg-amber-100/80 dark:bg-amber-900/30",
        "text-amber-700 dark:text-amber-300",
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
  if (status === "cancelled") {
    return clsx(
      "bg-amber-100/80 dark:bg-amber-900/30",
      "text-amber-700 dark:text-amber-300",
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
  onPanelOpen,
}: CollapsiblePillProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const hasChildren = children !== undefined;

  const handleToggle = () => {
    if (!expandable && !hasChildren) return;
    if (onPanelOpen) {
      onPanelOpen();
      return;
    }
    const newState = !isExpanded;
    setIsExpanded(newState);
    onExpandChange?.(newState);
  };

  const canExpand = expandable || hasChildren;

  // Format label: capitalize first letter and convert underscores to spaces
  const formattedLabel = label
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");

  return (
    <div className="my-1 min-w-0">
      <button
        onClick={handleToggle}
        className={clsx(
          "inline-flex items-center gap-1 sm:gap-2 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-colors",
          getButtonStyles(status, variant),
          canExpand && "cursor-pointer",
          !canExpand && "cursor-default",
        )}
      >
        <StatusIndicator status={status} variant={variant} />
        {icon}
        <span className="font-mono truncate max-w-[200px] sm:max-w-[400px]">
          {formattedLabel}
        </span>
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

      {isExpanded && hasChildren && (
        <div className="mt-1 animate-[fade-in_150ms_ease-out]">{children}</div>
      )}
    </div>
  );
}

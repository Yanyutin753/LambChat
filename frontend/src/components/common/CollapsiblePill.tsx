import { clsx } from "clsx";
import { useEffect, useRef, useState } from "react";
import { Ban, CheckCircle, XCircle, ChevronRight } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";

export type CollapsibleStatus =
  | "idle"
  | "loading"
  | "success"
  | "error"
  | "cancelled";
export type CollapsibleVariant = "default" | "tool" | "thinking" | "summary";

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
  /** Add animated typing dots after label */
  animatedDots?: boolean;
  /** Preserve label text exactly instead of applying title formatting */
  formatLabel?: boolean;
}

// Unified status-based colors — same status always gets the same color
const statusStyles: Record<CollapsibleStatus, string> = {
  idle: "bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400",
  loading:
    "bg-amber-100/80 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300",
  success:
    "bg-emerald-100/80 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300",
  error: "bg-red-100/80 dark:bg-red-900/30 text-red-700 dark:text-red-300",
  cancelled:
    "bg-stone-200/60 dark:bg-stone-700/50 text-stone-500 dark:text-stone-400",
};

// Status indicator icon/spinner colors
const statusIconColors: Record<CollapsibleStatus, string> = {
  idle: "",
  loading: "text-amber-500 dark:text-amber-400",
  success: "text-emerald-500 dark:text-emerald-400",
  error: "text-red-500 dark:text-red-400",
  cancelled: "text-stone-400 dark:text-stone-500",
};

function StatusIndicator({ status }: { status: CollapsibleStatus }) {
  if (status === "loading") {
    return (
      <LoadingSpinner
        size="xs"
        className="shrink-0"
        color={statusIconColors[status]}
      />
    );
  }
  if (status === "success") {
    return (
      <CheckCircle
        size={12}
        className={clsx("shrink-0", statusIconColors[status])}
      />
    );
  }
  if (status === "error") {
    return (
      <XCircle
        size={12}
        className={clsx("shrink-0", statusIconColors[status])}
      />
    );
  }
  if (status === "cancelled") {
    return (
      <Ban size={12} className={clsx("shrink-0", statusIconColors[status])} />
    );
  }
  return null;
}

export function CollapsiblePill({
  status = "idle",
  icon,
  label,
  suffix,
  defaultExpanded = false,
  onExpandChange,
  variant: _variant = "default",
  children,
  expandable = true,
  onPanelOpen,
  animatedDots = false,
  formatLabel = true,
}: CollapsiblePillProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [enterClass, setEnterClass] = useState("");
  const prevStatus = useRef(status);
  const hasChildren = children !== undefined;

  // One-shot enter animation when status changes to success/error
  useEffect(() => {
    if (prevStatus.current === status) return;
    prevStatus.current = status;
    if (status === "success") {
      setEnterClass("pill-enter-success");
      const t = setTimeout(() => setEnterClass(""), 500);
      return () => clearTimeout(t);
    }
    if (status === "error") {
      setEnterClass("pill-enter-error");
      const t = setTimeout(() => setEnterClass(""), 350);
      return () => clearTimeout(t);
    }
  }, [status]);

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
  const displayedLabel = formatLabel ? formattedLabel : label;

  return (
    <div className="my-1 min-w-0 max-w-full">
      <button
        type="button"
        onClick={handleToggle}
        className={clsx(
          "pill-btn",
          "inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium max-w-full h-7",
          statusStyles[status],
          enterClass,
          status === "loading" && "pill-loading-breathe",
          canExpand && "cursor-pointer",
          !canExpand && "cursor-default",
        )}
      >
        {status === "loading" && <StatusIndicator status={status} />}
        {icon}
        <span
          className={clsx(
            "font-mono min-w-0 truncate overflow-hidden leading-none",
            animatedDots && "typing-dots",
          )}
        >
          {displayedLabel}
        </span>
        {suffix}
        {canExpand && (
          <ChevronRight
            size={12}
            className={clsx(
              "shrink-0 transition-transform duration-200",
              statusIconColors[status] || "text-stone-500 dark:text-stone-400",
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

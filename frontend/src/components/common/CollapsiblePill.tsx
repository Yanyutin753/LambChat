import { useTranslation } from "react-i18next";
import { InteractiveIcon } from "./InteractiveIcon";
import { clsx } from "clsx";
import { Children, useId, useState } from "react";
import { ChevronRight } from "lucide-react";

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
  description?: string;
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

export function CollapsiblePill({
  status = "idle",
  icon,
  label,
  description,
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
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const contentId = useId();
  const hasChildren = Children.toArray(children).length > 0;

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
  const displayedLabel =
    formatLabel && _variant !== "tool" ? formattedLabel : label;

  const terminalLabel =
    status === "loading" || status === "error" || status === "cancelled"
      ? t(`chat.eventStatus.${status}`)
      : "";

  return (
    <div className="my-1 min-w-0 max-w-full">
      <button
        type="button"
        data-variant={_variant}
        data-status={status}
        aria-expanded={hasChildren && !onPanelOpen ? isExpanded : undefined}
        aria-controls={
          hasChildren && isExpanded && !onPanelOpen ? contentId : undefined
        }
        aria-disabled={!canExpand || undefined}
        onClick={handleToggle}
        className={clsx(
          "pill-btn",
          "text-theme-text-secondary",
          canExpand && "cursor-pointer",
          !canExpand && "cursor-default",
        )}
      >
        <span className="pill-btn__icon" aria-hidden="true">
          <InteractiveIcon>{icon}</InteractiveIcon>
        </span>
        <span
          className={clsx(
            "pill-btn__label min-w-0 flex-1 truncate overflow-hidden",
            description && "flex items-center gap-2",
            animatedDots && !description && "typing-dots",
          )}
        >
          {description ? (
            <>
              <span className="shrink-0">{displayedLabel}</span>
              <span className="min-w-0 truncate font-normal text-theme-text-secondary">
                {description}
              </span>
            </>
          ) : (
            displayedLabel
          )}
        </span>
        {_variant === "tool" &&
          terminalLabel &&
          !displayedLabel.includes(terminalLabel) && (
            <span
              className={
                status === "error" ? "sr-only" : "shrink-0 text-12 font-normal"
              }
            >
              {terminalLabel}
            </span>
          )}
        {suffix != null && (
          <span className="pill-btn__suffix min-w-0 max-w-[40%] truncate text-12 font-normal text-theme-text-secondary tabular-nums">
            {suffix}
          </span>
        )}
        {canExpand && (
          <span className="pill-btn__chevron" aria-hidden="true">
            <InteractiveIcon>
              <ChevronRight
                size={12}
                className={clsx(
                  "shrink-0 transition-transform duration-200",
                  "text-theme-text-secondary",
                  isExpanded && "rotate-90",
                )}
              />
            </InteractiveIcon>
          </span>
        )}
      </button>

      {isExpanded && hasChildren && (
        <div id={contentId} className="mt-1 animate-[fade-in_150ms_ease-out]">
          {children}
        </div>
      )}
    </div>
  );
}

import { useCallback, useState } from "react";
import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";

/** 标题 → 快照定位 slug：面板历史返回时按 key 恢复小节展开状态 */
function snapshotKeySlug(title: string): string {
  return (
    title
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
      .replace(/^-+|-+$/g, "") || "section"
  );
}

export function CollapsibleSection({
  title,
  defaultExpanded = true,
  action,
  variant = "default",
  className,
  expandedClassName,
  children,
}: {
  title: string;
  defaultExpanded?: boolean;
  action?: React.ReactNode;
  variant?: "default" | "error";
  className?: string;
  expandedClassName?: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isError = variant === "error";
  const toggleExpanded = useCallback(() => setExpanded((v) => !v), []);
  const sectionKey = `section:${snapshotKeySlug(title)}`;

  return (
    <div
      className={clsx(
        "collapsible-section-card p-3 sm:p-4 rounded-lg sm:rounded-xl",
        className,
        expanded && expandedClassName,
        isError
          ? "collapsible-section-card--error bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50"
          : "collapsible-section-card--default bg-theme-bg-card border border-theme-border shadow-sm",
      )}
    >
      <div className="flex items-center justify-between w-full gap-2">
        <button
          type="button"
          aria-expanded={expanded}
          data-sidebar-snapshot-key={sectionKey}
          onClick={toggleExpanded}
          className="flex items-center gap-1.5 flex-1 min-w-0 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)]/50 rounded-md"
        >
          <ChevronDown
            size={12}
            className={clsx(
              "transition-transform duration-200",
              isError
                ? "text-red-500 dark:text-red-400"
                : "text-theme-text-tertiary",
              !expanded && "-rotate-90",
            )}
          />
          <span
            className={clsx(
              "text-xs uppercase tracking-wider font-medium",
              isError
                ? "text-red-600 dark:text-red-400"
                : "text-theme-text-tertiary",
            )}
          >
            {title}
          </span>
        </button>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {expanded && (
        <div
          data-sidebar-snapshot-key={`${sectionKey}-content`}
          className="mt-2 flex-1 min-h-0 overflow-y-auto animate-[fade-in_150ms_ease-out]"
        >
          {children}
        </div>
      )}
    </div>
  );
}

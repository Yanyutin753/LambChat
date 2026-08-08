import { useState, useCallback } from "react";
import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";

/**
 * Lightweight collapsible block for tool result panel detail views.
 * Used by PersonaItem, TeamItem, EnvVarItem, etc.
 */
export function DetailSection({
  title,
  icon,
  defaultExpanded = false,
  badge,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  defaultExpanded?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const toggleExpanded = useCallback(() => setExpanded((v) => !v), []);

  return (
    <div className={clsx("tool-detail-section", expanded && "is-expanded")}>
      <button
        type="button"
        onClick={toggleExpanded}
        className="tool-detail-section__header"
        aria-expanded={expanded}
      >
        <ChevronDown
          size={12}
          className={clsx(
            "tool-detail-section__chevron",
            !expanded && "is-collapsed",
          )}
        />
        {icon && <span className="tool-detail-section__icon">{icon}</span>}
        <span className="tool-detail-section__title">{title}</span>
        {badge && <span className="tool-detail-section__badge">{badge}</span>}
      </button>
      {expanded && <div className="tool-detail-section__body">{children}</div>}
    </div>
  );
}

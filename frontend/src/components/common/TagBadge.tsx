import type { HTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";

/** Read-only metadata; selectable tags keep their own button semantics. */
export function TagBadge({
  icon,
  children,
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { icon?: ReactNode }) {
  return (
    <span className={clsx("tag-badge", className)} {...props}>
      {icon && (
        <span className="tag-badge__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="tag-badge__label">{children}</span>
    </span>
  );
}

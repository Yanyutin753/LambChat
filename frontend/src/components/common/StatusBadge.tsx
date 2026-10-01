import type { ReactNode } from "react";

/**
 * Predefined semantic color tokens for StatusBadge.
 * Each token maps to a semantic dot color; label text stays neutral.
 *
 * Conventions used across the app:
 *   - stone  = neutral / inactive / paused
 *   - emerald/green = positive / active / success
 *   - blue   = informational / scheduled / running
 *   - red    = negative / expired / failed
 *   - amber  = warning / timeout
 */
export type StatusColor =
  | "stone"
  | "emerald"
  | "green"
  | "blue"
  | "red"
  | "amber";

export interface StatusBadgeProps {
  /** Semantic color token */
  color?: StatusColor;
  /** Status text to display (already translated by caller) */
  label: ReactNode;
  /** Legacy size hint; status labels use a consistent 12px rhythm. */
  size?: "sm" | "md";
}

const COLOR_MAP: Record<StatusColor, string> = {
  stone: "bg-theme-text-tertiary",
  emerald: "bg-theme-success",
  green: "bg-theme-success",
  blue: "bg-theme-info",
  red: "bg-theme-error",
  amber: "bg-theme-warning",
};

/** A text status with a decorative 8px semantic dot. */
export function StatusBadge({ color = "stone", label }: StatusBadgeProps) {
  return (
    <span className="status-dot inline-flex shrink-0 items-center gap-1.5 text-12 text-theme-text-secondary">
      <span
        aria-hidden="true"
        className={`inline-block size-2 shrink-0 rounded-full ${COLOR_MAP[color]}`}
      />
      {label}
    </span>
  );
}

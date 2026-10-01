import { type ReactNode } from "react";
import { CopyButton } from "../../../common/CopyButton";

type ToolArgsBlockSize = "detail" | "compact";

const sizeClasses: Record<ToolArgsBlockSize, string> = {
  detail:
    "tool-args-block group/args relative flex items-center gap-2 px-3 py-2 rounded-[var(--radius-sm)] bg-theme-bg-card text-14 text-theme-text-tertiary font-mono",
  compact:
    "tool-args-block group/args relative flex items-center gap-2 mb-2 px-2 py-1.5 rounded-[var(--radius-sm)] bg-theme-bg-card text-12 text-theme-text-tertiary font-mono",
};

export function ToolArgsBlock({
  children,
  className = "",
  size,
  wrap = false,
  copyText,
}: {
  children: ReactNode;
  className?: string;
  size: ToolArgsBlockSize;
  wrap?: boolean;
  /** When provided, a copy button appears on hover to copy this text. */
  copyText?: string;
}) {
  return (
    <div
      className={[sizeClasses[size], wrap ? "flex-wrap" : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="min-w-0 flex-1 overflow-x-auto">{children}</span>
      {copyText && (
        <CopyButton
          text={copyText}
          size={size === "detail" ? 12 : 10}
          className="sm:opacity-0 sm:group-hover/args:opacity-100 focus-visible:opacity-100"
        />
      )}
    </div>
  );
}

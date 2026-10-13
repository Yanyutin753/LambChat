import { type ReactNode } from "react";
import { CopyButton } from "../../../common/CopyButton";

type ToolArgsBlockSize = "detail" | "compact";

const sizeClasses: Record<ToolArgsBlockSize, string> = {
  detail:
    "tool-args-block group/args relative flex items-center gap-2 px-3 py-2 rounded-[var(--radius-sm)] bg-theme-bg-card text-14 text-theme-text-secondary font-mono",
  compact:
    "tool-args-block group/args relative flex items-center gap-2 mb-2 px-2 py-1.5 rounded-[var(--radius-sm)] bg-theme-bg-card text-12 text-theme-text-secondary font-mono",
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
  /** Full source text, even when the displayed preview is truncated. */
  copyText: string;
}) {
  return (
    <div
      data-size={size}
      className={[sizeClasses[size], className].filter(Boolean).join(" ")}
    >
      <span
        className={[
          "tool-args-block__content min-w-0 flex-1 flex items-center gap-2 overflow-x-auto",
          wrap ? "tool-args-block__content--wrap" : "",
        ].join(" ")}
      >
        {children}
      </span>
      <CopyButton text={copyText} size={12} className="tool-args-block__copy" />
    </div>
  );
}

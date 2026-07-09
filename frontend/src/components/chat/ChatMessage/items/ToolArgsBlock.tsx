import { type ReactNode, useCallback, useState } from "react";
import { Check, Copy } from "lucide-react";
import { copyToClipboard } from "../../../../utils/clipboard";

type ToolArgsBlockSize = "detail" | "compact";

const sizeClasses: Record<ToolArgsBlockSize, string> = {
  detail:
    "tool-args-block group/args relative flex items-center gap-2 px-3 py-2 rounded-[var(--radius-sm)] bg-white dark:bg-[var(--theme-bg-card)] text-sm text-theme-text-tertiary font-mono",
  compact:
    "tool-args-block group/args relative flex items-center gap-2 mb-2 px-2 py-1.5 rounded-[var(--radius-sm)] bg-white dark:bg-[var(--theme-bg-card)] text-xs text-theme-text-tertiary font-mono",
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
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!copyText) return;
      copyToClipboard(copyText).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    },
    [copyText],
  );

  return (
    <div
      className={[sizeClasses[size], wrap ? "flex-wrap" : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="min-w-0 flex-1">{children}</span>
      {copyText && (
        <button
          type="button"
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy"}
          className="shrink-0 grid place-items-center w-5 h-5 rounded-[var(--radius-inner)] opacity-0 group-hover/args:opacity-100 focus-visible:opacity-100 transition-all duration-[var(--duration-fast)] text-[var(--theme-text-tertiary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-bg-elevated)] active:scale-90"
        >
          {copied ? (
            <Check
              size={size === "detail" ? 12 : 10}
              className="text-[var(--color-icon-green)]"
            />
          ) : (
            <Copy size={size === "detail" ? 12 : 10} />
          )}
        </button>
      )}
    </div>
  );
}

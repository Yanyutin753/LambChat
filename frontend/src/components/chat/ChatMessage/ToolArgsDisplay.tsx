import { useCallback, useMemo, useState } from "react";
import { Check, ChevronDown, Copy } from "lucide-react";

/**
 * Renders tool-call arguments as a styled key-value list instead of raw JSON.
 *
 * Each top-level key gets its own row with a subtle pill background and
 * an individual copy button on hover:
 * - **Simple values** (string / number / boolean / null) are shown inline.
 * - **Objects / arrays** are shown as a collapsible sub-block with pretty JSON.
 */
export function ToolArgsDisplay({
  args,
  compact = false,
}: {
  args: Record<string, unknown>;
  /** When true, use tighter spacing (inline expand). Default false (panel). */
  compact?: boolean;
}) {
  const entries = useMemo(() => Object.entries(args), [args]);
  if (entries.length === 0) return null;

  return (
    <div className={`flex flex-col ${compact ? "gap-1" : "gap-1.5"}`}>
      {entries.map(([key, value]) => (
        <ArgRow key={key} name={key} value={value} compact={compact} />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Individual argument row                                            */
/* ------------------------------------------------------------------ */

function ArgRow({
  name,
  value,
  compact,
}: {
  name: string;
  value: unknown;
  compact: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const isComplex =
    value !== null && typeof value === "object" && !(value instanceof Date);

  const copyText = useMemo(() => {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }, [value]);

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      navigator.clipboard.writeText(copyText).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    },
    [copyText],
  );

  if (!isComplex) {
    return (
      <div
        className={`group/arg flex items-center gap-2 rounded-[var(--radius-sm)] px-2 transition-colors duration-[var(--duration-fast)] ${
          compact
            ? "bg-[var(--theme-bg-subtle)] hover:bg-[var(--theme-bg-elevated)] py-1 text-[11px]"
            : "bg-[var(--theme-bg-subtle)] hover:bg-[var(--theme-bg-elevated)] py-1.5 text-xs"
        }`}
      >
        <ArgKey name={name} compact={compact} />
        <ArgSeparator />
        <span className="min-w-0 flex-1 text-[var(--theme-text-secondary)] break-all">
          <FormattedValue value={value} />
        </span>
        <CopyButtonInline copied={copied} onClick={handleCopy} />
      </div>
    );
  }

  return (
    <ComplexArgRow
      name={name}
      value={value}
      copied={copied}
      onCopy={handleCopy}
      compact={compact}
    />
  );
}

function ComplexArgRow({
  name,
  value,
  copied,
  onCopy,
  compact,
}: {
  name: string;
  value: object;
  copied: boolean;
  onCopy: (e: React.MouseEvent) => void;
  compact: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const preview = useMemo(() => {
    try {
      const s = JSON.stringify(value);
      return s.length > 60 ? `${s.slice(0, 57)}…` : s;
    } catch {
      return String(value);
    }
  }, [value]);

  const formatted = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);

  return (
    <div>
      <div
        className={`group/arg flex items-center gap-2 rounded-[var(--radius-sm)] px-2 transition-colors duration-[var(--duration-fast)] cursor-pointer ${
          expanded
            ? "bg-[var(--theme-bg-elevated)]"
            : "bg-[var(--theme-bg-subtle)] hover:bg-[var(--theme-bg-elevated)]"
        } ${compact ? "py-1 text-[11px]" : "py-1.5 text-xs"}`}
        onClick={() => setExpanded((v) => !v)}
      >
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 text-[var(--theme-text-tertiary)] transition-transform duration-[var(--duration-fast)]"
          style={{ transform: expanded ? "rotate(0deg)" : "rotate(-90deg)" }}
        >
          <ChevronDown size={compact ? 10 : 12} />
        </button>
        <ArgKey name={name} compact={compact} />
        <ArgSeparator />
        <span className="min-w-0 flex-1 text-[var(--theme-text-tertiary)] break-all opacity-60 group-hover/arg:opacity-100 transition-opacity">
          {expanded ? null : preview}
        </span>
        <CopyButtonInline copied={copied} onClick={onCopy} />
      </div>

      {expanded && (
        <pre
          className={`mt-1 ml-3 pl-3 border-l-2 border-[var(--theme-border)] overflow-x-auto max-h-60 overflow-y-auto rounded-[var(--radius-sm)] bg-[var(--theme-bg-subtle)] p-2.5 font-mono text-[11px] leading-relaxed text-[var(--theme-text-secondary)] animate-[fade-in_150ms_ease-out] ${
            compact ? "" : ""
          }`}
        >
          {formatted}
        </pre>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Shared small sub-components                                         */
/* ------------------------------------------------------------------ */

/** Formatted key label (e.g. "search_query" → "Search Query") */
function ArgKey({ name, compact }: { name: string; compact: boolean }) {
  return (
    <span
      className={`shrink-0 font-medium tracking-wide uppercase ${
        compact
          ? "text-[9px] text-[var(--theme-text-tertiary)]"
          : "text-[10px] text-[var(--theme-text-tertiary)]"
      }`}
    >
      {formatKeyName(name)}
    </span>
  );
}

/** Thin dot separator between key and value */
function ArgSeparator() {
  return (
    <span className="shrink-0 w-px self-stretch bg-[var(--theme-border)]" />
  );
}

/* ------------------------------------------------------------------ */
/* Tiny inline copy button (appears on hover)                         */
/* ------------------------------------------------------------------ */

function CopyButtonInline({
  copied,
  onClick,
}: {
  copied: boolean;
  onClick: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={copied ? "Copied!" : "Copy value"}
      className="shrink-0 grid place-items-center w-5 h-5 rounded-[var(--radius-inner)] opacity-0 group-hover/arg:opacity-100 focus-visible:opacity-100 transition-all duration-[var(--duration-fast)] text-[var(--theme-text-tertiary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-bg-elevated)] active:scale-90"
    >
      {copied ? (
        <Check size={10} className="text-[var(--color-icon-green)]" />
      ) : (
        <Copy size={10} />
      )}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatKeyName(key: string): string {
  // snake_case → Title Case, camelCase → Title Case
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function FormattedValue({ value }: { value: unknown }) {
  if (value === null) return <span className="italic opacity-40">null</span>;
  if (value === undefined)
    return <span className="italic opacity-40">undefined</span>;
  if (typeof value === "boolean") {
    return (
      <span
        className={
          value
            ? "text-[var(--color-icon-green)] font-medium"
            : "text-[var(--theme-text-tertiary)]"
        }
      >
        {String(value)}
      </span>
    );
  }
  if (typeof value === "number") {
    return (
      <span className="text-[var(--color-icon-orange)] tabular-nums font-medium">
        {value}
      </span>
    );
  }
  // string – keep readable
  const s = String(value);
  const needsQuoting = /\s|[\\"'`,]/.test(s) || s === "" || s.length === 0;
  if (!needsQuoting && s.length < 72) {
    return <span>{s}</span>;
  }
  // Long or special strings → show clipped
  if (s.length > 200) {
    return (
      <span className="italic opacity-60">
        {JSON.stringify(s.slice(0, 197))}…
      </span>
    );
  }
  return <span className="italic opacity-70">{JSON.stringify(s)}</span>;
}

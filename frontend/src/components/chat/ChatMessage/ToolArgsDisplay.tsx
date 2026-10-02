import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CopyButton } from "../../common/CopyButton";

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
  const { t } = useTranslation();
  const isComplex =
    value !== null && typeof value === "object" && !(value instanceof Date);

  const copyText = useMemo(() => {
    try {
      return JSON.stringify(value) ?? String(value);
    } catch {
      return String(value);
    }
  }, [value]);

  if (!isComplex) {
    return (
      <div
        className={`group/arg flex items-center gap-2 rounded-[var(--radius-sm)] px-2 transition-colors duration-[var(--duration-fast)] ${
          compact
            ? "bg-[var(--theme-bg-subtle)] hover:bg-[var(--theme-bg-elevated)] py-1 text-11"
            : "bg-[var(--theme-bg-subtle)] hover:bg-[var(--theme-bg-elevated)] py-1.5 text-12"
        }`}
      >
        <ArgKey name={name} compact={compact} />
        <ArgSeparator />
        <span className="min-w-0 flex-1 text-[var(--theme-text-secondary)] break-all">
          <FormattedValue value={value} />
        </span>
        <CopyButton
          text={copyText}
          label={t("chat.message.copyArgument", { name })}
          size={12}
          className="sm:opacity-0 sm:group-hover/arg:opacity-100 focus-visible:opacity-100"
        />
      </div>
    );
  }

  return (
    <ComplexArgRow
      name={name}
      value={value}
      copyText={copyText}
      compact={compact}
    />
  );
}

function ComplexArgRow({
  name,
  value,
  copyText,
  compact,
}: {
  name: string;
  value: object;
  copyText: string;
  compact: boolean;
}) {
  const { t } = useTranslation();
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
        } ${compact ? "py-1 text-11" : "py-1.5 text-12"}`}
      >
        <button
          type="button"
          aria-label={`${t(expanded ? "common.collapse" : "common.expand")} ${name}`}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="tool-arg-expand flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronDown
            size={compact ? 10 : 12}
            className="shrink-0"
            style={{ transform: expanded ? "rotate(0deg)" : "rotate(-90deg)" }}
            aria-hidden="true"
          />
          <ArgKey name={name} compact={compact} />
          <ArgSeparator />
          <span className="min-w-0 flex-1 text-[var(--theme-text-tertiary)] break-all opacity-60 group-hover/arg:opacity-100 transition-opacity">
            {expanded ? null : preview}
          </span>
        </button>
        <CopyButton
          text={copyText}
          label={t("chat.message.copyArgument", { name })}
          size={12}
          className="sm:opacity-0 sm:group-hover/arg:opacity-100 focus-visible:opacity-100"
        />
      </div>

      {expanded && (
        <pre
          className={`mt-1 ml-3 pl-3 border-l-2 border-[var(--theme-border)] overflow-x-auto max-h-60 overflow-y-auto rounded-[var(--radius-sm)] bg-[var(--theme-bg-subtle)] p-2.5 font-mono text-11 leading-relaxed text-[var(--theme-text-secondary)] animate-[fade-in_150ms_ease-out] ${
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
          ? "text-9 text-[var(--theme-text-tertiary)]"
          : "text-10 text-[var(--theme-text-tertiary)]"
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
